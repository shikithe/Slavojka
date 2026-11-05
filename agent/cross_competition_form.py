#!/usr/bin/env python3
"""Find each playing club's last five finished ESPN matches across competitions.

Sources include league seasons, domestic cups, UEFA competitions and club friendlies.
An empty/unsupported ESPN source is not invented as a completed match. Teams are
identified by ESPN's league team directories and exact normalized names; the UEFA
scoreboard ID is *not* a prerequisite for domestic form.
"""
import argparse
import json
import re
import unicodedata
from collections import defaultdict
from datetime import datetime, timezone, timedelta
from pathlib import Path
from urllib.parse import urlencode
from agent.espn_statistics import fetch, extract_summary

ROOT="https://site.api.espn.com/apis/site/v2/sports/soccer"
EUROPE=("uefa.champions","uefa.europa","uefa.europa.conf",
        "uefa.champions_qual","uefa.europa_qual","uefa.europa.conf_qual",
        "uefa.super_cup")
DOMESTIC=("eng.1","eng.2","esp.1","esp.2","ger.1","ger.2","ita.1",
          "ita.2","fra.1","fra.2","ned.1","ned.2","por.1",
          "bel.1","tur.1","sco.1","sco.2","aut.1","sui.1","gre.1",
          "den.1","nor.1","swe.1","cze.1","pol.1","ukr.1",
          "cro.1","ser.1","cyp.1","irl.1","bra.1","arg.1")
CUPS=("eng.fa","eng.league_cup","eng.charity","esp.copa_del_rey",
      "esp.super_cup","ger.dfb_pokal","ger.super_cup",
      "ita.coppa_italia","ita.super_cup","fra.coupe_de_france",
      "fra.super_cup","ned.cup","ned.supercup","por.taca.portugal",
      "sco.tennents","sco.cis","arg.copa","bra.copa_do_brazil")
OTHER=("club.friendly",)
COMPETITIONS=tuple(dict.fromkeys(DOMESTIC+CUPS+EUROPE+OTHER))


def normalize(name):
    text=unicodedata.normalize("NFKD",str(name or "").casefold().replace("ı","i").replace("ø","o"))
    return re.sub(r"[^a-z0-9]","",text.encode("ascii","ignore").decode("ascii"))


def iso(value):
    result=datetime.fromisoformat(str(value).replace("Z","+00:00"))
    if result.tzinfo is None:
        result=result.replace(tzinfo=timezone.utc)
    return result.astimezone(timezone.utc)


def competitors(event):
    return (event.get("competitions") or [{}])[0].get("competitors") or []


def team_id(event,name):
    for c in competitors(event):
        team=c.get("team") or {}
        if normalize(team.get("displayName"))==normalize(name):
            return str(team.get("id")) if team.get("id") else None
    return None


def events_for_team(schedule,team_name,cutoff,days):
    found=[]
    for event in schedule.get("events",[]):
        try:
            if not cutoff-timedelta(days=days)<=iso(event["date"])<cutoff:
                continue
            if (event.get("status") or {}).get("type",{}).get("state")!="post":
                continue
            names={normalize((c.get("team") or {}).get("displayName")) for c in competitors(event)}
            if normalize(team_name) not in names:
                continue
            if not event.get("id"):
                continue
            found.append(event)
        except (KeyError,TypeError,ValueError):
            continue
    return found


def club_names(info):
    return [info.get(field) for field in ("displayName","shortDisplayName","name")
            if isinstance(info.get(field),str) and normalize(info[field])]


def directory_index(doc):
    index=defaultdict(list)
    listed=[]
    for sport in doc.get("sports",[]):
        for grp in sport.get("leagues",[]):
            listed.extend(grp.get("teams",[]))
    # Also accept the direct list representation some ESPN competitions provide.
    listed.extend(doc.get("teams",[]))
    for item in listed:
        info=item.get("team",item)
        if not isinstance(info,dict) or not info.get("id"):
            continue
        for name in club_names(info):
            normalized=normalize(name)
            pair=(str(info["id"]),info.get("displayName") or name)
            if pair not in index[normalized]:
                index[normalized].append(pair)
    return index


def event_scores(event):
    scores={}
    for c in competitors(event):
        side=c.get("homeAway")
        if side in ("home","away") and c.get("score") is not None:
            scores[side]=c["score"]
    return scores


