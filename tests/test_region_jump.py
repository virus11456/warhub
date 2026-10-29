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
    def test_two_level_jump_to_high_alerts_once_per_cooldown(self):
        jumps, levels = alerts.region_jumps([region('korea', 'HIGH')], {'region_levels': {'korea': 'WATCH'}}, NOW)
        self.assertEqual([j['previous_level'] for j in jumps], ['WATCH'])
        self.assertEqual(levels, {'korea': 'HIGH'})
        recent = {'region_levels': {'korea': 'WATCH'}, 'region_alerted': {'korea': (NOW - timedelta(hours=2)).isoformat()}}
        self.assertEqual(alerts.region_jumps([region('korea', 'HIGH')], recent, NOW)[0], [])

    def test_one_step_unknown_and_insufficient_do_not_alert(self):
        self.assertEqual(alerts.region_jumps([region('korea', 'HIGH')], {'region_levels': {'korea': 'ELEVATED'}}, NOW)[0], [])
        self.assertEqual(alerts.region_jumps([region('korea', 'HIGH')], {}, NOW)[0], [])          # first run: no baseline
        jumps, levels = alerts.region_jumps([region('korea', 'INSUFFICIENT_DATA', None)],
                                            {'region_levels': {'korea': 'WATCH'}}, NOW)
        self.assertEqual((jumps, levels), ([], {'korea': 'WATCH'}))                                # a data gap keeps the known level

    def test_message_names_change_volume_and_headline(self):
        msg = alerts.build_region_jump_alert([region('korea', 'HIGH', 62.5, previous_level='WATCH',
                                                     factors={'gdelt_delta': 1116.3},
                                                     headline={'title': '北韓發射約十二枚彈道導彈'})])
        self.assertIn('韓國：觀察 → HIGH（62.5）', msg)
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

    async def test_sent_only_to_owner_and_cooldown_recorded_on_success(self):
        sender = AsyncMock(return_value={'tg': True})
        with patch.object(alerts, '_send_all', sender):
            state = await alerts.run_notifications(self.data, {'region_levels': {'korea': 'WATCH'}})
        call = sender.call_args_list[0]
        self.assertIn('地區風險跳升', call.args[0][0])
        self.assertEqual((call.kwargs['tg_chats'], call.kwargs['discord']), (['private'], False))
        self.assertIn('korea', state['region_alerted'])
        self.assertEqual(state['region_levels'], {'korea': 'HIGH'})

    async def test_failed_delivery_retries_next_run(self):
        sender = AsyncMock(return_value={'tg': False})
        with patch.object(alerts, '_send_all', sender):
            state = await alerts.run_notifications(self.data, {'region_levels': {'korea': 'WATCH'}})
        self.assertEqual(state['region_levels'], {'korea': 'WATCH'})
        self.assertNotIn('korea', state['region_alerted'])

    async def test_digest_only_keeps_region_state(self):
        sender = AsyncMock(return_value={'tg': True})
        prev = {'region_levels': {'korea': 'WATCH'}, 'region_alerted': {}}
        with patch.object(alerts, '_send_all', sender):
            state = await alerts.run_notifications(self.data, prev, digest_only=True)
        self.assertEqual(state['region_levels'], {'korea': 'WATCH'})
        self.assertFalse(any('地區風險跳升' in (c.args[0][0] if c.args[0] else '') for c in sender.call_args_list))


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
