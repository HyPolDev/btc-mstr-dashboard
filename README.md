# Bitcoin & Strategy daily monitor

Public dashboard: https://hypoldev.github.io/btc-mstr-dashboard/

A portable, static research dashboard for MSTR price, both mNAV definitions,
treasury obligations, Bitcoin holder turnover, filings and a configurable exit
policy. Original HTML/CSS/JS; no ChatGPT hosting/runtime dependency, paid APIs,
broker connection, CDN dependencies or account required to read it.

## Views

- Overview: paired prices, valuation, review queue and source health.
- MSTR & capital: actual trading dates, historical legacy/current-definition
  mNAV, calculation bridge, instrument register and dated corporate checks.
- BTC holders: cumulative and90-day turnover, selectable proxy/cohort, lazy
  step-by-step lesson, transparent reset assumptions and timing-only forecast.
- Exit policy: causal market conditions, three separate rally tranches and
  browser-local settings/fills. An observation is not an executable order.
- Filings & news: primary links, factual summaries and explicit review status.
- Sources: dates, definitions, carry-forward limits, downloads and feed errors.

## Run locally

Python3.10+ and a static HTTP server suffice:

```sh
python scripts/refresh.py
python -m unittest discover -s tests
python scripts/build.py
python -m http.server 8080 --directory dist
```

Use `python scripts/refresh.py --offline` to rebuild derived state from saved
observations without fetching. It labels feeds cached, not freshly checked.
No package install or credentials are needed. Missing feeds retain the last
valid component and show an error. No numeric value is filled with zero simply
because a provider is unavailable. The source data dates differ intentionally.

## Daily operation

The requested Codex daily updater follows [UPDATE.md](UPDATE.md), including
primary-source capital/news review before publishing. No GitHub scheduled data
workflow duplicates it. GitHub Pages publishes `main:/docs`; `scripts/build.py`
produces that directory from explicit public assets and data only. GitHub CI
checks changes. Execution history lives in Git; updater failures remain visible.

## Accounting and evidence

`scripts/accounting.py` is the previously reviewed pure calculation contract.
Legacy EV/grossBTC and current price/netBTC-per-diluted-share stay separate.
Capital ledgers preserve disclosure dates, cash, principal/face claims and share
counts. Converted claims are removed when conversion shares are added. Carry-
forward dates, rounding, FX proxies and nonpositive netBTC are disclosed.

The initial capital update reviews the October26,2026SEC8-K:848,517BTC;2,068,459
STRC shares repurchased;4.83bnUSD reserve and242.4mUSD other cash as ofOctober25.
Common shares/awards/debt and preferred FX include dated carried inputs. This is
not a complete current solvency sign-off. Historical capital before disclosure
is retrospective and unsuitable as a validated point-in-time trading signal.

Data comes from public Yahoo OHLC, Coinbase venue candles, Coin Metrics
Community, Bitview, Open Bitcoin Metrics, and issuer/SEC disclosures. Cached
observations remain subject to provider rights. Research charts are not a
licensed market-data redistribution service. Credentials and broker data are
not used. Full news articles are not republished.

## Personal settings

Entry, protective intention and actual fills are stored only in browser
localStorage. They are not sent to GitHub, this project, or a brokerage. Export/
import moves them between devices. Browsers/devices do not automatically sync.
Do not commit personal settings or export files. Daily monitoring cannot enforce
an intraday floor. Gaps and execution delays can produce lower proceeds.

## Portability

Deploy `dist/` on any static HTTP host. `docs/` is the same build for GitHub
Pages. Refresh scripts work independently of Codex; replace the scheduler without
changing the frontend. Back up the repository and data snapshots. A host or
scheduler can fail; no provider is promised to remain available forever.

The visual implementation is original. The12axes reference informed broad
editorial preferences only; none of its restricted CSS/assets is bundled.

MIT for original code; seeLICENSE for upstream-data exclusions.
