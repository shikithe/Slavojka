#!/usr/bin/env python3
"""ListaSix Scout 6/6: evaluate every ESPN fixture on all SIX football markets.

This is a transparent statistical PRE-SCOUT, not calibrated certainty.
Every fixture is modeled, even if its odds are missing or kickoff has passed.
One strongest market per fixture; a second-highest probability breaks ties
between fixtures. B can only use fixtures with 3+ as the top market.
Ticket proposals are NEVER approved or published by this module:
the independent analyst must review injuries, suspensions, lineup, H2H, xG
when available, and source odds before publishing.
"""
import argparse
import hashlib
import itertools
import json
import math
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

TZ = ZoneInfo("Europe/Sarajevo")

def canonical_hash(obj):
    """Match MemaraSix source synchronization's canonical JSON SHA256."""
    payload = json.dumps(obj, ensure_ascii=False, sort_keys=True,
                         separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()
MARKETS = ("1", "X", "2", "3+", "GG", "NG")
MARKET_FIELDS = {
    "1": "home_odds", "X": "draw_odds", "2": "away_odds",
    "3+": "over25_odds", "GG": "btts_yes_odds", "NG": "btts_no_odds",
}
TIE_PRIORITY = {"3+": 0, "1": 1, "2": 2, "GG": 3, "NG": 4, "X": 5}
MODELED_MAX_GOALS = 16
MAX_LEGS = 3
MAX_CANDIDATES_PER_POOL = 36
MAX_COMBOS_PER_POOL = 130
DETAILED_SCOUT_LIMIT = 10

def clamp(number, low, high):
    return min(high, max(low, float(number)))

def league_goal_reference(league_record):
    """Deduplicate recent ESPN events. Shrink league rates toward broad priors."""
    unique = {}
    for team in league_record.get("teams", {}).values():
        for item in team.get("matches", []):
            if item.get("event_id") and isinstance(item.get("home_goals"), (int, float)) and isinstance(item.get("away_goals"), (int, float)):
                unique[str(item["event_id"])] = item
    count = len(unique)
    home = (sum(x["home_goals"] for x in unique.values()) + 18 * 1.45) / (count + 18)
    away = (sum(x["away_goals"] for x in unique.values()) + 18 * 1.15) / (count + 18)
    return clamp(home, 0.85, 2.15), clamp(away, 0.65, 1.95), count

def rates(record, expected_for, expected_against, preferred_side):
    """Recency-weighted actual scores; 3-match prior limits five-game noise."""
    games = record.get("matches", [])[:5] if isinstance(record, dict) else []
    weighted = []
    side_weighted = []
    for index, item in enumerate(games):
        try:
            gf, ga = int(item["goals_for"]), int(item["goals_against"])
            if not (0 <= gf <= 25 and 0 <= ga <= 25):
                continue
            w = (1.20, 1.10, 1.00, 0.90, 0.80)[min(index, 4)]
            weighted.append((w, gf, ga))
            if item.get("side") == preferred_side:
                side_weighted.append((w, gf, ga))
        except (TypeError, KeyError, ValueError):
            continue
    sumw = sum(x[0] for x in weighted)
    attack = (3.0 * expected_for + sum(w*gf for w, gf, _ in weighted)) / (3.0 + sumw)
    concede = (3.0 * expected_against + sum(w*ga for w, _, ga in weighted)) / (3.0 + sumw)
    if len(side_weighted) >= 2:
        sw = sum(x[0] for x in side_weighted)
        specific_attack = (2.0 * expected_for + sum(w*gf for w, gf, _ in side_weighted)) / (2.0 + sw)
        specific_concede = (2.0 * expected_against + sum(w*ga for w, _, ga in side_weighted)) / (2.0 + sw)
        attack = 0.75 * attack + 0.25 * specific_attack
        concede = 0.75 * concede + 0.25 * specific_concede
    return attack, concede, len(weighted)

def poisson_mass(lam):
    pmf = [math.exp(-lam)]
    for k in range(1, MODELED_MAX_GOALS+1):
        pmf.append(pmf[-1] * lam / k)
    return pmf

def six_probs(home_xg, away_xg):
    """Independently modeled goals -> mutually coherent 1X2 and GG/NG outcomes."""
    h, a = poisson_mass(home_xg), poisson_mass(away_xg)
    vals = {k: 0.0 for k in MARKETS}
    covered_mass = sum(h) * sum(a)
    for hg, hp in enumerate(h):
        for ag, ap in enumerate(a):
            weight = hp * ap / covered_mass
            vals["1" if hg > ag else ("X" if hg == ag else "2")] += weight
            if hg + ag >= 3: vals["3+"] += weight
            vals["GG" if (hg > 0 and ag > 0) else "NG"] += weight
    # Show one decimal; ensure complementary and exhaustive outcomes still sum to 100.
    ans = {k: round(100.0 * v, 1) for k, v in vals.items()}
    ans["2"] = round(100.0 - ans["1"] - ans["X"], 1)
    ans["NG"] = round(100.0 - ans["GG"], 1)
    return ans

def available_odd(fixture, market):
    val = fixture.get(MARKET_FIELDS[market])
    if isinstance(val, bool) or not isinstance(val, (int, float)) or not 1.01 < val < 50:
        return None
    return float(val)

def evaluate_fixture(fixture, history, now):
    fixture_id = fixture["fixture_id"]
    league = fixture_id.split(":")[2]
    if " - " not in fixture["match"]:
        raise ValueError("Fixture has invalid ESPN match name: " + fixture_id)
    home, away = fixture["match"].split(" - ", 1)
    records = history.get("leagues", {}).get(league, {}).get("teams", {})
    h, a = records.get(home, {}), records.get(away, {})
    base_h, base_a, league_sample = league_goal_reference(history.get("leagues", {}).get(league, {}))
    # Home attack and away defensive concessions belong on a home-scoring scale;
    # away attack and home defensive concessions belong on the away scale.
    hgf, hga, hn = rates(h, base_h, base_a, "home")
    agf, aga, an = rates(a, base_a, base_h, "away")
    xgh = clamp((hgf + aga) * .5, .35, 3.65)
    xga = clamp((agf + hga) * .5, .30, 3.45)
    pcts = six_probs(xgh, xga)
    ranked = sorted(MARKETS, key=lambda k: (-pcts[k], TIE_PRIORITY[k]))
    top, second = ranked[:2]
    odds = {k: available_odd(fixture, k) for k in MARKETS}
    start = datetime.fromisoformat(fixture["datetime"].replace("Z","+00:00")).astimezone(timezone.utc)
    notes = []
    if min(hn, an) < 4:
        notes.append("Incomplete ESPN last-five form: independent model confidence low")
    if odds[top] is None:
        notes.append("The strongest market has no verified price: do not substitute the second market")
    if start <= now + timedelta(minutes=20):
        notes.append("Started or less than 20 minutes to kickoff; exclude from new tickets")
    return {
        "fixture_id": fixture_id, "league": league, "match": fixture["match"],
        "datetime": fixture["datetime"],
        "probability_pct": pcts, "odds": odds,
        "strongest_market": top, "strongest_pct": pcts[top],
        "second_market": second, "second_pct": pcts[second],
        "third_pct": pcts[ranked[2]], "strongest_odds": odds[top],
        "strongest_implied_pct": round(100.0 / odds[top],1) if odds[top] else None,
        "estimated_goals": {"home": round(xgh, 2), "away": round(xga, 2)},
        "evidence": {"home_last_matches": hn, "away_last_matches": an,
                     "league_unique_result_matches": league_sample,
                     "used_xg": False, "lineups_checked": False,
                     "injuries_checked": False, "h2h_checked": False},
        "candidate_A": bool(odds[top] and start > now + timedelta(minutes=20)),
        "candidate_B": bool(top == "3+" and odds[top]
                            and start > now + timedelta(minutes=20)),
        "history_evidence_complete": bool(min(hn, an) >= 4),
        "confidence": "normal" if min(hn, an) >= 4 else "low_data",
        "requires_independent_ai_review": True,
        "needs_independent_ai_review": True, "limitations": notes
    }

def ranking(candidate):
    """Most probable top outcome; in exact ties the runner-up is decisive."""
    return (-candidate["strongest_pct"], -candidate["second_pct"],
            -candidate["third_pct"], candidate["fixture_id"])

def ticket_combos(rows):
    pool = sorted(rows, key=ranking)[:MAX_CANDIDATES_PER_POOL]
    combos = []
    for n in (2, 3):
        for combo in itertools.combinations(pool, n):
            product = math.prod(x["strongest_odds"] for x in combo)
            if not (2.0 <= product <= 3.0):
                continue
            scores = [x.get("scout_value_score") if x.get("scout_value_score") is not None else x["strongest_pct"] for x in combo]
            second = [x["second_pct"] for x in combo]
            # Favor higher top-market reliability rather than high odds.
            # Lower n helps avoid extra legs when equally rated.
            grade = (round(sum(scores)/n, 5), min(scores),
                     round(sum(second)/n, 5), -n, -abs(product-2.5))
            combos.append({"rows": combo, "odds": round(product, 3), "grade": grade,
                           "ids": frozenset(x["fixture_id"] for x in combo)})
    combos.sort(key=lambda c: c["grade"], reverse=True)
    return combos[:MAX_COMBOS_PER_POOL]

def suggestions(ranked):
    a_pool = [f for f in ranked if f["candidate_A"]]
    b_pool = [f for f in ranked if f["candidate_B"]]
    a_combos, b_combos = ticket_combos(a_pool), ticket_combos(b_pool)
    if not a_combos:
        return {"A": None,"B": None,"reason": "No 2-3 leg A combination totaling 2.00-3.00"}
    if not b_combos:
        best = a_combos[0]
        return {"A": format_combo(best, "A"), "B": None,
                "reason": "No 2-3 leg B combination: only fixtures with 3+ as TOP market qualify"}
    chosen = None
    for a in a_combos:
        for b in b_combos:
            if a["ids"] & b["ids"]:
                continue
            leg_list = list(a["rows"]) + list(b["rows"])
            all_scores = [r.get("scout_value_score") if r.get("scout_value_score") is not None else r["strongest_pct"] for r in leg_list]
            next_scores = [r["second_pct"] for r in leg_list]
            score = (round(sum(all_scores)/len(all_scores),5), min(all_scores),
                     round(sum(next_scores)/len(next_scores),5),
                     -len(leg_list), a["grade"], b["grade"])
            if chosen is None or score > chosen[0]:
                chosen = (score,a,b)
    if chosen is None:
        best=a_combos[0]
        return {"A":format_combo(best,"A"),"B":None,
                "reason":"No eligible pair of NON-overlapping A and B combinations totaling 2.00-3.00 each"}
    return {"A":format_combo(chosen[1],"A"),"B":format_combo(chosen[2],"B"),
            "reason":"Statistical proposals only. Independent Scout must verify and explicitly approve."}

def format_combo(combo, tid):
    return {
        "id":tid,"combined_odds":combo["odds"],
        "selection_method":"highest conservative market EV/probability/evidence score; tie by model probability then runner-up",
        "ready_for_publication":False,"requires_independent_ai_approval":True,
        "matches":[{
            "fixture_id":r["fixture_id"],"match":r["match"],"datetime":r["datetime"],
            "pick":r["strongest_market"],"probability_pct":r["strongest_pct"],
            "rank_score":r.get("scout_value_score"),
            "conservative_ev_pct":r.get("recommended_ev_pct"),
            "data_quality_index_pct":r.get("data_quality_index_pct"),
            "second_best_pct":r["second_pct"],"odd":r["strongest_odds"]
        } for r in combo["rows"]]
    }

def detailed_ai_handoff(rows, now=None):
    """Top 10 still eligible fixtures, with existing math evidence reusable as-is.

    These are the only matches for detailed AI investigation, not 10 new math
    calculations. Independent analyst owns all remaining nonmathematical checks.
    """
    selected = [r for r in rows if r["candidate_A"]][:DETAILED_SCOUT_LIMIT]
    research_only = False
    # If the statistical acceptance gate has no candidates because history is
    # unavailable, still send future, quoted fixtures for independent review.
    # This DOES NOT authorize publication or loosen ticket proposal rules.
    if not selected and now is not None:
        selected = [r for r in rows
                    if r.get("recommended_market") and r.get("recommended_odds")
                    and datetime.fromisoformat(r["datetime"].replace("Z","+00:00")) > now+timedelta(minutes=20)][:DETAILED_SCOUT_LIMIT]
        research_only = True
    items = []
    for rank, r in enumerate(selected, 1):
        items.append({
            "rank": rank, "fixture_id": r["fixture_id"],
            "match": r["match"], "datetime": r["datetime"],
            "top_market": r["strongest_market"],
            "top_probability_pct": r["strongest_pct"],
            "recommended_market": r["recommended_market"],
            "recommended_probability_pct": r["recommended_pct"],
            "recommended_adjusted_probability_pct": r["recommended_adjusted_pct"],
            "recommended_score": r["recommended_score"],
            "recommended_ev_pct": r["recommended_ev_pct"],
            "data_quality_index_pct": r["data_quality_index_pct"],
            "second_market": r["second_market"],
            "second_probability_pct": r["second_pct"],
            "top_market_odds": r["strongest_odds"],
            "recommended_market_odds": r["recommended_odds"],
            "eligible_for_A": bool(r["candidate_A"]),
            "eligible_for_B": bool(r["candidate_B"]),
            "research_only": bool(research_only and not r["candidate_A"]),
            "confidence": r.get("confidence","unknown"),
            "history_evidence_complete": bool(r.get("history_evidence_complete",False)),
            "all_six_probabilities_pct": r["probability_pct"],
            "math_already_done": {
                "last_five_matches_per_team": {
                    "home": r["evidence"]["home_last_matches"],
                    "away": r["evidence"]["away_last_matches"]},
                "recent_goals_attack_defence": "Present" if r.get("history_evidence_complete") else "Missing; modeled using broad priors, not actual recent form",
                "home_away_form": "Present" if r.get("history_evidence_complete") else "Missing; independent research required",
                "league_goal_average": "Historical rates where present; otherwise unverified broad priors",
                "modeled_goals": r["estimated_goals"],
                "poisson_probabilities": r["probability_pct"]
            },
            "ai_checks_still_required": [
                "actual_xg_xga_if_available", "injuries_and_suspensions",
                "expected_lineups", "recent_h2h_up_to_five",
                "table_and_motivation", "rest_days_and_schedule",
                "odds_identity_and_source"
            ],
            "ai_review_status": "pending_independent_review"
        })
    return {
        "limit": DETAILED_SCOUT_LIMIT,
        "selection_rule": "Research-only future quoted matches if zero statistically qualified; otherwise top statistically qualified matches",
        "research_only": research_only,
        "count": len(items),
        "math_recalculation_prohibited": True,
        "independent_ai_review_required": True,
        "candidates": items
    }

def analyze(feed, active, history, now):
    if feed.get("date") != active.get("date"):
        raise ValueError("ESPN feed and odds must be SAME date")
    if not isinstance(history, dict) or history.get("date") != feed["date"]:
        history = {"date": feed["date"], "fixtures": feed.get("football_candidates", []),
                   "leagues": {}, "head_to_head": {}, "history_status": "unavailable_no_fabrication"}
    official = {x["fixture_id"]:x for x in feed.get("football_candidates",[])}
    display = {x["fixture_id"]:x for x in active.get("fixtures",[])}
    historical = {x["fixture_id"] for x in history.get("fixtures",[])}
    if not official or len(official)!=len(feed["football_candidates"]):
        raise ValueError("Missing or duplicated ESPN fixture IDs")
    if official.keys()!=display.keys():
        raise ValueError("Cannot score: missing ESPN fixtures in displayed odds")
    if not official.keys()<=historical:
        history = {"date": feed["date"], "fixtures": feed["football_candidates"],
                   "leagues": {}, "head_to_head": {}, "history_status": "incomplete_no_fabrication"}
    records = []
    for fid, f in official.items():
        display_row=display[fid]
        if display_row.get("match")!=f["home"]+" - "+f["away"] or display_row.get("datetime")!=f["start_utc"]:
            raise ValueError("ESPN team or kickoff discrepancy for "+fid)
        records.append(evaluate_fixture(display_row,history,now))
    from lista.scout_value import apply_value_model, proposal_view
    records = apply_value_model(records, history, now)
    handoff = detailed_ai_handoff(records, now)
    selected_ids = {x["fixture_id"] for x in handoff["candidates"]}
    # Every proposed A/B leg must be among the exact 10 forwarded to Detailed AI.
    possible = suggestions([proposal_view(r) for r in records if r["fixture_id"] in selected_ids])
    return {
        "schema_version":2,"date":feed["date"],
        "generated_at_utc":now.isoformat(),"source_feed_generated_at_utc":feed.get("generated_at_utc"),
        "source_active_sha256":canonical_hash(active),
        "source_history_sha256":canonical_hash(history),
        "model":"Poisson 6/6 + market-anchored adjusted probabilities + conservative EV + sample-quality index across six markets",
        "history_status":history.get("history_status","available"),
        "history_missing":history.get("history_status") in ("unavailable_no_fabrication","incomplete_no_fabrication"),
        "value_selection_enabled":True,
        "score_formula":"0.42*adjusted_probability_pct + 0.43*clamp(conservative_ev_pct,-25,30) + 0.15*data_quality_index_pct",
        "value_selection_not_backtested":True,
        "data_quality_index_is_not_accuracy":True,
        "probabilities_are_calibrated":False,
        "disclaimer":"Statistical estimates, not observed win chances or guarantees. Validate via rolling backtest; separate analyst review for injuries/xG/H2H.",
        "all_six_markets":list(MARKETS),
        "total_espn_fixtures":len(official),"total_market_probabilities":len(records)*6,
        "all_fixtures_evaluated":len(records),
        "all_six_odds_present":sum(all(x["odds"][m] is not None for m in MARKETS) for x in records),
        "candidate_A_count":sum(x["candidate_A"] for x in records),
        "candidate_B_count":sum(x["candidate_B"] for x in records),
        "ranked_fixtures":records,
        "detailed_ai_handoff":handoff,
        "detailed_ai_top_ten_fixture_ids":[x["fixture_id"] for x in handoff["candidates"]],
        "ticket_proposals":possible,
        "publication_allowed":False
    }

def render_text(doc):
    out=[
        "LISTASIX SCOUT 6/6 | "+doc["date"],
        "PROBABILITY MODEL (NOT BACKTEST-CALIBRATED). No ticket is auto-published.",
        "Number of matches: "+str(doc["all_fixtures_evaluated"])+"; probability estimates: "+str(doc["total_market_probabilities"]),
        "RANK | FIXTURE | 1 | X | 2 | 3+ | GG | NG | TOP | RUNNER-UP | ODDS | STATUS"
    ]
    for n,r in enumerate(doc["ranked_fixtures"],1):
        odds = "-" if r["strongest_odds"] is None else f'{r["strongest_odds"]:.2f}'
        ps=" | ".join(f'{r["probability_pct"][m]:.1f}%' for m in MARKETS)
        stat="A/B" if r["candidate_B"] else ("A" if r["candidate_A"] else "OUT")
        out.append(f'{n} | {r["match"]} | {ps} | {r["strongest_market"]} {r["strongest_pct"]:.1f}% | {r["second_market"]} {r["second_pct"]:.1f}% | {odds} | {stat}')
    out.append("")
    out.append("PRICE/EV RANKING | match | pick | raw p% | conservative p% | evidence /100 | conservative EV% | score | odds | eligible")
    for rank, r in enumerate(doc["ranked_fixtures"], 1):
        if r["recommended_market"] is None:
            continue
        out.append(f'{rank} | {r["match"]} | {r["recommended_market"]} | '
                   f'{r["recommended_pct"]:.1f}% | {r["recommended_adjusted_pct"]:.1f}% '
                   f'| {r["data_quality_index_pct"]:.1f} | {r["recommended_ev_pct"]:+.1f}% '
                   f'| {r["recommended_score"]:.2f} | {r["recommended_odds"]:.2f} '
                   f'| {"YES" if r["candidate_A"] else "NO"}')
    out.append("")
    out.append("DETAILED AI SCOUT: TOP " + str(doc["detailed_ai_handoff"]["count"]) +
               " ONLY (mathematical form, goals, home/away, league averages ALREADY DONE)")
    for item in doc["detailed_ai_handoff"]["candidates"]:
        out.append(f'{item["rank"]}. {item["match"]} | VALUE PICK {item["recommended_market"]} '
                   f'{item["recommended_probability_pct"]:.1f}% | conservative p '
                   f'{item["recommended_adjusted_probability_pct"]:.1f}% | EV '
                   f'{item["recommended_ev_pct"]:+.1f}% | evidence '
                   f'{item["data_quality_index_pct"]:.1f}/100 | score {item["recommended_score"]:.2f} '
                   f'| odds {item["recommended_market_odds"]:.2f} | Independent AI review pending')
    out.append("")
    for tid in ("A","B"):
        t=doc["ticket_proposals"][tid]
        if t:
            out.append(f'{tid} PROPOSAL (UNAPPROVED) {t["combined_odds"]:.2f}: '+
                       "; ".join(f'{x["match"]} [{x["pick"]} {x["odd"]:.2f}, p={x["probability_pct"]:.1f}%]' for x in t["matches"]))
        else:out.append(tid+" NO ELIGIBLE PROPOSAL")
    out.append(doc["ticket_proposals"]["reason"])
    return "\n".join(out)+"\n"

def save(path, data, raw=False):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    temp=path.with_name(path.name+".tmp")
    temp.write_text(data if raw else json.dumps(data,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    temp.replace(path)

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--root", default=".")
    args=parser.parse_args()
    root=Path(args.root)
    now=datetime.now(timezone.utc)
    day=now.astimezone(TZ).date().isoformat()
    feed=json.loads((root/"shared/collector-feed.json").read_text(encoding="utf-8"))
    active=json.loads((root/"shared/active-list.json").read_text(encoding="utf-8"))
    history_path=root/"shared/agent/history-h2h.json"
    try:
        history=json.loads(history_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        history={}
    if feed.get("date") != day:
        print("SCOUT_6OF6_WAIT_TODAY_ESPN",feed.get("date"),day)
        return
    if active.get("date") != day:
        print("SCOUT_6OF6_WAIT_QUOTES",active.get("date"),day)
        return
    history_ids={x.get("fixture_id") for x in history.get("fixtures", [])}
    feed_ids={x.get("fixture_id") for x in feed.get("football_candidates", [])}
    if history.get("date") != day or history_ids != feed_ids:
        print("SCOUT_6OF6_HISTORY_MISSING_DEGRADED",history.get("date"),day)
        history={"date":day,"fixtures":feed["football_candidates"],"leagues":{},
                 "head_to_head":{},"history_status":"unavailable_no_fabrication"}
        save(history_path,history)
    result=analyze(feed,active,history,now)
    save(root/"shared/agent"/f"scout-six-markets-{day}.json",result)
    save(root/"shared/agent/scout-six-markets.json",result)
    save(root/"docs/scout-six-markets.json",result)
    save(root/"docs/scout-six-markets.txt",render_text(result),raw=True)
    print("SCOUT_6OF6_COMPLETE",result["total_espn_fixtures"],result["total_market_probabilities"],
          "FULL_ODDS",result["all_six_odds_present"],
          "A",result["candidate_A_count"],"B",result["candidate_B_count"])
    print("SCOUT_6OF6_PROPOSALS", json.dumps(result["ticket_proposals"],ensure_ascii=False))
if __name__=="__main__":
    main()
