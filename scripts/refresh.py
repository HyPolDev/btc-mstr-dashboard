"""Free public-data refresh. Python stdlib only; no broker keys or trading.

Each feed is validated before atomic replacement. Failed feeds retain last good
data and produce a visible health error. Capital changes require a dated issuer
review; a successful HTTP request never asserts corporate solvency.
"""
import argparse,csv,copy,hashlib,io,json,math,os,re,statistics,time
from concurrent.futures import ThreadPoolExecutor
from datetime import date,datetime,timedelta,timezone
from pathlib import Path
from urllib.request import Request,urlopen
from urllib.parse import urlencode
from zoneinfo import ZoneInfo
import accounting
ROOT=Path(__file__).resolve().parents[1];D=ROOT/'data'
URLS={
 'bulk':'https://bitview.space/api/series/bulk?series=date,lth_supply,supply&index=day1&start=2187',
 'cumulative':'https://bitview.space/api/series/lth_transfer_volume_cumulative/day1?start=2187',
 'coinmetrics':'https://community-api.coinmetrics.io/v4/timeseries/asset-metrics?assets=btc&metrics=PriceUSD,SplyCur&frequency=1d&start_time=2014-12-29&page_size=10000',
 'obm':'https://raw.githubusercontent.com/diegorllanos/open-bitcoin-metrics/main/metrics/obm_spent_value_ge155d_btc_daily/obm_spent_value_ge155d_btc_daily.csv',
 'sec':'https://data.sec.gov/submissions/CIK0001050446.json',
 'press':'https://www.strategy.com/press'}

def read(n):return json.loads((D/n).read_text(encoding='utf-8'))
def save(n,x):
    p=D/n;tmp=p.with_suffix('.tmp');tmp.write_text(json.dumps(x,ensure_ascii=False,allow_nan=False,separators=(',',':')),encoding='utf-8');os.replace(tmp,p)
def fetch(url,json_data=True):
    # SEC identifies a research user agent, never an API credential.
    req=Request(url,headers={'User-Agent':'BTC-MSTR-Research/1.0 public-dashboard https://github.com/HyPolDev/btc-mstr-dashboard','Accept':'application/json,text/html,text/csv,*/*'})
    for attempt in range(3):
        try:
            with urlopen(req,timeout=35) as res:raw=res.read()
            return json.loads(raw) if json_data else raw.decode('utf-8-sig')
        except Exception:
            if attempt==2:raise
            time.sleep(1+attempt)

def validate_dates(rows,continuous=False):
    dates=[x['date'] for x in rows]
    if not dates or dates!=sorted(set(dates)):raise ValueError('Empty, duplicate or unordered dates')
    if continuous and any((date.fromisoformat(b)-date.fromisoformat(a)).days!=1 for a,b in zip(dates,dates[1:])):raise ValueError('Interior daily gap')

def equity_close(day,venue=None):
    day=date.fromisoformat(day) if isinstance(day,str) else day
    if venue and datetime.fromtimestamp(venue['start'],ZoneInfo('America/New_York')).date()==day:
        return datetime.fromtimestamp(venue['end'],timezone.utc)
    nov=date(day.year,11,1);thanks=nov+timedelta(days=(3-nov.weekday())%7+21)
    early=day==thanks+timedelta(days=1) or (day.month==12 and day.day==24 and day.weekday()<5) or (day.month==7 and day.day==3 and day.weekday()<5)
    return datetime(day.year,day.month,day.day,13 if early else 16,tzinfo=ZoneInfo('America/New_York')).astimezone(timezone.utc)

def completed_equity_day(day,today,now,venue=None):
    return day<=today and equity_close(day,venue)<=now

