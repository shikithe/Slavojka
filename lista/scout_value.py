"""Price-aware extension of the existing six-market pre-Scout.

Computes six hypothetical market-anchored probabilities, expected-return edges
and an explicit data-quality index during the SAME pipeline execution.
NOT an empirically calibrated betting model; no extra API calls.
"""
import math
from datetime import datetime, timedelta, timezone

MARKETS = ("1", "X", "2", "3+", "GG", "NG")
PREFERRED = {"3+":0, "1":1, "2":2, "GG":3, "NG":4, "X":5}

def bounded(v, lo, hi):
    return max(lo, min(hi, float(v)))

def quality(home, away, league_games):
    """0–100 *data coverage index*, never 'chance of winning'."""
    home = (home or {}).get("matches", [])[:5]
    away = (away or {}).get("matches", [])[:5]
    n = min(len(home), len(away))
    venue_home = sum(x.get("side") == "home" for x in home)
    venue_away = sum(x.get("side") == "away" for x in away)
    def variance(games):
        seq = []
        for m in games:
            if isinstance(m.get("goals_for"), (float, int)) and isinstance(m.get("goals_against"), (float, int)):
                seq.append(m["goals_for"] + m["goals_against"])
        if not seq: return 8.0
        mean = sum(seq) / len(seq)
        return sum((x - mean)**2 for x in seq) / len(seq)
    volatility=(variance(home)+variance(away))/2
    confidence=bounded(.20 + .26 * n/5
                        + .12 * min(1.0, (venue_home+venue_away)/6)
                        + .10 * min(1.0,league_games/60)
                        - .13 * min(1.0,volatility/8), .20, .72)
    details={"home_last_matches":len(home),"away_last_matches":len(away),
             "home_home_games":venue_home,"away_away_games":venue_away,
             "league_games":league_games,"goal_variance":round(volatility,3)}
    return confidence, details

def market_evaluation(probs, odds, confidence):
    """EV is illustrative p * price - 1, not an actual measured player edge.

    For each six-market quote shrink the raw Poisson probability towards the
    quoted implied probability by data quality. Using a market prior instead of
    artificial 100% confidence avoids treating five goal-heavy results as proof.
    """
    ret={}
    for m in MARKETS:
        price=odds.get(m)
        p=probs[m]
        if price is None or isinstance(price,bool) or not isinstance(price,(int,float)) or not math.isfinite(price) or not 1.01<price<50:
            ret[m]={"raw_probability_pct":p, "odds":None, "implied_probability_pct":None,
                    "adjusted_probability_pct":None,"raw_ev_pct":None,
                    "conservative_ev_pct":None,"score":None}
            continue
        implied=100.0/price
        adjusted=implied+confidence*(p-implied)
        raw_ev=p*price-100.0
        ev=adjusted*price-100.0
        score=(.42*adjusted+.43*bounded(ev,-25,30)+.15*confidence*100)
        ret[m]={"raw_probability_pct":p,"odds":round(price,3),
                "implied_probability_pct":round(implied,2),
                "adjusted_probability_pct":round(adjusted,2),
                "raw_ev_pct":round(raw_ev,2),
                "conservative_ev_pct":round(ev,2),
                "score":round(score,3)}
    return ret

def rank_key(row):
    score=row.get("recommended_score")
    if score is None:
        score=-1e10
    return (-score, -float(row.get("recommended_pct") or 0),
            -float(row.get("second_pct") or 0),
            -float(row.get("third_pct") or 0),
            row["fixture_id"])

