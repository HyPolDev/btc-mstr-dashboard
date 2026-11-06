"""Parse Strategy's published delivery feed; unknown structures fail closed.

The feed is the same public Contentstack production content used by Strategy's
website. The public read-only delivery token is kept in an Actions secret.
No browser, model, text generation, or privileged Contentstack API is used.
"""
import copy
import hashlib
import json
import math
import os
import re
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlencode, urlparse
import accounting
from public_sources import fetch

STACK = 'bltf8d808d9b8cebd37'
BASE = 'https://cdn.contentstack.io/v3/content_types/'
DEBTS = {'2028':'convert_2028','2029':'convert_2029','2030A':'convert_2030_a',
         '2030B':'convert_2030_b','2031':'convert_2031','2032':'convert_2032'}
PREFS = {'STRC','STRD','STRE','STRF','STRK'}

def now(): return datetime.now(timezone.utc).isoformat()

def instant(value):
    parsed = datetime.fromisoformat(value.replace('Z','+00:00'))
    if parsed.tzinfo is None: raise ValueError('Source publication time has no timezone')
    return parsed.astimezone(timezone.utc).isoformat()

def number(value, label, positive=False):
    if isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(value) or value < 0 or (positive and value == 0):
        raise ValueError('Invalid or missing '+label)
    return value

def publication(entry): return instant(entry['publish_details']['time'])

def entries(content_type, token, query=None):
    rows = []
    for skip in range(0, 5000, 100):
        params = dict(environment='production', include_count='true', include_publish_details='true', limit=100, skip=skip)
        if query: params['query']=json.dumps(query,separators=(',',':'))
        data = fetch(BASE+content_type+'/entries?'+urlencode(params), headers={'api_key':STACK,'access_token':token})
        part = data['entries']; total = data['count']
        if not isinstance(part,list) or not isinstance(total,int): raise ValueError('Issuer pagination/schema changed')
        rows.extend(part)
        if len(rows)>=total: return rows
        if not part: raise ValueError('Issuer pagination truncated')
    raise ValueError('Issuer pagination exceeds audited limit')

