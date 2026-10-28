import copy
import json
import sys
import unittest
from datetime import date,timedelta
from pathlib import Path
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import indicators,refresh


def bars(closes):
    start=date(2020,1,1)
    return [dict(date=(start+timedelta(days=i)).isoformat(),open=100.0,sharePrice=x) for i,x in enumerate(closes)]


class IndicatorTests(unittest.TestCase):
    def test_requested_mean_is_open_close_not_true_range(self):
        rows=bars([101,98,103,96,105,94,107,92,109,90,110])
        rows[0]['high']=1000
        result=indicators.calculate(rows)
        self.assertIsNone(result[8]['atrPct10'])
        self.assertAlmostEqual(result[9]['atrPct10'],5.5)
        self.assertAlmostEqual(result[10]['atrPct10'],6.4)

    def test_rsi_seed_and_wilder_update_hand_calculated(self):
        # 30 gains of $1 and 10 losses of $1 seed RSI = 75. A further
        # $1 gain makes average gain 0.75625 and average loss 0.24375.
        closes=[100]
        for change in [1]*30+[-1]*10+[1]:closes.append(closes[-1]+change)
        result=indicators.calculate(bars(closes))
        self.assertIsNone(result[39]['rsi40'])
        self.assertAlmostEqual(result[40]['rsi40'],75)
        self.assertAlmostEqual(result[41]['rsi40'],75.625)

    def test_flat_up_down_and_causality(self):
        self.assertEqual(indicators.calculate(bars([100]*41))[-1]['rsi40'],50)
        self.assertEqual(indicators.calculate(bars(list(range(100,141))))[-1]['rsi40'],100)
        self.assertEqual(indicators.calculate(bars(list(range(141,100,-1))))[-1]['rsi40'],0)
        x=bars([100+i%7 for i in range(60)])
        before=indicators.calculate(x)
        x[-1]['sharePrice']=999
        after=indicators.calculate(x)
        self.assertEqual(before[:-1],after[:-1])

    def test_invalid_bar_rejects_instead_of_bridging_gap(self):
        for bad in [None,0,-1,float('nan'),float('inf')]:
            rows=bars([100]*50);rows[25]['open']=bad
            with self.assertRaisesRegex(ValueError,'Missing or invalid'):indicators.calculate(rows)
        rows=bars([100]*50);rows[25]['date']=rows[24]['date']
        with self.assertRaisesRegex(ValueError,'Duplicate or unordered'):indicators.calculate(rows)

    def test_offline_snapshot_recomputes_and_reports_consistent_date(self):
        market=json.loads((ROOT/'data/mstr.json').read_text(encoding='utf-8'))['rows']
        calculated=indicators.calculate(market)[-1]
        snapshot=json.loads((ROOT/'data/snapshot.json').read_text(encoding='utf-8'))
        self.assertEqual(calculated,snapshot['indicators'])
        self.assertEqual(calculated['date'],snapshot['market']['date'])

    def test_failed_calculation_keeps_existing_data_and_reports_error(self):
        m=refresh.read('mstr.json');m=copy.deepcopy(m);m['rows'][100]['open']=None
        existing=refresh.read('indicators.json')
        actual_read=refresh.read
        def mocked_read(name):
            return m if name=='mstr.json' else actual_read(name)
        written={}
        def mocked_save(name,value):written[name]=value
        feeds=[dict(name='MSTR and paired BTC',state='cached')]
        with patch.object(refresh,'read',side_effect=mocked_read),patch.object(refresh,'save',side_effect=mocked_save):
            result=refresh.assemble('2026-10-28',feeds)
        self.assertNotIn('indicators.json',written)
        self.assertEqual(result['indicators'],existing['rows'][-1])
        self.assertEqual(next(f for f in feeds if f['name']=='MSTR daily indicators')['state'],'error')


if __name__=='__main__':unittest.main()
