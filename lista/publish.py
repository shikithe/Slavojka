#!/usr/bin/env python3
"""Publish verified Kvoter odds and merge approved manual matches into one offer."""
import argparse,json
from datetime import datetime,timedelta,time
from pathlib import Path
from zoneinfo import ZoneInfo

TZ=ZoneInfo("Europe/Sarajevo")
def expiry(day):
    return datetime.combine(day+timedelta(days=1),time(9,59),tzinfo=TZ).isoformat()
def pick(record):
    for offer in record.get("odds_offers",[]):
        markets=offer.get("markets",{})
        h=markets.get("1X2",{})
        over=markets.get("3+",{})
        if not isinstance(h,dict) or not isinstance(over,dict):continue
        vals=[h.get("home"),h.get("draw"),h.get("away"),over.get("over")]
        if not any(isinstance(x,(int,float)) and x>1 for x in vals):continue
        return {"fixture_id":record["fixture_id"],"datetime":record.get("start_utc",""),
                "match":str(record.get("home",""))+" - "+str(record.get("away","")),
                "home_odds":h.get("home"),"draw_odds":h.get("draw"),
                "away_odds":h.get("away"),"over25_odds":over.get("over"),
                "bookmaker":offer.get("bookmaker","")}
    return None
def publish(feed_path,match_path,manual_path,shared,docs):
    feed=json.loads(Path(feed_path).read_text(encoding="utf-8"))
    report=json.loads(Path(match_path).read_text(encoding="utf-8"))
    day=datetime.fromisoformat(feed["date"]).date()
    approved={}
    if manual_path and Path(manual_path).exists():
        manual=json.loads(Path(manual_path).read_text(encoding="utf-8"))
        for row in manual.get("matched_fixtures",[]):
            if row.get("fixture_id"):approved[row["fixture_id"]]=row
    ids={f["fixture_id"] for f in feed.get("football_candidates",[])}
    rows={}
    for item in report.get("matched_fixtures",[])+list(approved.values()):
        if item.get("fixture_id") not in ids:continue
        chosen=pick(item)
        if chosen:rows[chosen["fixture_id"]]=chosen
    result={"date":feed["date"],"expires_at":expiry(day),"publication_allowed":bool(rows),
            "fixtures":sorted(rows.values(),key=lambda x:(x["datetime"],x["match"]))}
    if not rows:
        print("NO_VERIFIED_ODDS: no public offer created")
        return 0
    shared,docs=Path(shared),Path(docs)
    shared.mkdir(parents=True,exist_ok=True);docs.mkdir(parents=True,exist_ok=True)
    txt=["Br. | Datum/sat | Utakmica | 1 | X | 2 | 3+ | Kladionica"]
    for i,r in enumerate(result["fixtures"],1):
        txt.append(" | ".join(str(v if v is not None else "-") for v in
          [i,r["datetime"],r["match"],r["home_odds"],r["draw_odds"],r["away_odds"],r["over25_odds"],r["bookmaker"]]))
    for path,data in [(shared/"active-list.json",json.dumps(result,ensure_ascii=False,indent=2)+"\n"),
                      (docs/"active-list.json",json.dumps(result,ensure_ascii=False,indent=2)+"\n"),
                      (shared/"kvoter-ponuda.txt","\n".join(txt)+"\n"),
                      (docs/"kvoter-ponuda.txt","\n".join(txt)+"\n")]:
        temp=path.with_name(path.name+".tmp");temp.write_text(data,encoding="utf-8");temp.replace(path)
    print("PUBLISHED_VERIFIED_FIXTURES",len(rows),"EXPIRES",result["expires_at"])
    return len(rows)
def main():
    p=argparse.ArgumentParser()
    p.add_argument("--feed",default="shared/collector-feed.json")
    p.add_argument("--matches",default="shared/kvoter/matched-fixtures.json")
    p.add_argument("--manual",default="shared/kvoter/manual-matched.json")
    p.add_argument("--shared",default="shared")
    p.add_argument("--docs",default="docs")
    a=p.parse_args()
    publish(a.feed,a.matches,a.manual,a.shared,a.docs)
if __name__=="__main__":main()
