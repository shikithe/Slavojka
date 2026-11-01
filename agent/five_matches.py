#!/usr/bin/env python3
"""Read-only historical form audit driven by collector-feed.json."""
import argparse
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlencode
from espn_statistics import fetch, extract_summary

ROOT="https://site.api.espn.com/apis/site/v2/sports"
def build(feed, request=fetch, days=120, last=5):
    if not isinstance(feed,dict):
        raise ValueError("Feed must be an object")
    fixtures=feed.get("football_candidates",[])
    if not isinstance(fixtures,list):
        raise ValueError("football_candidates must be an array")
    leagues={}
    for f in fixtures:
        if f.get("sport")!="football" or f.get("status")!="pre":
            continue
        league=f.get("league")
        if not league or not f.get("home") or not f.get("away"):
            continue
        leagues.setdefault(league,set()).update([f["home"],f["away"]])
    now=datetime.now(timezone.utc)
    result={"schema_version":"agent-five-matches-v1","generated_at_utc":now.isoformat(),
            "target_matches_per_team":last,"leagues":{},"errors":[],
            "publication_allowed":False,"bank_modified":False}
    for league,team_names in sorted(leagues.items()):
        events={}
        errors=[]
        # Request one day at a time, because some ESPN soccer leagues reject ranges.
        # Stop only once every team has at least five matches, or history is exhausted.
        for offset in range(1,days+1):
            date=(now-timedelta(days=offset)).strftime("%Y%m%d")
            url=f"{ROOT}/soccer/{league}/scoreboard?"+urlencode({"dates":date,"limit":500})
            try:
                doc=request(url)
                for e in doc.get("events",[]):
                    if (e.get("status") or {}).get("type",{}).get("state")=="post":
                        events[str(e["id"])]=e
            except Exception as exc:
                errors.append({"date":date,"error":str(exc)})
            counts={name:0 for name in team_names}
            for e in events.values():
                comps=(e.get("competitions") or [{}])[0].get("competitors",[])
                names={c.get("team",{}).get("displayName") for c in comps}
                for name in names & team_names:
                    counts[name]+=1
            if all(n>=last for n in counts.values()):
                break
        per_team={}
        summaries={}
        for name in sorted(team_names):
            matches=[]
            for e in events.values():
                comps=(e.get("competitions") or [{}])[0].get("competitors",[])
                if name in {c.get("team",{}).get("displayName") for c in comps}:
                    matches.append(e)
            matches=sorted(matches,key=lambda e:e.get("date",""),reverse=True)[:last]
            rows=[]
            for e in matches:
                event_id=str(e["id"])
                if event_id not in summaries:
                    try:
                        summaries[event_id]=extract_summary(request(f"{ROOT}/soccer/{league}/summary?"+urlencode({"event":event_id})))
                    except Exception as exc:
                        errors.append({"event_id":event_id,"error":str(exc)})
                        summaries[event_id]={"available":False,"team_statistics":[]}
                rows.append({"event_id":event_id,"date":e.get("date"),"name":e.get("name"),
                             "statistics":summaries[event_id]})
            per_team[name]={"found":len(rows),"complete":len(rows)==last,"matches":rows}
        result["leagues"][league]={"teams":per_team,"source_errors":errors,
                                   "completed_events_scanned":len(events)}
        result["errors"].extend({"league":league,**err} for err in errors)
    return result

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--input",required=True)
    p.add_argument("--output",required=True)
    p.add_argument("--days",type=int,default=120)
    a=p.parse_args()
    if not 5<=a.days<=365:
        p.error("--days must be 5..365")
    feed=json.loads(Path(a.input).read_text(encoding="utf-8"))
    result=build(feed,days=a.days)
    path=Path(a.output)
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    for league,d in result["leagues"].items():
        print(league, "teams=",len(d["teams"]),"complete=",sum(x["complete"] for x in d["teams"].values()),"errors=",len(d["source_errors"]))
    print("TOTAL_ERRORS",len(result["errors"]))
if __name__=="__main__":
    main()
