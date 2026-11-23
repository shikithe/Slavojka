#!/usr/bin/env python3
"""Independent, machine-readable Scout 6/6 and TOP10 feedback gates.

Checks report freshness, original ESPN IDs and source fingerprints; emits signals
but does not approve tips or invoke AI in GitHub Actions.
"""
import hashlib
import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

TZ = ZoneInfo("Europe/Sarajevo")
MARKETS = {"1", "X", "2", "3+", "GG", "NG"}

def canonical_hash(obj):
    return hashlib.sha256(json.dumps(obj, ensure_ascii=False, sort_keys=True,
                    separators=(",", ":")).encode("utf-8")).hexdigest()

def inspect(feed, active, history, scout, today):
    if any(not isinstance(doc, dict) or doc.get("date") != today
           for doc in (feed, active, scout)):
        raise ValueError("Feed, odds and Scout report must have today's Sarajevo date")
    if not isinstance(history, dict) or history.get("date") != today:
        raise ValueError("Scout history input must be a same-day unavailable marker or history")
    fixtures = feed.get("football_candidates", [])
    ids = [f.get("fixture_id") for f in fixtures]
    if not ids or len(set(ids)) != len(ids):
        raise ValueError("Invalid or empty ESPN feed")
    if scout.get("source_feed_generated_at_utc") != feed.get("generated_at_utc"):
        raise ValueError("Scout source ESPN timestamp is outdated")
    if scout.get("source_active_sha256") != canonical_hash(active):
        raise ValueError("Scout does not match current odds list")
    if scout.get("source_history_sha256") != canonical_hash(history):
        raise ValueError("Scout does not match current football history")
    ranked = scout.get("ranked_fixtures", [])
    if len(ranked) != len(ids) or set(x.get("fixture_id") for x in ranked) != set(ids):
        raise ValueError("Scout has not evaluated exactly every ESPN match")
    if scout.get("all_fixtures_evaluated") != len(ids) or scout.get("total_market_probabilities") != 6 * len(ids):
        raise ValueError("Scout 6/6 count mismatch")
    for row in ranked:
        probs = row.get("probability_pct", {})
        if set(probs) != MARKETS or any(not isinstance(p, (int, float)) or isinstance(p, bool)
                                        or not 0 <= p <= 100 for p in probs.values()):
            raise ValueError("Incomplete six-market probabilities")
    fingerprint = canonical_hash({
        "date": today, "feed": scout["source_feed_generated_at_utc"],
        "active": scout["source_active_sha256"], "history": scout["source_history_sha256"]
    })
    completed = {
        "date": today, "feedback": "SCOUT_6OF6_COMPLETE",
        "status": "complete", "all_fixtures_evaluated": len(ids),
        "market_probabilities": len(ids) * 6, "source_fingerprint": fingerprint,
        "generated_at_utc": scout.get("generated_at_utc"),
        "history_status": scout.get("history_status","available"),
        "next_action": "validate_top10"
    }
    handoff = scout.get("detailed_ai_handoff", {})
    selected = handoff.get("candidates", [])
    selected_ids = [x.get("fixture_id") for x in selected]
    if (handoff.get("count") != len(selected) or len(selected) > 10 or
        len(set(selected_ids)) != len(selected_ids) or
        selected_ids != scout.get("detailed_ai_top_ten_fixture_ids", [])):
        raise ValueError("TOP10 selection identity/count mismatch")
    available = {row["fixture_id"]: row for row in ranked}
    for position, item in enumerate(selected, 1):
        original = available.get(item["fixture_id"])
        research_only = bool(item.get("research_only"))
        eligible = bool(original and (original.get("candidate_A") or (
            research_only and not original.get("candidate_A")
            and original.get("recommended_market") and original.get("recommended_odds"))))
        if not eligible or item.get("rank") != position:
            raise ValueError("TOP10 candidate ineligible or incorrect rank")
        if research_only and item.get("eligible_for_A"):
            raise ValueError("Research-only candidate cannot be marked eligible for ticket A")
        if item.get("recommended_market") != original.get("recommended_market"):
            raise ValueError("TOP10 recommended market mismatch")
    ready = bool(selected)
    top10 = {
        "date": today, "feedback": "TOP10_READY" if ready else "TOP10_UNAVAILABLE",
        "status": "ready" if ready else "unavailable",
        "source_fingerprint": fingerprint,
        "scout_report": "shared/agent/scout-six-markets.json",
        "count": len(selected),
        "fixture_ids": selected_ids,
        "candidates": selected,
        "next_action": "independent_ai_detailed_scout" if ready else "report_no_eligible_candidates",
        "history_status": scout.get("history_status","available"),
        "research_only": bool(handoff.get("research_only")),
        "ai_approval_required": True,
        "publication_allowed": False
    }
    return completed, top10

def main(root=Path(".")):
    today = datetime.now(TZ).date().isoformat()
    def read(relative):
        return json.loads((root / relative).read_text(encoding="utf-8"))
    completed, top10 = inspect(
        read("shared/collector-feed.json"), read("shared/active-list.json"),
        read("shared/agent/history-h2h.json"),
        read("shared/agent/scout-six-markets.json"), today
    )
    paths = {
        "shared/agent/scout-feedback.json": completed,
        "shared/agent/top10-feedback.json": top10,
    }
    for name, data in paths.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(completed["feedback"], completed["all_fixtures_evaluated"])
    print(top10["feedback"], top10["count"])
    return completed, top10

if __name__ == "__main__":
    main()
