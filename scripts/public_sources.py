"""Deterministic access to public data, with bounded retries and no AI calls."""
import json
import time
from urllib.error import HTTPError
from urllib.request import Request, urlopen

USER_AGENT = 'BTC-MSTR-Research/2.0 https://github.com/HyPolDev/btc-mstr-dashboard'

def fetch(url, json_data=True, headers=None):
    request = Request(url, headers={'User-Agent': USER_AGENT,
        'Accept': 'application/json,text/html,text/csv,*/*', **(headers or {})})
    for attempt in range(3):
        try:
            with urlopen(request, timeout=30) as response:
                raw = response.read()
            return json.loads(raw) if json_data else raw.decode('utf-8-sig')
        except HTTPError as exc:
            # Permanent denial is disclosed, never evaded or retried indefinitely.
            if exc.code in (400, 401, 403, 404) or attempt == 2: raise
            wait = min(30, int(exc.headers.get('Retry-After', '5'))) if str(exc.headers.get('Retry-After', '5')).isdigit() else 5
            time.sleep(max(wait, 2 ** attempt))
        except Exception:
            if attempt == 2: raise
            time.sleep(2 ** attempt)
