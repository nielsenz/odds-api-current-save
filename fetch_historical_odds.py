#!/usr/bin/env python3
"""Fetch historical NHL odds from The Odds API.

Usage:
    python fetch_historical_odds.py
    python fetch_historical_odds.py 2024-10-04 2025-06-25
    python fetch_historical_odds.py 2025-12-24 2026-02-08 --snapshot-hour-utc 16 --snapshot-minute-utc 30
"""

import csv
import os
import time
import argparse
import requests
from datetime import datetime, timedelta

API_KEY = os.environ.get("HISTORICAL_ODDS_API_KEY", "cfd75fb9867d2f369463d7577ab057b7")
BASE_URL = "https://api.the-odds-api.com/v4/historical"
SPORT = "icehockey_nhl"
MARKETS = "h2h,spreads,totals"
# Filter to BetMGM and Caesars (williamhill_us is Caesars' key in the API)
BOOKMAKER_KEYS = {"betmgm", "williamhill_us"}
BOOKMAKER_DISPLAY = {"betmgm": "betmgm", "williamhill_us": "caesars"}

# Default snapshot time: noon Eastern (17:00 UTC) to get pre-game lines
DEFAULT_SNAPSHOT_HOUR_UTC = 17
DEFAULT_SNAPSHOT_MINUTE_UTC = 0

OUTPUT_DIR = "odds-data/historical"
EXISTING_FILE_DIRS = ("odds-data/historical", "odds-data")

CSV_COLUMNS = [
    "date",
    "sport",
    "game_id",
    "commence_time",
    "snapshot_taken_at_utc",
    "api_snapshot_timestamp_utc",
    "response_received_at_utc",
    "bookmaker_last_update_utc",
    "home_team",
    "away_team",
    "bookmaker",
    "ml_home",
    "ml_away",
    "spread_home",
    "spread_home_odds",
    "spread_away",
    "spread_away_odds",
    "total_line",
    "total_over_odds",
    "total_under_odds",
]


def fetch_historical_odds(date_str, snapshot_hour_utc, snapshot_minute_utc):
    """Fetch historical odds snapshot for a given date."""
    url = f"{BASE_URL}/sports/{SPORT}/odds/"
    params = {
        "apiKey": API_KEY,
        "regions": "us",
        "markets": MARKETS,
        "oddsFormat": "american",
        "date": f"{date_str}T{snapshot_hour_utc:02d}:{snapshot_minute_utc:02d}:00Z",
    }

    response = requests.get(url, params=params)
    response.raise_for_status()

    remaining = response.headers.get("x-requests-remaining", "N/A")
    used = response.headers.get("x-requests-used", "N/A")
    response_received_at = response.headers.get("date", "")

    return response.json(), remaining, used, response_received_at


def parse_market(markets, market_key, home_team, away_team):
    """Extract odds from a specific market."""
    for market in markets:
        if market["key"] == market_key:
            outcomes = {o["name"]: o for o in market["outcomes"]}
            return outcomes
    return None


def parse_game_odds(
    game,
    bookmaker_data,
    date_str,
    snapshot_taken_at_utc,
    api_snapshot_timestamp_utc,
    response_received_at_utc,
):
    """Extract odds from a game's bookmaker data into a row dict."""
    home_team = game["home_team"]
    away_team = game["away_team"]

    markets = bookmaker_data.get("markets", [])

    # Parse moneyline (h2h)
    h2h = parse_market(markets, "h2h", home_team, away_team)
    ml_home = h2h[home_team]["price"] if h2h and home_team in h2h else ""
    ml_away = h2h[away_team]["price"] if h2h and away_team in h2h else ""

    # Parse spreads
    spreads = parse_market(markets, "spreads", home_team, away_team)
    spread_home = ""
    spread_home_odds = ""
    spread_away = ""
    spread_away_odds = ""
    if spreads:
        if home_team in spreads:
            spread_home = spreads[home_team].get("point", "")
            spread_home_odds = spreads[home_team].get("price", "")
        if away_team in spreads:
            spread_away = spreads[away_team].get("point", "")
            spread_away_odds = spreads[away_team].get("price", "")

    # Parse totals
    totals = parse_market(markets, "totals", home_team, away_team)
    total_line = ""
    total_over_odds = ""
    total_under_odds = ""
    if totals:
        if "Over" in totals:
            total_line = totals["Over"].get("point", "")
            total_over_odds = totals["Over"].get("price", "")
        if "Under" in totals:
            total_under_odds = totals["Under"].get("price", "")

    return {
        "date": date_str,
        "sport": "NHL",
        "game_id": game["id"],
        "commence_time": game["commence_time"],
        "snapshot_taken_at_utc": snapshot_taken_at_utc,
        "api_snapshot_timestamp_utc": api_snapshot_timestamp_utc,
        "response_received_at_utc": response_received_at_utc,
        "bookmaker_last_update_utc": bookmaker_data.get("last_update", ""),
        "home_team": home_team,
        "away_team": away_team,
        "bookmaker": BOOKMAKER_DISPLAY.get(bookmaker_data["key"], bookmaker_data["key"]),
        "ml_home": ml_home,
        "ml_away": ml_away,
        "spread_home": spread_home,
        "spread_home_odds": spread_home_odds,
        "spread_away": spread_away,
        "spread_away_odds": spread_away_odds,
        "total_line": total_line,
        "total_over_odds": total_over_odds,
        "total_under_odds": total_under_odds,
    }


