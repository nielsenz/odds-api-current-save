# Odds API

Collects NHL betting odds from [The Odds API](https://the-odds-api.com/), including daily forward-looking line snapshots and historical data.

## Goals

- Focus collection on NHL markets only.
- Capture line movement across the day with three snapshots:
  - `open` (8:00 PM PT, prior evening)
  - `morning` (7:00 AM PT)
  - `close` (4:00 PM PT)
- Preserve every pull by writing timestamped files (no same-day overwrites).

## Data

### Daily odds (`odds-data/`)

Three GitHub Actions workflows run daily and commit timestamped CSV snapshots:

- Open: 8:00 PM PT (`04:00 UTC`)
- Morning: 7:00 AM PT (`15:00 UTC`)
- Close: 4:00 PM PT (`00:00 UTC`)

Files are written as `odds_YYYY-MM-DD_<snapshot_label>_YYYYMMDDTHHMMSSZ.csv`.

### Historical odds (`odds-data/historical/`)

Pre-game snapshots (noon ET / 17:00 UTC) for NHL games, fetched from The Odds API's historical endpoint. Current coverage:

| Season  | Date Range                    | Files |
|---------|-------------------------------|-------|
| 2023-24 | Oct 10, 2023 - Jun 25, 2024  | 260   |
| 2024-25 | Oct 4, 2024 - Jun 25, 2025   | 265   |
| 2025-26 | Oct 4, 2025 - Jan 9, 2026    | 97    |

### Line phases for value alignment

Use these snapshots to standardize line movement analysis:

- `open`: 8:00 PM PT prior evening (`04:00 UTC`)
- `mid`: 7:00 AM PT (`15:00 UTC`) from the morning pull
- `close`: 4:00 PM PT (`00:00 UTC`) from the close pull
- Historical endpoint snapshot: noon ET (`17:00 UTC`) for backfilling missing days

### Current timing profile (this repo)

- Historical files (`odds-data/historical/`): currently dominated by `17:00:00Z` snapshots (607 files).
- Daily files (`odds-data/`): 28 plain-date files (`odds_YYYY-MM-DD.csv`) where exact pull timestamp is not encoded in the filename.
- Practical takeaway: the large majority of stored odds snapshots are noon ET (`17:00 UTC`) historical pulls.

### CSV format

Both daily and historical files share the same schema:

```
date, sport, game_id, commence_time, home_team, away_team, bookmaker,
snapshot_taken_at_utc, api_snapshot_timestamp_utc, response_received_at_utc, bookmaker_last_update_utc,
ml_home, ml_away, spread_home, spread_home_odds, spread_away,
spread_away_odds, total_line, total_over_odds, total_under_odds
```

- Bookmakers: BetMGM, Caesars
- Markets: moneyline (h2h), spreads, totals
- Odds format: American
- Timestamp fields:
  - `snapshot_taken_at_utc`: requested/effective snapshot target (`17:00:00Z` default for historical; current UTC time for live pulls)
  - `api_snapshot_timestamp_utc`: historical API's returned snapshot timestamp (closest available at or before requested time). Blank for live pulls.
  - `response_received_at_utc`: HTTP response `Date` header from The Odds API
  - `bookmaker_last_update_utc`: per-bookmaker odds update timestamp returned by the API

## Scripts

### `fetch_odds.py`

Fetches current NHL odds snapshots. Used by the GitHub Actions workflows.

```bash
ODDS_API_KEY=your_key uv run python fetch_odds.py
```

### `fetch_historical_odds.py`

Fetches historical NHL odds for a date range. Resumable (skips dates with existing files in `odds-data/historical/` or `odds-data/`).

Behavior:
- Makes one historical request per day in the date range.
- Uses one requested timestamp per day (default `17:00 UTC`), not automatic hourly/half-hourly pulls.
- Use `--snapshot-label` to store additional same-day snapshots (for example, `open_9pm_pst`) without overwriting or skip-collisions.

```bash
# Default: 2025-26 season pre-collection gap
uv run python fetch_historical_odds.py

# Specific date range
uv run python fetch_historical_odds.py 2023-10-10 2024-06-25

# Choose a different historical snapshot time (UTC)
uv run python fetch_historical_odds.py 2025-12-24 2026-02-08 --snapshot-hour-utc 16 --snapshot-minute-utc 30

# Store an additional same-day snapshot series for opening-line studies
uv run python fetch_historical_odds.py 2025-10-04 2026-02-08 --snapshot-hour-utc 5 --snapshot-minute-utc 0 --snapshot-label open_9pm_pst
```

Requires a separate API key with historical access:

```bash
HISTORICAL_ODDS_API_KEY=your_key uv run python fetch_historical_odds.py 2024-10-04 2025-06-25
```

The historical endpoint is not one fixed snapshot per day. You can request different UTC times via
`--snapshot-hour-utc` / `--snapshot-minute-utc`, and the API resolves to the closest available historical snapshot
at or before that time.

If you want intraday curves (hourly or every 30 minutes), you need multiple requests per day:
- Hourly: `24 x number_of_days`
- Every 30 minutes: `48 x number_of_days`

### `backfill_snapshot_timestamps.py`

Backfills timestamp columns in existing CSVs without making API calls.

```bash
# Preview only
python3 backfill_snapshot_timestamps.py --dry-run

# Apply in place
python3 backfill_snapshot_timestamps.py
```

This can infer `snapshot_taken_at_utc` from filenames, but cannot reconstruct historical
`api_snapshot_timestamp_utc`, `bookmaker_last_update_utc`, or `response_received_at_utc`
for old files unless you re-fetch from the API.

## Setup

```bash
uv sync
```

Requires Python 3.11+.
