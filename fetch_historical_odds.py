#!/usr/bin/env python3
"""Fetch historical NHL odds from The Odds API.

Usage:
    python fetch_historical_odds.py                     # defaults: 2025-10-04 to 2026-01-09
    python fetch_historical_odds.py 2024-10-04 2025-06-25
    python fetch_historical_odds.py 2023-10-10 2024-06-25
"""

import csv
import os
import sys
import time
import requests
from datetime import datetime, timedelta

API_KEY = os.environ.get("HISTORICAL_ODDS_API_KEY", "cfd75fb9867d2f369463d7577ab057b7")
BASE_URL = "https://api.the-odds-api.com/v4/historical"
SPORT = "icehockey_nhl"
MARKETS = "h2h,spreads,totals"
# Filter to BetMGM and Caesars (williamhill_us is Caesars' key in the API)
BOOKMAKER_KEYS = {"betmgm", "williamhill_us"}
BOOKMAKER_DISPLAY = {"betmgm": "betmgm", "williamhill_us": "caesars"}

# Snapshot time: noon Eastern (17:00 UTC) to get pre-game lines
SNAPSHOT_HOUR_UTC = 17

OUTPUT_DIR = "data/historical"

CSV_COLUMNS = [
    "date",
    "sport",
    "game_id",
    "commence_time",
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


def fetch_historical_odds(date_str):
    """Fetch historical odds snapshot for a given date."""
    url = f"{BASE_URL}/sports/{SPORT}/odds/"
    params = {
        "apiKey": API_KEY,
        "regions": "us",
        "markets": MARKETS,
        "oddsFormat": "american",
        "date": f"{date_str}T{SNAPSHOT_HOUR_UTC:02d}:00:00Z",
    }

    response = requests.get(url, params=params)
    response.raise_for_status()

    remaining = response.headers.get("x-requests-remaining", "N/A")
    used = response.headers.get("x-requests-used", "N/A")

    return response.json(), remaining, used


def parse_market(markets, market_key, home_team, away_team):
    """Extract odds from a specific market."""
    for market in markets:
        if market["key"] == market_key:
            outcomes = {o["name"]: o for o in market["outcomes"]}
            return outcomes
    return None


def parse_game_odds(game, bookmaker_data, date_str):
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
    if len(sys.argv) >= 3:
        start_date = datetime.strptime(sys.argv[1], "%Y-%m-%d")
        end_date = datetime.strptime(sys.argv[2], "%Y-%m-%d")
    else:
        start_date = datetime(2025, 10, 4)
        end_date = datetime(2026, 1, 9)

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
    print()

    while current <= end_date:
        day_num += 1
        date_str = current.strftime("%Y-%m-%d")
        output_file = os.path.join(OUTPUT_DIR, f"odds_{date_str}.csv")

        # Skip if file already exists (resumable)
        if os.path.exists(output_file):
            days_skipped += 1
            print(f"[{day_num}/{total_days}] {date_str} - already exists, skipping")
            current += timedelta(days=1)
            continue

        try:
            data, remaining, used = fetch_historical_odds(date_str)
            games = data.get("data", [])

            rows = []
            for game in games:
                for bookmaker in game.get("bookmakers", []):
                    if bookmaker["key"] in BOOKMAKER_KEYS:
                        row = parse_game_odds(game, bookmaker, date_str)
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
