#!/usr/bin/env python3
"""Compare history-h2h fixtures with Odds API league offers. No publishing or betting."""
import argparse
import json
from datetime import datetime,timezone
from pathlib import Path
from team_identity import same_team
from category_filter import excluded

def utc(value):
    try: return datetime.fromisoformat(str(value).replace("Z","+00:00")).astimezone(timezone.utc)
    except (ValueError,TypeError): return None

def match(fixture,offer,tolerance_minutes=90):
    if excluded(fixture.get('home'), fixture.get('away'), fixture.get('league')) or excluded(offer.get('home'), offer.get('away'), offer.get('league')): return False
    if fixture.get("league")!=offer.get("league"): return False
    a,b=utc(fixture.get("start_utc")),utc(offer.get("start_utc"))
    if not a or not b or abs((a-b).total_seconds())>tolerance_minutes*60: return False
    league=fixture["league"]
    return (same_team(fixture.get("home"),offer.get("home"),league)
            and same_team(fixture.get("away"),offer.get("away"),league))

def build(history,offers,source="the-odds-api-v4"):
    fixtures=history.get("fixtures",[])
    if not isinstance(fixtures,list) or not isinstance(offers,list): raise ValueError("Invalid input")
    matched=[]; unmatched=[]
    for fixture in fixtures:
        hits=[offer for offer in offers if isinstance(offer,dict) and match(fixture,offer)]
        record={"fixture_id":fixture.get("fixture_id") or fixture.get("id"),
                "league":fixture.get("league"),"home":fixture.get("home"),
                "away":fixture.get("away"),"start_utc":fixture.get("start_utc")}
        if hits:
            record["provider_events"]=sorted({str(h.get("event_id")) for h in hits if h.get("event_id")})
            record["bookmakers"]=sorted({str(h.get("bookmaker")) for h in hits if h.get("bookmaker")})
            record["odds_offers"]=[{"event_id":h.get("event_id"),"bookmaker":h.get("bookmaker"),"updated_at_utc":h.get("updated_at_utc"),"markets":h.get("markets",{})} for h in hits if h.get("markets")]
            matched.append(record)
        else: unmatched.append(record)
    return {"generated_at_utc":datetime.now(timezone.utc).isoformat(),
            "source":source,"total":len(fixtures),"matched":len(matched),
            "unavailable":len(unmatched),"matched_fixtures":matched,
            "unmatched_fixtures":unmatched,"publication_allowed":False,
            "bank_modified":False,"tickets_published":False}

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--feed",default="/shared/agent/history-h2h.json")
    p.add_argument("--offers",default="/shared/kvoter/provider-offers.json")
    p.add_argument("--output",default="/shared/kvoter/match-report.json")
    a=p.parse_args()
    history=json.loads(Path(a.feed).read_text(encoding="utf-8"))
    offers_doc=json.loads(Path(a.offers).read_text(encoding="utf-8"))
    offers=offers_doc.get("offers",[]) if isinstance(offers_doc,dict) else offers_doc
    report=build(history,offers)
    output=Path(a.output);output.parent.mkdir(parents=True,exist_ok=True)
    output.write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print("KVOTER_MATCH",json.dumps({"total":report["total"],"matched":report["matched"],"unmatched":report["unavailable"]}))
if __name__=="__main__":main()
