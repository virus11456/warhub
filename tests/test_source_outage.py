import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import AsyncMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import alerts

T0 = datetime(2026, 10, 28, 0, 0, tzinfo=timezone.utc)


def health(**status):
    return {k: {'label': k.upper(), 'status': v, 'note': f'{k} note'} for k, v in status.items()}


class OutageAlertTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.env = patch.multiple(alerts, TELEGRAM_BOT_TOKEN='fake', TELEGRAM_CHAT_ID='private',
                                  TELEGRAM_CHANNEL_ID='channel', TELEGRAM_CHANNEL_SCOPE='all',
                                  DISCORD_WEBHOOK='https://discord.invalid/hook', ALERT_SOURCE_OUTAGE=True,
                                  SOURCE_OUTAGE_HOURS=6)
        self.env.start()
        self.addCleanup(self.env.stop)

    async def run_at(self, when, prev, ok=True, **status):
        sent = []
        async def fake_send(session, text, chat_id, pacer=None):
            sent.append((chat_id, text)); return ok
        class Clock(datetime):
            @classmethod
            def now(cls, tz=None): return when
        data = {'score': {'alert_level': 'LOW'}, 'firms': {}, 'source_health': health(**status)}
        with patch.object(alerts, 'send_telegram', fake_send), patch.object(alerts, 'send_discord', AsyncMock(return_value=True)) as discord, \
             patch.object(alerts, 'datetime', Clock):
            state = await alerts.run_notifications(data, prev)
        outage = [(c, t) for c, t in sent if '資料來源' in t]
        return state, outage, discord

    async def test_alert_once_after_six_hours_then_recovery_only_to_owner(self):
        s1, out, _ = await self.run_at(T0, {}, pizza='unavailable', gdelt='available')
        self.assertEqual(out, [])
        self.assertEqual(s1['source_down_since'], {'pizza': T0.isoformat()})
        s2, out, discord = await self.run_at(T0 + timedelta(hours=5), s1, pizza='unavailable')
        self.assertEqual(out, [])
        s3, out, discord = await self.run_at(T0 + timedelta(hours=7), s2, pizza='stale')
        self.assertEqual([c for c, _ in out], ['private'])           # never the public channel
        self.assertIn('PIZZA：已約 7 小時沒有有效資料（pizza note）', out[0][1])
        self.assertFalse(any('資料來源' in str(c) for c in discord.call_args_list))   # never Discord
        s4, out, _ = await self.run_at(T0 + timedelta(hours=9), s3, pizza='unavailable')
        self.assertEqual(out, [])                                     # no repeat for the same outage
        s5, out, _ = await self.run_at(T0 + timedelta(hours=10), s4, pizza='available')
        self.assertEqual([c for c, _ in out], ['private'])
        self.assertIn('資料來源恢復', out[0][1])
        self.assertIn('中斷約 10 小時', out[0][1])
        self.assertEqual((s5['source_down_since'], s5['source_alerted']), ({}, {}))

    async def test_failed_delivery_is_retried_and_partial_is_not_an_outage(self):
        prev = {'source_down_since': {'gdelt': (T0 - timedelta(hours=8)).isoformat()}}
        s1, out, _ = await self.run_at(T0, prev, ok=False, gdelt='stale', notams='partial')
        self.assertEqual(len(out), 1)
        self.assertEqual(s1['source_alerted'], {})
        self.assertNotIn('notams', s1['source_down_since'])
        s2, out, _ = await self.run_at(T0 + timedelta(hours=2), s1, gdelt='stale')
        self.assertEqual(len(out), 1)
        self.assertIn('gdelt', s2['source_alerted'])

    async def test_missing_health_row_keeps_state_and_digest_only_does_not_touch_it(self):
        prev = {'source_down_since': {'pizza': T0.isoformat()}, 'source_alerted': {'pizza': T0.isoformat()}}
        s1, out, _ = await self.run_at(T0 + timedelta(hours=1), prev, gdelt='available')
        self.assertEqual((out, s1['source_alerted']), ([], {'pizza': T0.isoformat()}))
        data = {'score': {'alert_level': 'LOW'}, 'firms': {}, 'source_health': health(pizza='available')}
        with patch.object(alerts, 'send_telegram', AsyncMock(return_value=True)):
            s2 = await alerts.run_notifications(data, prev, digest_only=True)
        self.assertEqual(s2['source_alerted'], prev['source_alerted'])


if __name__ == '__main__':
    unittest.main()