def parse_capital(tracker, converts, maintenance, previous, checked_at):
    """Convert known issuer fields into the unchanged accounting contract."""
    economic = date.fromisoformat(tracker['as_of_date']).isoformat()
    if economic > checked_at[:10]: raise ValueError('Future capital economic date')
    shares = tracker['shares']
    if set(k for k in shares if k.startswith('convert_')) != set(DEBTS.values())|{'convert_strk'}:
        raise ValueError('Unfamiliar conversion security: maintain mapping before accepting capital')
    if {k[:-8].upper() for k in tracker if k.endswith('_metrics')} != PREFS:
        raise ValueError('Unfamiliar preferred series: capital requires review')
    by = {}
    for row in converts:
        match = re.fullmatch(r'Convert (\d{4})\s*([AB]?)', row['title'])
        if not match: raise ValueError('Unfamiliar debt instrument '+row['title'])
        security = ''.join(match.groups())
        if security in by: raise ValueError('Duplicate debt instrument')
        by[security] = row
    if set(by) != set(DEBTS): raise ValueError('Debt instrument set changed; do not infer retirement or new terms')
    cap = dict(schemaVersion=accounting.SCHEMA_VERSION, asOf=economic,
        publishedAt=max([publication(tracker)]+[publication(row) for row in converts]),
        readAt=checked_at, basicShares=number(tracker['basic_shares_outstanding'],'basic shares',True),
        btcHeld=number(tracker['btc_holdings'],'BTC holdings',True),
        usdReserve=number(tracker['cash'],'USD reserve'),
        usdTreasuryCash=number(tracker['operating_cash'],'USD treasury cash'),
        preferredNotionalUSD=number(tracker['pref'],'preferred notional'),
        totalDebtUSD=number(tracker['debt'],'convertible debt'),
        otherDebtUSD=number(maintenance['otherDebt']['valueUSD'],'carried other debt'),
        options=number(shares['options_outstanding'],'options'),
        rsuPsu=number(shares['rsu_psu_unvested'],'RSU/PSU'),debtTranches=[],unmodeledSecurities=[])
    terms = []
    for security, field in DEBTS.items():
        row=by[security]; principal=number(row['notional'],security+' principal')
        strike=number(row['strike_price'],security+' conversion price',True)
        converted=number(shares[field],security+' conversion shares')
        if abs(converted-principal/strike)>max(1000,principal/strike*.001):
            raise ValueError('Unreconciled conversion shares/principal for '+security)
        cap['debtTranches'].append(dict(id=security,principal=principal,conversionPrice=strike,conversionShares=converted))
        terms.append(dict(id=security,principalUSD=principal,conversionPrice=strike,conversionShares=converted,
            couponPct=number(row['coupon'],security+' coupon'),maturity=date.fromisoformat(row['maturity_date']).isoformat(),
            putDate=date.fromisoformat(row['put_date']).isoformat(),publishedAt=publication(row)))
    preferred = []
    for security in sorted(PREFS):
        row=tracker[security.lower()+'_metrics']
        # STRE shares are already expressed as USD-equivalent units by the issuer.
        face=number(row['shares'],security+' USD-equivalent units')*100
        if security=='STRE':
            expected=number(row['notional_intl'],'STRE EUR units')*number(row['current_fx_rate'],'STRE FX',True)*100
            if abs(expected-face)>1000: raise ValueError('STRE FX/notional mismatch')
        preferred.append(dict(id=security,notionalUSD=face,couponPct=number(row['dividend'],security+' annual rate'),
            nextRecordDate=row['next_record_date'],nextPayoutDate=row['next_payout_date']))
    if abs(sum(p['notionalUSD'] for p in preferred)-cap['preferredNotionalUSD'])>1000:
        raise ValueError('Preferred claims do not reconcile to issuer aggregate')
    strike=number(maintenance['strkConversion']['priceUSD'],'reviewed STRK conversion price',True)
    strk_face=next(p['notionalUSD'] for p in preferred if p['id']=='STRK')
    strk_shares=number(shares['convert_strk'],'STRK conversion shares')
    if abs(strk_shares-strk_face/strike)>1000: raise ValueError('STRK conversion terms changed or mismatch')
    cap['strk']=dict(id='STRK',notionalUSD=strk_face,conversionPrice=strike,conversionShares=strk_shares)
    adso=number(tracker['ibit_shares'],'assumed diluted shares',True)
    expected=cap['basicShares']+cap['options']+cap['rsuPsu']+sum(x['conversionShares'] for x in cap['debtTranches'])+strk_shares
    if abs(adso-expected)>1000: raise ValueError('Assumed diluted shares mismatch; possible unmodeled conversion')
    # First observations of a newly changed schema cannot silently claim precision.
    accounting.validate_capital_snapshot(cap)
    # A CMS republish of identical economic facts is not a new disclosure of
    # those facts. Preserve the first already-observed publication boundary.
    economic_keys=set(cap)-{'readAt','publishedAt','sourceId'}
    if previous and all(previous.get(key)==cap[key] for key in economic_keys):
        cap['publishedAt']=previous['publishedAt']
    stable={k:v for k,v in cap.items() if k!='readAt'}
    cap['sourceId']='issuer-cms-'+hashlib.sha256(json.dumps(stable,sort_keys=True).encode()).hexdigest()[:16]
    provenance = dict(sourceId=cap['sourceId'],economicDate=economic,publishedAt=cap['publishedAt'],
        retrievedAt=checked_at,publicationBasis='Conservative latest current CMS publication time; earlier original disclosure may exist',
        sources=['https://www.strategy.com/','https://www.strategy.com/debt','https://www.strategy.com/shares'],
        assumedDilutedShares=adso,conversionShareRoundingResidual=expected-adso, debtTerms=terms, preferred=preferred,
        components=[dict(input='BTC, basic shares, cash, preferred, awards and conversion shares',economicDate=economic,
                         publishedAt=publication(tracker),status='automated issuer fields'),
                    dict(input='Convertible debt principal, strikes, puts and maturities',economicDate=None,
                         publishedAt=max(publication(x) for x in converts),status='automated current terms; individual economic change dates not supplied'),
                    dict(input='Other secured indebtedness',economicDate=maintenance['otherDebt']['asOf'],
                         publishedAt=maintenance['otherDebt']['publishedAt'],status='manual balance carried forward'),
                    dict(input='STRK conversion strike and complex legal rights',economicDate=maintenance['strkConversion']['asOf'],
                         publishedAt=maintenance['strkConversion']['publishedAt'],status='reviewed rule carried; new legal terms require review')])
    return cap,provenance

