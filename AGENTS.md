# Dashboard maintenance

Read UPDATE.md before any data refresh. This repository is the public project;
preserve its original frontend and the user's presentation changes. Do not import
plugin-owned frontend bundles or the restricted12axes styles/assets.

- All data fetching and accounting happens in scripts/, not in the browser.
- Keep original code MIT and respect upstream data rights/attribution.
- Personal settings, position data, keys, task IDs and tokens stay out of commits.
- A source HTTP success does not establish current capital or corporate health.
- Preserve actual trading sessions and BTC pairing; fail on schema/split drift.
- Unavailable inputs remain null or retained with explicit errors, never zero.
- Do not change policy thresholds, cycle anchors or formulas during a refresh.
- Run Python unit tests, node --check app.js, then scripts/build.py.
- Publish only validated public files and docs/ to main; verify Pages readback.
- No broker operations, paid API use or external messages/alerts.
