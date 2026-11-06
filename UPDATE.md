# Python daily pipeline

The public site is maintained by `.github/workflows/daily-publish.yml` using
Python's standard library and standard GitHub-hosted Ubuntu runners. There is no
AI runtime, paid API, broker connection, or personal computer left running.

## Schedule and manual runs

The daily cron is **22:37 UTC**, after the 16:00 New York close in either US
clock regime. This is 23:37 Madrid in winter and 00:37 the next day in summer.
GitHub can delay scheduled jobs. Weekends and holidays keep the last genuine
stock session while BTC and holder series advance independently.

Actions -> **Refresh and publish dashboard** -> **Run workflow** is the manual
entry point. `refresh=true` fetches sources; false republishes saved data.
Pushes to main validate and publish saved data. Scheduled/manual refreshes fetch
sources and deploy directly in the same run; a bot commit need not trigger a
second workflow.

## Sources and coverage

Read [SOURCE_AUDIT.md](SOURCE_AUDIT.md). Strategy's public production Contentstack
entries supply dated BTC, basic/assumed diluted shares, reserve/treasury cash,
preferred notionals/FX, awards and potential conversion shares. The current
convertible table supplies principal, conversion strikes, coupons, puts and
maturities. Totals and the conversion-share bridge must reconcile.

The **ISSUER_DELIVERY_TOKEN** Actions secret holds the public read-only delivery
token used by Strategy's frontend. It grants no publishing/management access.
Keep it out of code, public datasets, URLs, logs and artifacts. No personal
Alpaca/FMP key is used. A local operator may use an ignored
`private/issuer-delivery.json` with a `deliveryToken` property. On issuer token
rotation, update the repository secret after inspecting the issuer's source.

Full capital coverage is **partial**. Other secured debt is carried from its
dated reviewed balance; STRK's legal conversion strike and complex rights,
amendments, covenants, dividend provisions and unfamiliar instruments require
occasional human review. Maintain `data/capital-maintenance.json` and the
instrument register from primary disclosures. Advance `legalReviewedThrough`
only after actually reviewing the listed documents. Debt-term economic change
dates are not supplied individually and remain unknown. CMS publication dates
are conservative current-version timestamps, possibly later than original
SEC disclosure or reflecting republication. Fetch time never substitutes for
an economic date.

## Failure handling

- Transient requests retry three times with bounded backoff. 429 respects a
  bounded Retry-After; permanent 400/401/403/404 errors are disclosed. No identity
  rotation, stealth browser or access-control bypass is used.
- Holder data, equity/paired BTC, BTC daily highs, issuer indexes and capital
  update independently. Failed components retain last validated observations,
  including their original observation dates and source dates.
- Unknown securities, missing fields, incomplete pagination, and inconsistent
  claims/conversion/share totals prevent capital replacement. Old balances
  remain with an explicit source/schema exception beside mNAV estimates.
- The 155-day cross-check can fail without blocking the 150-day primary cohort;
  a missing tail stays null. The retired Bitview supply field is unused in
  turnover and is retained historically/null thereafter. Established turnover,
  indicator, cycle-reset and exit-policy formulas do not change.
- New releases and filings use factual original titles, dates and links. New
  8-K/10-Q/10-K/424B/S-3 entries after the legal-review cutoff raise review
  exceptions. This rule does not declare bankruptcy, custody loss, default,
  solvency, or an automatic exit. No detected news does not prove safety.
- Attempt timestamps, observation dates, capital economic/publication dates,
  component dates and last successful extraction are separate on the site.
- Critical validation/test/build failures stop commit and deployment. Source
  failures with valid retained data publish a visibly degraded dashboard while
  independent feeds continue updating.
- Deployment/readback failure fails the workflow. Check Actions and on-page
  freshness after repeated failures; no automatic external trading or alerts.

## Local validation and publication

1. `python scripts/refresh.py` (or `--offline` for retained data only).
2. `python -m unittest discover -s tests`
3. `node --test tests/*.test.mjs` and `node --check app.js`
4. `python scripts/validate.py` and `python scripts/build.py`
5. Commit only public source/data/docs, never keys or personal inputs.
6. The workflow uploads `dist/` and invokes `actions/deploy-pages` directly.
7. `python scripts/verify_deployment.py` compares deployed core datasets and
   application files with that run's generated bundle. Provenance appears in
   `data/deployment.json`; public data artifacts retain 30 days in Actions.

Publication jobs queue. Non-fast-forward pushes fail rather than force-pushing
user edits. Personal purchase information stays in browser localStorage and
never enters the workflow.

## Rollback and maintenance

Tag `pre-python-pipeline-2026-11-06` preserves the preceding app/data/runbook.
The Codex updater is paused only after a complete replacement run is verified
live; its configuration is retained privately.

Restore `data/` from a good commit, commit the restoration, then run with
refresh=false to republish old data. For a full rollback, revert migration
commits on a repair branch, validate/build, and publish main. Restore the old
`main:/docs` publishing setting in Settings -> Pages if abandoning Actions.
Never re-enable the former updater while this Python schedule is enabled.

Maintenance needs: issuer schema or token changes, new instruments/splits,
quarterly other debt, legal amendments, review exceptions, and GitHub service
or permissions changes. Use only standard free hosted runners in this public
repository. GitHub may disable schedules after repository inactivity; regular
data commits provide activity, but inspect the workflow if dates stop advancing.
