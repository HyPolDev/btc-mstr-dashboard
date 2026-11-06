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
            (out/(name+'.txt')).write_bytes(data)
        except Exception as exc:
            row = dict(name=name, url=url, error=str(exc))
        rows.append(row)
    result = dict(checkedAt=datetime.now(timezone.utc).isoformat(), sources=rows)
    (out/'audit.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps(result,indent=2))
    # Normal Chromium rendering only: no stealth, proxy rotation or challenges.
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            for name in ['issuer','debt','press','filings']:
                try:
                    response = page.goto(SOURCES[name],wait_until='domcontentloaded',timeout=45000)
                    raw = page.locator('#__NEXT_DATA__').text_content(timeout=15000)
                    (out/(name+'-page.json')).write_text(raw,encoding='utf-8')
                    print(name,'Chromium',response.status,'structured data bytes',len(raw))
                except Exception as exc: print(name,'Chromium failed',str(exc)[:200])
            browser.close()
    except ImportError: pass

if __name__ == '__main__': main()
