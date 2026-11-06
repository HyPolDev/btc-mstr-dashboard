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
- Python/GitHub Actions owns scheduled refresh and direct Pages deployment.
- Publish only validated public source/data/docs; verify the generated bundle against live Pages.
- Preserve capital component dates and exception state; full capital/legal coverage remains partial.
- Keep the issuer's public read-only delivery token in Actions Secrets or ignored private configuration.
- Never re-enable the paused Codex updater while the Python schedule is active.
- No broker operations, paid API use or external messages/alerts.
