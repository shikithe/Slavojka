#!/usr/bin/env python3
"""Isolated ESPN rolling 23h59m fixture collection. Never writes live site data."""
import argparse
import importlib.util
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

BASE = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("memara_base_collector", BASE / "collector.py")
base = importlib.util.module_from_spec(spec)
spec.loader.exec_module(base)
WINDOW = timedelta(hours=23, minutes=59)

def collect(now=None, leagues=None):
    now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    until = now + WINDOW
    selected = [("football", "soccer", league) for league in (leagues or base.FOOTBALL)]
    selected.append(("basketball", "basketball", "nba"))
    dates = []
    day = now.date()
    while day <= until.date():
        dates.append(day.strftime("%Y%m%d"))
        day += timedelta(days=1)
    fixtures, sources, errors = [], [], []
    for sport, category, league in selected:
        for date_str in dates:
            url = f"{base.ROOT}/{category}/{league}/scoreboard?" + urlencode({"dates": date_str, "limit": 500})
            try:
                with urlopen(Request(url, headers={"User-Agent":"MEMARA-Isolated-Collector/1.0", "Accept":"application/json"}), timeout=12) as response:
                    raw = response.read(8 * 1024 * 1024 + 1)
                if len(raw) > 8 * 1024 * 1024:
                    raise ValueError("response too large")
                events = json.loads(raw)["events"]
                if not isinstance(events, list):
                    raise ValueError("events is not a list")
                accepted = 0
                for event in events:
                    try:
                        competition = event["competitions"][0]
                        kickoff = base.timestamp(event.get("date") or competition["date"])
                        if not (now <= kickoff < until):
                            continue
                        normalized = base.normalized(event, sport, league, kickoff.astimezone(base.ZONE).date())
                        if normalized and normalized["status"] == "pre":
                            fixtures.append(normalized)
                            accepted += 1
                    except (KeyError, IndexError, TypeError, ValueError, AttributeError):
                        continue
                sources.append({"league":league,"date":date_str,"status":"ok","count":accepted})
            except (OSError, ValueError, KeyError, TypeError) as exc:
                sources.append({"league":league,"date":date_str,"status":"error","count":0})
                errors.append(f"{league}/{date_str}: {type(exc).__name__}: {exc}")
    unique = {item["id"]: item for item in fixtures}
    return {
        "schema_version":"rolling-24h-test-v1",
        "date":now.astimezone(base.ZONE).date().isoformat(),
        "window_start_utc":now.isoformat(),
        "window_end_utc":until.isoformat(),
        "fixture_count":len(unique),
        "fixtures":sorted(unique.values(), key=lambda x:x["start_utc"]),
        "sources":sources,
        "errors":errors,
        "status":"partial" if errors else "ok",
        "publication_allowed":False
    }

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output",default="/tmp/memara-collector-test/collector-raw.json")
    parser.add_argument("--now-utc",help="Fixed ISO UTC timestamp for repeatable tests")
    args = parser.parse_args()
    now = base.timestamp(args.now_utc) if args.now_utc else None
    result = collect(now)
    target = Path(args.output)
    target.parent.mkdir(parents=True,exist_ok=True)
    target.write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({"window_start":result["window_start_utc"],"window_end":result["window_end_utc"],"fixtures":result["fixture_count"],"errors":len(result["errors"])},ensure_ascii=False))
    return 0 if result["fixture_count"] else 2

if __name__=="__main__":
    sys.exit(main())
