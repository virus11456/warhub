import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import AsyncMock, patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import alerts

NOW = datetime(2026, 10, 29, 7, 30, tzinfo=timezone.utc)


def region(key, level, score=60.0, **extra):
    return {'key': key, 'name': '韓國', 'flag': '🇰🇷', 'level': level, 'score': score, **extra}


class RegionJumpRuleTests(unittest.TestCase):
    def test_news_only_jump_waits_one_run_then_alerts(self):
        prev = {'region_levels': {'korea': 'WATCH'}}
        jumps, levels, pending = alerts.region_jumps([region('korea', 'HIGH')], prev, NOW)
        self.assertEqual((jumps, levels['korea'], pending['korea']['from']), ([], 'HIGH', 'WATCH'))
        later = NOW + timedelta(hours=2)
        jumps, _, pending = alerts.region_jumps([region('korea', 'HIGH')],
                                                {'region_levels': levels, 'region_pending': pending}, later)
        self.assertEqual([(j['previous_level'], j['confirmed_by']) for j in jumps], [('WATCH', 'two_runs')])
        self.assertEqual(pending, {})

    def test_falling_back_cancels_and_data_gap_keeps_waiting(self):
        state = {'region_levels': {'korea': 'HIGH'}, 'region_pending': {'korea': {'from': 'WATCH'}}}
        jumps, _, pending = alerts.region_jumps([region('korea', 'ELEVATED', 30)], state, NOW)
        self.assertEqual((jumps, pending), ([], {}))
        jumps, levels, pending = alerts.region_jumps([region('korea', 'INSUFFICIENT_DATA', None)], state, NOW)
        self.assertEqual((jumps, levels['korea'], 'korea' in pending), ([], 'HIGH', True))

    def test_airspace_rise_alerts_at_once(self):
        for factors in ({'notam': 80}, {'notam_closure': True}):
            jumps, _, pending = alerts.region_jumps([region('korea', 'HIGH', factors=factors)],
                                                    {'region_levels': {'korea': 'WATCH'}}, NOW)
            self.assertEqual([j['confirmed_by'] for j in jumps], ['airspace'])
            self.assertEqual(pending, {})
        jumps, _, _ = alerts.region_jumps([region('korea', 'HIGH', factors={'notam': 60})],
                                          {'region_levels': {'korea': 'WATCH'}}, NOW)
        self.assertEqual(jumps, [])

    def test_one_step_first_run_and_cooldown_do_not_alert(self):
        self.assertEqual(alerts.region_jumps([region('korea', 'HIGH')], {'region_levels': {'korea': 'ELEVATED'}}, NOW)[0], [])
        self.assertEqual(alerts.region_jumps([region('korea', 'HIGH')], {}, NOW)[0], [])
        recent = {'region_levels': {'korea': 'WATCH'}, 'region_pending': {'korea': {'from': 'WATCH'}},
                  'region_alerted': {'korea': (NOW - timedelta(hours=2)).isoformat()}}
        self.assertEqual(alerts.region_jumps([region('korea', 'HIGH')], recent, NOW)[0], [])

    def test_message_names_change_reason_volume_and_headline(self):
        msg = alerts.build_region_jump_alert([region('korea', 'HIGH', 62.5, previous_level='WATCH', confirmed_by='two_runs',
                                                     factors={'gdelt_delta': 1116.3},
                                                     headline={'title': '北韓發射約十二枚彈道導彈'})])
        self.assertIn('韓國：觀察 → HIGH（62.5）', msg)
        self.assertIn('已連續兩輪維持 HIGH 以上', msg)
        self.assertIn('新聞量約為平常的 12 倍', msg)
        self.assertIn('主要新聞：北韓發射約十二枚彈道導彈', msg)
        self.assertIn('只送站長', msg)


class RegionJumpDeliveryTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        env = patch.multiple(alerts, TELEGRAM_BOT_TOKEN='fake-token', TELEGRAM_CHAT_ID='private',
                             TELEGRAM_CHANNEL_ID='channel', TELEGRAM_CHANNEL_SCOPE='all', DISCORD_WEBHOOK='',
                             ALERT_REGION_JUMP=True)
        env.start()
        self.addCleanup(env.stop)
        self.data = {'score': {'alert_level': 'LOW'}, 'firms': {}, 'regions': [region('korea', 'HIGH')]}
        self.waiting = {'region_levels': {'korea': 'HIGH'}, 'region_pending': {'korea': {'from': 'WATCH'}}}

    async def test_first_run_only_records_pending(self):
        sender = AsyncMock(return_value={'tg': True})
        with patch.object(alerts, '_send_all', sender):
            state = await alerts.run_notifications(self.data, {'region_levels': {'korea': 'WATCH'}})
        self.assertFalse(any(c.args[0] and '地區風險跳升' in c.args[0][0] for c in sender.call_args_list))
        self.assertEqual(state['region_pending']['korea']['from'], 'WATCH')

    async def test_confirmed_alert_goes_only_to_owner_and_records_cooldown(self):
        sender = AsyncMock(return_value={'tg': True})
        with patch.object(alerts, '_send_all', sender):
            state = await alerts.run_notifications(self.data, self.waiting)
        call = sender.call_args_list[0]
        self.assertIn('地區風險跳升', call.args[0][0])
        self.assertEqual((call.kwargs['tg_chats'], call.kwargs['discord']), (['private'], False))
        self.assertIn('korea', state['region_alerted'])
        self.assertEqual(state['region_pending'], {})

    async def test_failed_delivery_stays_pending(self):
        sender = AsyncMock(return_value={'tg': False})
        with patch.object(alerts, '_send_all', sender):
            state = await alerts.run_notifications(self.data, self.waiting)
        self.assertEqual(state['region_pending']['korea']['from'], 'WATCH')
        self.assertNotIn('korea', state['region_alerted'])

    async def test_digest_only_keeps_region_state(self):
        sender = AsyncMock(return_value={'tg': True})
        with patch.object(alerts, '_send_all', sender):
            state = await alerts.run_notifications(self.data, self.waiting, digest_only=True)
        self.assertEqual((state['region_levels'], state['region_pending']), (self.waiting['region_levels'], self.waiting['region_pending']))


class RegionHeadlineTests(unittest.TestCase):
    def test_action_headline_beats_newer_diplomacy_and_stale_or_unsafe_items_are_skipped(self):
        import fetch_data as f
        news = [{'region': 'korea', 'title_zh': '美韓支持北韓制裁執行', 'url': 'https://a', 'ts': '2026-10-29T07:00:00+00:00'},
                {'region': 'korea', 'title_zh': '北韓發射約十二枚彈道導彈', 'url': 'https://b', 'ts': '2026-10-29T05:00:00+00:00', 'domain': 'Yonhap'},
                {'region': 'korea', 'title_zh': '舊聞：飛彈', 'url': 'https://c', 'ts': '2026-10-29T08:00:00+00:00', 'stale': True},
                {'region': 'korea', 'title_zh': '飛彈', 'url': 'javascript:x', 'ts': '2026-10-29T09:00:00+00:00'},
                {'region': 'taiwan', 'title_zh': '台灣停飛阿帕奇', 'url': 'https://d', 'ts': '2026-10-29T06:00:00+00:00'}]
        regions = [{'key': 'korea'}, {'key': 'taiwan'}, {'key': 'mideast'}]
        f.attach_region_headlines(regions, news)
        self.assertEqual(regions[0]['headline'], {'title': '北韓發射約十二枚彈道導彈', 'url': 'https://b',
                                                  'ts': '2026-10-29T05:00:00+00:00', 'source': 'Yonhap'})
        self.assertEqual(regions[1]['headline']['title'], '台灣停飛阿帕奇')   # no action headline: newest
        self.assertNotIn('headline', regions[2])


class HeadlineCleanupTests(unittest.TestCase):
    def test_source_and_section_tails_are_removed_but_real_dashes_stay(self):
        import fetch_data as f
        c = f.clean_headline
        self.assertEqual(c('美國太平洋陸軍司令：2027年台灣入侵窗口仍「有效」-新聞-台灣國際電台'), '美國太平洋陸軍司令：2027年台灣入侵窗口仍「有效」')
        self.assertEqual(c('美國示警威脅依然存在｜鏡轉全球｜#鏡新聞', 'Yahoo新聞'), '美國示警威脅依然存在')
        self.assertEqual(c('日防衛省首公布中海警船同共艦通過鹿兒島外海- 國際'), '日防衛省首公布中海警船同共艦通過鹿兒島外海')
        self.assertEqual(c('Hegseth fires planner - Reuters', 'Reuters'), 'Hegseth fires planner')
        self.assertEqual(c('德國與南韓在俄羅斯-北韓擔憂中深化安全夥伴關係'), '德國與南韓在俄羅斯-北韓擔憂中深化安全夥伴關係')
        self.assertEqual(c('Russia-Ukraine talks', 'x'), 'Russia-Ukraine talks')
        self.assertIsNone(c(None))


if __name__ == '__main__':
    unittest.main()
