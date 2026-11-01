#!/usr/bin/env python3
"""ListaSix Collector: fixed Sarajevo 11:00-to-11:00 ESPN fixture window."""
import json
import os
import sys
from datetime import datetime, time, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo
from collector.collector_24h import collect

TZ=ZoneInfo("Europe/Sarajevo")
ROOT=Path(os.environ.get("LISTASIX_SHARED","shared"))
def window(now=None):
    local=(now or datetime.now(TZ)).astimezone(TZ)
    start=datetime.combine(local.date(),time(11),tzinfo=TZ)
    end=datetime.combine(local.date()+timedelta(days=1),time(11),tzinfo=TZ)
    return start,end
def main():
    start,end=window()
    # Query the complete 11:00-to-next-11:00 window, not a rolling 24h interval.
    raw=collect(start.astimezone(timezone.utc), end_utc=end.astimezone(timezone.utc), football_only=True)
    raw["date"]=start.date().isoformat()
    raw["window_start_local"]=start.isoformat()
    raw["window_end_local"]=end.isoformat()
    raw["data_expires_at_utc"]=end.astimezone(timezone.utc).isoformat()
    raw["publication_allowed"]=False
    football=[{"fixture_id":f["id"],"home":f["home"],"away":f["away"],"league":f["league"],"start_utc":f["start_utc"],"sport":"football"} for f in raw["fixtures"] if f["sport"]=="football"]
    feed={"date":raw["date"],"generated_at_utc":datetime.now(timezone.utc).isoformat(),
          "window_start_utc":raw["window_start_utc"],"window_end_utc":raw["window_end_utc"],
          "expires_at_utc":raw["data_expires_at_utc"],"football_candidates":football,
          "nba_games":[],"errors":raw["errors"],"publication_allowed":False}
    ROOT.mkdir(parents=True,exist_ok=True)
    if not football:
        print("COLLECTOR_EMPTY: keeping previous active database unchanged",file=sys.stderr)
        return 2
    for name,data in (("collector-raw.json",raw),("collector-feed.json",feed)):
        dest=ROOT/name
        temp=ROOT/(name+".tmp")
        temp.write_text(json.dumps(data,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
        temp.replace(dest)
    print("LISTASIX_COLLECTED",len(football),"ERRORS",len(raw["errors"]),"EXPIRES",end.isoformat())
    return 0
if __name__=="__main__":
    sys.exit(main())
