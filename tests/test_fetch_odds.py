from __future__ import annotations

import unittest

from fetch_odds import parse_game_odds, sport_name


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


if __name__ == "__main__":
    unittest.main()
