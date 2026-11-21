#!/usr/bin/env python3
"""Merge human/AI-web-verified odds with public CSV results, no manual alias UI.
Only exact ESPN fixture_id, league, sides, and kickoff are accepted. Do not
infer prices, interpolate markets, or carry prices to the next day.
"""
import json
import sys
from datetime import datetime,timezone
from pathlib import Path

def write(path,obj):
    p=Path(path);p.parent.mkdir(parents=True,exist_ok=True)
    temp=p.with_name(p.name+".tmp")
    temp.write_text(json.dumps(obj,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    temp.replace(p)

def main():
    root=Path("shared")
    feed=json.loads((root/"collector-feed.json").read_text(encoding="utf-8"))
    date=feed["date"]
    verified=root/"kvoter"/("ai-verified-"+date+".json")
    if not verified.exists():
        print("AI_ODDS_NO_SNAPSHOT_FOR_DATE",date)
        return
    ai=json.loads(verified.read_text(encoding="utf-8"))
    if ai.get("date")!=date:
        print("AI_ODDS_SNAPSHOT_STALE",date)
        return
    expected={f["fixture_id"]:f for f in feed["football_candidates"]}
    dest=root/"kvoter"
    matched_path=dest/"matched_fixtures.json"
    matched=json.loads(matched_path.read_text(encoding="utf-8"))
    found={f["fixture_id"]:f for f in matched.get("fixtures",[])}
    offers_path=dest/"provider-offers.json"
    provider=json.loads(offers_path.read_text(encoding="utf-8"))
    provider.setdefault("offers",[])
    for item in ai.get("fixtures",[]):
        fid=item.get("fixture_id")
        f=expected.get(fid)
        if not f or any(f.get(k)!=item.get(k) for k in ("league","home","away","start_utc")):
            raise ValueError("AI odds identity or fixture date mismatch: "+str(fid))
        if not item.get("source_urls") or not all(u.startswith("https://") for u in item["source_urls"]):
            raise ValueError("Verified odds require public source URLs")
        markets={}
        for name,outcomes in item.get("markets",{}).items():
            if name not in ("1X2","3+","BTTS") or not isinstance(outcomes,dict):raise ValueError("Unsupported market")
            valid={}
            allowed={"1X2":{"home","draw","away"},"3+":{"over"},"BTTS":{"yes","no"}}[name]
            for option,value in outcomes.items():
                if option not in allowed or not isinstance(value,(float,int)) or isinstance(value,bool) or not 1<value<1000:
                    raise ValueError("Invalid verified quote")
                valid[option]=value
            if valid:markets[name]=valid
        if not markets:continue
        row=found.get(fid) or {k:f[k] for k in ("fixture_id","league","home","away","start_utc")}
        old=row.get("odds_offers",[])
        # A snapshot may have only one market. Preserve already found prices
        # for the same match and fill missing columns from subsequent sources.
        prior=next((o for o in old if o.get("event_id")=="ai-web:"+fid),{})
        combined={k:dict(v) for k,v in prior.get("markets",{}).items()}
        for name,values in markets.items():
            target=combined.setdefault(name,{})
            for outcome,price in values.items():
                target.setdefault(outcome,price)
        source_urls=list(dict.fromkeys(prior.get("source_urls",[])+item["source_urls"]))
        offer={"event_id":"ai-web:"+fid,
               "bookmaker":prior.get("bookmaker") or item.get("bookmaker") or "AI public web offers",
               "updated_at_utc":datetime.now(timezone.utc).isoformat(),
               "source_urls":source_urls,
               "markets":combined}
        # Preserve optional per-market source information for traceability.
        old_sources=dict(prior.get("market_sources",{}))
        old_sources.update({k:v for k,v in item.get("market_sources",{}).items() if k not in old_sources})
        if old_sources: offer["market_sources"]=old_sources
        row["odds_offers"]=[offer]+[o for o in old if not str(o.get("event_id","")).startswith("ai-web:")]
        row["provider_events"]=list(dict.fromkeys([offer["event_id"]]+row.get("provider_events",[])))
        row["bookmakers"]=list(dict.fromkeys([offer["bookmaker"]]+row.get("bookmakers",[])))
        found[fid]=row
        provider["offers"]=[o for o in provider["offers"] if o.get("event_id")!=offer["event_id"]]
        provider["offers"].append({**{k:f[k] for k in ("league","home","away","start_utc")},**offer})
    rows=list(found.values())
    unmatched=[f for f in feed["football_candidates"] if f["fixture_id"] not in found]
    stamp=datetime.now(timezone.utc).isoformat()
    write(matched_path,{"generated_at_utc":stamp,"total":len(rows),"fixtures":rows})
    write(dest/"unmatched_fixtures.json",{"generated_at_utc":stamp,"total":len(unmatched),"fixtures":unmatched})
    write(offers_path,provider)
    report_path=dest/"match-report.json"
    report=json.loads(report_path.read_text(encoding="utf-8"))
    report.update(matched=len(rows),unavailable=len(unmatched),matched_fixtures=rows,unmatched_fixtures=unmatched)
    write(report_path,report)
    coverage_path=dest/"coverage.json"
    if coverage_path.exists():
        coverage=json.loads(coverage_path.read_text(encoding="utf-8"))
        coverage.update(matched=len(rows),unmatched=len(unmatched))
        for item in coverage.get("fixtures",[]):
            if item.get("fixture_id") in found:
                item.update(status="matched",source="AI verified public web odds")
        write(coverage_path,coverage)
    print("AI_ODDS_MERGED",len(rows),"of",len(expected))

if __name__=="__main__":
    main()