def parse_news(documents, releases, today):
    result=[]
    for row in documents:
        pub=instant(row['published_date']); url=row.get('file_reference',{}).get('url')
        if pub[:10]>today or not url: continue
        if urlparse(url).hostname!='assets.contentstack.io': raise ValueError('Unexpected issuer filing asset host')
        result.append(dict(id='issuer-filing-'+row['uid'],eventDate=pub[:10],publishedAt=pub,
            category='Issuer filing',headline=row.get('display_title') or row['title'],
            change='Published filing detected automatically. Financial and legal implications are not adjudicated.',
            relevance='Primary issuer-hosted filing',status='Detected automatically',reviewStatus='Needs review',sourceUrl=url))
    for row in releases:
        day=date.fromisoformat(row['publication_date'][:10]).isoformat()
        if day>today: continue
        path=row['url']
        if not path.startswith('/press/'): continue
        pub=publication(row)
        result.append(dict(id='issuer-release-'+row['uid'],eventDate=day,publishedAt=pub,
            category='Issuer release',headline=row.get('display_title') or row['title'],
            change='Issuer title reproduced as published. Open the release for the full disclosure; no generated news summary.',
            relevance='Primary issuer release',status='Detected automatically',reviewStatus='Needs review',sourceUrl='https://www.strategy.com'+path))
    return sorted(result,key=lambda x:x['publishedAt'],reverse=True)

