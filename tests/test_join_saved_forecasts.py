import importlib.util
from pathlib import Path
import sys
import unittest
import csv
import gzip
import json
import tempfile
import contextlib
import io
from unittest.mock import patch
from dataclasses import replace

spec = importlib.util.spec_from_file_location('saved_join', Path(__file__).parents[1]/'research/join_saved_forecasts.py')
j = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = j
spec.loader.exec_module(j)

class SavedForecastJoinTests(unittest.TestCase):
    def forecast(self, **kwargs):
        base = dict(model='model', sport='americanfootball_nfl', game_id='native', date='2025-09-08', home='KC', away='BUF', market='spreads', prediction=6.0, actual=3.0)
        return j.Forecast(**(base | kwargs))

    def quote(self, **kwargs):
        return dict(sport='americanfootball_nfl', event_id='vendor', commence_time='2025-09-09T00:30:00Z', home_team='Kansas City Chiefs', away_team='Buffalo Bills', market='spreads', outcome='Kansas City Chiefs', point='-3', price='-110', description='', requested_snapshot='2025-09-08T15:00:00Z', retrieved_at='2026-10-02T00:00:00Z', requested_cutoff_safe='True', vendor_snapshot_consistent='True') | kwargs

    def test_eastern_date_and_abbreviations(self):
        f=self.forecast()
        self.assertEqual(j.Join([f]).match(self.quote()), ([f], 'matched'))

    def test_excluded_forecast_retained_but_never_joined(self):
        f=self.forecast(basis='excluded_training_cutoff_unverified')
        self.assertEqual(j.Join([f]).match(self.quote()),([], 'no_saved_forecast'))

    def test_vendor_identity_does_not_override_home_away(self):
        f=self.forecast(game_id='vendor',home='BUF',away='KC')
        self.assertEqual(j.Join([f]).match(self.quote()), ([], 'home_away_mismatch'))

    def test_kickoff_mismatch_rejected(self):
        f=self.forecast(game_id='vendor',commence_time='2025-09-10T00:30:00Z')
        self.assertEqual(j.Join([f]).match(self.quote())[1], 'kickoff_mismatch')

    def test_player_alias_suffix_and_ambiguity(self):
        f=self.forecast(market='player_receptions',player_id='id',subject='John Smith Jr.')
        q=self.quote(market='player_receptions',description='John Smith',outcome='Over',point='3.5')
        self.assertEqual(j.Join([f]).match(q)[0],[f])
        other=replace(f,player_id='id2')
        self.assertEqual(j.Join([f,other]).match(q)[1], 'ambiguous_player_or_game')

    def test_multiple_models_retained_but_duplicate_identity_rejected(self):
        f=self.forecast(); other=replace(f,model='other')
        self.assertEqual(len(j.Join([f,other]).match(self.quote())[0]),2)
        with self.assertRaises(ValueError):j.Join([f,f])

    def test_spread_sign_and_push(self):
        f=self.forecast()
        home=j.compare(f,self.quote());away=j.compare(f,self.quote(outcome='Buffalo Bills',point='3'))
        self.assertEqual(home['model_difference'],3)
        self.assertEqual(away['model_difference'],-3)
        self.assertEqual(home['statistic_result'],'push')
        self.assertIsNone(home['wager_profit'])

    def test_total_and_prop_signs(self):
        f=self.forecast(market='player_receptions',prediction=5,actual=4,player_id='id')
        q=self.quote(market='player_receptions',outcome='Under',point='4.5')
        r=j.compare(f,q)
        self.assertEqual(r['model_difference'],-.5)
        self.assertEqual(r['statistic_result'],'win')
        self.assertEqual(r['settlement_status'],'statistic_only_action_unknown')

    def test_no_capture_clock_is_not_prospective(self):
        r=j.compare(self.forecast(),self.quote())
        self.assertFalse(r['forecast_precedes_quote'])
        self.assertTrue(r['strict_quote_timing'])

    def test_late_quote_and_poststart_excluded(self):
        f=self.forecast(captured_at='2025-09-08T16:00:00Z')
        r=j.compare(f,self.quote(vendor_snapshot_consistent='False'))
        self.assertFalse(r['strict_quote_timing']);self.assertFalse(r['forecast_precedes_quote'])
        r=j.compare(f,self.quote(requested_snapshot='2025-09-09T00:31:00Z'))
        self.assertFalse(r['quote_prestart']);self.assertFalse(r['strict_quote_timing'])

    def test_moneyline_probability_orientation(self):
        r=j.compare(self.forecast(market='h2h',prediction=.6,actual=1),self.quote(market='h2h',outcome='Buffalo Bills',point='',price='150'))
        self.assertEqual(r['model_probability'],.4)
        self.assertEqual(r['price_implied_probability'],.4)
        self.assertEqual(r['statistic_result'],'loss')

    def test_future_team_identity_and_probability(self):
        sport='americanfootball_nfl_super_bowl_winner'
        f=self.forecast(sport=sport,home='',away='',market='outrights',date='2027-02-14',subject='KC',prediction=.1,actual=None)
        q=self.quote(sport=sport,home_team='',away_team='',market='outrights',commence_time='2027-02-14T23:35:00Z',point='',price='900')
        self.assertEqual(j.Join([f]).match(q)[0],[f])
        r=j.compare(f,q)
        self.assertEqual(r['model_probability'],.1)
        self.assertEqual(r['settlement_status'],'unresolved_future_event')
        self.assertEqual(r['statistic_result'],'')

    def test_export_keeps_full_quote_and_forecast_denominators(self):
        f=self.forecast(); other=replace(f,model='other'); missing=replace(f,game_id='missing',date='2025-09-12')
        with tempfile.TemporaryDirectory() as tmp:
            base=Path(tmp); odds=base/'odds.csv'; output=base/'output'
            quotes=[self.quote(), self.quote(event_id='unknown',commence_time='2025-09-11T00:30:00Z'), self.quote(price='130')]
            with odds.open('w',newline='') as stream:
                writer=csv.DictWriter(stream,fieldnames=list(quotes[0]));writer.writeheader();writer.writerows(quotes)
            with patch.object(j,'load_forecasts',return_value=([f,other,missing],{},[],{})), patch.object(sys,'argv',['join','--sports-home',tmp,'--odds',str(odds),'--out',str(output)]), contextlib.redirect_stdout(io.StringIO()):
                j.main()
            summary=json.loads((output/'summary.json').read_text())
            self.assertEqual(summary['odds_rows'],3)
            self.assertEqual(summary['matched_odds_rows'],2)
            self.assertEqual(summary['unmatched_odds_rows'],1)
            with gzip.open(output/'joined_quotes.csv.gz','rt') as stream:
                result=list(csv.DictReader(stream))
            self.assertEqual(len(result),5)
            self.assertEqual(sum(r['join_status']=='no_saved_forecast' for r in result),1)
            self.assertEqual(summary['conflicting_price_quote_identities'],1)
            self.assertTrue(all(r['quote_price_conflict']=='True' and r['comparison_quote_eligible']=='False' for r in result if r['model']))
            with gzip.open(output/'unmatched_forecasts.csv.gz','rt') as stream:
                self.assertEqual([r['game_id'] for r in csv.DictReader(stream)],['missing'])

    def test_malformed_quotes_fail_explicitly(self):
        with self.assertRaises(ValueError):j.compare(self.forecast(),self.quote(point=''))
        with self.assertRaises(ValueError):j.compare(self.forecast(),self.quote(outcome='Unknown'))
        with self.assertRaises(ValueError):j.stamp('2025-09-08T12:00:00')

if __name__=='__main__':unittest.main()
