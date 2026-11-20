#!/usr/bin/env python3
"""No-key public odds snapshots, strict cross-source joining, no synthetic prices.

First provider is Football-Data's upcoming-fixtures CSV. Further PUBLIC CSV
sources may be added through LISTASIX_ODDS_CSV_SOURCES (comma-separated URLs)
using the same documented column schema; a provider is not assumed to work
unless it returns actual rows. Sources are tried in order only for ESPN matches
missing the required odds. All candidates remain visible in coverage.json.
"""
import argparse
import csv
import io
import json
import os
import re
import unicodedata
from datetime import datetime, timezone
from difflib import SequenceMatcher
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from kvoter.kvoter import utc
from kvoter.category_filter import excluded

PRIMARY = "https://www.football-data.co.uk/fixtures.csv"
MIRROR = "https://football-data.co.uk/matches/fixtures.csv"
DIVISIONS = {
    "E0":"eng.1", "D1":"ger.1", "SP1":"esp.1",
    "I1":"ita.1", "F1":"fra.1", "N1":"ned.1",
    "P1":"por.1", "B1":"bel.1", "SC0":"sco.1",
    "T1":"tur.1", "G1":"gre.1",
}
BLOCKED = re.compile(r"\b(?:women|woman|wfc|ladies|u(?:17|18|19|20|21|23)|youth|reserves|reserve|ii|b team)\b", re.I)
STOP = {"fc","cf","sc","afc","fk","ac","club","football","futbol","de","the","sv","ssc","calcio","sporting"}
def norm(name):
    s = unicodedata.normalize("NFKD", str(name or "").casefold())
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = s.replace("&"," and ")
    return " ".join(re.findall(r"[a-z0-9]+",s))
def key(name):
    words=[x for x in norm(name).split() if x not in STOP]
    # Common published abbreviations; do not strip distinctive team tokens.
    canonical={"man":"manchester","utd":"united","st":"saint","ath":"athletic"}
    return " ".join(canonical.get(x,x) for x in words)
def similarity(a,b):
    a,b=key(a),key(b)
    if not a or not b: return 0.
    if a==b: return 1.
    return SequenceMatcher(None,a,b).ratio()
def safe_price(value):
    try: n=float(str(value).replace(",","."))
    except (ValueError,TypeError): return None
    return round(n,3) if 1 < n < 1000 else None
def first_price(row, *names):
    for name in names:
        p=safe_price(row.get(name))
        if p is not None:return p
    return None
def read_date(date,clock):
    date=str(date or "").strip()
    clock=str(clock or "00:00").strip() or "00:00"
    for fmt in ("%d/%m/%Y %H:%M","%d/%m/%y %H:%M","%Y-%m-%d %H:%M"):
        try:
            from zoneinfo import ZoneInfo
            return datetime.strptime(date+" "+clock,fmt).replace(tzinfo=ZoneInfo("Europe/London")).astimezone(timezone.utc).isoformat()
        except ValueError:pass
    return None
def row_offer(row, source, stamp):
    league=DIVISIONS.get((row.get("Div") or "").strip())
    if not league:return None
    home,away=row.get("HomeTeam",""),row.get("AwayTeam","")
    if not home or not away or BLOCKED.search(home) or BLOCKED.search(away) or excluded(home,away,league):
        return None
    start=read_date(row.get("Date"),row.get("Time"))
    if not start:return None
    markets={}
    one={k:v for k,v in {
        "home":first_price(row,"B365H","PSH","AvgH","MaxH"),
        "draw":first_price(row,"B365D","PSD","AvgD","MaxD"),
        "away":first_price(row,"B365A","PSA","AvgA","MaxA"),
    }.items() if v}
    if one: markets["1X2"]=one
    over=first_price(row,"B365>2.5","P>2.5","Avg>2.5","Max>2.5")
    if over:markets["3+"]={"over":over}
    yes=first_price(row,"B365BTTSY","BTTSY","GG")
    no=first_price(row,"B365BTTSN","BTTSN","NG")
    if yes or no:markets["BTTS"]={k:v for k,v in (("yes",yes),("no",no)) if v}
    if not markets:return None
    return {"event_id":f"{source}:{league}:{start}:{norm(home)}:{norm(away)}",
        "league":league,"home":home,"away":away,"start_utc":start,
        "bookmaker":source,"updated_at_utc":stamp,"markets":markets}
def get_rows(url):
    parsed=urlparse(url)
    if parsed.scheme != "https" or not parsed.hostname:
        raise ValueError("Only HTTPS odds snapshot URLs supported")
    req=Request(url,headers={"User-Agent":"ListaSixPublicOdds/1.0 (+daily CSV verification)","Accept":"text/csv,text/plain"})
    with urlopen(req,timeout=22) as reply:
        data=reply.read(4_000_001)
    if len(data)>4_000_000:raise ValueError("Snapshot too large")
    text=data.decode("utf-8-sig",errors="replace")
    reader=csv.DictReader(io.StringIO(text))
    if not reader.fieldnames or not {"Div","Date","HomeTeam","AwayTeam"}.issubset(reader.fieldnames):
        raise ValueError("CSV lacks expected fixture columns")
    return list(reader)
