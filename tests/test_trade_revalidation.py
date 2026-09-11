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

    async def test_partial_month_retries_and_transient_loss_preserves_coverage(self):
        now=f.datetime.now(f.timezone.utc);cur=now.year*100+now.month
        ym=lambda n:f._ym_add(cur,-n)
        key=lambda n:f'{ym(n)//100}-{ym(n)%100:02d}'
        material={"cmd":"4001","exp":[("A","A"),("B","B")]}
        old={"schema_version":2,"src":"mirror","4001":12,
             "coverage":{"4001":["A","B"]}}
        partial={"schema_version":2,"src":"mirror","4001":4,
                 "coverage":{"4001":["A"]}}
        async def response(session,rep,cmd,month):
            if month==ym(1):
                return 10000000 if rep=="A" else None
            return 30000000
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'hist.json'
            p.write_text(json.dumps({"months":{key(1):old,key(2):partial}}))
            get=AsyncMock(side_effect=response)
            with patch.object(f,'STRAT_HISTORY_FILE',p),patch.object(f,'STRAT_HIST_MONTHS',2),patch.object(f,'STRAT_MATERIALS',[material]),patch.object(f,'_comtrade_one',get),patch.object(f.asyncio,'sleep',AsyncMock()):
                await f.fetch_strategic_history(None)
            result=json.loads(p.read_text())['months']
        self.assertEqual(result[key(1)]['4001'],12)
        self.assertEqual(result[key(1)]['coverage']['4001'],['A','B'])
        self.assertEqual(result[key(2)]['4001'],6)
        self.assertEqual(result[key(2)]['coverage']['4001'],['A','B'])
        self.assertTrue(result[key(2)]['recheck_attempted_at'])
        self.assertEqual(get.await_count,4)

    async def test_empty_months_rotate_instead_of_starving_older_gaps(self):
        now=f.datetime.now(f.timezone.utc);cur=now.year*100+now.month
        ym=lambda n:f._ym_add(cur,-n)
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'hist.json'
            get=AsyncMock(return_value=None)
            with patch.object(f,'STRAT_HISTORY_FILE',p),patch.object(f,'STRAT_HIST_MONTHS',4),patch.object(f,'STRAT_MATERIALS',[{"cmd":"4001","exp":[("A","A")]}]),patch.object(f,'_comtrade_one',get),patch.object(f.asyncio,'sleep',AsyncMock()):
                for _ in range(4):
                    before=get.await_count
                    await f.fetch_strategic_history(None)
                    self.assertLessEqual(get.await_count-before,f.STRAT_HIST_MIRROR_BUDGET)
            result=json.loads(p.read_text())['months']
        self.assertEqual({c.args[3] for c in get.call_args_list},{ym(n) for n in range(1,5)})
        self.assertTrue(all(r.get('schema_version')!=2 for r in result.values()))
