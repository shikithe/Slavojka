#!/usr/bin/env python3
"""Build today's real football last-five history from ESPN public scoreboards.

Must not invent missing form/xG: returns found=0 when public ESPN results are
unavailable. League/day/fixture IDs always come from today's Slavojka ESPN feed.
"""
import json
import re
import time
import unicodedata
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from difflib import SequenceMatcher
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

TZ = ZoneInfo("Europe/Sarajevo")
BASE = "https://site.api.espn.com/apis/site/v2/sports/soccer/"
USER_AGENT = "ListaSix scout-history 1.0 (+public ESPN scoreboard)"
ALIASES = {
    "paris saint germain":"psg","1 fc union berlin":"union berlin",
    "fc utrecht":"utrecht", "fc groningen":"groningen",
    "racing genk":"genk","st mirren":"saint mirren",
    "sint truidense":"sint truiden","st truidense":"sint truiden",
    "heart of midlothian":"hearts","borussia monchengladbach":"monchengladbach",
    "nec nijmegen":"nec", "psv eindhoven":"psv",
    "feyenoord rotterdam":"feyenoord", "new england revolution":"new england",
    "inter miami cf":"inter miami", "kvc westerlo":"westerlo",
    "royal charleroi sc":"charleroi","fc dallas":"dallas",
    "caykur rizespor":"rizespor", "sv elversberg":"elversberg",
    "sc paderborn 07":"paderborn","sc freiburg":"freiburg",
    "1 fc cologne":"cologne", "fc cologne":"cologne",
    "vfb stuttgart":"stuttgart", "tsg hoffenheim":"hoffenheim",
    "ra al la louviere":"raal la louviere",
}
def norm(value):
    a = unicodedata.normalize("NFKD", str(value).casefold())
    a = "".join(c for c in a if not unicodedata.combining(c))
    a = re.sub(r"[^a-z0-9]+", " ", a).strip()
    a = re.sub(r"\s+", " ", a)
    a = ALIASES.get(a, a)
    a = re.sub(r"^(?:fc|ac|as|sc|sv|fk|afc) ", "", a)
    a = re.sub(r" (?:fc|cf|afc|sc)$", "", a)
    return ALIASES.get(a, a)

def similarity(a, b):
    a, b = norm(a), norm(b)
    if a == b:
        return 1.0
    if not a or not b:
        return 0.0
    return SequenceMatcher(None, a, b).ratio()

def get_scoreboard(league, season_month):
    url = BASE + league + "/scoreboard?" + urlencode({"dates": season_month, "limit": 500})
    req = Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    with urlopen(req, timeout=35) as response:
        raw = response.read(15_000_000)
    return json.loads(raw).get("events", [])

def get_team_schedule(team_id, season_year):
    """ESPN all-competitions team feed, including domestic and UEFA results."""
    if not re.fullmatch(r"\d{1,9}", str(team_id)):
        raise ValueError("Unverified ESPN team id")
    url = BASE + "all/teams/" + str(team_id) + "/schedule?" + urlencode({"dates":str(season_year)})
    req = Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    with urlopen(req, timeout=30) as response:
        raw = response.read(15_000_000)
    events = json.loads(raw).get("events", [])
    if not isinstance(events, list):
        raise ValueError("Invalid ESPN schedule data")
    return events


def scoreboard_team_ids(event):
    """Only an original ESPN event identifies the correct home/away club IDs."""
    try:
        comp=event["competitions"][0]
        members={}
        for member in comp["competitors"]:
            side=member["homeAway"]
            team=member["team"]
            if side in ("home","away") and str(team["id"]).isdigit():
                members[side]={"id":str(team["id"]), "name":team.get("displayName",team.get("name",""))}
        if len(members)==2:
            return members
    except (KeyError, TypeError, IndexError):
        pass
    return None


