"""Read back deployed assets and compare with this run's exact generated bundle."""
import hashlib
import json
import sys
import time
from pathlib import Path
from urllib.request import Request,urlopen

ROOT=Path(__file__).resolve().parents[1]
BASE='https://hypoldev.github.io/btc-mstr-dashboard/'
FILES=['index.html','app.js','dilution.mjs','style.css','data/snapshot.json','data/deployment.json',
       'data/mstr.json','data/indicators.json','data/holders.json','data/capital-status.json','data/news.json']

def verify():
    marker=json.loads((ROOT/'dist/data/deployment.json').read_text())['validatedAt']
    for attempt in range(12):
        failed=[]
        for name in FILES:
            try:
                request=Request(BASE+name+'?validation='+marker,headers={'Cache-Control':'no-cache'})
                with urlopen(request,timeout=25) as response:remote=response.read()
                local=(ROOT/'dist'/name).read_bytes()
                if name.endswith('.json'):
                    match=json.loads(remote)==json.loads(local)
                else:match=remote.replace(b'\r\n',b'\n')==local.replace(b'\r\n',b'\n')
                if not match:failed.append(name)
            except Exception:failed.append(name)
        if not failed:
            print('Verified live deployment: '+', '.join(FILES));return
        print('Awaiting CDN update for: '+', '.join(failed),flush=True)
        if attempt<11:time.sleep(10)
    raise RuntimeError('Deployed site does not match generated bundle')

if __name__=='__main__':verify()
