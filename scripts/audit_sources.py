"""Probe primary public sources from the actual scheduled runner, without AI."""
import json
from pathlib import Path
from datetime import datetime, timezone
from urllib.request import Request, urlopen

SOURCES = {
    'issuer': 'https://www.strategy.com/',
    'ledger': 'https://www.strategy.com/ledger',
    'press': 'https://www.strategy.com/press',
    'filings': 'https://www.strategy.com/financial-documents',
    'notes': 'https://www.strategy.com/notes',
    'debt': 'https://www.strategy.com/debt',
    'submissions': 'https://data.sec.gov/submissions/CIK0001050446.json',
    'companyfacts': 'https://data.sec.gov/api/xbrl/companyfacts/CIK0001050446.json',
}

def main():
    out = Path('source-audit'); out.mkdir(exist_ok=True)
    rows = []
    for name, url in SOURCES.items():
        try:
            req = Request(url, headers={'User-Agent': 'BTC-MSTR-Research/1.0 https://github.com/HyPolDev/btc-mstr-dashboard', 'Accept':'application/json,text/html,*/*'})
            with urlopen(req, timeout=30) as response:
                data = response.read()
                row = dict(name=name, url=url, status=response.status, bytes=len(data), contentType=response.headers.get('Content-Type'))
            # The audit stores status/size only, not full articles or credentials.
        except Exception as exc:
            row = dict(name=name, url=url, error=str(exc))
        rows.append(row)
    import os
    token=os.environ.get('ISSUER_DELIVERY_TOKEN')
    if token:
        try:
            req=Request('https://cdn.contentstack.io/v3/content_types/btc_tracker/entries?environment=production&limit=1',headers={'api_key':'bltf8d808d9b8cebd37','access_token':token})
            with urlopen(req,timeout=30) as response:
                payload=json.load(response)
                rows.append(dict(name='issuer public structured delivery',url='https://www.strategy.com/',status=response.status,entryCount=len(payload['entries'])))
        except Exception as exc:rows.append(dict(name='issuer public structured delivery',error=type(exc).__name__+': source unavailable'))
    result = dict(checkedAt=datetime.now(timezone.utc).isoformat(), sources=rows)
    (out/'audit.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps(result,indent=2))

if __name__ == '__main__': main()
