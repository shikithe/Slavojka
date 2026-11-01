#!/usr/bin/env python3
"""Clear yesterday's Collector JSON before the next 10:00 Sarajevo run."""
import json
from datetime import datetime, time
from pathlib import Path
from zoneinfo import ZoneInfo

TZ = ZoneInfo("Europe/Sarajevo")
FILES = (Path("shared/collector-feed.json"), Path("shared/collector-raw.json"))

def expire(now=None):
    local = (now or datetime.now(TZ)).astimezone(TZ)
    if local.time() < time(9, 59):
        print("COLLECTOR_CLEANUP_NOT_DUE")
        return False
    removed = False
    for path in FILES:
        if not path.exists():
            continue
        data = json.loads(path.read_text(encoding="utf-8"))
        date = data.get("date")
        if not date:
            raise ValueError(f"Missing Collector date: {path}")
        from datetime import date as Date
        if Date.fromisoformat(date) < local.date():
            path.unlink()
            removed = True
            print("DELETED_OLD_COLLECTOR", path)
        else:
            print("PRESERVED_CURRENT_COLLECTOR", path)
    return removed

if __name__ == "__main__":
    expire()
