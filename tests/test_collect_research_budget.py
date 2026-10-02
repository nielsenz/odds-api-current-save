import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import urllib.error

from collect_research_budget import Capture


class Response:
    status = 200
    headers = {'x-requests-last': '10', 'x-requests-remaining': '5000'}

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass

    def read(self):
        return json.dumps({'timestamp': '2025-01-01T14:55:00Z', 'data': [{
            'id': 'event', 'sport_key': 'sport', 'commence_time': '2025-01-01T20:00:00Z',
            'home_team': 'Home', 'away_team': 'Away', 'bookmakers': [{
                'key': 'book', 'last_update': '2025-01-01T14:54:00Z', 'markets': [{
                    'key': 'spreads', 'outcomes': [{'name': 'Home', 'point': -3.5, 'price': -115}]
                }]
            }]
        }]}).encode()


class BudgetTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.root = Path(self.directory.name)
        self.params = {'date': '2025-01-01T15:00:00Z', 'markets': 'spreads'}

    def tearDown(self):
        self.directory.cleanup()

    def capture(self, budget=20):
        return Capture(self.root, 'private-test-key', budget)

    def test_budget_rejects_call_before_network(self):
        cap = self.capture(9)
        with patch('urllib.request.urlopen') as network:
            self.assertIsNone(cap.get('historical/test', self.params, 'pilot', 10))
            network.assert_not_called()

    def test_account_reserve_rejects_call(self):
        cap = self.capture(); cap.remaining = 1009
        with patch('urllib.request.urlopen') as network:
            self.assertIsNone(cap.get('historical/test', self.params, 'pilot', 10))
            network.assert_not_called()

    def test_resume_reuses_raw_without_spending_and_keeps_price(self):
        cap = self.capture()
        with patch('urllib.request.urlopen', return_value=Response()) as network, patch('time.sleep'):
            first = cap.get('historical/test', self.params, 'pilot', 10)
            second = self.capture().get('historical/test', self.params, 'pilot', 10)
            self.assertEqual(first, second)
            self.assertEqual(network.call_count, 1)
        resumed = self.capture()
        self.assertEqual(resumed.spent, 10)
        self.assertEqual(resumed.remaining, 5000)
        with contextlib.redirect_stdout(io.StringIO()): resumed.export()
        text = (self.root / 'outcomes.csv').read_text()
        self.assertIn('-3.5,-115,True', text)
        self.assertIn('2025-01-01T14:55:00Z', text)
        self.assertNotIn('private-test-key', resumed.journal.read_text())

    def test_auth_error_stops_and_does_not_log_secret_url(self):
        cap = self.capture()
        error = urllib.error.HTTPError('https://example/?apiKey=private-test-key', 401, 'Unauthorized', {}, None)
        with patch('urllib.request.urlopen', side_effect=error), patch('time.sleep'), contextlib.redirect_stdout(io.StringIO()):
            with self.assertRaisesRegex(RuntimeError, '401'):
                cap.get('historical/test', self.params, 'pilot', 10)
        self.assertNotIn('private-test-key', cap.journal.read_text())
        self.assertEqual(cap.records[0]['status'], 401)

    def test_actual_cost_is_used_in_budget(self):
        cap = self.capture(10)
        with patch('urllib.request.urlopen', return_value=Response()), patch('time.sleep'):
            cap.get('historical/test', self.params, 'pilot', 1)
        with patch('urllib.request.urlopen') as network:
            self.assertIsNone(cap.get('historical/other', self.params, 'pilot', 1))
            network.assert_not_called()

    def test_effective_snapshot_after_requested_is_rejected(self):
        cap = self.capture()
        with patch('urllib.request.urlopen', return_value=Response()), patch('time.sleep'):
            with self.assertRaisesRegex(ValueError, 'later than requested'):
                cap.get('historical/test', {'date': '2025-01-01T14:00:00Z'}, 'pilot', 10)
        self.assertEqual(self.capture().spent, 10)
        self.assertEqual(cap.records[0]['status'], 'invalid_effective_snapshot')
        with self.assertRaisesRegex(ValueError, 'Cached historical'):
            self.capture().get('historical/test', {'date': '2025-01-01T14:00:00Z'}, 'pilot', 10)

    def test_late_market_update_is_preserved_but_marked_unsafe(self):
        class Late(Response):
            def read(self):
                data = json.loads(super().read())
                data['data'][0]['bookmakers'][0]['markets'][0]['last_update'] = '2025-01-01T15:01:00Z'
                return json.dumps(data).encode()
        cap = self.capture()
        with patch('urllib.request.urlopen', return_value=Late()), patch('time.sleep'):
            cap.get('historical/test', self.params, 'pilot', 10)
        with contextlib.redirect_stdout(io.StringIO()): cap.export()
        import csv
        with (self.root / 'outcomes.csv').open() as f:
            row = next(csv.DictReader(f))
        self.assertEqual(row['market_update'], '2025-01-01T15:01:00Z')
        self.assertEqual(row['pre_start'], 'True')
        self.assertEqual(row['requested_cutoff_safe'], 'False')
        self.assertEqual(row['vendor_snapshot_consistent'], 'False')


if __name__ == '__main__':
    unittest.main()