def parsed_event(event, league, today):
    try:
        comp = event["competitions"][0]
        if not comp.get("competitors"):
            return None
        home = next(x for x in comp["competitors"] if x["homeAway"] == "home")
        away = next(x for x in comp["competitors"] if x["homeAway"] == "away")
        status = event.get("status", {}).get("type", {})
        if not status.get("completed", False):
            return None
        event_at = datetime.fromisoformat(event["date"].replace("Z","+00:00"))
        if event_at.date() >= today:
            return None
        def score(c):
            v = c.get("score")
            if isinstance(v, dict):
                v = v.get("value", v.get("displayValue"))
            return int(float(v))
        return {"event_id":str(event["id"]), "date":event["date"],
                "league":league,
                "source_competition": (event.get("season") or {}).get("displayName",league),
                "home_team_id":str(home["team"].get("id", "")),
                "away_team_id":str(away["team"].get("id", "")),
                "home":home["team"].get("displayName", home["team"].get("name","")),
                "away":away["team"].get("displayName", away["team"].get("name","")),
                "home_goals":score(home),"away_goals":score(away)}
    except (KeyError, TypeError, StopIteration, ValueError):
        return None

def league_results(league, today):
    # Month queries efficiently return full league seasons with a bounded limit.
    months = []
    for offset in range(3):
        d = (today.replace(day=1) - timedelta(days=offset*31)).replace(day=1)
        stamp = d.strftime("%Y%m")
        if stamp not in months:
            months.append(stamp)
    events = {}
    errors = []
    fixture_team_ids = {}
    for stamp in months:
        try:
            raw = get_scoreboard(league, stamp)
            for entry in raw:
                teams=scoreboard_team_ids(entry)
                if teams and entry.get("id") is not None:
                    fixture_team_ids[str(entry["id"])] = teams
                parsed = parsed_event(entry,league,today)
                if parsed:
                    events[parsed["event_id"]] = parsed
        except Exception as error:
            errors.append({"league":league,"month":stamp,"error":str(error)[:180]})
        time.sleep(0.25)
    return league,list(events.values()),errors,fixture_team_ids

def team_form(team, results, team_id=None):
    matches=[]
    for r in results:
        # When the club's ID came from the exact scheduled ESPN fixture,
        # never attach a match simply because a similarly named club appears.
        if team_id:
            home=float(r.get("home_team_id")==str(team_id))
            away=float(r.get("away_team_id")==str(team_id))
        else:
            home=similarity(team,r["home"])
            away=similarity(team,r["away"])
        if home >= 0.87 and (home > away + 0.10):
            goals_for, goals_against = r["home_goals"],r["away_goals"]
            side="home"
        elif away >= 0.87 and (away > home + 0.10):
            goals_for, goals_against = r["away_goals"],r["home_goals"]
            side="away"
        else:
            continue
        matches.append({**r,"side":side,"goals_for":goals_for,
                        "goals_against":goals_against, "total_goals":r["home_goals"]+r["away_goals"],
                        "points":3 if goals_for>goals_against else (1 if goals_for==goals_against else 0)})
    matches.sort(key=lambda x:x["date"],reverse=True)
    last=matches[:5]
    return {"found":len(last),"complete":len(last)>=5, "matches":last,
            "goals_for":sum(x["goals_for"] for x in last),
            "goals_against":sum(x["goals_against"] for x in last),
            "over25":sum(x["total_goals"]>=3 for x in last),
            "btts":sum(x["goals_for"]>0 and x["goals_against"]>0 for x in last),
            "points":sum(x["points"] for x in last),
            "xg_status":"unavailable_in_scoreboard_do_not_infer"}

def verified_cross_competition_form(team, team_id, league_events, today):
    """Fill the genuine last five from ESPN all-competitions schedules.

    Never substitute another club, an unfinished game, invented xG or a future
    result. Original league results and the schedule are deduplicated by ID.
    """
    merged={x["event_id"]:x for x in league_events}
    errors=[]
    for year in (today.year, today.year-1):
        if len(team_form(team, list(merged.values()),team_id)["matches"]) >= 5:
            break
        try:
            for event in get_team_schedule(team_id,year):
                parsed=parsed_event(event, "all", today)
                if parsed and str(team_id) in (parsed["home_team_id"],parsed["away_team_id"]):
                    merged.setdefault(parsed["event_id"],parsed)
        except Exception as exc:
            errors.append({"team":team,"team_id":team_id,"source":"espn_all_schedule",
                           "season":year,"error":str(exc)[:180]})
    result=team_form(team,list(merged.values()),team_id)
    result["cross_competition_matches"]=sum(x.get("league")!="uefa.champions"
                          for x in result["matches"])
    result["form_source"]="ESPN verified all-competition schedule plus league scoreboards"
    return result,errors


