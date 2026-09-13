import importlib.util
from pathlib import Path
from datetime import datetime,timezone
import tempfile
import unittest
from unittest.mock import patch

spec=importlib.util.spec_from_file_location('totals_capture',Path(__file__).with_name('totals_capture.py'));capture=importlib.util.module_from_spec(spec);spec.loader.exec_module(capture)

class CaptureTests(unittest.TestCase):
    def test_naive_timestamp_rejected(self):
        with self.assertRaises(ValueError):capture.stamp('2026-09-12T15:00:00')
    def test_utc_window(self):
        for hour,minute,expected in [(14,59,'early'),(15,4,'early'),(15,5,'capture'),(15,19,'capture'),(15,20,'missed')]:self.assertEqual(capture.phase(datetime(2026,9,12,hour,minute,tzinfo=timezone.utc)),expected)
    def test_pairing_and_asof(self):
        payload={'timestamp':'2026-09-12T14:55:00Z','data':[{'id':'g','commence_time':'2026-09-12T23:00:00Z','home_team':'A','away_team':'B','bookmakers':[{'key':'williamhill_us','last_update':'2026-09-12T14:54:00Z','markets':[{'key':'totals','outcomes':[{'name':'Over','point':6,'price':-110},{'name':'Under','point':6,'price':100},{'name':'Over','point':6.5,'price':110}]}]}]}]}
        now=capture.stamp('2026-09-12T15:07:00Z');rows,games=capture.normalize(payload,capture.stamp('2026-09-12T15:00:00Z'),now);self.assertEqual(len(rows),1);self.assertEqual(rows[0]['bookmaker'],'caesars');self.assertEqual(rows[0]['line'],6)
        payload['timestamp']='2026-09-12T15:01:00Z'
        with self.assertRaises(ValueError):capture.normalize(payload,capture.stamp('2026-09-12T15:00:00Z'),now)
    def test_missed_does_not_fetch(self):
        with tempfile.TemporaryDirectory() as tmp,patch.object(capture,'fetch') as fetch:
            result=capture.collect(Path(tmp),'capture',capture.stamp('2026-09-12T16:00:00Z'));self.assertEqual(result['status'],'missed_window');fetch.assert_not_called();self.assertFalse(result['prospective_capture'])
    def test_failure_is_credential_safe(self):
        with tempfile.TemporaryDirectory() as tmp,patch.object(capture,'fetch',side_effect=RuntimeError('secret-token')):
            result=capture.collect(Path(tmp),'probe',capture.stamp('2026-09-12T16:00:00Z'));self.assertEqual(result['status'],'failed');self.assertNotIn('secret-token',str(result))
    def test_empty_and_immutable(self):
        payload={'timestamp':'2026-09-12T14:55:00Z','data':[]}
        with tempfile.TemporaryDirectory() as tmp,patch.object(capture,'fetch',return_value=(payload,{})) as fetch:
            result=capture.collect(Path(tmp),'capture',capture.stamp('2026-09-12T15:07:00Z'));self.assertEqual(result['status'],'no_totals_returned');self.assertEqual(capture.collect(Path(tmp),'capture',capture.stamp('2026-09-12T15:08:00Z')),result);self.assertEqual(fetch.call_count,1)

if __name__=='__main__':unittest.main()
