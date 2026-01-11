#!/usr/bin/env python3
"""Fetch daily betting lines from Odds API for NHL and NBA."""

import csv
import os
import sys
import requests
from datetime import datetime

API_KEY = os.environ.get("ODDS_API_KEY", "80debdc11ce820b8f41822eb502d42f7")
BASE_URL = "https://api.the-odds-api.com/v4"
SPORTS = ["icehockey_nhl", "basketball_nba"]
BOOKMAKERS = "betmgm,caesars"
MARKETS = "h2h,spreads,totals"

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

    return response.json()


def parse_market(markets, market_key, home_team, away_team):
    """Extract odds from a specific market."""
    for market in markets:
        if market["key"] == market_key:
            outcomes = {o["name"]: o for o in market["outcomes"]}
            return outcomes
    return None


def parse_game_odds(game, bookmaker_data, today_str):
    """Extract odds from a game's bookmaker data into a row dict."""
    home_team = game["home_team"]
    away_team = game["away_team"]
    sport_key = game["sport_key"]
    sport_name = "NHL" if "nhl" in sport_key else "NBA"

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
    today = datetime.now()
    today_str = today.strftime("%Y-%m-%d")

    # Ensure data directory exists
    os.makedirs("data", exist_ok=True)
    output_file = f"data/odds_{today_str}.csv"

    print(f"Fetching odds for {today_str}...")

    all_rows = []

    for sport in SPORTS:
        sport_name = "NHL" if "nhl" in sport else "NBA"
        print(f"\nFetching {sport_name} odds...")

        try:
            games = fetch_odds(sport)
            print(f"  Found {len(games)} games")

            for game in games:
                for bookmaker in game.get("bookmakers", []):
                    row = parse_game_odds(game, bookmaker, today_str)
                    all_rows.append(row)

        except requests.exceptions.HTTPError as e:
            print(f"  Error fetching {sport_name}: {e}")
        except Exception as e:
            print(f"  Unexpected error for {sport_name}: {e}")

    if all_rows:
        with open(output_file, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS)
            writer.writeheader()
            writer.writerows(all_rows)

        print(f"\nWrote {len(all_rows)} rows to {output_file}")
    else:
        print("\nNo odds data found.")


if __name__ == "__main__":
    main()
