#!/usr/bin/env python3
"""Clear previous-day live football offers before the 09:00 Sarajevo intake.

Never clear a current-day list or historical archives. GitHub workflow applies
the time gate; this module additionally rejects use at/after 09:00 by default.
"""
import json
from datetime import datetime, time
from pathlib import Path
from zoneinfo import ZoneInfo

TZ = ZoneInfo("Europe/Sarajevo")

FILES = {
    "shared/collector-feed.json": {"football_candidates": [], "publication_allowed": False},
    "shared/collector-raw.json": {"fixtures": [], "fixture_count": 0},
    "shared/active-list.json": {"fixtures": [], "publication_allowed": False},
    "docs/collector-feed.json": {"football_candidates": [], "publication_allowed": False},
    "docs/active-list.json": {"fixtures": [], "publication_allowed": False},
    "shared/agent/history-h2h.json": {"fixtures": [], "leagues": {}, "head_to_head": {}, "publication_allowed": False},
    "shared/agent/scout-six-markets.json": {"ranked_fixtures": [], "detailed_ai_handoff": {"count": 0, "candidates": []}, "publication_allowed": False},
    "docs/scout-six-markets.json": {"ranked_fixtures": [], "detailed_ai_handoff": {"count": 0, "candidates": []}, "publication_allowed": False},
    "shared/agent/scout-feedback.json": {"feedback": "WAIT_ESPN", "status": "waiting"},
    "shared/agent/top10-feedback.json": {"feedback": "WAIT_SCOUT_6OF6", "status": "waiting", "count": 0, "fixture_ids": [], "candidates": []},
    "shared/kvoter/coverage-feedback.json": {"status": "waiting_for_espn", "espn_total": 0, "with_at_least_one_quote": 0, "without_quote": 0, "missing_fixtures": []},
    "shared/kvoter/tipster-status.json": {"espn": 0, "paired": 0, "unpaired": [], "failures": []},
    "shared/kvoter/coverage.json": {"total": 0, "matched": 0, "unmatched": 0, "fixtures": [], "sources": []},
    "shared/kvoter/match-report.json": {"total": 0, "matched": 0, "unavailable": 0, "matched_fixtures": [], "unmatched_fixtures": [], "publication_allowed": False},
    "shared/kvoter/matched_fixtures.json": {"total": 0, "fixtures": []},
    "shared/kvoter/unmatched_fixtures.json": {"total": 0, "fixtures": []},
    "shared/kvoter/provider-offers.json": {"offers": []},
}
TEXT_FILES = ("shared/kvoter-ponuda.txt", "docs/kvoter-ponuda.txt", "docs/scout-six-markets.txt")

def reset(root, now):
    local = now.astimezone(TZ)
    if local.time().replace(tzinfo=None) >= time(9):
        raise ValueError("Daily reset forbidden after 09:00 Sarajevo")
    today = local.date().isoformat()
    marker = root / "shared/agent/daily-reset-feedback.json"
    changed = False
    # Retry-safe: reset stale files individually, preserve all current-day data.
    for name, template in FILES.items():
        path = root/name
        if path.exists():
            try:
                existing = json.loads(path.read_text(encoding="utf-8"))
            except (ValueError, OSError):
                raise ValueError("Invalid existing daily file: "+name)
            if existing.get("date") == today:
                continue
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"date": today, **template}, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
        changed = True
    # Never overwrite current-day text after the feed has been collected.
    feed_path = root/"shared/collector-feed.json"
    feed = json.loads(feed_path.read_text(encoding="utf-8")) if feed_path.exists() else {}
    if not feed.get("football_candidates"):
        for name in TEXT_FILES:
            path=root/name
            empty="Dnevna ponuda je prazna — čeka ESPN preuzimanje poslije 09:00 Sarajevo.\n"
            if not path.exists() or path.read_text(encoding="utf-8") != empty:
                path.parent.mkdir(parents=True,exist_ok=True)
                path.write_text(empty,encoding="utf-8")
                changed=True
    marker.parent.mkdir(parents=True,exist_ok=True)
    feedback={"date": today, "feedback": "DAILY_RESET_COMPLETE", "status": "complete", "next_action": "espn_after_0900"}
    if not marker.exists() or json.loads(marker.read_text(encoding="utf-8")) != feedback:
        marker.write_text(json.dumps(feedback, indent=2)+"\n",encoding="utf-8")
        changed=True
    return changed

if __name__ == "__main__":
    changed=reset(Path("."), datetime.now(TZ))
    print("DAILY_RESET_COMPLETE" if changed else "DAILY_RESET_ALREADY_DONE")
