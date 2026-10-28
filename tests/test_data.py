import copy,json,math,sys,unittest
from datetime import date,timedelta
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'scripts'))
import accounting,refresh
def read(n):return json.loads((ROOT/'data'/n).read_text(encoding='utf-8'))

class DataTests(unittest.TestCase):
    def test_cash_and_claim_bridge_independent_reconciliation(self):
        s=read('snapshot.json');c=s['capital'];p=s['market'];v=s['valuation'];cash=c['usdReserve']+c['usdTreasuryCash'];gross=c['btcHeld']*p['btcPrice']
        ev=c['basicShares']*p['sharePrice']+c['totalDebtUSD']+c.get('otherDebtUSD',0)+c['preferredNotionalUSD']-cash
        self.assertAlmostEqual(ev/gross,v['metrics']['legacyEvToGrossBtc'],places=10)
        self.assertAlmostEqual(p['sharePrice']*v['conversions']['fdso']/(v['conversions']['netBtc']*p['btcPrice']),v['metrics']['strategyMnav'],places=10)
    def test_conversion_removes_claim_and_adds_shares_once(self):
        c=read('capital-ledger.json')['snapshots'][-1];s=read('snapshot.json');p=dict(schemaVersion='mstr-mnav-refresh/1.0',asOf='2026-10-27',publishedAt='2026-10-27T20:00:00Z',readAt='2026-10-28T23:00:00Z',stockPriceUSD=1001,btcPriceUSD=100000)
        v=accounting.calculate_refresh(c,p)['conversions'];debt=sum(t['principal'] for t in c['debtTranches']);added=sum(t['conversionShares'] for t in c['debtTranches'])+c['strk']['conversionShares']
        self.assertAlmostEqual(v['removedDebtClaimUSD'],debt);self.assertAlmostEqual(v['removedStrkClaimUSD'],c['strk']['notionalUSD'])
        self.assertAlmostEqual(v['fdso'],c['basicShares']+c['options']+c['rsuPsu']+added)
    def test_no_future_capital_in_current_snapshot(self):
        s=read('snapshot.json');self.assertLessEqual(s['capital']['publishedAt'],s['market']['btcMarkTimeUTC'])
    def test_future_capital_is_rejected(self):
        c=copy.deepcopy(read('capital-ledger.json')['snapshots'][-1]);c['publishedAt']='2026-10-29T20:00:00Z';c['readAt']='2026-10-30T00:00:00Z';s=read('snapshot.json');p=dict(schemaVersion='mstr-mnav-refresh/1.0',asOf='2026-10-27',publishedAt='2026-10-27T20:00:00Z',readAt='2026-10-28T23:00:00Z',stockPriceUSD=140,btcPriceUSD=80000)
        with self.assertRaises(accounting.ContractError):accounting.calculate_refresh(c,p)
    def test_actual_equity_calendar_and_completed_ohlc(self):
        s=read('snapshot.json');rows=read('mstr.json')['rows'];refresh.validate_dates(rows)
        self.assertNotIn('2026-01-19',[r['date'] for r in rows])
        for r in rows:
            self.assertLess(r['date'],s['clientDate']);self.assertLess(date.fromisoformat(r['date']).weekday(),5)
            self.assertLessEqual(r['low'],min(r['open'],r['sharePrice']));self.assertGreaterEqual(r['high'],max(r['open'],r['sharePrice']))
    def test_holder_days_contiguous_and_volumes_valid(self):
        rows=read('holders.json')['rows'];refresh.validate_dates(rows,True)
        for r in rows:self.assertGreaterEqual(r['grossSpent150'],0);self.assertGreater(r['circulatingSupply'],0);self.assertGreater(r['price'],0)
    def test_no_zero_fill_for_missing_155day_tail(self):
        r=read('holders.json')['rows'][-1];self.assertIn('grossSpent155',r)
        self.assertTrue(r['grossSpent155'] is None or isinstance(r['grossSpent155'],(int,float)) and r['grossSpent155']>=0)
    def test_signal_rank_excludes_current_observation(self):
        rows=read('signals.json')['rows'];last=rows[-1]
        for key in ['relative','extension','volume']:
            past=[r[key] for r in rows[-253:-1] if r[key] is not None]
            self.assertAlmostEqual(sum(x<=last[key] for x in past)/len(past),last[key+'Rank'],places=10)
    def test_bitcoin_record_never_uses_current_utc_day_high(self):
        daily=read('btc-candles.json')['rows'];m=read('mstr.json')['rows'];signals=read('signals.json')['rows'];dates=[r['date'] for r in m]
        for f in signals[-20:]:
            i=dates.index(f['date']);eligible=False
            for r in m[max(0,i-20):i+1]:
                high=max(x['high'] for x in daily if x['date']<r['date'])
                eligible|=r['btcPrice']>high
            self.assertEqual(f['btcRecordPhase'],eligible)
    def test_missing_or_duplicate_dates_fail(self):
        with self.assertRaises(ValueError):refresh.validate_dates([{'date':'2026-01-01'},{'date':'2026-01-03'}],True)
        with self.assertRaises(ValueError):refresh.validate_dates([{'date':'2026-01-01'},{'date':'2026-01-01'}])
    def test_public_files_exclude_private_context(self):
        for p in (ROOT/'data').glob('*.json'):
            text=p.read_text(encoding='utf-8')
            for secret in ['costBasisUSD','protectiveReviewUSD','brokerOrdersAuthorized','C:/Users/','C:\\\\Users\\\\','ghp_','gho_','ALPACA_API_KEY']:
                self.assertNotIn(secret,text,p.name)
    def test_all_published_numbers_finite(self):
        def walk(x):
            if isinstance(x,float):self.assertTrue(math.isfinite(x))
            elif isinstance(x,dict):
                for v in x.values():walk(v)
            elif isinstance(x,list):
                for v in x:walk(v)
        for p in (ROOT/'data').glob('*.json'):walk(json.loads(p.read_text(encoding='utf-8')))

if __name__=='__main__':unittest.main()
