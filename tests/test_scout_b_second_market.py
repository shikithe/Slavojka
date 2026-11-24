"""Ticket B can select verified 3+ goals as 1st or 2nd value market.

No real bets, tickets, payouts, or repo publication in this test.
"""
import unittest
from datetime import datetime, timezone, timedelta
from unittest.mock import patch

from lista.scout_value import apply_value_model
from lista.scout_six_markets import suggestions, detailed_ai_handoff

NOW = datetime(2026, 11, 24, 11, 0, tzinfo=timezone.utc)
KEYS = ("1", "X", "2", "3+", "GG", "NG")


def markets(over_score=39, over_ev=8, top="GG", top_odds=1.82):
    values = {}
    for market in KEYS:
        values[market] = dict(score=8, odds=2.0,
                              adjusted_probability_pct=60,
                              conservative_ev_pct=2)
    values[top] = dict(score=45, odds=top_odds,
                        adjusted_probability_pct=65,
                        conservative_ev_pct=10)
    values["3+"] = dict(score=over_score, odds=1.63,
                          adjusted_probability_pct=65,
                          conservative_ev_pct=over_ev)
    if top == "3+":
        values["3+"]["score"] = 47
        values["3+"]["odds"] = 1.55
        values["3+"]["conservative_ev_pct"] = 7
    return values


def fixture(fid, first="GG", at=None):
    prices={k:2.0 for k in KEYS}
    prices.update({"GG":1.82,"3+":1.63})
    return {
        "fixture_id":str(fid),"league":"eng.1",
        "match":f"Home{fid} - Away{fid}",
        "datetime":(at or (NOW+timedelta(hours=8))).isoformat(),
        "probability_pct":{k:60 for k in KEYS},
        "odds":prices, "strongest_market":first, "second_market":"3+",
        "strongest_odds":prices[first], "estimated_goals":{"home":2.1,"away":1.4},
        "strongest_pct":70,"second_pct":68,"third_pct":55,
        "evidence":{"home_last_matches":5,"away_last_matches":5,
                    "league_unique_result_matches":32},
    }


class SecondaryThreePlusTests(unittest.TestCase):
    def score(self, fixture_row, values):
        with patch("lista.scout_value.market_evaluation", return_value=values):
            result=apply_value_model([fixture_row], {"leagues":{}}, NOW)
        return result[0]

    def test_b_second_market_uses_own_3plus_odd_probability_and_ev(self):
        r=self.score(fixture("a"), markets())
        self.assertEqual(r["recommended_market"],"GG")
        self.assertTrue(r["candidate_A"])
        self.assertTrue(r["candidate_B"])
        self.assertEqual(r["b_market_rank"],2)
        self.assertEqual(r["b_market"],"3+")
        self.assertEqual(r["b_odds"],1.63)
        self.assertEqual(r["b_conservative_ev_pct"],8)

    def test_b_still_accepts_3plus_as_first_market(self):
        r=self.score(fixture("b"), markets(top="3+"))
        self.assertTrue(r["candidate_B"])
        self.assertEqual(r["b_market_rank"],1)

    def test_second_market_with_negative_ev_must_not_be_accepted(self):
        r=self.score(fixture("c"), markets(over_ev=-3))
        self.assertTrue(r["candidate_A"])
        self.assertFalse(r["candidate_B"])

    def test_3plus_third_market_is_ineligible_even_with_positive_ev(self):
        price=markets(over_score=30)
        price["2"]=dict(score=41,odds=2.5,adjusted_probability_pct=55,
                        conservative_ev_pct=4)
        r=self.score(fixture("d"),price)
        self.assertEqual(r["b_market_rank"],3)
        self.assertFalse(r["candidate_B"])

    def test_b_only_market_can_qualify_without_approval_for_a(self):
        r=self.score(fixture("e"), markets(top_odds=3.10))
        self.assertFalse(r["candidate_A"])
        self.assertTrue(r["candidate_B"])
        handoff=detailed_ai_handoff([r],NOW)
        self.assertEqual(handoff["count"],1)
        self.assertFalse(handoff["candidates"][0]["eligible_for_A"])
        self.assertTrue(handoff["candidates"][0]["eligible_for_B"])
        self.assertFalse(handoff["candidates"][0]["research_only"])

    def test_stale_kickoff_and_weak_history_stay_out(self):
        old=self.score(fixture("f",at=NOW+timedelta(minutes=15)),markets())
        self.assertFalse(old["candidate_B"])
        sparse=fixture("g")
        sparse["evidence"]["home_last_matches"]=3
        weak=self.score(sparse,markets())
        self.assertFalse(weak["candidate_B"])

    def test_ticket_b_uses_3plus_not_first_market_quotes_and_no_a_overlap(self):
        rows=[]
        for n in range(4):
            r={
              "fixture_id":f"id{n}","match":f"Home{n} - Away{n}",
              "datetime":(NOW+timedelta(hours=5)).isoformat(),
              "strongest_market":"GG","strongest_odds":1.60,
              "strongest_pct":70,"second_pct":68,"third_pct":55,
              "candidate_A":True,"candidate_B":n in (2,3),
              "scout_value_score":42.0-n,"recommended_ev_pct":8.0,
              "data_quality_index_pct":65,
            }
            if n in (2,3):
                r.update(b_odds=1.45 if n==2 else 1.8,
                         b_probability_pct=64 if n==2 else 66,
                         b_score=37.0,b_conservative_ev_pct=5)
            rows.append(r)
        out=suggestions(rows)
        self.assertIsNotNone(out["A"])
        self.assertIsNotNone(out["B"])
        b=out["B"]
        self.assertTrue(all(leg["pick"]=="3+" for leg in b["matches"]))
        self.assertEqual({leg["odd"] for leg in b["matches"]},{1.45,1.8})
        self.assertEqual({leg["probability_pct"] for leg in b["matches"]},{64,66})
        self.assertTrue(2<=b["combined_odds"]<=3)
        self.assertFalse(b["ready_for_publication"])
        self.assertTrue({x["fixture_id"] for x in out["A"]["matches"]}.isdisjoint(
                         {x["fixture_id"] for x in b["matches"]}))


if __name__ == "__main__":
    unittest.main()
