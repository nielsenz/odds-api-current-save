# Odds API

Collects NHL and NBA betting odds from [The Odds API](https://the-odds-api.com/), including daily forward-looking lines and historical data.

## Data

### Daily odds (`data/`)

A GitHub Actions workflow runs daily at 4 PM UTC and commits a CSV file (`odds_YYYY-MM-DD.csv`) with that day's lines for all NHL and NBA games. Collection started January 10, 2026.

### Historical odds (`data/historical/`)

Pre-game snapshots (noon ET / 17:00 UTC) for NHL games, fetched from The Odds API's historical endpoint. Current coverage:

| Season  | Date Range                    | Files |
|---------|-------------------------------|-------|
| 2023-24 | Oct 10, 2023 - Jun 25, 2024  | 260   |
| 2024-25 | Oct 4, 2024 - Jun 25, 2025   | 265   |
| 2025-26 | Oct 4, 2025 - Jan 9, 2026    | 97    |

### CSV format

Both daily and historical files share the same schema:

```
date, sport, game_id, commence_time, home_team, away_team, bookmaker,
ml_home, ml_away, spread_home, spread_home_odds, spread_away,
spread_away_odds, total_line, total_over_odds, total_under_odds
```

- Bookmakers: BetMGM, Caesars
- Markets: moneyline (h2h), spreads, totals
- Odds format: American

## Scripts

### `fetch_odds.py`

Fetches current-day odds for NHL and NBA. Used by the GitHub Actions workflow.

```bash
ODDS_API_KEY=your_key uv run python fetch_odds.py
```

### `fetch_historical_odds.py`

Fetches historical NHL odds for a date range. Resumable (skips dates with existing files).

```bash
# Default: 2025-26 season pre-collection gap
uv run python fetch_historical_odds.py

# Specific date range
uv run python fetch_historical_odds.py 2023-10-10 2024-06-25
```

Requires a separate API key with historical access:

```bash
HISTORICAL_ODDS_API_KEY=your_key uv run python fetch_historical_odds.py 2024-10-04 2025-06-25
```

## Setup

```bash
uv sync
```

Requires Python 3.11+.
