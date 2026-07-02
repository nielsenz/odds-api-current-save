#!/usr/bin/env python3
"""Fetch NHL betting line snapshots from The Odds API."""

import csv
import os
import sys
import requests
from datetime import datetime

API_KEY = os.environ.get("ODDS_API_KEY", "")
HEARTBEAT_FILE = "data/heartbeat.csv"
HEARTBEAT_COLUMNS = [
    "run_at_utc",
    "snapshot_label",
    "sport",
    "games",
    "rows",
    "error",
    "quota_used",
    "quota_remaining",
]
BASE_URL = "https://api.the-odds-api.com/v4"
SPORTS = ["icehockey_nhl", "basketball_wnba"]
# Sharp + square coverage for the sharp_vs_square filter used by the WNBA
# consensus tracker (see wnba/analysis/cover/eda/MULTI_BOOK_DISPERSION_RESULTS.md).
# Adding bookmakers to a single regions/markets call does not multiply API quota cost.
BOOKMAKERS = "betmgm,caesars,fanduel,draftkings,betrivers"
MARKETS = "h2h,spreads,totals"

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


def fetch_odds(sport):
    """Fetch odds for a sport from the Odds API."""
    url = f"{BASE_URL}/sports/{sport}/odds/"
    params = {
        "apiKey": API_KEY,
        "regions": "us",
        "markets": MARKETS,
        "bookmakers": BOOKMAKERS,
        "oddsFormat": "american",
    }

    response = requests.get(url, params=params)
    response.raise_for_status()

    # Print quota info from headers
    remaining = response.headers.get("x-requests-remaining", "N/A")
    used = response.headers.get("x-requests-used", "N/A")
    print(f"  API quota - Used: {used}, Remaining: {remaining}")

    response_received_at = response.headers.get("date", "")
    return response.json(), response_received_at, used, remaining


def redact_key(text):
    """Strip the API key from error text before it hits logs or the committed heartbeat."""
    return str(text).replace(API_KEY, "***") if API_KEY else str(text)


def append_heartbeat(rows):
    """Record every run's outcome so silent failures are impossible.

    The June 12-30 2026 outage (quota 401s swallowed for 19 days, losing the
    Cup Final closes) motivated this: the heartbeat commits on every run, so a
    day with no odds files but a heartbeat row showing an error is
    distinguishable from the collector simply not running.
    """
    os.makedirs("data", exist_ok=True)
    write_header = not os.path.exists(HEARTBEAT_FILE)
    with open(HEARTBEAT_FILE, "a", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=HEARTBEAT_COLUMNS)
        if write_header:
            writer.writeheader()
        writer.writerows(rows)


def parse_market(markets, market_key, home_team, away_team):
    """Extract odds from a specific market."""
    for market in markets:
        if market["key"] == market_key:
            outcomes = {o["name"]: o for o in market["outcomes"]}
            return outcomes
    return None


def parse_game_odds(game, bookmaker_data, today_str, snapshot_taken_at_utc, response_received_at_utc):
    """Extract odds from a game's bookmaker data into a row dict."""
    home_team = game["home_team"]
    away_team = game["away_team"]
    sport_key = game["sport_key"]
    if "wnba" in sport_key:
        sport_name = "WNBA"
    elif "nhl" in sport_key:
        sport_name = "NHL"
    elif "nba" in sport_key:
        sport_name = "NBA"
    else:
        sport_name = sport_key.upper()

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
        "date": today_str,
        "sport": sport_name,
        "game_id": game["id"],
        "commence_time": game["commence_time"],
        "snapshot_taken_at_utc": snapshot_taken_at_utc,
        "api_snapshot_timestamp_utc": "",
        "response_received_at_utc": response_received_at_utc,
        "bookmaker_last_update_utc": bookmaker_data.get("last_update", ""),
        "home_team": home_team,
        "away_team": away_team,
        "bookmaker": bookmaker_data["key"],
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
    """Main entry point."""
    if not API_KEY:
        print("ERROR: ODDS_API_KEY is not set (the hardcoded fallback key was removed).")
        sys.exit(1)
    today = datetime.utcnow()
    today_str = today.strftime("%Y-%m-%d")
    fetched_at_utc = today.strftime("%Y%m%dT%H%M%SZ")
    snapshot_taken_at_utc = today.strftime("%Y-%m-%dT%H:%M:%SZ")
    snapshot_label = os.environ.get("ODDS_SNAPSHOT_LABEL", "snapshot").strip().lower()
    if not snapshot_label:
        snapshot_label = "snapshot"

    # Ensure data directory exists
    os.makedirs("data", exist_ok=True)
    output_file = f"data/odds_{today_str}_{snapshot_label}_{fetched_at_utc}.csv"

    print(f"Fetching odds for {today_str} ({snapshot_label})...")

    all_rows = []
    heartbeat_rows = []
    errors = []

    for sport in SPORTS:
        sport_name = "NHL" if "nhl" in sport else sport.upper()
        print(f"\nFetching {sport_name} odds...")

        sport_rows = 0
        n_games = 0
        error_text = ""
        quota_used = ""
        quota_remaining = ""
        try:
            games, response_received_at_utc, quota_used, quota_remaining = fetch_odds(sport)
            n_games = len(games)
            print(f"  Found {n_games} games")

            for game in games:
                for bookmaker in game.get("bookmakers", []):
                    row = parse_game_odds(
                        game,
                        bookmaker,
                        today_str,
                        snapshot_taken_at_utc,
                        response_received_at_utc,
                    )
                    all_rows.append(row)
                    sport_rows += 1

        except requests.exceptions.HTTPError as e:
            error_text = redact_key(f"HTTPError: {e}")
            print(f"  Error fetching {sport_name}: {error_text}")
        except Exception as e:
            error_text = redact_key(f"{type(e).__name__}: {e}")
            print(f"  Unexpected error for {sport_name}: {error_text}")

        if error_text:
            errors.append(f"{sport_name}: {error_text}")
        heartbeat_rows.append({
            "run_at_utc": snapshot_taken_at_utc,
            "snapshot_label": snapshot_label,
            "sport": sport_name,
            "games": n_games,
            "rows": sport_rows,
            "error": error_text,
            "quota_used": quota_used,
            "quota_remaining": quota_remaining,
        })

    append_heartbeat(heartbeat_rows)

    if all_rows:
        with open(output_file, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS)
            writer.writeheader()
            writer.writerows(all_rows)

        print(f"\nWrote {len(all_rows)} rows to {output_file}")
    else:
        print("\nNo odds data found.")

    if errors:
        # Fail the run loudly: a scheduled-workflow failure emails the repo
        # owner, whereas the old swallow-and-exit-0 path hid a 19-day outage.
        print(f"\nFAILED: {len(errors)} sport fetch error(s):")
        for err in errors:
            print(f"  - {err}")
        sys.exit(1)


if __name__ == "__main__":
    main()
