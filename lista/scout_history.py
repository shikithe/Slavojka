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
    for stamp in months:
        try:
            raw = get_scoreboard(league, stamp)
            for entry in raw:
                parsed = parsed_event(entry,league,today)
                if parsed:
                    events[parsed["event_id"]] = parsed
        except Exception as error:
            errors.append({"league":league,"month":stamp,"error":str(error)[:180]})
        time.sleep(0.25)
    return league,list(events.values()),errors

def team_form(team, results):
    matches=[]
    for r in results:
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
    errors=[]
    with ThreadPoolExecutor(max_workers=7) as pool:
        futures=[pool.submit(league_results, league, today) for league in leagues]
        for fut in as_completed(futures):
            league,events,problems=fut.result()
            results[league]=events
            errors.extend(problems)
    data={"schema_version":2,"date":today.isoformat(),
          "generated_at_utc":now.isoformat(),"target_matches_per_team":5,
          "fixtures":fixtures,"leagues":{},"head_to_head":{},
          "errors":errors, "publication_allowed":False,"bank_modified":False,
          "form_scope":"last five completed league matches from ESPN scoreboards (no fabricated xG)",
          "form_competitions_scanned":leagues}
    for league in leagues:
        teams={t for fixture in fixtures if fixture["league"]==league for t in (fixture["home"],fixture["away"])}
        data["leagues"][league]={"teams":{t:team_form(t,results.get(league,[])) for t in sorted(teams)}}
    found=[o["found"] for L in data["leagues"].values() for o in L["teams"].values()]
    write(root/"agent/history-h2h.json",data)
    print("ESPN_HISTORY_READY",today.isoformat(),"fixtures",len(fixtures),"leagues",len(leagues),
          "teams",len(found),"found_4plus",sum(n>=4 for n in found),"fetch_errors",len(errors))
    if found and not any(n>=4 for n in found):
        print("::warning::ESPN scoreboard did not yield sufficient past results; Scout must use external sources and report limitations")
if __name__=="__main__":
    main()
