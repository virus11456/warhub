"""Explicit, bounded live NOTAC check. Never collects other sources or notifies."""
import asyncio
import json
import os
from pathlib import Path
import aiohttp
from notac_client import collect_region


async def main():
    async with aiohttp.ClientSession() as session:
        result = await collect_region(session, os.environ.get('NOTAC_API_KEY', ''), ['RCAA'])
    safe = {key: value for key, value in result.items() if key != 'rows'}
    Path('notac-check.json').write_text(json.dumps(safe, ensure_ascii=False, indent=2))
    print(json.dumps(safe, ensure_ascii=False))
    # A valid first page can prove access even when the bounded list is partial.
    return 0 if result.get('complete') or result.get('reason') == 'page_budget_reached' else 1


if __name__ == '__main__':
    raise SystemExit(asyncio.run(main()))