def augment(result,request=fetch,days=120,now=None):
    now=now or datetime.now(timezone.utc)
    target=result.get("target_matches_per_team",5)
    directories={}
    schedules={}
    summaries={}
    errors=result.setdefault("errors",[])
    result["form_scope"]="Last five finished matches across available ESPN club competitions"
    result["form_competitions_scanned"]=list(COMPETITIONS)

    all_teams={name for group in result.get("leagues",{}).values()
               for name in group.get("teams",{})}
    # Build ESPN club directory once per competition, not once per team.
    index=defaultdict(list)
    for competition in COMPETITIONS:
        try:
            doc=request(ROOT+"/"+competition+"/teams?"+urlencode({"limit":500}))
            directories[competition]=directory_index(doc)
            for name,pairs in directories[competition].items():
                for teamid,display in pairs:
                    index[name].append((competition,teamid,display))
        except Exception as exc:
            errors.append({"stage":"team_directory","competition":competition,
                           "error":str(exc)[:180]})
            directories[competition]={}

    # The original single-league results were already fetched by five_matches.py.
    for league,group in result.get("leagues",{}).items():
        for name,entry in group.get("teams",{}).items():
            collected={}
            for row in entry.get("matches",[]):
                try:
                    stamp=iso(row["date"])
                    if now-timedelta(days=days)<=stamp<now and row.get("event_id"):
                        existing=dict(row)
                        existing.setdefault("competition",league)
                        collected[str(row["event_id"])]=existing
                except (KeyError,ValueError,TypeError):
                    continue
            matched_competitions=[]
            # Club names in ESPN can differ across competition team directories.
            # Never silently approve fuzzy identity; allow exact normalized identity
            # and IDs provided by the same ESPN competition.
            matches=index.get(normalize(name),[])
            for competition,teamid,display in matches:
                matched_competitions.append(competition)
                key=(competition,teamid)
                if key not in schedules:
                    schedules[key]={}
                    try:
                        schedules[key]=request(ROOT+"/"+competition+"/teams/"+teamid+
                                               "/schedule?"+urlencode({"season":now.year}))
                    except Exception as exc:
                        errors.append({"stage":"team_schedule","competition":competition,
                                       "team":name,"error":str(exc)[:180]})
                schedule=schedules[key]
                display_name=(schedule.get("team") or {}).get("displayName")
                if display_name and normalize(display_name)!=normalize(name):
                    # A different club resolved in a team directory: fail closed.
                    continue
                for event in events_for_team(schedule,display,now,days):
                    eventid=str(event["id"])
                    previous=collected.get(eventid)
                    if not previous or iso(event["date"])>iso(previous["date"]):
                        collected[eventid]={
                            "event_id":eventid,"date":event["date"],
                            "name":event.get("name"),"competition":competition,
                            "scores":event_scores(event),
                            "_source_competition":competition}
            # Request detailed stats ONLY for the last five, avoiding summaries
            # for games that will never appear in the current form window.
            rows=sorted(collected.values(),key=lambda x:x.get("date",""),reverse=True)[:target]
            for row in rows:
                source=row.pop("_source_competition",None)
                if source and "statistics" not in row:
                    cache_key=(source,row["event_id"])
                    if cache_key not in summaries:
                        try:
                            summaries[cache_key]=extract_summary(request(
                                ROOT+"/"+source+"/summary?"+urlencode({"event":row["event_id"]})))
                        except Exception as exc:
                            errors.append({"stage":"match_summary","team":name,
                                           "competition":source,"event_id":row["event_id"],
                                           "error":str(exc)[:180]})
                            summaries[cache_key]={"available":False,"team_statistics":[]}
                    row["statistics"]=summaries[cache_key]
            entry.update({"matches":rows,"found":len(rows),"complete":len(rows)==target,
                          "form_scope":"available ESPN competitions",
                          "competitions_used":sorted({x.get("competition",league) for x in rows}),
                          "competitions_matched":sorted(set(matched_competitions))})
            if len(rows)<target:
                entry["cross_competition_note"]=(
                    "Fewer than five finished ESPN games verified across available competitions"
                    if matches else "Club not resolved in available ESPN competition directories")
            else:
                entry.pop("cross_competition_note",None)
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
    output.write_text(json.dumps(data,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    for league,group in data.get("leagues",{}).items():
        teams=group["teams"]
        print("CROSS_COMPETITION",league,"complete",
              sum(t["complete"] for t in teams.values()),"of",len(teams))
if __name__=="__main__":
    main()
