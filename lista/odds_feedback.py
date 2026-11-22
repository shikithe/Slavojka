#!/usr/bin/env python3
"""Two-way, fail-closed ESPN -> TipsterArea quote coverage feedback.

One valid real source price for EVERY ESPN fixture is sufficient to run Scout 6/6.
Any missing price produces an AI identity-research handoff, not a guessed quote.
"""
import json
import os
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

TZ = ZoneInfo("Europe/Sarajevo")
FIELDS = ("home_odds", "draw_odds", "away_odds",
          "over25_odds", "btts_yes_odds", "btts_no_odds")

def valid_price(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and 1.01 < value < 50

def evaluate(feed, active, today):
    if feed.get("date") != today or not feed.get("football_candidates"):
        raise ValueError("Fresh nonempty ESPN fixture feed is required")
    if active.get("date") != today:
        raise ValueError("Daily odds list date differs from ESPN feed")
    fixtures = feed["football_candidates"]
    originals = {x["fixture_id"]: x for x in fixtures}
    if len(originals) != len(fixtures):
        raise ValueError("Duplicate ESPN fixture IDs")
    rows = active.get("fixtures")
    if not isinstance(rows, list):
        raise ValueError("Missing daily offer rows")
    mapped = {row["fixture_id"]: row for row in rows}
    if len(mapped) != len(rows) or set(mapped) != set(originals):
        raise ValueError("Daily offer rows do not correspond 1:1 to ESPN")
    missing = []
    with_quotes = 0
    for fixture in fixtures:
        fid = fixture["fixture_id"]
        row = mapped[fid]
        if row.get("datetime") != fixture["start_utc"] or row.get("match") != fixture["home"] + " - " + fixture["away"]:
            raise ValueError("Identity mismatch for " + fid)
        if any(valid_price(row.get(field)) for field in FIELDS):
            with_quotes += 1
        else:
            missing.append({key: fixture[key] for key in ("fixture_id", "league", "home", "away", "start_utc")})
    return {
        "date": today,
        "status": "ready_for_scout" if not missing else "ai_review_required",
        "feedback": "ODDS_COMPLETE_SCOUT_6OF6" if not missing else "ODDS_MISSING_AI_REVIEW",
        "espn_total": len(fixtures), "with_at_least_one_quote": with_quotes,
        "without_quote": len(missing), "missing_fixtures": missing,
        "ai_prompt": "prompts/tipster-unmatched-ai-review.md" if missing else None,
        "next_action": "scout_6of6" if not missing else "ai_review_handoff_then_scout_6of6_and_rescout_after_recovery"
    }

def main():
    root = Path(".")
    today = datetime.now(TZ).date().isoformat()
    feed = json.loads((root / "shared/collector-feed.json").read_text(encoding="utf-8"))
    active = json.loads((root / "shared/active-list.json").read_text(encoding="utf-8"))
    result = evaluate(feed, active, today)
    output = root / "shared/kvoter/coverage-feedback.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if os.getenv("GITHUB_OUTPUT"):
        with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as out:
            out.write("ready=" + ("true" if result["status"] == "ready_for_scout" else "false") + "\n")
            out.write("missing=" + str(result["without_quote"]) + "\n")
    print(result["feedback"], f'{result["with_at_least_one_quote"]}/{result["espn_total"]}')
    return result

if __name__ == "__main__":
    main()
