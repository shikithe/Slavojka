#!/usr/bin/env python3
"""Compact, loss-minimizing ESPN form index for AI prepublication research.

The full history-h2h.json is very large and may exceed GitHub connector read
limits. This file extracts only each day's listed teams and their last five
recorded matches, keeping dates, opponents, score evidence and source
competition without inventing absent statistics. It does not approve bets.
"""
import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

def short_match(row):
    if not isinstance(row, dict):
        return {}
    stats = row.get("statistics") or {}
    return {
        "event_id": row.get("event_id"),
        "date": row.get("date"),
        "match": row.get("name"),
        "competition": row.get("competition"),
        "scores": row.get("scores") or None,
        "source_statistics_available": bool(stats.get("available")) if isinstance(stats, dict) else False,
    }

def short_form(data, league, team_name):
    entry = ((data.get("leagues") or {}).get(league) or {}).get("teams", {}).get(team_name, {})
    matches = entry.get("matches") or []
    return {
        "name": team_name,
        "matches_found": len(matches),
        "complete": len(matches) >= 5,
        "competitions_used": entry.get("competitions_used", []),
        "cross_competition_note": entry.get("cross_competition_note"),
        "last_five_matches": [short_match(item) for item in matches[:5]],
    }

def compress(data):
    if not isinstance(data, dict) or not isinstance(data.get("fixtures"), list):
        raise ValueError("Expected full ESPN history with fixtures")
    fixtures = []
    for fixture in data["fixtures"]:
        if not isinstance(fixture, dict):
            continue
        league, home, away = fixture.get("league"), fixture.get("home"), fixture.get("away")
        if not all([league, home, away, fixture.get("fixture_id")]):
            continue
        key = fixture["fixture_id"]
        h2h = (data.get("head_to_head") or {}).get(key) or {}
        fixtures.append({
            "fixture_id": key,
            "league": league,
            "home": home,
            "away": away,
            "start_utc": fixture.get("start_utc"),
            "home_form": short_form(data, league, home),
            "away_form": short_form(data, league, away),
            "head_to_head": {
                "found": len(h2h.get("matches") or []),
                "matches": [
                    {"date": m.get("date"),
                     "home": m.get("home_team"),
                     "away": m.get("away_team")}
                    for m in (h2h.get("matches") or [])[:5]
                ],
            },
        })
    return {
        "schema_version": "listasix-espn-ai-analysis-brief-v1",
        "date": data.get("date"),
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "full_history_generated_at_utc": data.get("generated_at_utc"),
        "source": "shared/agent/history-h2h.json",
        "form_scope": data.get("form_scope"),
        "source_fixture_count": len(data["fixtures"]),
        "fixture_count": len(fixtures),
        "fixtures": fixtures,
        "limitations": [
            "Missing scores remain null; do not infer match results from names.",
            "ESPN feed form and matches may be incomplete; independently verify all important claims.",
            "Neither odds, injuries, xG nor expected value are approved by this brief.",
            "This is analysis input, not ticket authorization or publication."
        ],
        "publication_allowed": False
    }

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--expected-date", default=None)
    args = parser.parse_args()
    source = json.loads(Path(args.input).read_text(encoding="utf-8"))
    if args.expected_date and source.get("date") != args.expected_date:
        raise ValueError("Cannot publish a stale ESPN analysis brief")
    data = compress(source)
    if not data["fixtures"]:
        raise ValueError("No fixtures to summarize")
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":"))+"\n", encoding="utf-8")
    print("LISTASIX_ANALYSIS_BRIEF", json.dumps({
        "date": data["date"], "fixtures": data["fixture_count"],
        "bytes": output.stat().st_size,
        "home_complete": sum(f["home_form"]["complete"] for f in data["fixtures"]),
        "away_complete": sum(f["away_form"]["complete"] for f in data["fixtures"]),
    }))
    if output.stat().st_size > 1_000_000:
        raise ValueError("Compact form file exceeded 1 MB; cannot rely on GitHub reader")

if __name__=="__main__":
    main()
