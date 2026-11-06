import copy
import json
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import accounting
import issuer
from public_sources import fetch
from urllib.error import HTTPError

class IssuerTests(unittest.TestCase):
    def setUp(self):
        self.fixture=json.loads((ROOT/'tests/fixtures/issuer-known.json').read_text())
        self.maintenance=json.loads((ROOT/'data/capital-maintenance.json').read_text())

    def parse(self):
        return issuer.parse_capital(self.fixture['tracker'],self.fixture['converts'],self.maintenance,{},'2026-11-06T22:40:00+00:00')

    def test_known_issuer_fields_reconcile_independently(self):
        c,e=self.parse()
        self.assertEqual(c['basicShares'],423533159)
        self.assertEqual(c['btcHeld'],849327)
        self.assertEqual(c['usdReserve']+c['usdTreasuryCash'],4922000000)
        self.assertEqual(c['preferredNotionalUSD'],13135891600)
        self.assertEqual(e['conversionShareRoundingResidual'],514)
        self.assertEqual(e['components'][2]['economicDate'],'2026-06-30')
        self.assertIn('manual',e['components'][2]['status'])
        self.assertEqual(c['asOf'],'2026-11-02')
        self.assertEqual(c['publishedAt'],'2026-11-03T12:05:11.581000+00:00')

    def test_valuation_reconciles_in_money_claims_once(self):
        c,e=self.parse()
        p=dict(schemaVersion=accounting.SCHEMA_VERSION,asOf='2026-11-05',publishedAt='2026-11-05T21:00:00Z',readAt='2026-11-06T22:40:00Z',stockPriceUSD=400,btcPriceUSD=142000)
        v=accounting.calculate_refresh(c,p)
        chosen=[x for x in c['debtTranches'] if x['id'] in ['2028','2030A','2031','2032']]
        self.assertEqual(set(v['conversions']['itmSecurityIds']),{'2028','2030A','2031','2032'})
        self.assertEqual(v['conversions']['removedDebtClaimUSD'],sum(x['principal'] for x in chosen))
        self.assertEqual(v['conversions']['fdso'],c['basicShares']+c['options']+c['rsuPsu']+sum(x['conversionShares'] for x in chosen))

    def test_republishing_identical_facts_does_not_erase_first_known_date(self):
        previous,_=self.parse()
        self.fixture['tracker']['publish_details']['time']='2026-11-06T12:00:00Z'
        current,_=issuer.parse_capital(self.fixture['tracker'],self.fixture['converts'],self.maintenance,previous,'2026-11-06T22:40:00+00:00')
        self.assertEqual(current['publishedAt'],previous['publishedAt'])
        self.assertEqual(current['sourceId'],previous['sourceId'])

    def test_actual_conversion_reduces_remaining_claim_and_potential_shares(self):
        before,_=self.parse(); count=100000; retired=count*183.19
        self.fixture['tracker']['basic_shares_outstanding']+=count
        self.fixture['tracker']['shares']['convert_2028']-=count
        self.fixture['tracker']['debt']-=retired
        next(x for x in self.fixture['converts'] if x['title']=='Convert 2028')['notional']-=retired
        after,_=self.parse()
        self.assertEqual(after['basicShares']-before['basicShares'],count)
        self.assertAlmostEqual(before['totalDebtUSD']-after['totalDebtUSD'],retired)
        self.assertEqual(sum(x['conversionShares'] for x in before['debtTranches'])-sum(x['conversionShares'] for x in after['debtTranches']),count)

    def test_unknown_security_or_inconsistent_conversion_fails_closed(self):
        for mutate in [lambda t:t['shares'].update(convert_2035=10000),lambda t:t.update(strz_metrics={'shares':100}),lambda t:t['shares'].update(convert_2028=4000000),lambda t:t.update(pref=1),lambda t:t.update(ibit_shares=1)]:
            original=copy.deepcopy(self.fixture)
            mutate(self.fixture['tracker'])
            with self.assertRaises(ValueError):self.parse()
            self.fixture=original

    def test_publication_does_not_allow_economic_date_lookahead(self):
        c,_=self.parse()
        p=dict(schemaVersion=accounting.SCHEMA_VERSION,asOf='2026-11-02',publishedAt='2026-11-02T21:00:00Z',readAt='2026-11-06T22:40:00Z',stockPriceUSD=200,btcPriceUSD=100000)
        with self.assertRaises(accounting.ContractError):accounting.calculate_refresh(c,p)

    def test_capital_parse_failure_preserves_ledger_but_publishes_independent_news(self):
        with TemporaryDirectory() as temp:
            root=Path(temp);(root/'data').mkdir()
            store={'capital-maintenance.json':self.maintenance,'capital-ledger.json':{'snapshots':[{'asOf':'2026-10-25'}]},'news.json':{'items':[{'id':'old','publishedAt':None}]}}
            original=copy.deepcopy(store['capital-ledger.json'])
            def response(kind,token,query=None):
                if kind=='sec_document':return [{'uid':'new','published_date':'2026-11-04T12:00:00Z','display_title':'Form 8-K','file_reference':{'url':'https://assets.contentstack.io/example.pdf'}}]
                if kind=='press_release':return []
                raise ValueError('Unfamiliar financing')
            with patch.dict('os.environ',{'ISSUER_DELIVERY_TOKEN':'test-public-fixture-token'}),patch.object(issuer,'entries',side_effect=response):
                feeds=issuer.run('2026-11-06',lambda n:store[n],lambda n,d:store.__setitem__(n,copy.deepcopy(d)),root)
            self.assertEqual(store['capital-ledger.json'],original)
            self.assertTrue(any(x['id']=='issuer-filing-new' for x in store['news.json']['items']))
            self.assertTrue(any(f['name']=='Issuer capital' and f['state']=='error' for f in feeds))
            self.assertIn('does not establish',store['capital-status.json']['corporateRiskConclusion'])

    def test_news_titles_are_factual_and_future_releases_excluded(self):
        row={'uid':'a','publication_date':'2026-11-02','url':'/press/example','title':'An issuer title','publish_details':{'time':'2026-11-02T13:00:00Z'}}
        result=issuer.parse_news([], [row], '2026-11-06')
        self.assertEqual(result[0]['headline'],'An issuer title')
        self.assertEqual(result[0]['reviewStatus'],'Needs review')
        self.assertEqual(issuer.parse_news([], [row], '2026-10-01'),[])

    def test_temporary_http_error_retries_but_denial_does_not(self):
        for status,expected in [(503,3),(403,1)]:
            with patch('public_sources.urlopen',side_effect=HTTPError('https://example.com',status,'test',{},None)) as request,patch('public_sources.time.sleep'):
                with self.assertRaises(HTTPError):fetch('https://example.com')
                self.assertEqual(request.call_count,expected)

    def test_pagination_requires_complete_source(self):
        with patch.object(issuer,'fetch',side_effect=[{'entries':[{}]*100,'count':101},{'entries':[],'count':101}]):
            with self.assertRaises(ValueError):issuer.entries('sec_document','test')

if __name__=='__main__':unittest.main()
