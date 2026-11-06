# Public source audit — 6 November 2026

The audit ran locally and on GitHub-hosted Ubuntu before source selection.
The manual Audit public issuer sources workflow can repeat the access check.

| Source | Observed access | Use and limitation |
|---|---|---|
| Strategy website HTML, ledger, debt, press and filing pages | HTTP 403 from Python and runner; normal headless Chromium lacked structured data | Human-readable source links; no stealth or challenge bypass. |
| Strategy public production Contentstack delivery API | HTTP 200 using the frontend's read-only delivery token | Chosen source: btc_tracker, converts, sec_document and press_release entries used by the issuer site. No management API. |
| Strategy /btc/bitcoinKpis and /btc/mstrKpiData API | HTTP 200 | Aggregate cross-check. Market timestamps cannot establish capital economic dates; rounded market cap/mNAV are not reverse-engineered into capital inputs. |
| SEC submissions, companyfacts and archive HTML | HTTP 403 in local and hosted audit | Independent filing detection is attempted; failures disclosed. Standard companyfacts also excludes custom taxonomy facts and would not supply all treasury fields. |
| Issuer-linked Contentstack PDFs | HTTP 200 | Primary evidence and review links. Full legal/prospectus interpretation remains unsupported. |
| Yahoo daily equity history | HTTP 200 | Genuine split-adjusted OHLCV sessions. New splits stop replacement pending reviewed rebasing. |
| Coinbase candles | HTTP 200 | Completed minute at equity close plus separate completed UTC-day highs. |
| Bitview date, 150-day holder supply and cumulative transfers | HTTP 200 | Primary turnover inputs. Retired total supply/bulk endpoint returned 404; it was an unused dependency. |
| Coin Metrics Community and Open Bitcoin Metrics | HTTP 200 | Circulating-supply normalization, BTC price, separate 155-day cross-check. Coverage dates remain explicit. |

The public read-only delivery token stays in the ISSUER_DELIVERY_TOKEN repository
secret. No paid service, personal brokerage key, AI service, authenticated issuer
account or running personal computer is part of the daily execution path.

## Actual capital coverage

Known six convertible series and five preferred series are reconciled. Dated
BTC, basic shares, reported assumed diluted shares, reserve, treasury cash,
preferred USD-equivalent notional/FX, awards and potential conversion shares are
ingested. FDSO is calculated from basic shares, awards and eligible in-money
conversion shares; it is not replaced by GAAP diluted EPS or all-convertible
ADSO. Converted claims are removed exactly when conversion shares are added.
Actual retired/converted balances must reconcile remaining principal and
potential shares; an inconsistent update is rejected.

Economic dates come from the issuer tracker. Current CMS publication times are
recorded conservatively; they may be later than original disclosure or reflect
republication. Individual economic dates for debt-term changes are not supplied
and stay unknown in the coverage table. These snapshots do not establish a
validated point-in-time historical backtest.

**Not fully automated:** other secured debt retains its reviewed June 30 balance;
STRK strike and complex contractual rights retain dated review. New series or
inconsistent totals retain the prior capital and raise exceptions. New financing
and periodic filings require human review; titles are not corporate-risk
conclusions. The dashboard labels mNAV as estimates needing review even after a
successful issuer-field refresh.

References: [Strategy definitions](https://www.strategy.com/notes),
[SEC API coverage](https://www.sec.gov/search-filings/edgar-application-programming-interfaces),
[GitHub Pages deployment](https://docs.github.com/en/pages/getting-started-with-github-pages/using-custom-workflows-with-github-pages).
