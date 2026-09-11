import json,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import AsyncMock,patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import fetch_data as f
from merge_history import _union_months

class TradeRevalidation(unittest.IsolatedAsyncioTestCase):
    def test_verified_remote_history_wins_over_legacy_local(self):
        old={'months':{'2025-12':{'4001':2.9}}}
        verified={'months':{'2025-12':{'schema_version':2,'4001':11.5}}}
        self.assertEqual(_union_months(old,verified)['2025-12'],verified['months']['2025-12'])
        self.assertEqual(_union_months(verified,old)['2025-12'],verified['months']['2025-12'])
    async def test_legacy_month_is_rechecked_within_existing_budget(self):
        now=f.datetime.now(f.timezone.utc);cur=now.year*100+now.month
        ym=lambda n: f._ym_add(cur,-n)
        key=lambda n:f'{ym(n)//100}-{ym(n)%100:02d}'
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'hist.json';p.write_text(json.dumps({'months':{key(2):{'schema_version':2,'src':'mirror'},key(3):{'src':'mirror','4001':2.9}}}))
            get=AsyncMock(return_value=10000000)
            with patch.object(f,'STRAT_HISTORY_FILE',p),patch.object(f,'STRAT_HIST_MONTHS',4),patch.object(f,'_comtrade_one',get),patch.object(f.asyncio,'sleep',AsyncMock()):
                await f.fetch_strategic_history(None)
            result=json.loads(p.read_text())['months']
        self.assertEqual(result[key(3)]['schema_version'],2)
        months={c.args[3] for c in get.call_args_list}
        self.assertIn(ym(3),months)
        self.assertLessEqual(len(months),f.STRAT_HIST_MIRROR_BUDGET)
