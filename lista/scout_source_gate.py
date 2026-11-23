#!/usr/bin/env python3
"""Daily source readiness guard; never treat yesterday's history as current."""
import json
import os
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

TZ = ZoneInfo("Europe/Sarajevo")

def is_ready(feed, active, history, date):
    if any(not isinstance(x, dict) or x.get("date") != date for x in (feed, active)):
        return False, "ESPN and odds lists must be current"
    fixtures = feed.get("football_candidates", [])
    if not fixtures:
        return False, "empty ESPN feed"
    ids = [x.get("fixture_id") for x in fixtures]
    if None in ids or len(set(ids)) != len(ids):
        return False, "duplicate or missing ESPN fixture ID"
    if {x.get("fixture_id") for x in active.get("fixtures", [])} != set(ids):
        return False, "TipsterArea missing current ESPN fixtures"
    if not isinstance(history, dict) or history.get("date") != date or {x.get("fixture_id") for x in history.get("fixtures", [])} != set(ids):
        return True, "DEGRADED: fresh ESPN/odds available; no usable same-day history (low confidence)"
    return True, "all source files are current"

def main():
    today = datetime.now(TZ).date().isoformat()
    def load(p):
        try:
            return json.loads(Path(p).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
    ready, reason = is_ready(load("shared/collector-feed.json"),
                             load("shared/active-list.json"),
                             load("shared/agent/history-h2h.json"), today)
    print("SCOUT_SOURCE_READY" if ready else "SCOUT_WAIT_HISTORY_OR_QUOTES", reason)
    if os.getenv("GITHUB_OUTPUT"):
        with open(os.environ["GITHUB_OUTPUT"], "a") as f:
            f.write("ready=" + ("true" if ready else "false") + "\n")
    return ready

if __name__ == "__main__":
    main()
