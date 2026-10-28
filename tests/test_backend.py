import unittest,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from backend import normalize_air,extract_forecasts,assess

class Tests(unittest.TestCase):
 def test_psi(self):
  data={'items':[{'timestamp':'2026-10-28T05:00:00Z','readings':{'psi_twenty_four_hourly':{'north':78,'south':-1,'east':'bad'}}}]}
  df=normalize_air(data,'PSI')
  self.assertEqual(len(df),1)
  self.assertEqual(df.iloc[0]['value'],78)
 def test_forecast(self):
  data={'items':[{'forecasts':[{'date':'2026-10-29','forecast':'Thundery showers','temperature':{'low':25,'high':31}}]}]}
  self.assertEqual(extract_forecasts(data).iloc[0]['temp_high'],31)
 def test_stale(self):
  self.assertEqual(assess(70,10,120)[0],'DATA UNAVAILABLE / STALE')
 def test_missing(self):
  self.assertEqual(assess(None,10,10)[0],'INCOMPLETE DATA')
if __name__=='__main__':unittest.main()
