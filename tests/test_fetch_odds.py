from __future__ import annotations

import unittest

from datetime import datetime, timezone

from fetch_odds import MARKETS, markets_for, parse_game_odds, sport_name, upcoming_events


class FetchOddsTests(unittest.TestCase):
    def test_stable_sport_labels(self) -> None:
        self.assertEqual(sport_name("americanfootball_nfl"), "NFL")
        self.assertEqual(sport_name("americanfootball_ncaaf"), "CFB")
        self.assertEqual(sport_name("basketball_wnba"), "WNBA")
        self.assertEqual(sport_name("basketball_ncaab"), "NCAAB")

    def test_football_row_uses_short_sport_label(self) -> None:
        game = {
            "id": "game-1",
            "sport_key": "americanfootball_ncaaf",
            "commence_time": "2026-08-20T00:00:00Z",
            "home_team": "Home",
            "away_team": "Away",
        }
        bookmaker = {
            "key": "example",
            "last_update": "2026-08-13T15:47:00Z",
            "markets": [],
        }
        row = parse_game_odds(
            game,
            bookmaker,
            "2026-08-13",
            "2026-08-13T15:47:00Z",
            "Thu, 13 Aug 2026 15:47:00 GMT",
        )
        self.assertEqual(row["sport"], "CFB")

    def test_per_sport_markets(self) -> None:
        env = {"ODDS_MARKETS_ICEHOCKEY_NHL": "h2h"}
        self.assertEqual(markets_for("icehockey_nhl", env), "h2h")
        self.assertEqual(markets_for("basketball_wnba", env), MARKETS)

    def test_upcoming_events_skip_started_and_far(self) -> None:
        now = datetime(2026, 10, 16, 2, 0, tzinfo=timezone.utc)
        events = [{"commence_time": "2026-10-16T01:00:00Z"},   # started
                  {"commence_time": "2026-10-16T03:30:00Z"},   # within 3h
                  {"commence_time": "2026-10-17T00:00:00Z"}]   # tomorrow
        self.assertEqual(len(upcoming_events(events, now, 3)), 1)
        self.assertEqual(len(upcoming_events(events[:1], now, 3)), 0)
        self.assertEqual(len(upcoming_events(events, now, 36)), 2)


if __name__ == "__main__":
    unittest.main()