def candidate(fixture,offer):
    if fixture.get("league") != offer.get("league"):return None
    if excluded(fixture.get("home"),fixture.get("away"),fixture.get("league")):return None
    for x in (fixture.get("home",""),fixture.get("away",""),offer["home"],offer["away"]):
        if BLOCKED.search(x):return None
    a,b=utc(fixture.get("start_utc")),utc(offer.get("start_utc"))
    if not a or not b or abs((a-b).total_seconds())>90*60:return None
    h=similarity(fixture.get("home"),offer["home"])
    v=similarity(fixture.get("away"),offer["away"])
    if h < .87 or v < .87:return None
    return min(h,v)+(h+v)/10
def choose(fixtures,offers):
    """Mutual unique-best matching avoids confusing nearby teams or swapped sides."""
    bids={}
    for fi,f in enumerate(fixtures):
        hits=sorted(((s,oi) for oi,o in enumerate(offers) if (s:=candidate(f,o)) is not None),reverse=True)
        if hits and (len(hits)==1 or hits[0][0]-hits[1][0]>.08):
            bids[fi]=hits[0]
    claimed={}
    for fi,(_,oi) in bids.items(): claimed.setdefault(oi,[]).append(fi)
    return {fi:offers[oi] for fi,(_,oi) in bids.items() if len(claimed[oi])==1}
def write(path,doc):
    p=Path(path);p.parent.mkdir(parents=True,exist_ok=True)
    temp=p.with_name(p.name+".tmp")
    temp.write_text(json.dumps(doc,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    os.replace(temp,p)
def main():
    a=argparse.ArgumentParser()
    a.add_argument("--feed",default="shared/collector-feed.json")
    a.add_argument("--out-dir",default="shared/kvoter")
    args=a.parse_args()
    doc=json.loads(Path(args.feed).read_text(encoding="utf-8"))
    fixtures=doc.get("football_candidates",[])
    if not isinstance(fixtures,list):raise ValueError("Invalid ESPN fixture feed")
    sources=[PRIMARY,MIRROR]
    sources += [x.strip() for x in os.getenv("LISTASIX_ODDS_CSV_SOURCES","").split(",") if x.strip()]
    # Avoid duplicate URLs; the two defaults are mirrors, not independent publishers.
    sources=list(dict.fromkeys(sources))
    stamp=datetime.now(timezone.utc).isoformat()
    resolved={};attempts=[]
    for index,url in enumerate(sources):
        pending=[(i,f) for i,f in enumerate(fixtures) if i not in resolved]
        if not pending:break
        try:
            rows=get_rows(url)
            offers=[o for row in rows if (o:=row_offer(row,url,stamp))]
            selected=choose([f for _,f in pending],offers)
            for relative,offer in selected.items():
                resolved[pending[relative][0]]=offer
            attempts.append({"source":url,"rows":len(rows),"valid_offers":len(offers),
                             "new_matches":len(selected),"pending":len(fixtures)-len(resolved)})
        except Exception as exc:
            attempts.append({"source":url,"error":f"{type(exc).__name__}: {str(exc)[:130]}",
                             "new_matches":0,"pending":len(fixtures)-len(resolved)})
    matched=[];unmatched=[];coverage=[]
    for i,f in enumerate(fixtures):
        record={k:f.get(k) for k in ("fixture_id","league","home","away","start_utc")}
        offer=resolved.get(i)
        if offer:
            record["provider_events"]=[offer["event_id"]]
            record["bookmakers"]=[offer["bookmaker"]]
            record["odds_offers"]=[{k:offer[k] for k in ("event_id","bookmaker","updated_at_utc","markets")}]
            matched.append(record)
        else:unmatched.append(record)
        coverage.append(dict(record if not offer else {k:f.get(k) for k in ("fixture_id","league","home","away","start_utc")},
                             status="matched" if offer else "no_verified_quote",
                             source=offer["bookmaker"] if offer else None))
    base=Path(args.out_dir)
    write(base/"provider-offers.json",{"source":"public-csv-cascade","offers":list(resolved.values()),"attempts":attempts})
    write(base/"matched_fixtures.json",{"generated_at_utc":stamp,"total":len(matched),"fixtures":matched})
    write(base/"unmatched_fixtures.json",{"generated_at_utc":stamp,"total":len(unmatched),"fixtures":unmatched})
    write(base/"coverage.json",{"date":doc.get("date"),"generated_at_utc":stamp,"total":len(fixtures),
        "matched":len(matched),"unmatched":len(unmatched),"fixtures":coverage,"sources":attempts})
    write(base/"match-report.json",{"generated_at_utc":stamp,"source":"public-csv-cascade",
        "provider_status":"public_source_checked","provider_errors":[a for a in attempts if "error" in a],
        "total":len(fixtures),"matched":len(matched),"unavailable":len(unmatched),
        "matched_fixtures":matched,"unmatched_fixtures":unmatched,"publication_allowed":False,
        "bank_modified":False,"tickets_published":False,"provider_coverage":attempts})
    print("PUBLIC_KVOTER",json.dumps({"ESPN":len(fixtures),"matched":len(matched),
                                    "unmatched":len(unmatched),"sources":attempts}))
if __name__=="__main__":main()