def holders(today):
    keys=['bulk','cumulative','coinmetrics','obm']
    with ThreadPoolExecutor(max_workers=4) as pool:values=list(pool.map(lambda k:fetch(URLS[k],k!='obm'),keys))
    bulk,cum,cm,ob=values
    if cm.get('next_page_url'):raise ValueError('Coin Metrics pagination must be resolved, not truncated')
    if len(bulk)!=3 or any(x['index']!='day1' for x in bulk) or len({(x['start'],x['end'],len(x['data'])) for x in bulk})!=1:raise ValueError('Bitview schema/alignment changed')
    prices={r['time'][:10]:r for r in cm['data']};spent={x['date']:float(x['value']) for x in csv.DictReader(io.StringIO(ob))}
    cumulative={cum['start']+i:x for i,x in enumerate(cum['data'])}
    endpoint=min(max(d for d in bulk[0]['data'] if d<today),max(d for d in prices if d<today and prices[d].get('PriceUSD') and prices[d].get('SplyCur')))
    rows=[]
    for i,d in enumerate(bulk[0]['data']):
        if not '2015-01-01'<=d<=endpoint:continue
        p=prices[d];ix=bulk[0]['start']+i;gross=cumulative[ix]-cumulative[ix-1];lth=bulk[1]['data'][i];supply=float(p['SplyCur'])
        if not 0<=gross or not 0<=lth<=supply or not float(p['PriceUSD'])>0:raise ValueError('Invalid holder value')
        rows.append(dict(date=d,price=float(p['PriceUSD']),circulatingSupply=supply,lthSupply150=lth,netDecline150=max(0,bulk[1]['data'][i-1]-lth),grossSpent150=gross,grossSpent155=spent.get(d),utxoSupply150=bulk[2]['data'][i]))
    validate_dates(rows,True)
    old=read('holders.json');old.update(rows=rows,fetchedAt=datetime.now(timezone.utc).isoformat(),sourceURLs=list(URLS[k] for k in keys))
    save('holders.json',old);return rows[-1]['date']

def market(today):
    # A genuine venue quote series supplies the equity trading calendar, not a
    # provider's carried holiday prices. Use unadjusted-for-dividend split OHLC.
    # Include today's bar ONLY after the exchange's actual session close. UTC
    # Bitcoin days keep their separate completed-day boundary.
    end=int((datetime.fromisoformat(today).replace(tzinfo=timezone.utc)+timedelta(days=1)).timestamp())
    u='https://query1.finance.yahoo.com/v8/finance/chart/MSTR?'+urlencode(dict(period1=1597017600,period2=end,interval='1d',events='splits',includeAdjustedClose='true'))
    data=fetch(u)['chart']['result'][0];q=data['indicators']['quote'][0];rows=[]
    for split in data.get('events',{}).get('splits',{}).values():
        split_date=datetime.fromtimestamp(split['date'],ZoneInfo('America/New_York')).date().isoformat()
        if split_date!='2024-08-08' or str(split.get('splitRatio')) not in ['10:1','10/1']:
            raise ValueError('New or changed equity split requires a reviewed historical price/share rebasing')
    old=read('mstr.json');by={r['date']:r for r in old['rows']};ledger=read('capital-ledger.json')['snapshots'];now=datetime.now(timezone.utc);venue=data.get('meta',{}).get('currentTradingPeriod',{}).get('regular')
    # Get BTC at the matching regular-session close, using the last completed
    # one-minute Coinbase candle. Only new observations need network marks.
    for i,t in enumerate(data['timestamp']):
        d=datetime.fromtimestamp(t,ZoneInfo('America/New_York')).date().isoformat()
        if not completed_equity_day(d,today,now,venue) or q['close'][i] is None:continue
        r=dict(by.get(d,{}));r.update(date=d,sharePrice=q['close'][i],open=q['open'][i],high=q['high'][i],low=q['low'][i],stockVolume=q['volume'][i])
        if not all(isinstance(r[k],(int,float)) and r[k]>0 for k in ['sharePrice','open','high','low']):raise ValueError('Invalid equity OHLC')
        if not r.get('btcMarkTimeUTC') or not r.get('btcPrice'):
            # Yahoo timestamps identify each exchange opening session. Standard
            # closes16:00 ET; explicit US half-days follow Thanksgiving/Christmas.
            close=equity_close(d,venue)
            a=close-timedelta(minutes=1);cu='https://api.exchange.coinbase.com/products/BTC-USD/candles?'+urlencode({'start':a.isoformat(),'end':close.isoformat(),'granularity':60})
            candles=fetch(cu);c=next((x for x in candles if x[0]==int(a.timestamp())),None)
            if c is None:raise ValueError('Missing matched BTC minute '+d)
            r.update(btcPrice=c[4],btcMarkTimeUTC=close.isoformat(),btcPriceBasis='Coinbase completed minute immediately before equity close')
            time.sleep(.12)
        eligible=[s for s in ledger if s['publishedAt'][:10]<=d]
        # Retain historical reconstruction; recalculate only forward reviewed days.
        if eligible and d>=min(s['publishedAt'][:10] for s in ledger):
            cap=max(eligible,key=lambda s:s['publishedAt']);price=dict(schemaVersion='mstr-mnav-refresh/1.0',asOf=d,publishedAt=r['btcMarkTimeUTC'],readAt=datetime.now(timezone.utc).isoformat(),stockPriceUSD=r['sharePrice'],btcPriceUSD=r['btcPrice'])
            if cap['publishedAt']>price['publishedAt']:eligible=[s for s in eligible if s['publishedAt']<=price['publishedAt']];cap=max(eligible,key=lambda s:s['publishedAt'])
            calc=accounting.calculate_refresh(cap,price);r.update(legacyEvBtcNav=calc['metrics']['legacyEvToGrossBtc'],strategyMnav=calc['metrics']['strategyMnav'],capitalAsOf=cap['asOf'],capitalPublishedAt=cap['publishedAt'],btcHeld=cap['btcHeld'],issuedShares=cap['basicShares'],totalCash=cap['usdReserve']+cap['usdTreasuryCash'],totalDebt=cap['totalDebtUSD']+cap.get('otherDebtUSD',0),totalPreferredStock=cap['preferredNotionalUSD'],qualityFlags=calc['qualityFlags'])
        rows.append(r)
    validate_dates(rows);old.update(rows=rows,fetchedAt=datetime.now(timezone.utc).isoformat(),ohlcSource='https://finance.yahoo.com/quote/MSTR/history/',btcSource='https://docs.cdp.coinbase.com/api-reference/exchange-api/rest-api/products/get-product-candles')
    save('mstr.json',old);return rows[-1]['date']

