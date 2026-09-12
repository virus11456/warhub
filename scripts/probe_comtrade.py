"""One production collector query, without writing data or sending notifications."""
import asyncio
import os
import aiohttp
from comtrade_client import setup
from fetch_data import _comtrade_one

async def main():
    if not os.getenv('COMTRADE_API_KEY', '').strip():
        raise SystemExit('COMTRADE_PROBE secret_missing')
    async with aiohttp.ClientSession() as session:
        client = setup(session)
        value = await _comtrade_one(session, '36', '2601', 202607)
        print('COMTRADE_PROBE', client.report())
        if value is None or client.report()['successes'] != 1:
            raise SystemExit('COMTRADE_PROBE production_collector_failed')
        print('COMTRADE_PROBE Australia to China iron ore 202607 netWgt_kg=', value)

if __name__ == '__main__':
    asyncio.run(main())