def write(p, obj):
    p=Path(p);p.parent.mkdir(exist_ok=True,parents=True)
    tmp=p.with_suffix(p.suffix+".tmp")
    tmp.write_text(json.dumps(obj,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
    tmp.replace(p)

def main():
    root=Path("shared")
    feed=json.loads((root/"collector-feed.json").read_text(encoding="utf-8"))
    now=datetime.now(timezone.utc)
    today=now.astimezone(TZ).date()
    if feed.get("date")!=today.isoformat() or not feed.get("football_candidates"):
        print("ESPN_HISTORY_WAIT_FRESH_FIXTURES")
        return
    fixtures=feed["football_candidates"]
    leagues=sorted({f["league"] for f in fixtures})
    results={}
    source_ids={}
    errors=[]
    with ThreadPoolExecutor(max_workers=7) as pool:
        futures=[pool.submit(league_results, league, today) for league in leagues]
        for fut in as_completed(futures):
            league,events,problems,ids=fut.result()
            results[league]=events
            source_ids[league]=ids
            errors.extend(problems)
    data={"schema_version":2,"date":today.isoformat(),
          "generated_at_utc":now.isoformat(),"target_matches_per_team":5,
          "fixtures":fixtures,"leagues":{},"head_to_head":{},
          "errors":errors, "publication_allowed":False,"bank_modified":False,
          "form_scope":"real last five completed matches, including other competitions when ESPN team ID confirms identity (no fabricated xG)",
          "form_competitions_scanned":leagues+["ESPN all-competitions team schedules"],
          "cross_competition_teams_enriched":0}
    for league in leagues:
        teams={t for fixture in fixtures if fixture["league"]==league for t in (fixture["home"],fixture["away"])}
        data["leagues"][league]={"league":league,"teams":{
            t:team_form(t,results.get(league,[])) for t in sorted(teams)}}
    # Match each original ESPN fixture by event ID, then confirm team name/side.
    # No guessed mapping to another competition or same-name reserve teams.
    club_ids={}
    ambiguous=set()
    for fixture in fixtures:
        event_id=fixture["fixture_id"].split(":")[-1]
        found=source_ids.get(fixture["league"],{}).get(event_id)
        if not found:
            continue
        for side in ("home","away"):
            item=found[side]
            if similarity(fixture[side],item["name"])<0.87:
                continue
            key=(fixture["league"],fixture[side])
            if key in club_ids and club_ids[key]!=item["id"]:
                ambiguous.add(key)
            club_ids[key]=item["id"]
    for key in ambiguous:
        club_ids.pop(key,None)
    pending=[]
    for league in leagues:
        for team, record in data["leagues"][league]["teams"].items():
            tid=club_ids.get((league,team))
            if record["found"]<5 and tid:
                pending.append((league,team,tid))
    with ThreadPoolExecutor(max_workers=7) as pool:
        jobs={pool.submit(verified_cross_competition_form,team,tid,
                          results.get(league,[]),today):(league,team)
              for league,team,tid in pending}
        for fut in as_completed(jobs):
            league,team=jobs[fut]
            enriched,problems=fut.result()
            errors.extend(problems)
            if enriched["found"]>data["leagues"][league]["teams"][team]["found"]:
                data["leagues"][league]["teams"][team]=enriched
                data["cross_competition_teams_enriched"]+=1
    found=[o["found"] for L in data["leagues"].values() for o in L["teams"].values()]
    write(root/"agent/history-h2h.json",data)
    print("ESPN_HISTORY_READY",today.isoformat(),"fixtures",len(fixtures),"leagues",len(leagues),
          "teams",len(found),"found_4plus",sum(n>=4 for n in found),"fetch_errors",len(errors),"cross_comp_teams",data["cross_competition_teams_enriched"])
    if found and not any(n>=4 for n in found):
        print("::warning::ESPN scoreboard did not yield sufficient past results; Scout must use external sources and report limitations")
if __name__=="__main__":
    main()