def news(today):
    filings=fetch(URLS['sec'])['filings']['recent'];items=read('news.json')['items'];seen={x.get('id') for x in items}
    for i,form in enumerate(filings['form']):
        if form not in ['8-K','10-Q','10-K','DEFA14A','DEF 14A','S-3','424B5']:continue
        d=filings['filingDate'][i]
        if d<'2026-09-01' or d>today:continue
        accession=filings['accessionNumber'][i];doc=filings['primaryDocument'][i]
        if accession in seen:continue
        url=f'https://www.sec.gov/Archives/edgar/data/1050446/{accession.replace("-","")}/{doc}'
        items.append(dict(id=accession,eventDate=d,publishedAt=d,category='Issuer filing',headline=f'Strategy files {form}',change='Primary filing detected. Read source for facts; capital and risk implications require review.',relevance='Disclosure review',status='Needs review',sourceUrl=url));seen.add(accession)
    items.sort(key=lambda x:x.get('publishedAt') or x.get('eventDate') or '',reverse=True)
    save('news.json',dict(checkedAt=datetime.now(timezone.utc).isoformat(),items=items[:100],sourceURL=URLS['sec']))
    return items[0].get('publishedAt') if items else today

def btc_daily(today):
    old=read('btc-candles.json');by={r['date']:r for r in old['rows']}
    start=datetime.fromisoformat(max(by)).replace(tzinfo=timezone.utc)-timedelta(days=2);end=datetime.fromisoformat(today).replace(tzinfo=timezone.utc)
    u='https://api.exchange.coinbase.com/products/BTC-USD/candles?'+urlencode({'start':start.isoformat(),'end':end.isoformat(),'granularity':86400})
    for x in fetch(u):
        d=datetime.fromtimestamp(x[0],timezone.utc).date().isoformat()
        if d<today:by[d]=dict(date=d,high=x[2],low=x[1],open=x[3],close=x[4])
    rows=sorted(by.values(),key=lambda r:r['date']);validate_dates(rows,True)
    save('btc-candles.json',dict(rows=rows,source='https://api.exchange.coinbase.com/products/BTC-USD/candles',fetchedAt=datetime.now(timezone.utc).isoformat()));return rows[-1]['date']

