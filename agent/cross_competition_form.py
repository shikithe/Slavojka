#!/usr/bin/env python3
"""Enrich Champions/Europa team form using their domestic and UEFA matches."""
import argparse
import json
import re
from datetime import datetime, timezone, timedelta
from pathlib import Path
from urllib.parse import urlencode
from agent.espn_statistics import fetch, extract_summary

ROOT="https://site.api.espn.com/apis/site/v2/sports/soccer"
EUROPE={"uefa.champions","uefa.europa","uefa.europa.conf"}
DOMESTIC=("eng.1","esp.1","ger.1","ita.1","fra.1","ned.1","por.1",
          "bel.1","tur.1","sco.1","aut.1","sui.1","gre.1","den.1",
          "nor.1","swe.1","cze.1","pol.1","ukr.1","cro.1","ser.1")
def normalize(name):
    return re.sub(r"[^a-z0-9]","",str(name).casefold()
                  .replace("ü","u").replace("ö","o").replace("ä","a"))
def iso(value):
    return datetime.fromisoformat(str(value).replace("Z","+00:00")).astimezone(timezone.utc)
def competitors(event):
    return (event.get("competitions") or [{}])[0].get("competitors") or []
def team_id(event,name):
    for c in competitors(event):
        team=c.get("team") or {}
        if normalize(team.get("displayName"))==normalize(name):
            return str(team.get("id")) if team.get("id") else None
    return None
def events_for_team(schedule, team_name, cutoff, days):
    found=[]
    for event in schedule.get("events",[]):
        try:
            if not (cutoff-timedelta(days=days) <= iso(event["date"]) < cutoff):
                continue
            if (event.get("status") or {}).get("type",{}).get("state")!="post":
                continue
            if team_id(event,team_name) is None and normalize(team_name) not in {
                normalize(c.get("team",{}).get("displayName")) for c in competitors(event)}:
                continue
            found.append(event)
        except (KeyError,TypeError,ValueError):
            continue
    return found
def augment(result, request=fetch, days=120, now=None):
    now=now or datetime.now(timezone.utc)
    target=result.get("target_matches_per_team",5)
    summary_cache={}
    teams_cache={}
    schedules={}
    result.setdefault("errors",[])
    result["form_scope"]="UEFA teams: five latest completed matches across domestic and UEFA competitions"
    for league,group in result.get("leagues",{}).items():
        if league not in EUROPE:
            continue
        teams=group.get("teams",{})
        # Resolve club IDs from the UEFA scoreboard for the day of the selected fixture.
        current={}
        for f in result.get("fixtures",[]):
            if f.get("league")!=league:continue
            key=f.get("start_utc","")[:10].replace("-","")
            if not key:continue
            if key not in teams_cache:
                try:
                    teams_cache[key]=request(ROOT+"/"+league+"/scoreboard?"+urlencode({"dates":key,"limit":500}))
                except Exception as exc:
                    result["errors"].append({"league":league,"stage":"uefa_team_ids","error":str(exc)})
                    teams_cache[key]={}
            for event in teams_cache[key].get("events",[]):
                for name in (f.get("home"),f.get("away")):
                    if name and name not in current:
                        ident=team_id(event,name)
                        if ident:current[name]=ident
        for name,entry in teams.items():
            collected={}
            # Retain original UEFA results, including their ESPN summary.
            for row in entry.get("matches",[]):
                try:
                    stamp=iso(row["date"])
                    if now-timedelta(days=days)<=stamp<now:
                        collected[str(row["event_id"])]=dict(row,competition=league)
                except (KeyError,ValueError):
                    continue
            ident=current.get(name)
            if not ident:
                entry["cross_competition_note"]="UEFA team ID unresolved; domestic form not verified"
                continue
            for domestic in DOMESTIC:
                key=(domestic,ident)
                if key not in schedules:
                    try:
                        schedules[key]=request(ROOT+"/"+domestic+"/teams/"+ident+"/schedule?"+
                                               urlencode({"season":now.year}))
                    except Exception:
                        schedules[key]={}
                doc=schedules[key]
                # Prevent falsely joining clubs with identical numeric IDs across leagues.
                doc_team=(doc.get("team") or {}).get("displayName")
                if doc_team and normalize(doc_team)!=normalize(name):
                    continue
                for event in events_for_team(doc,name,now,days):
                    eventid=str(event.get("id",""))
                    if not eventid or eventid in collected:
                        continue
                    try:
                        eid=iso(event["date"])
                        if eid>=now:continue
                        summary_key=(domestic,eventid)
                        if summary_key not in summary_cache:
                            summary_cache[summary_key]=extract_summary(request(
                                ROOT+"/"+domestic+"/summary?"+urlencode({"event":eventid})))
                        collected[eventid]={"event_id":eventid,"date":event["date"],
                                           "name":event.get("name"),
                                           "competition":domestic,
                                           "statistics":summary_cache[summary_key]}
                    except Exception as exc:
                        result["errors"].append({"league":league,"team":name,
                                                 "stage":"domestic_summary","event_id":eventid,
                                                 "error":str(exc)})
                if len(collected)>=target:
                    # Continue only if no more plausible newer domestic matches would be found.
                    pass
            rows=sorted(collected.values(),key=lambda x:x.get("date",""),reverse=True)[:target]
            entry.update({"matches":rows,"found":len(rows),"complete":len(rows)==target,
                          "form_scope":"all verified competitions",
                          "competitions_used":sorted({x.get("competition",league) for x in rows})})
    return result

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--input",required=True)
    p.add_argument("--output",required=True)
    p.add_argument("--days",type=int,default=120)
    args=p.parse_args()
    path=Path(args.input)
    data=json.loads(path.read_text(encoding="utf-8"))
    augment(data,days=args.days)
    output=Path(args.output)
    output.parent.mkdir(parents=True,exist_ok=True)
    output.write_text(json.dumps(data,ensure_ascii=False,indent=2)+"\\n",encoding="utf-8")
    for league in EUROPE & data.get("leagues",{}).keys():
        teams=data["leagues"][league]["teams"]
        print("CROSS_COMPETITION",league,"complete",sum(t["complete"] for t in teams.values()),"of",len(teams))
if __name__=="__main__":
    main()
