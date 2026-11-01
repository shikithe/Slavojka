#!/usr/bin/env python3
"""Read-only ESPN statistics acquisition for the 16 collector soccer leagues.
Does not touch collector, selector, tickets, bank or publication.
"""
import argparse
import json
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

LEAGUES=("eng.1","esp.1","ger.1","ita.1","fra.1","ned.1","por.1","bel.1",
         "tur.1","sco.1","uefa.champions","uefa.europa","uefa.europa.conf",
         "usa.1","bra.1","arg.1")
ROOT="https://site.api.espn.com"
def fetch(url, retries=2):
    for attempt in range(retries+1):
        try:
            req=Request(url,headers={"User-Agent":"MEMARASIX-agent/0.1","Accept":"application/json"})
            with urlopen(req,timeout=18) as res:
                data=res.read(5_000_001)
            if len(data)>5_000_000:
                raise ValueError("ESPN response too large")
            return json.loads(data)
        except (HTTPError,URLError,TimeoutError,ValueError) as exc:
            if attempt==retries:
                raise RuntimeError(f"{type(exc).__name__}: {exc}") from exc
            time.sleep(1.5*(attempt+1))

def get(url,errors,label):
    try:
        return fetch(url)
    except RuntimeError as exc:
        errors.append({"source":label,"error":str(exc)})
        return None

def extract_summary(doc):
    if not isinstance(doc,dict):
        return {"available":False,"team_statistics":[]}
    box=doc.get("boxscore") or {}
    teams=box.get("players",[]) if isinstance(box,dict) else []
    teamstats=box.get("teams",[]) if isinstance(box,dict) else []
    return {
        "available":bool(doc.get("header") or box),
        "team_statistics":teamstats if isinstance(teamstats,list) else [],
        "player_groups":len(teams) if isinstance(teams,list) else 0,
        "available_sections":sorted(k for k,v in doc.items() if v not in (None,{},[]))
    }

def collect(days=14,per_league=3,as_of=None):
    now=as_of or datetime.now(timezone.utc)
    end=(now-timedelta(days=1)).strftime("%Y%m%d")
    start=(now-timedelta(days=days)).strftime("%Y%m%d")
    report={"schema_version":"agent-espn-v1","generated_at_utc":now.isoformat(),
            "range":{"start":start,"end":end},"league_count":len(LEAGUES),
            "leagues":{},"errors":[],"publication_allowed":False}
    for league in LEAGUES:
        errors=[]
        base=f"{ROOT}/apis/site/v2/sports/soccer/{league}"
        # A date range may not work in every league; use one request per day.
        events={}
        for offset in range(1,days+1):
            day=(now-timedelta(days=offset)).strftime("%Y%m%d")
            doc=get(base+"/scoreboard?"+urlencode({"dates":day,"limit":500}),errors,f"{league}/scoreboard/{day}")
            if not isinstance(doc,dict):
                continue
            for event in doc.get("events",[]):
                if (event.get("status") or {}).get("type",{}).get("state")=="post":
                    events[str(event.get("id"))]=event
            if len(events)>=per_league:
                break
            time.sleep(.15)
        standings=get(f"{ROOT}/apis/v2/sports/soccer/{league}/standings",errors,f"{league}/standings")
        samples=[]
        for event in sorted(events.values(),key=lambda e:e.get("date",""),reverse=True)[:per_league]:
            event_id=str(event["id"])
            doc=get(base+"/summary?"+urlencode({"event":event_id}),errors,f"{league}/summary/{event_id}")
            samples.append({"event_id":event_id,"date":event.get("date"),
                            "name":event.get("name"),"statistics":extract_summary(doc)})
            time.sleep(.15)
        report["leagues"][league]={
            "completed_events_found":len(events),"sample_count":len(samples),
            "standings_available":isinstance(standings,dict) and bool(standings),
            "standings_keys":sorted(standings) if isinstance(standings,dict) else [],
            "samples":samples,"errors":errors}
        report["errors"].extend(errors)
        print(f"{league}: completed={len(events)} samples={len(samples)} standings={bool(standings)} errors={len(errors)}",flush=True)
    return report

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--days",type=int,default=14)
    p.add_argument("--per-league",type=int,default=3)
    p.add_argument("--output",default="/tmp/memara-agent-test/espn-statistics.json")
    args=p.parse_args()
    if not 1<=args.days<=30 or not 1<=args.per_league<=10:
        p.error("days must be 1..30 and per-league 1..10")
    report=collect(args.days,args.per_league)
    path=Path(args.output)
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(f"Saved {path}; errors={len(report['errors'])}")
if __name__=="__main__":
    main()
