#!/usr/bin/env python3
"""Expire previous-day transient ListaSix data at/after 08:55 Sarajevo."""
import json
from datetime import date, datetime, time
from pathlib import Path
from zoneinfo import ZoneInfo

TZ=ZoneInfo("Europe/Sarajevo")
TRANSIENT=[
 "shared/collector-feed.json","shared/collector-raw.json",
 "shared/agent/history-h2h.json",
 "shared/kvoter/provider-offers.json","shared/kvoter/league-odds-raw.json",
 "shared/kvoter/match-report.json","shared/kvoter/matched_fixtures.json",
 "shared/kvoter/unmatched_fixtures.json","shared/kvoter/manual-candidates.json",
 "shared/active-list.json","shared/kvoter-ponuda.txt",
 "docs/active-list.json","docs/kvoter-ponuda.txt",
 "docs/manual-candidates.json","docs/unmatched_fixtures.json",
]
def expire(now=None):
    local=(now or datetime.now(TZ)).astimezone(TZ)
    if local.time()<time(8,55):
        print("LISTASIX_CLEANUP_NOT_DUE")
        return False
    feed=Path("shared/collector-feed.json")
    if not feed.exists():
        print("NO_COLLECTOR_FEED_TO_EXPIRE")
        return False
    info=json.loads(feed.read_text(encoding="utf-8"))
    if date.fromisoformat(info["date"])>=local.date():
        print("PRESERVED_CURRENT_DAY_DATA")
        return False
    removed=[]
    for name in TRANSIENT:
        path=Path(name)
        if path.exists():
            path.unlink()
            removed.append(name)
    for name in ("shared/agent/.last-processed-sha256","shared/agent/.validated-collector-feed.json"):
        Path(name).unlink(missing_ok=True)
    print("EXPIRED_PREVIOUS_DAY_DATA",len(removed))
    return bool(removed)
if __name__=="__main__":
    expire()