def apply_value_model(rows, history, now):
    """One-pass supplement to the already computed 6/6 outcome probabilities."""
    for r in rows:
        teams=history.get("leagues",{}).get(r["league"],{}).get("teams",{})
        home,away=r["match"].split(" - ",1)
        confidence,detail=quality(teams.get(home),teams.get(away),
                                  r["evidence"]["league_unique_result_matches"])
        markets=market_evaluation(r["probability_pct"],r["odds"],confidence)
        available=[m for m in MARKETS if markets[m]["score"] is not None]
        available.sort(key=lambda m:(-markets[m]["score"],-r["probability_pct"][m],PREFERRED[m]))
        chosen=available[0] if available else None
        runnerup=available[1] if len(available)>1 else None
        sel=markets[chosen] if chosen else None
        r["market_value"]=markets
        r["data_quality_index_pct"]=round(confidence*100,1)
        r["data_quality_factors"]=detail
        r["recommended_market"]=chosen
        r["recommended_pct"]=r["probability_pct"][chosen] if chosen else None
        r["recommended_odds"]=r["odds"][chosen] if chosen else None
        r["recommended_score"]=sel["score"] if sel else None
        r["recommended_adjusted_pct"]=sel["adjusted_probability_pct"] if sel else None
        r["recommended_ev_pct"]=sel["conservative_ev_pct"] if sel else None
        r["value_runner_up_market"]=runnerup
        r["value_runner_up_score"]=markets[runnerup]["score"] if runnerup else None
        start=datetime.fromisoformat(r["datetime"].replace("Z","+00:00"))
        # A two-leg ticket with an individual selection >=3.00 cannot be 2–3.
        qualified=bool(sel and sel["odds"]<3.00
                       and sel["conservative_ev_pct"]>0
                       and sel["adjusted_probability_pct"]>=50
                       and min(r["evidence"]["home_last_matches"],
                               r["evidence"]["away_last_matches"])>=4
                       and start>now+timedelta(minutes=20))
        # Ticket B always plays 3+ goals. Accept 3+ when it is the
        # best OR second-best VALUE-ranked market, not only the A pick.
        # B must pass every safety rule using its OWN 3+ odds and EV.
        over=markets["3+"]
        over_rank=available.index("3+")+1 if "3+" in available else None
        b_qualified=bool(over_rank in (1,2)
                         and over["odds"] is not None
                         and over["odds"]<3.00
                         and over["conservative_ev_pct"]>0
                         and over["adjusted_probability_pct"]>=50
                         and min(r["evidence"]["home_last_matches"],
                                 r["evidence"]["away_last_matches"])>=4
                         and start>now+timedelta(minutes=20))
        r["candidate_A"]=qualified
        r["candidate_B"]=b_qualified
        r["b_market_rank"]=over_rank
        r["b_market"]="3+" if b_qualified else None
        r["b_odds"]=over["odds"] if b_qualified else None
        r["b_probability_pct"]=r["probability_pct"]["3+"] if b_qualified else None
        r["b_adjusted_probability_pct"]=over["adjusted_probability_pct"] if b_qualified else None
        r["b_conservative_ev_pct"]=over["conservative_ev_pct"] if b_qualified else None
        r["b_score"]=over["score"] if b_qualified else None
        reasons=[]
        if chosen is None:reasons.append("No verified odds for any of six markets")
        elif sel["odds"]>=3:reasons.append("Chosen market odds 3+ prevents a 2–3 multi-leg ticket")
        elif sel["conservative_ev_pct"]<=0:reasons.append("No positive conservative EV for chosen market")
        elif sel["adjusted_probability_pct"]<50:reasons.append("Risk-adjusted probability below 50% for chosen market")
        if not qualified and start<=now+timedelta(minutes=20):
            reasons.append("Kickoff already started or within twenty minutes")
        r["value_limitations"]=reasons
    rows.sort(key=rank_key)
    return rows

def proposal_view(r):
    """Keep existing combination algorithm but feed it the selected value market."""
    copy=dict(r)
    copy["strongest_market"]=r["recommended_market"]
    copy["strongest_odds"]=r["recommended_odds"]
    copy["strongest_pct"]=r["recommended_pct"]
    copy["scout_value_score"]=r["recommended_score"]
    return copy
