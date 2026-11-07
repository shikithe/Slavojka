#!/usr/bin/env python3
"""Read-only historical form audit driven by collector-feed.json."""
import argparse
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlencode
try:
    from agent.espn_statistics import fetch, extract_summary
except ModuleNotFoundError:
    from espn_statistics import fetch, extract_summary

ROOT="https://site.api.espn.com/apis/site/v2/sports"
def verified_scores(event):
    """Only retain scores supplied by a finished ESPN scoreboard event."""
    if (event.get("status") or {}).get("type",{}).get("state")!="post":
        return None
    competition=(event.get("competitions") or [{}])[0]
    home=away=None
    for competitor in competition.get("competitors",[]):
        side=competitor.get("homeAway")
        value=competitor.get("score")
        if side=="home" and value is not None: home=value
        if side=="away" and value is not None: away=value
    return {"home":home,"away":away} if home is not None and away is not None else None
def build(feed, request=fetch, days=120, last=5):
    if not isinstance(feed,dict):
        raise ValueError("Feed must be an object")
    fixtures=feed.get("football_candidates",[])
    if not isinstance(fixtures,list):
        raise ValueError("football_candidates must be an array")
    leagues={}
    for f in fixtures:
        if f.get("sport")!="football" or f.get("status", "pre")!="pre":
            continue
        league=f.get("league")
        if not league or not f.get("home") or not f.get("away"):
            continue
        leagues.setdefault(league,set()).update([f["home"],f["away"]])
    now=datetime.now(timezone.utc)
    result={"schema_version":"agent-five-matches-v2","date":feed.get("date"),"generated_at_utc":now.isoformat(),
            "target_matches_per_team":last,"fixtures":[f for f in fixtures if f.get("sport")=="football" and f.get("status","pre")=="pre"],"leagues":{},"head_to_head":{},"errors":[],
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
                             "competition":league,"scores":verified_scores(e),
                             "statistics":summaries[event_id]})
            per_team[name]={"found":len(rows),"complete":len(rows)==last,"matches":rows}
        # H2H: inspect saved completed fixtures first; then fill historical meetings
        # from each home team's season schedule (up to three seasons) when possible.
        for fixture in result["fixtures"]:
            if fixture.get("league") != league:
                continue
            home,away=fixture["home"],fixture["away"]
            pair_key=fixture["fixture_id"]
            pair_events={}
            def add_meeting(event):
                comps=(event.get("competitions") or [{}])[0].get("competitors",[])
                names={c.get("team",{}).get("displayName") for c in comps}
                state=(event.get("status") or {}).get("type",{}).get("state")
                if {home,away}.issubset(names) and state=="post":
                    pair_events[str(event["id"])]=event
            for event in events.values():
                add_meeting(event)
            team_id=None
            for item in per_team.get(home,{}).get("matches",[]):
                for team in item.get("statistics",{}).get("team_statistics",[]):
                    if team.get("team",{}).get("displayName")==home:
                        team_id=team.get("team",{}).get("id")
                        break
                if team_id:break
            if team_id and len(pair_events)<5:
                for season in (now.year,now.year-1,now.year-2,now.year-3):
                    try:
                        schedule=request(f"{ROOT}/soccer/{league}/teams/{team_id}/schedule?"+urlencode({"season":season}))
                        for event in schedule.get("events",[]):
                            add_meeting(event)
                    except Exception as exc:
                        errors.append({"fixture_id":pair_key,"season":season,"h2h_error":str(exc)})
                    if len(pair_events)>=5:break
            records=[]
            for event in sorted(pair_events.values(),key=lambda e:e.get("date",""),reverse=True)[:5]:
                competitors=(event.get("competitions") or [{}])[0].get("competitors",[])
                def side(name):
                    for c in competitors:
                        if c.get("team",{}).get("displayName")==name:
                            return {"name":name,"home_away":c.get("homeAway"),"score":c.get("score")}
                    return {"name":name,"score":None}
                eid=str(event["id"])
                if eid not in summaries:
                    try:
                        summaries[eid]=extract_summary(request(f"{ROOT}/soccer/{league}/summary?"+urlencode({"event":eid})))
                    except Exception as exc:
                        errors.append({"fixture_id":pair_key,"event_id":eid,"h2h_error":str(exc)})
                        summaries[eid]={"available":False,"team_statistics":[]}
                records.append({"event_id":eid,"date":event.get("date"),
                    "home_team":side(home),"away_team":side(away),
                    "statistics":summaries[eid]})
            result["head_to_head"][pair_key]={"home":home,"away":away,"found":len(records),
                "complete":len(records)==5,"matches":records}
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
