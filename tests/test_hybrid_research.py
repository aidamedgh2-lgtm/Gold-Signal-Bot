import unittest
import hybrid_research as h

def bar(o, hi, lo, c, t):
    return {"open":o,"high":hi,"low":lo,"close":c,"time":str(t)}

class HybridResearchTests(unittest.TestCase):
    def test_bullish_mss_requires_close_above_prior_swing_and_recent_zone_touch(self):
        bars=[bar(100,101,99,100,i) for i in range(8)]
        bars[-2]=bar(99,100,98,99,6)
        bars[-1]=bar(100,103,99.5,102,7)
        zone={"direction":"DEMAND","low":98.5,"high":100.5}
        self.assertEqual(h.mss_confirmation(bars,zone),"M1 bullish MSS")

    def test_mss_rejects_break_without_prior_zone_touch(self):
        bars=[bar(100,101,99,100,i) for i in range(8)]
        bars[-1]=bar(100,103,100,102,7)
        zone={"direction":"DEMAND","low":95,"high":96}
        self.assertIsNone(h.mss_confirmation(bars,zone))

    def test_atr_series_uses_only_data_available_at_each_index(self):
        bars=[bar(100,101,99,100,i) for i in range(20)]
        values=h.build_atr_series(bars,14)
        self.assertIsNone(values[13])
        self.assertEqual(values[14],2)
        changed=bars[:15]+[bar(100,200,1,150,i) for i in range(15,20)]
        self.assertEqual(values[14],h.build_atr_series(changed,14)[14])


    def test_zone_is_not_consumed_when_trade_cannot_be_created(self):
        state={"seen":set(),"trades":[],"last_exit":-1}
        key=("H1","DEMAND",2300.0,2305.0,"2026-11-27")
        self.assertFalse(h.commit_trade(state,key,None))
        self.assertNotIn(key,state["seen"])
        self.assertEqual(state["trades"],[])

    def test_zone_is_consumed_only_after_valid_trade_is_created(self):
        state={"seen":set(),"trades":[],"last_exit":-1}
        key=("H1","DEMAND",2300.0,2305.0,"2026-11-27")
        trade={"exit_index":42,"net_r":1.2}
        self.assertTrue(h.commit_trade(state,key,trade))
        self.assertIn(key,state["seen"])
        self.assertEqual(state["trades"],[trade])
        self.assertEqual(state["last_exit"],42)

    def test_m5_candle_end_is_five_minutes(self):
        import supply_demand_backtest as bt
        start=bt.parse_time("2026-11-27 10:00:00")
        self.assertEqual(bt.candle_end(start,"5min").isoformat(),"2026-11-27T10:05:00+00:00")

    def test_m1_candle_end_is_one_minute(self):
        import supply_demand_backtest as bt
        start=bt.parse_time("2026-11-27 10:00:00")
        self.assertEqual(bt.candle_end(start,"1min").isoformat(),"2026-11-27T10:01:00+00:00")

    def test_m5_alignment_requires_directional_close(self):
        bars=[bar(99,101,98,100,0),bar(100,102,99,101,1),bar(101,103,100,102,2)]
        self.assertTrue(h.directional_m5_alignment(bars,"BUY"))
        self.assertFalse(h.directional_m5_alignment(bars,"SELL"))

if __name__ == "__main__":
    unittest.main()
