"""Validate generated public data before any commit or deployment."""
import hashlib
import json
import math
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path
import accounting
import indicators

ROOT=Path(__file__).resolve().parents[1]

def read(name): return json.loads((ROOT/'data'/name).read_text(encoding='utf-8'))

def check():
    token=os.environ.get('ISSUER_DELIVERY_TOKEN')
    private=ROOT/'private/issuer-delivery.json'
    if not token and private.exists():token=json.loads(private.read_text(encoding='utf-8'))['deliveryToken']
    def walk(value):
        if isinstance(value,float) and not math.isfinite(value):raise ValueError('Non-finite public value')
        if isinstance(value,dict):
            for item in value.values():walk(item)
        if isinstance(value,list):
            for item in value:walk(item)
    for path in (ROOT/'data').glob('*.json'):
        text=path.read_text(encoding='utf-8');walk(json.loads(text))
        for secret in ['C:/Users/','ghp_','gho_','ALPACA_API_KEY','delivery_token','deliveryToken']+([token] if token else []):
            if secret in text:raise ValueError('Private context/credentials in '+path.name)
    s=read('snapshot.json');m=read('mstr.json')['rows'];h=read('holders.json')['rows']
    for rows in [m,h,read('btc-candles.json')['rows']]:
        dates=[r['date'] for r in rows]
        if dates!=sorted(set(dates)):raise ValueError('Unordered/duplicate public observations')
        if dates[-1]>s['clientDate']:raise ValueError('Future observation')
    if s['market']!=m[-1]:raise ValueError('Snapshot/history market mismatch')
    price=dict(schemaVersion=accounting.SCHEMA_VERSION,asOf=s['market']['date'],publishedAt=s['market']['btcMarkTimeUTC'],
        readAt=s['generatedAt'],stockPriceUSD=s['market']['sharePrice'],btcPriceUSD=s['market']['btcPrice'])
    v=accounting.calculate_refresh(s['capital'],price)
    if v['metrics']!=s['valuation']['metrics']:raise ValueError('mNAV reconciliation failed')
    if s['capital']['publishedAt']>s['market']['btcMarkTimeUTC']:raise ValueError('Capital publication lookahead')
    expected=indicators.calculate(m)[-1]
    if s['indicators']!=expected:
        if not any(f['name']=='MSTR daily indicators' and f['state']=='error' for f in s['feeds']):raise ValueError('Indicator mismatch without an explicit retained-data error')
    if not isinstance(s.get('capitalStatus'),dict):raise ValueError('Capital coverage status is required')
    return s

def main():
    s=check()
    data=dict(schemaVersion=1,validatedAt=datetime.now(timezone.utc).isoformat(),snapshotGeneratedAt=s['generatedAt'],
        sourceCommit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),runUrl=('https://github.com/'+os.environ['GITHUB_REPOSITORY']+'/actions/runs/'+os.environ['GITHUB_RUN_ID']) if os.environ.get('GITHUB_RUN_ID') else None,
        feedErrors=[f['name'] for f in s['feeds'] if f['state']=='error'],capitalCoverage=s['capitalStatus']['state'])
    (ROOT/'data/deployment.json').write_text(json.dumps(data,separators=(',',':')),encoding='utf-8')
    print(json.dumps(data))
    if os.environ.get('GITHUB_STEP_SUMMARY'):
        lines=['## Public dashboard refresh','', 'Market: '+s['market']['date'], 'Holder data: '+s['holder']['date'], 'Capital economic date: '+s['capital']['asOf'], 'Capital coverage: '+s['capitalStatus']['state'], 'Source errors retained: '+(', '.join(data['feedErrors']) or 'none'), '', 'Review exceptions remain visible on the published dashboard.']
        with open(os.environ['GITHUB_STEP_SUMMARY'],'a',encoding='utf-8') as summary:summary.write('\n'.join(lines)+'\n')

if __name__=='__main__':main()