def run(today, read, save, root):
    checked=now(); old=read('capital-status.json') if (root/'data/capital-status.json').exists() else {}
    status=dict(schemaVersion=1,lastAttemptAt=checked,lastSuccessAt=old.get('lastSuccessAt'),
                state='error',capitalAsOf=old.get('capitalAsOf'),capitalPublishedAt=old.get('capitalPublishedAt'),coverage=old.get('coverage',[]),exceptions=[],sourceURL='https://www.strategy.com/')
    feeds=[]
    token=os.environ.get('ISSUER_DELIVERY_TOKEN')
    if not token:
        private=root/'private/issuer-delivery.json'
        if private.exists(): token=json.loads(private.read_text(encoding='utf-8'))['deliveryToken']
    def fail(name,exc,observation=None):
        # Never log request headers or tokens.
        message=type(exc).__name__+': '+str(exc)[:180]
        if token: message=message.replace(token,'[redacted]')
        feeds.append(dict(name=name,state='error',checkedAt=checked,observationDate=observation,error=message))
        status['exceptions'].append(dict(rule='source_or_schema_failure',detail=name+': '+message))
    documents=[]
    if not token:
        fail('Issuer capital',ValueError('ISSUER_DELIVERY_TOKEN unavailable'))
        fail('Issuer releases and filings',ValueError('ISSUER_DELIVERY_TOKEN unavailable'))
    else:
        cutoff=(date.fromisoformat(today)-timedelta(days=45)).isoformat()
        # Index refresh is independent of capital parsing and SEC availability.
        for content_type,label in [('sec_document','Issuer filing index'),('press_release','Issuer releases')]:
            try:
                key='published_date' if content_type=='sec_document' else 'publication_date'
                data=entries(content_type,token,{key:{'$gte':cutoff}})
                parsed=parse_news(data,[],today) if content_type=='sec_document' else parse_news([],data,today)
                if content_type=='sec_document': documents=parsed
                current=read('news.json'); by={x['id']:x for x in current['items']}
                for item in parsed:
                    if item['id'] not in by: by[item['id']]=item
                current.update(checkedAt=checked,items=sorted(by.values(),key=lambda x:x.get('publishedAt') or x.get('eventDate') or '',reverse=True)[:250])
                save('news.json',current)
                feeds.append(dict(name=label,state='ok',checkedAt=checked,observationDate=max((x['publishedAt'] for x in parsed),default=None),error=None))
            except Exception as exc: fail(label,exc)
        try:
            tracker_rows=entries('btc_tracker',token,{'latest':True})
            if len(tracker_rows)!=1: raise ValueError('Expected one current issuer capital entry')
            tracker=tracker_rows[0];converts=entries('converts',token)
            maintenance=read('capital-maintenance.json');ledger=read('capital-ledger.json')
            previous=ledger['snapshots'][-1]
            cap,evidence=parse_capital(tracker,converts,maintenance,previous,checked)
            if cap['asOf']<previous['asOf']: raise ValueError('Issuer capital would move backwards')
            same=next((x for x in ledger['snapshots'] if x['asOf']==cap['asOf']),None)
            if same and same.get('sourceId')==cap['sourceId']: cap=same
            else:
                update=accounting.upsert_capital_snapshot(ledger['snapshots'],cap,correction_reason='Reconciled issuer delivery entry or correction')
                ledger['snapshots']=update['snapshots']
                ledger.setdefault('audit',[]).extend(update['audit'])
                ledger['latestSource']='https://www.strategy.com/'
                save('capital-ledger.json',ledger)
            archive=read('capital-evidence.json') if (root/'data/capital-evidence.json').exists() else {'observations':[]}
            if not any(x['sourceId']==evidence['sourceId'] for x in archive['observations']):
                archive['observations'].append(evidence);save('capital-evidence.json',archive)
            instruments=read('instruments.json')
            for row in instruments['rows']:
                term=next((x for x in evidence['debtTerms'] if x['id']==row['id']),None)
                pref=next((x for x in evidence['preferred'] if x['id']==row['id']),None)
                if term:
                    for k in ['principalUSD','conversionPrice','conversionShares','couponPct','maturity','putDate']: row[k]=term[k]
                    row['status']='automated issuer balance/terms; legal conditions need review'
                if pref:
                    for k in ['notionalUSD','couponPct']: row[k]=pref[k]
                    row['nextRecordDate']=pref['nextRecordDate'];row['nextPayoutDate']=pref['nextPayoutDate']
                    row['status']='automated issuer notional/rate; complex legal rights need review'
                if term or pref:
                    row['asOf']=cap['asOf'];row['publishedAt']=term['publishedAt'] if term else publication(tracker)
                    row['sourceUrl']='https://www.strategy.com/debt' if term else 'https://www.strategy.com/'
            save('instruments.json',instruments)
            status.update(state='partial',lastSuccessAt=checked,capitalAsOf=cap['asOf'],capitalPublishedAt=cap['publishedAt'],
                          coverage=evidence['components'],sourceId=cap['sourceId'])
            status['exceptions'].append(dict(rule='manual_component',detail='Other secured debt remains carried from '+maintenance['otherDebt']['asOf']+'; the issuer dashboard excludes it. Complex preferred rights and STRK strike retain dated review.'))
            feeds.append(dict(name='Issuer capital',state='partial',checkedAt=checked,observationDate=cap['asOf'],error=None))
        except Exception as exc: fail('Issuer capital',exc,old.get('capitalAsOf'))
    # Detection raises a review request, never a corporate sell recommendation.
    maintenance=read('capital-maintenance.json')
    for item in documents:
        if item['publishedAt'][:10]>maintenance['legalReviewedThrough'] and re.search(r'8-K|10-Q|10-K|424B|S-3',item['headline'],re.I):
            status['exceptions'].append(dict(rule='unreviewed_financing_or_periodic_filing',detail=item['headline']+' published '+item['publishedAt'][:10]+' requires legal/capital review.',sourceUrl=item['sourceUrl'],publishedAt=item['publishedAt']))
    # An outage or the rolling index window must not clear unresolved exceptions.
    for exception in old.get('exceptions',[]):
        if exception['rule']!='unreviewed_financing_or_periodic_filing':continue
        match=re.search(r'published (\d{4}-\d{2}-\d{2})',exception.get('detail',''))
        published=exception.get('publishedAt') or (match[1] if match else None)
        if published and published[:10]>maintenance['legalReviewedThrough'] and not any(x.get('sourceUrl')==exception.get('sourceUrl') for x in status['exceptions']):status['exceptions'].append(exception)
    status['corporateRiskConclusion']='Not automatically adjudicated. No detected event does not establish corporate safety.'
    save('capital-status.json',status)
    return feeds
