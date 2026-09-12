"""Translate saved titles only: no source collection, scoring or notifications."""
import asyncio
import copy
import json
import os
from pathlib import Path
import aiohttp
import fetch_data as collector
from translations import update_cache


async def refresh_file(session, path):
    if not os.environ.get('GROQ_API_KEY', '').strip():
        raise ValueError('GROQ_API_KEY is required')
    original = json.loads(path.read_text(encoding='utf-8'))
    result = copy.deepcopy(original)
    old_path = collector.DATA_FILE
    old_provider = os.environ.get('WARHUB_TRANSLATION_PROVIDER')
    try:
        collector.DATA_FILE = path
        os.environ['WARHUB_TRANSLATION_PROVIDER'] = 'groq'
        await collector._translate_titles(session, result.get('news', []))
        await collector._translate_market_questions(session, result.get('polymarket', []))
    finally:
        collector.DATA_FILE = old_path
        if old_provider is None:
            os.environ.pop('WARHUB_TRANSLATION_PROVIDER', None)
        else:
            os.environ['WARHUB_TRANSLATION_PROVIDER'] = old_provider
    news, markets = result.get('news', []), result.get('polymarket', [])
    # Do not publish a partial repair or discard a saved title on provider failure.
    if any(not r.get('title_zh') for r in news) or any(not r.get('question_zh') for r in markets):
        raise ValueError('Some translations are unavailable; saved snapshot was not modified')
    result['translation_cache'] = update_cache(original, news, markets)
    content = json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + '\n'
    temporary = path.with_suffix('.translation-tmp')
    temporary.write_text(content, encoding='utf-8')
    temporary.replace(path)
    return {'news': len(news), 'markets': len(markets), 'updated_at': result.get('updated_at')}


async def main():
    async with aiohttp.ClientSession() as session:
        report = await refresh_file(session, collector.DATA_FILE)
    print('Saved title translations:', json.dumps(report, ensure_ascii=False))


if __name__ == '__main__':
    asyncio.run(main())
