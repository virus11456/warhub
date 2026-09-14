import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import alerts


class Response:
    def __init__(self, status, body):
        self.status, self.body = status, body
    async def __aenter__(self): return self
    async def __aexit__(self, *args): pass
    async def json(self): return self.body


class Session:
    def __init__(self, status=200, body=None):
        self.response = Response(status, {'ok': True} if body is None else body)
        self.calls = []
    def post(self, url, **kwargs):
        self.calls.append(kwargs)
        return self.response


class DeliveryTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.env = patch.multiple(alerts, TELEGRAM_BOT_TOKEN='fake-token',
                                  TELEGRAM_CHAT_ID='private', TELEGRAM_CHANNEL_ID='channel',
                                  TELEGRAM_CHANNEL_SCOPE='all', DISCORD_WEBHOOK='')
        self.env.start()
        self.addCleanup(self.env.stop)
        self.data = {'score': {'alert_level': 'LOW'}, 'firms': {}}

    async def test_experimental_and_legacy_scores_never_trigger_wpi_or_pizza_alarm(self):
        for flag in (True, None):
            data = {'score': {'alert_level': 'CRITICAL', 'combined_score': 99},
                    'pizza': [{'spike_magnitude': 'EXTREME', 'percentage_of_usual': 999}],
                    'firms': {}}
            if flag is not None:
                data['score']['experimental'] = flag
            sender = AsyncMock(return_value={'test': True})
            with patch.object(alerts, '_send_all', sender), patch.multiple(
                    alerts, ALERT_ESCALATION=True, ALERT_PIZZA=True):
                await alerts.run_notifications(data, {}, 'LOW')
            self.assertEqual(sender.call_args_list[0].args[0], [])
            digest = sender.call_args_list[1].args[0]
            self.assertEqual(len(digest), 1)
            self.assertIn('WPI 實驗指數', digest[0])
            self.assertNotIn('DEFCON', digest[0])

    async def test_experiment_policy_preserves_independent_hotspot_observation_alert(self):
        data = {'score': {'experimental': True, 'alert_level': 'LOW'},
                'firms': {'conflict_total': 1000}}
        sender = AsyncMock(return_value={'test': True})
        with patch.object(alerts, '_send_all', sender), patch.multiple(
                alerts, ALERT_HOTSPOT=True, HOTSPOT_SURGE_MIN=100, HOTSPOT_SURGE_RATIO=2):
            await alerts.run_notifications(data, {'hotspot_counter_version': 2, 'hotspots': 100})
        self.assertEqual(len(sender.call_args_list[0].args[0]), 1)

    async def test_plain_text_preserves_dynamic_characters(self):
        session = Session()
        text = 'INSUFFICIENT_DATA [news](url) *headline <tag> &'
        self.assertTrue(await alerts.send_telegram(session, text, 'private'))
        payload = session.calls[0]['json']
        self.assertEqual(payload['text'], text)
        self.assertNotIn('parse_mode', payload)

    async def test_rejections_are_not_acknowledged_or_immediately_retried(self):
        for status, body in [(400, {'ok': False}), (429, {'ok': False}),
                             (403, {'ok': False}), (200, {'ok': False})]:
            session = Session(status, body)
            self.assertFalse(await alerts.send_telegram(session, 'message', 'private'))
            self.assertEqual(len(session.calls), 1)

    async def test_partial_delivery_retries_only_failed_target(self):
        sender = AsyncMock(side_effect=[True, False])
        with patch.object(alerts, 'send_telegram', sender):
            first = await alerts.run_notifications(self.data, {}, 'LOW')
        self.assertIsNone(first['bucket'])
        self.assertEqual(len(first['digest_receipts']), 1)
        sender = AsyncMock(return_value=True)
        with patch.object(alerts, 'send_telegram', sender):
            second = await alerts.run_notifications(self.data, first, 'LOW')
            third = await alerts.run_notifications(self.data, second, 'LOW')
        self.assertEqual(sender.await_count, 1)
        self.assertEqual(sender.call_args.args[2], 'channel')
        self.assertEqual(second['bucket'], second['digest_attempt_bucket'])
        self.assertEqual(third['bucket'], second['bucket'])
        self.assertNotIn('private', str(second))

    async def test_timeout_keeps_bucket_unacknowledged(self):
        with patch.object(alerts, 'send_telegram', AsyncMock(side_effect=TimeoutError)) as sender:
            result = await alerts.run_notifications(self.data, {}, 'LOW')
        self.assertIsNone(result['bucket'])
        self.assertEqual(sender.await_count, 2)
        self.assertTrue(all(ok is False for ok in result['delivery']['digest'].values()))

    async def test_unconfigured_is_not_success(self):
        with patch.object(alerts, 'TELEGRAM_BOT_TOKEN', ''):
            result = await alerts.run_notifications(self.data, {}, 'LOW')
        self.assertIsNone(result['bucket'])
        self.assertEqual(result['digest_receipts'], {})

    async def test_legacy_bucket_is_not_trusted_after_failed_old_sender(self):
        bucket = int(alerts.datetime.now(alerts.timezone.utc).timestamp() // 3600) // alerts.DIGEST_EVERY_HOURS
        with patch.object(alerts, 'send_telegram', AsyncMock(return_value=True)) as sender:
            result = await alerts.run_notifications(self.data, {'bucket': bucket}, 'LOW')
        self.assertEqual(sender.await_count, 2)
        self.assertEqual(result['delivery_version'], 1)

    async def test_discord_failure_does_not_retry_successful_telegram(self):
        with patch.object(alerts, 'DISCORD_WEBHOOK', 'fake-webhook'), \
             patch.object(alerts, 'send_telegram', AsyncMock(return_value=True)) as tg, \
             patch.object(alerts, 'send_discord', AsyncMock(side_effect=[False, True])) as dc:
            first = await alerts.run_notifications(self.data, {}, 'LOW')
            second = await alerts.run_notifications(self.data, first, 'LOW')
        self.assertEqual(tg.await_count, 2)
        self.assertEqual(dc.await_count, 2)
        self.assertEqual(second['bucket'], second['digest_attempt_bucket'])

    async def test_spacing_shared_between_alert_and_digest_destinations(self):
        session = Session()
        ticks = [100.0]
        async def advance(delay):
            ticks[0] += delay
        data = {'score': {'experimental': True}, 'firms': {'conflict_total': 1000}}
        with patch.object(alerts.aiohttp, 'ClientSession') as factory, \
             patch.object(alerts.time, 'monotonic', side_effect=lambda: ticks[0]), \
             patch.object(alerts.asyncio, 'sleep', AsyncMock(side_effect=advance)) as sleep:
            factory.return_value.__aenter__.return_value = session
            result = await alerts.run_notifications(data, {'hotspot_counter_version': 2, 'hotspots': 10})
        self.assertEqual(len(session.calls), 4)
        self.assertEqual(sleep.await_count, 3)
        for call in sleep.await_args_list:
            self.assertAlmostEqual(call.args[0], 3.1)
        self.assertTrue(all(result['delivery']['digest'].values()))

    async def test_429_persists_across_runs_and_does_not_block_discord(self):
        session = Session(429, {'ok': False, 'parameters': {'retry_after': 7200}})
        with patch.object(alerts.aiohttp, 'ClientSession') as factory, \
             patch.object(alerts.time, 'time', return_value=1000), \
             patch.object(alerts, 'DISCORD_WEBHOOK', 'fake-webhook'), \
             patch.object(alerts, 'send_discord', AsyncMock(return_value=True)) as discord:
            factory.return_value.__aenter__.return_value = session
            first = await alerts.run_notifications(self.data)
            second = await alerts.run_notifications(self.data, first)
            self.assertEqual(discord.await_count, 1)
        self.assertEqual(len(session.calls), 1)
        self.assertEqual(first['telegram_retry_at'], 8200)
        self.assertEqual(second['telegram_retry_at'], 8200)
        self.assertIsNone(second['bucket'])
        self.assertEqual(len(second['digest_receipts']), 1)
        with patch.object(alerts.aiohttp, 'ClientSession') as factory, \
             patch.object(alerts.time, 'time', return_value=8201), \
             patch.object(alerts.asyncio, 'sleep', AsyncMock()):
            recovered = Session()
            factory.return_value.__aenter__.return_value = recovered
            third = await alerts.run_notifications(self.data, second)
        self.assertEqual(len(recovered.calls), 2)
        self.assertEqual(third['bucket'], third['digest_attempt_bucket'])

    async def test_malformed_429_stops_batch_without_immediate_retry(self):
        bodies = [None, [], {'parameters': None}, {'parameters': {'retry_after': 0}},
                  {'parameters': {'retry_after': True}}, {'parameters': {'retry_after': '10'}}]
        for body in bodies:
            session = Session(429, body)
            pacer = alerts.TelegramPacer()
            with patch.object(alerts.time, 'time', return_value=1000):
                self.assertFalse(await alerts.send_telegram(session, 'a', 'private', pacer))
                self.assertFalse(await alerts.send_telegram(session, 'b', 'channel', pacer))
            self.assertEqual(len(session.calls), 1)
            self.assertEqual(pacer.retry_at, 1060)

    async def test_non_json_429_and_api_error_code_keep_cooldown(self):
        for status, response in [(429, ValueError('bad json')), (429, TimeoutError()), (200, {'error_code': 429, 'parameters': {'retry_after': 120}})]:
            session = Session(status)
            session.response.json = (AsyncMock(side_effect=response) if isinstance(response, Exception)
                                     else AsyncMock(return_value=response))
            pacer = alerts.TelegramPacer()
            with patch.object(alerts.time, 'time', return_value=1000):
                self.assertFalse(await alerts.send_telegram(session, 'a', 'private', pacer))
            self.assertTrue(pacer.blocked)
            self.assertGreater(pacer.retry_at, 1000)

    async def test_manual_test_cannot_bypass_saved_cooldown(self):
        session = Session()
        with patch.object(alerts.aiohttp, 'ClientSession') as factory, \
             patch.object(alerts.time, 'time', return_value=1000):
            factory.return_value.__aenter__.return_value = session
            result = await alerts.run_notifications(self.data, {'telegram_retry_at': 9000}, force_test=True)
        self.assertEqual(session.calls, [])
        self.assertEqual(result['telegram_retry_at'], 9000)
        self.assertTrue(all(not ok for ok in result['delivery']['test'].values()))

    async def test_invalid_saved_cooldown_does_not_crash_or_delay(self):
        for value in (None, 'invalid', {}, True, float('nan'), float('inf'), -1):
            pacer = alerts.TelegramPacer(value)
            self.assertEqual(pacer.retry_at, 0)