def signals(rows):
    # Vector-free, auditable causal features. Current bar excluded from ranks.
    out=[];trs=[];daily=read('btc-candles.json')['rows'];j=0;record=0;lastbreak=-99999
    for i,r in enumerate(rows):
        if r.get('open') is None:continue
        prev=rows[i-1] if i else r;close=r['sharePrice'];atr=statistics.mean(trs[-14:]) if len(trs)>=14 else None
        tr=max(r['high']-r['low'],abs(r['high']-prev['sharePrice']),abs(r['low']-prev['sharePrice']));trs.append(tr)
        f=dict(date=r['date'],close=close,priorATR14=atr,priorLow=prev.get('low'),breakPriorLow=prev.get('low') is not None and close<prev['low'],new63CloseHigh=i>=63 and close>max(x['sharePrice'] for x in rows[i-63:i]),relative=None,extension=None,volume=None)
        if i>=20 and atr:
            base=rows[i-20];f['roc']=close/base['sharePrice']-1;f['relative']=(close/base['sharePrice'])/(r['btcPrice']/base['btcPrice'])-1
            f['extension']=(close-statistics.mean(x['sharePrice'] for x in rows[i-20:i]))/atr
            median=statistics.median(x['stockVolume'] for x in rows[i-20:i]);f['volume']=r['stockVolume']/median if median else None
        for k in ['relative','extension','volume']:
            past=[x[k] for x in out[-252:] if x[k] is not None];f[k+'Rank']=sum(x<=f[k] for x in past)/len(past) if len(past)>=60 and f[k] is not None else None
        ranks=[f[k+'Rank'] for k in ['relative','extension','volume']]
        f['stretch90']=f['new63CloseHigh'] and f.get('roc',0)>0 and (f['relative'] or 0)>0 and all(x is not None for x in ranks) and sum(x>=.9 for x in ranks)>=2
        f['extreme95']=f['stretch90'] and all(x>=.95 for x in ranks)
        while j<len(daily) and daily[j]['date']<r['date']:
            record=max(record,daily[j]['high']);j+=1
        if r['btcPrice']>record:lastbreak=i
        f['btcRecordPhase']=i-lastbreak<=20
        f['qualifiedWatch']=(f['stretch90'] and f['btcRecordPhase']) or f['extreme95']
        f['priorLow10']=min(x['low'] for x in rows[i-10:i]) if i>=10 and all(x.get('low') for x in rows[i-10:i]) else None
        f['pullback10']=f['priorLow10'] is not None and close<f['priorLow10']
        out.append(f)
    save('signals.json',dict(rows=out[-800:],source='Causal daily market features; prior-bar ranks; no personal position state'))
    return out[-1] if out else None

def assemble(today,feeds):
    h=read('holders.json');m=read('mstr.json');caps=read('capital-ledger.json');last=m['rows'][-1]
    cap=max((s for s in caps['snapshots'] if s['publishedAt']<=last['btcMarkTimeUTC']),key=lambda s:s['publishedAt'])
    price=dict(schemaVersion='mstr-mnav-refresh/1.0',asOf=last['date'],publishedAt=last['btcMarkTimeUTC'],readAt=datetime.now(timezone.utc).isoformat(),stockPriceUSD=last['sharePrice'],btcPriceUSD=last['btcPrice'])
    calc=accounting.calculate_refresh(cap,price);sig=signals(m['rows'])
    snapshot=dict(schemaVersion=1,generatedAt=datetime.now(timezone.utc).isoformat(),clientDate=today,market=last,previousMarket=m['rows'][-2],holder=h['rows'][-1],capital=cap,latestCapital=caps['snapshots'][-1],valuation=calc,signals=sig,feeds=feeds,capitalReviewThrough=caps['reviewedThrough'],capitalCaveats=caps['caveats'],news=read('news.json')['items'][:8],automation=read('operations.json')['automation'])
    save('snapshot.json',snapshot);return snapshot

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--as-of',default=datetime.now(ZoneInfo('Europe/Madrid')).date().isoformat());ap.add_argument('--offline',action='store_true');a=ap.parse_args();today=a.as_of;feeds=[]
    for name,fn,filename in [('Holders',holders,'holders.json'),('MSTR and paired BTC',market,'mstr.json'),('BTC venue daily highs',btc_daily,'btc-candles.json'),('SEC filings',news,'news.json')]:
        try:
            endpoint=fn(today) if not a.offline else None
            data=read(filename);endpoint=endpoint or (data.get('rows',[{}])[-1].get('date') if 'rows' in data else data.get('checkedAt'))
            feeds.append(dict(name=name,state='cached' if a.offline else 'ok',checkedAt=datetime.now(timezone.utc).isoformat(),observationDate=endpoint,error=None))
        except Exception as e:
            feeds.append(dict(name=name,state='error',checkedAt=datetime.now(timezone.utc).isoformat(),observationDate=(read(filename)['rows'][-1].get('date') if 'rows' in read(filename) else next((x.get('publishedAt') or x.get('eventDate') for x in read(filename).get('items',[]) if x.get('publishedAt')),None)),error=str(e)[:180]))
    s=assemble(today,feeds);print(json.dumps(dict(generatedAt=s['generatedAt'],marketAsOf=s['market']['date'],holderAsOf=s['holder']['date'],feeds=feeds)))
    return s

if __name__=='__main__':main()
