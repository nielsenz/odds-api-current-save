# Fixed-as-of NHL totals research archive

Daily GitHub Actions schedule: 15:07 UTC. Request NHL totals, US region, American prices, with a fixed vendor as-of 15:00 UTC. A run starting at 15:05–15:19 and finishing before 15:20 is timely. Later runs record a missed window without fetching. GitHub scheduling can be delayed or skipped; missing calendar dates are missing captures, never implicit empty slates. The archive is research only and creates no bets.

The [official historical API documentation](https://the-odds-api.com/liveapi/guides/v4/) specifies the closest snapshot at or before the requested date; snapshots use five-minute intervals. The collector permits at most ten minutes of vendor lag, rejects later market timestamps, and retains vendor, retrieval, market-update and game-start times. This single-market, single-region request normally costs ten credits; response quota headers are retained. Historical endpoint access is required on the configured account.

Each dated capture directory contains immutable raw response, paired exact-line Over/Under quotes, event coverage and status JSON. Book aliases normalize William Hill US to Caesars. Missing books are reported; collection does not filter to a trading policy. Coverage is relative to the vendor-returned event universe, not an independent NHL schedule. `no_totals_returned` does not prove there were no games. Join against the official schedule before evaluating coverage or forecasts. Existing status files prevent a second API request. Failures retain only safe error types.

```sh
python -m unittest discover -s research -p 'test_totals_capture.py' -v
python research/totals_capture.py health --root data/nhl_totals_15utc
python research/totals_capture.py probe --root data/nhl_totals_15utc
python research/totals_capture.py recover --date YYYY-MM-DD --root data/nhl_totals_15utc
```

API operations require `ODDS_API_KEY`; never place a credential in a command or archive. Manual probes/recoveries have separate directories and always have `prospective_capture=false`. A probe establishes endpoint access and persistence, not future scheduled reliability. Check workflow failures and calendar gaps; no automatic recovery fills missed days. Quotes alone are not a prospective betting test: forecasts and a fixed evaluation policy must also be archived before outcomes.
