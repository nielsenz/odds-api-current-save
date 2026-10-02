# Saved forecasts joined to the new odds archive

All 211,146 original odds outcomes are retained. 81,230 match 3,789 distinct saved forecasts across 13 models; 129,916 odds outcomes remain unmatched. Multiple models can match one quote, so the output has 212,466 rows. No API calls, retraining, wager selection, production-feed changes, or ledger writes.

## Coverage

Counts below are distinct model/game/market/player forecasts, not independent bets. Spreads and totals are separate forecasts; NFL futures count teams rather than games. Quote rows repeat books, sides and snapshots.

| Model | Matched forecasts | Matched games / future teams | Quote rows | Timing-safe quote rows | Eligible forecasts with actuals |
|---|---:|---:|---:|---:|---:|
| nfl_phase4_corrected | 281 | 281 | 10,142 | 10,142 | 266 |
| nfl_revamp_totals_saved | 281 | 281 | 9,820 | 9,820 | 266 |
| nfl_primary_epa | 30 | 15 | 660 | 660 | 0 |
| nfl_independent | 30 | 15 | 660 | 660 | 0 |
| nfl_prior_volume_calibration | 156 | 44 | 4,706 | 2,172 | 156 |
| nfl_injury_aware_yards_mean | 428 | 32 | 10,546 | 4,748 | 406 |
| nfl_injury_aware_reception_mean | 413 | 32 | 10,082 | 4,613 | 389 |
| nfl_experimental_super_bowl | 32 | 32 | 224 | 224 | 0 |
| cbb_canonical_ridge | 1,674 | 1,674 | 28,028 | 28,028 | 1,674 |
| wnba_joint_score | 28 | 14 | 748 | 748 | 28 |
| wnba_saved_spread_baseline | 128 | 64 | 3,324 | 3,324 | 128 |
| nhl_saved_site_pregame | 95 | 95 | 938 | 938 | 95 |
| nhl_prior_roster_sog_replay | 213 | 14 | 2,672 | 1,882 | 200 |

The largest immediate comparison sets are 1,674 CBB spread games and NFL player props across 44 sampled games (32 for the later-season receiving experiment). WNBA has 78 game/model combinations across two saved research models. NHL SOG matches 213 game/player forecasts across 14 games; five lack an outcome in the saved outcomes source.

## Identity, timing and interpretation

Games match by verified native Odds API ID where available, otherwise by Eastern game date and exact normalized home/away identities. Player matching uses normalized names and explicit NFL roster aliases. No fuzzy matching or automatic home/away reversal. Explicit kickoff timestamps must agree within one hour. Four CBB quote rows fail the home/away check and remain unmatched.

`strict_quote_timing` requires a pre-start quote and both original vendor/requested-cutoff flags. `comparison_quote_eligible` also requires a unique quote identity. Four Bovada reception quote identities have conflicting prices: all eight rows remain visible and excluded from comparison eligibility. `archive_row_number` traces every output row to the original archive.

`forecast_precedes_quote` separately compares a recorded forecast timestamp with the quote timestamp. Most historical forecasts lack a capture clock and are marked false. Current NFL forecasts use their recorded row timestamp when present, otherwise the refresh run-manifest time as a conservative upper bound on artifact availability. The NFL futures clock comes from its simulation manifest. These fields certify timestamp ordering only; they do not establish a funded, frozen or validated policy.

Spread forecasts represent home margin; `model_difference` adds the offered team handicap to the corresponding predicted margin. Totals/props compare the saved mean with the line, reversing the sign for Under. Means are not cover probabilities. NFL receiving yards uses the saved participation-adjusted expectation; receptions uses participation probability times conditional receptions. Actual receptions come only from the saved outcome panel. NHL moneyline and NFL futures retain saved probabilities; price-implied probabilities include bookmaker margin and are not de-vigged.

`statistic_result` grades the observed statistic against each offered side and line. Player participation/void rules are unknown, so prop results are explicitly statistic-only. `wager_profit` is blank throughout; this export does not establish ROI or select a betting strategy. NFL Super Bowl forecasts remain EXPERIMENTAL_UNVALIDATED. NHL site-history probabilities are separate from the frozen funded model.

## Remaining gaps

- CBB: retained unmatched and excluded from joining 487 2025 forecasts with cutoff on/after target date; fit exclusivity unverified.
- NBA saved walk-forward predictions end 2024-01-21; collected NBA quotes are 2025. No overlapping forecast source.
- NHL saved pregame forecasts begin October 2024; the new 2023-24 moneyline archive has no overlapping registered forecast. NHL championship futures source not registered.
- No registered 2026 WNBA player-prop or current CFB forecast source found for this archive.

The 114,932 unmatched saved forecasts are exported, including all 487 CBB rows excluded from matching because their training-cutoff exclusivity is unverified. No later model fit was substituted for an absent earlier forecast.

## Files and reproduction

- `joined_quotes.csv.gz`: all original quote columns, source-row identity, matched predictions, observed statistics, timing/conflict flags and unmatched reasons.
- `unmatched_forecasts.csv.gz`: saved forecasts without an accepted match, including excluded forecasts.
- `coverage.csv`: per-model coverage and available-statistic counts.
- `summary.json`: complete denominators and SHA-256 hashes of every registered source.
- `audit.json`: reconciliation of every original quote field, source hashes, unmatched forecasts and eligibility counts.

Run from the odds-api repository with Python 3.11+ and pandas/fastparquet for the two NFL Parquet adapters (the NFL model `.venv` supplies these):

```bash
python research/join_saved_forecasts.py \
  --sports-home "$SPORTS_HOME" \
  --odds research/odds-expansion-20261002/outcomes.csv.gz \
  --out research/forecast-join-new-run
```

The output directory must not already exist. Forecast sources are explicitly registered in the adapter; missing sources are reported. Source files, policies and ledgers are read-only. Validation: 14 join tests plus 15 existing collector/research tests; all 211,146 input rows and their original fields reconcile against the export, and every source hash remains unchanged.