def main():
    parser = argparse.ArgumentParser(description="Fetch historical NHL odds from The Odds API.")
    parser.add_argument("start_date", nargs="?", default="2025-10-04", help="Start date (YYYY-MM-DD)")
    parser.add_argument("end_date", nargs="?", default="2026-01-09", help="End date (YYYY-MM-DD)")
    parser.add_argument(
        "--snapshot-hour-utc",
        type=int,
        default=DEFAULT_SNAPSHOT_HOUR_UTC,
        help=f"Snapshot hour UTC (0-23). Default: {DEFAULT_SNAPSHOT_HOUR_UTC}",
    )
    parser.add_argument(
        "--snapshot-minute-utc",
        type=int,
        default=DEFAULT_SNAPSHOT_MINUTE_UTC,
        help=f"Snapshot minute UTC (0-59). Default: {DEFAULT_SNAPSHOT_MINUTE_UTC}",
    )
    parser.add_argument(
        "--snapshot-label",
        default="",
        help="Optional label to store an additional same-day snapshot (example: open_9pm_pst)",
    )
    args = parser.parse_args()

    if args.snapshot_hour_utc < 0 or args.snapshot_hour_utc > 23:
        raise ValueError("--snapshot-hour-utc must be between 0 and 23")
    if args.snapshot_minute_utc < 0 or args.snapshot_minute_utc > 59:
        raise ValueError("--snapshot-minute-utc must be between 0 and 59")
    snapshot_label = args.snapshot_label.strip()

    start_date = datetime.strptime(args.start_date, "%Y-%m-%d")
    end_date = datetime.strptime(args.end_date, "%Y-%m-%d")

    os.makedirs(OUTPUT_DIR, exist_ok=True)

    current = start_date
    total_days = (end_date - start_date).days + 1
    day_num = 0
    total_rows_written = 0
    days_skipped = 0
    days_no_games = 0

    print(f"Fetching historical NHL odds: {start_date.date()} to {end_date.date()} ({total_days} days)")
    print(f"Output directory: {OUTPUT_DIR}/")
    print(f"Bookmakers: BetMGM, Caesars")
    print(f"Markets: h2h, spreads, totals")
    print(f"Snapshot time: {args.snapshot_hour_utc:02d}:{args.snapshot_minute_utc:02d} UTC")
    print()

    while current <= end_date:
        day_num += 1
        date_str = current.strftime("%Y-%m-%d")
        filename = f"odds_{date_str}.csv" if not snapshot_label else f"odds_{date_str}_{snapshot_label}.csv"
        output_file = os.path.join(OUTPUT_DIR, filename)

        if snapshot_label:
            # Labeled mode allows multiple same-day snapshots (for CLV/open-line studies).
            # Only skip when the exact labeled file already exists.
            if os.path.exists(output_file):
                days_skipped += 1
                print(f"[{day_num}/{total_days}] {date_str} - labeled file exists, skipping")
                current += timedelta(days=1)
                continue
        else:
            # Default mode is one snapshot per day and avoids overlap with base daily pulls.
            if any(os.path.exists(os.path.join(d, f"odds_{date_str}.csv")) for d in EXISTING_FILE_DIRS):
                days_skipped += 1
                print(f"[{day_num}/{total_days}] {date_str} - already exists in tracked dirs, skipping")
                current += timedelta(days=1)
                continue

        try:
            data, remaining, used, response_received_at_utc = fetch_historical_odds(
                date_str,
                args.snapshot_hour_utc,
                args.snapshot_minute_utc,
            )
            games = data.get("data", [])
            api_snapshot_timestamp_utc = data.get("timestamp", "")
            snapshot_taken_at_utc = (
                f"{date_str}T{args.snapshot_hour_utc:02d}:{args.snapshot_minute_utc:02d}:00Z"
            )

            rows = []
            for game in games:
                for bookmaker in game.get("bookmakers", []):
                    if bookmaker["key"] in BOOKMAKER_KEYS:
                        row = parse_game_odds(
                            game,
                            bookmaker,
                            date_str,
                            snapshot_taken_at_utc,
                            api_snapshot_timestamp_utc,
                            response_received_at_utc,
                        )
                        rows.append(row)

            if rows:
                with open(output_file, "w", newline="") as f:
                    writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS)
                    writer.writeheader()
                    writer.writerows(rows)
                total_rows_written += len(rows)
                print(f"[{day_num}/{total_days}] {date_str} - {len(rows)} rows, {len(games)} games (quota remaining: {remaining})")
            else:
                days_no_games += 1
                print(f"[{day_num}/{total_days}] {date_str} - no games found (quota remaining: {remaining})")

        except requests.exceptions.HTTPError as e:
            print(f"[{day_num}/{total_days}] {date_str} - HTTP error: {e}")
        except Exception as e:
            print(f"[{day_num}/{total_days}] {date_str} - Error: {e}")

        # Rate limit: small delay between requests
        time.sleep(0.5)
        current += timedelta(days=1)

    print(f"\nDone! {total_rows_written} total rows written across {day_num - days_skipped - days_no_games} days")
    print(f"  Days skipped (already existed): {days_skipped}")
    print(f"  Days with no games: {days_no_games}")


if __name__ == "__main__":
    main()
