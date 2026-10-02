# Cross sport odds research collection

Completed October 2 UTC / October 1 Pacific. The collector spent 11,964 credits on 829 successful requests and retained 211,146 normalized outcome rows. The historical-access probe cost another 10 credits, for 11,974 total. The account had 1,281 credits remaining at the last response. No API request failed.

[Credit ledger](requests.jsonl), [coverage audit](coverage.json), [collection summary](summary.json), [collection plan](plan.json), [normalized outcomes CSV compressed with gzip](outcomes.csv.gz). Raw compressed JSON files are indexed and hashed in the ledger. The uncompressed CSV is retained in the workspace research archive.

| Sample | Requests | Credits | Outcome rows | Distinct vendor events | Empty responses |
| --- | ---: | ---: | ---: | ---: | ---: |
| live_reference | 4 | 12 | 5,828 | 119 | 0 |
| live_futures | 2 | 2 | 352 | 2 | 0 |
| nfl_2025_weekly_reference | 18 | 360 | 19,320 | 269 | 0 |
| nfl_props_24h | 44 | 1760 | 17,454 | 44 | 0 |
| nfl_props_30m | 44 | 1760 | 19,440 | 44 | 0 |
| cbb_noon_2025 | 61 | 610 | 35,632 | 2108 | 0 |
| wnba_decision_2026 | 47 | 940 | 9,384 | 209 | 0 |
| wnba_30m_2026 | 24 | 480 | 1,046 | 24 | 0 |
| nhl_sog_event_discovery | 8 | 80 | 1,054 | 102 | 0 |
| nhl_sog_24h | 16 | 40 | 196 | 4 | 12 |
| nhl_sog_30m | 16 | 160 | 2,880 | 16 | 0 |
| nba_priced_pilot | 19 | 380 | 4,910 | 126 | 0 |
| nhl_2023_24_open | 260 | 2600 | 43,366 | 1405 | 0 |
| nhl_2023_24_morning | 260 | 2600 | 49,636 | 1405 | 0 |
| wnba_props_24h | 3 | 90 | 154 | 3 | 0 |
| wnba_props_30m | 3 | 90 | 494 | 3 | 0 |

The 2023–24 NHL 05:00/15:00 UTC slots fill the season preceding the already captured 2024–26 all-book archive. These are fixed overnight and morning reference times, not proven first market openers. Raw boards can contain live games and games on later dates; `pre_start` distinguishes quote timing, and event-date selection must precede any model evaluation. The full returned event denominator is preserved.

NFL props cover an outcome-independent pilot of 44 games selected from the first three Sunday UTC-day events on each weekly reference board, capped chronologically. This sampling underrepresents later/primetime games and is not a full-season betting universe. Each selected game has requested 24-hour and 30-minute snapshots for passing yards, rushing yards, receiving yards and receptions. Missing 24-hour offers remain missing; no -110 or synthetic line is supplied.

CBB uses daily 12:00 UTC snapshots for November–December 2025; it does not create prospective 2026 captures. WNBA uses every-third-day 2026 decision boards, 24 sampled game closes and a three-game points/rebounds/assists prop pilot. NHL SOG covers 16 sampled games at 24 hours and 30 minutes; several 24-hour responses have no offered props. NBA is a bounded priced spread/total pilot. These samples establish collection/join inputs, not validated filters or ROI.

The live NFL reference is joined to all 15 remaining Week 4 games in the [NFL model refresh](https://github.com/nielsenz/nfl-team-model/blob/main/outputs/2026/week-4-refresh-20261002T050339Z/README.md), with 165 per-book rows. Supported NFL Super Bowl and NHL championship boards are also retained. Division, conference and make-playoffs markets are not assumed to exist.

All raw hashes, credit totals and finite American prices were checked. Historical effective timestamps are at or before requested cutoffs. Normalize William Hill US to Caesars only through an explicit bookmaker mapping; native keys and update times remain in this export. Props use provider player descriptions, which still need identity and book-specific action/void joins before settlement. No forecasts, real wagers, frozen execution feeds or paper ledgers are inferred from these odds.

Validation: nine main unit tests plus six existing research-capture tests passed. The new tests cover budget and account-reserve checks, resumability, actual cost accounting, secret-safe failures and rejection of future effective snapshots. Credentials are excluded from the archive.

The reusable collector is [collect_research_budget.py](../../collect_research_budget.py). A dry-run plan makes no network calls. Resuming this exact directory reuses its captured responses; use a new directory for fresh live observations.

20,881 rows have market update times later than the vendor effective snapshot; 1,128 are also later than the requested cutoff. `requested_cutoff_safe` requires a supplied quote-update time before the requested cutoff and kickoff. `vendor_snapshot_consistent` separately tests the returned vendor snapshot time. Use both flags for strict snapshot studies; unsafe rows remain in the raw archive. Missing timestamps never establish cutoff safety.
