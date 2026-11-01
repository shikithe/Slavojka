#!/usr/bin/env python3
"""The Odds API v4 adapter: history-h2h -> normalized bookmaker offers.
No API key means no requests and no fabricated odds.
"""
import argparse
import json
import os
import time
from datetime import datetime,timezone
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request,urlopen
from kvoter import utc,build
from team_identity import normalize as norm

LEAGUES={
"eng.1":"soccer_epl","ger.1":"soccer_germany_bundesliga",
"esp.1":"soccer_spain_la_liga","ita.1":"soccer_italy_serie_a",
"fra.1":"soccer_france_ligue_one","ned.1":"soccer_netherlands_eredivisie",
"por.1":"soccer_portugal_primeira_liga","bel.1":"soccer_belgium_first_div",
"sco.1":"soccer_spl","tur.1":"soccer_turkey_super_league",
"bra.1":"soccer_brazil_campeonato","arg.1":"soccer_argentina_primera_division",
"usa.1":"soccer_usa_mls",
}
BASE="https://api.the-odds-api.com/v4"
def request(path,key,params,fetch=None):
    url=BASE+path+"?"+urlencode(dict(params,apiKey=key))
    if fetch: return fetch(url)
    req=Request(url,headers={"User-Agent":"MEMARASIX-Kvoter/1.0"})
    with urlopen(req,timeout=20) as response:
        return json.load(response)

def parse_bookmaker(event,bookmaker,league):
    home,away=event.get("home_team"),event.get("away_team")
    markets={}
    updates=[]
    for market in bookmaker.get("markets",[]):
        kind=market.get("key")
        if kind in ("h2h","h2h_3_way"):
            outcomes={}
            for x in market.get("outcomes",[]):
                name=x.get("name")
                key="home" if norm(name)==norm(home) else "away" if norm(name)==norm(away) else "draw" if norm(name)=="draw" else None
                if key: outcomes[key]=x.get("price")
            if outcomes: markets["1X2"]=outcomes
        elif kind in ("totals","alternate_totals"):
            for x in market.get("outcomes",[]):
                if norm(x.get("name"))!="over": continue
                try: point=float(x.get("point"))
                except (ValueError,TypeError): continue
                if point==1.5: markets["2+"]={"over":x.get("price")}
                if point==2.5: markets["3+"]={"over":x.get("price")}
        elif kind=="btts":
            outcomes={norm(x.get("name")):x.get("price") for x in market.get("outcomes",[]) if norm(x.get("name")) in ("yes","no")}
            if outcomes: markets["BTTS"]=outcomes
        if market.get("last_update"): updates.append(market["last_update"])
    return {"event_id":event.get("id"),"league":league,"home":home,"away":away,
            "start_utc":event.get("commence_time"),"bookmaker":bookmaker.get("key"),
            "updated_at_utc":max(updates) if updates else None,"markets":markets}

def collect(history,key,regions="uk,eu",fetch=None,delay=0):
    """Fetch featured odds for every supported league in the collector's exact window."""
    fixtures=history.get("fixtures",[])
    leagues=sorted({f.get("league") for f in fixtures if f.get("league") in LEAGUES})
    starts=[utc(f.get("start_utc")) for f in fixtures]
    starts=[x for x in starts if x]
    if not starts: raise ValueError("No fixture kickoff times")
    window_start,window_end=min(starts),max(starts)
    offers=[]; raw_events=[]; coverage={}; errors=[]
    for league in leagues:
        try:
            events=request("/sports/"+LEAGUES[league]+"/odds",key,{
                "regions":regions,"markets":"h2h,totals","oddsFormat":"decimal",
                "commenceTimeFrom":window_start.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "commenceTimeTo":window_end.strftime("%Y-%m-%dT%H:%M:%SZ")},fetch)
            if not isinstance(events,list): raise ValueError("Invalid API response")
            selected=[e for e in events if utc(e.get("commence_time")) and window_start<=utc(e.get("commence_time"))<=window_end]
            coverage[league]={"api_events":len(events),"window_events":len(selected)}
            for event in selected:
                raw_events.append({"league":league,"event":event})
                for book in event.get("bookmakers",[]):
                    offer=parse_bookmaker(event,book,league)
                    if offer["markets"]: offers.append(offer)
        except Exception as exc:
            errors.append({"league":league,"error":str(exc)[:200]})
        if delay: time.sleep(delay)
    return offers,raw_events,coverage,errors

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--feed",default="/shared/agent/history-h2h.json")
    p.add_argument("--output",default="/shared/kvoter/odds.json")
    p.add_argument("--regions",default="uk,eu")
    p.add_argument("--raw-output",default="/shared/kvoter/league-odds-raw.json")
    p.add_argument("--offers-output",default="/shared/kvoter/provider-offers.json")
    a=p.parse_args()
    history=json.loads(Path(a.feed).read_text(encoding="utf-8"))
    key=os.getenv("THE_ODDS_API_KEY","").strip()
    if key:
        offers,raw_events,coverage,errors=collect(history,key,a.regions,delay=0.2)
        status="api_fetched"
    else:
        offers,raw_events,coverage,errors=[],[],{},[{"stage":"configuration","error":"THE_ODDS_API_KEY not configured"}]
        status="missing_api_key"
    for path,payload in [(a.raw_output,{"source":"the-odds-api-v4","events":raw_events}),(a.offers_output,{"offers":offers})]:
        dest=Path(path);dest.parent.mkdir(parents=True,exist_ok=True)
        tmp=dest.with_suffix(".tmp");tmp.write_text(json.dumps(payload,ensure_ascii=False,indent=2)+"\n",encoding="utf-8");os.replace(tmp,dest)
    result=build(history,offers,source="the-odds-api-v4")
    result["provider_status"]=status
    result["provider_coverage"]=coverage
    result["provider_errors"]=errors
    out=Path(a.output);out.parent.mkdir(parents=True,exist_ok=True)
    temp=out.with_suffix(".tmp")
    temp.write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    os.replace(temp,out)
    print("KVOTER",json.dumps({"total":result["total"],"matched":result["matched"],"provider_status":status,"errors":len(errors)}))
if __name__=="__main__":main()
