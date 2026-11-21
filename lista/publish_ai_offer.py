#!/usr/bin/env python3
"""Publish the AI's online prices directly to the named daily Kvoter offer.
No bookmaker comparison service, Kvoter Manual, or CSV matching required.
ESPN identity is the only fixture key. Keep existing same-day prices when a
new partial snapshot fills otherwise blank markets.
"""
import json
from datetime import datetime, timedelta, time
from pathlib import Path
from zoneinfo import ZoneInfo

FIELDS = {
    "1X2": {"home": "home_odds", "draw": "draw_odds", "away": "away_odds"},
    "3+": {"over": "over25_odds"},
    "BTTS": {"yes": "btts_yes_odds", "no": "btts_no_odds"},
}
TZ=ZoneInfo("Europe/Sarajevo")

def write(path, obj):
    path=Path(path)
    path.parent.mkdir(parents=True,exist_ok=True)
    temporary=path.with_name(path.name+".tmp")
    temporary.write_text(json.dumps(obj,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    temporary.replace(path)

def main():
    feed=json.loads(Path("shared/collector-feed.json").read_text(encoding="utf-8"))
    today=datetime.now(TZ).date().isoformat()
    if feed.get("date")!=today or not feed.get("football_candidates"):
        raise RuntimeError("Fresh ESPN feed is required before AI odds can be displayed")
    snapshot=Path("shared/kvoter")/("ai-verified-"+today+".json")
    if not snapshot.exists():
        print("ESPN_READY_AI_QUOTES_NOT_YET_AVAILABLE")
        return
    ai=json.loads(snapshot.read_text(encoding="utf-8"))
    if ai.get("date")!=today:
        raise ValueError("Odds snapshot has wrong date")
    fixtures={f["fixture_id"]:f for f in feed["football_candidates"]}
    previous={}
    old_path=Path("shared/active-list.json")
    if old_path.exists():
        doc=json.loads(old_path.read_text(encoding="utf-8"))
        if doc.get("date")==today:
            previous={f["fixture_id"]:f for f in doc.get("fixtures",[]) if f.get("fixture_id") in fixtures}
    for item in ai.get("fixtures",[]):
        fid=item.get("fixture_id")
        expected=fixtures.get(fid)
        if not expected or any(item.get(k)!=expected.get(k) for k in ("league","home","away","start_utc")):
            raise ValueError("AI odds do not match original ESPN league/teams/kickoff: "+str(fid))
        urls=item.get("source_urls",[])
        if not urls or not all(isinstance(u,str) and u.startswith("https://") for u in urls):
            raise ValueError("Public odds require source URLs: "+fid)
        row=previous.setdefault(fid,{"fixture_id":fid,"datetime":expected["start_utc"],
                                     "match":expected["home"]+" - "+expected["away"],
                                     "bookmakers_by_field":{},"source_urls":[]})
        row.setdefault("source_urls",[])
        row["source_urls"]=list(dict.fromkeys(row["source_urls"]+urls))
        row.setdefault("bookmakers_by_field",{})
        for market,prices in item.get("markets",{}).items():
            if market not in FIELDS or not isinstance(prices,dict):
                raise ValueError("Unsupported market")
            for outcome,price in prices.items():
                field=FIELDS[market].get(outcome)
                if not field or isinstance(price,bool) or not isinstance(price,(int,float)) or not 1.01<float(price)<50:
                    raise ValueError("Invalid online quote")
                if row.get(field) is None:
                    row[field]=price
                    row["bookmakers_by_field"][field]=item.get("bookmaker","AI verified public odds")
    all_rows=[]
    header=["Br.","Datum/sat","Utakmica","1","X","2","3+","GG","NG"]
    txt=[" | ".join(header)]
    keys=("home_odds","draw_odds","away_odds","over25_odds","btts_yes_odds","btts_no_odds")
    quoted=0
    for i,f in enumerate(sorted(fixtures.values(),key=lambda x:(x["start_utc"],x["home"])),1):
        fid=f["fixture_id"]
        row=previous.get(fid,{"fixture_id":fid,"datetime":f["start_utc"],
                              "match":f["home"]+" - "+f["away"],"bookmakers_by_field":{},"source_urls":[]})
        for key in keys:row.setdefault(key,None)
        if any(row[k] is not None for k in keys):quoted+=1
        all_rows.append(row)
        txt.append(" | ".join([str(i),row["datetime"],row["match"]]+
                  [str(row[k]) if row[k] is not None else "-" for k in keys]))
    expiration=datetime.combine(datetime.fromisoformat(today).date()+timedelta(days=1),time(8,59),tzinfo=TZ).isoformat()
    data={"date":today,"expires_at":expiration,"publication_allowed":bool(quoted),
          "fixtures":all_rows}
    for path in ("shared/active-list.json","docs/active-list.json"):
        write(path,data)
    for path in ("shared/kvoter-ponuda.txt","docs/kvoter-ponuda.txt"):
        Path(path).write_text("\n".join(txt)+"\n",encoding="utf-8")
    print("DAILY_KLADIONICARSKA_PONUDA",len(all_rows),"ESPN",quoted,"WITH_QUOTES")

if __name__=="__main__":
    main()
