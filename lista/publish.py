#!/usr/bin/env python3
"""Publish verified Kvoter odds and merge approved manual matches into one offer."""
import argparse,json
from math import isfinite
from datetime import datetime,timedelta,time
from pathlib import Path
from zoneinfo import ZoneInfo

TZ=ZoneInfo("Europe/Sarajevo")
def expiry(day):
    return datetime.combine(day+timedelta(days=1),time(8,59),tzinfo=TZ).isoformat()
# Public field, provider market, provider outcome, display label.
SELECTIONS = (
    ("home_odds", "1X2", "home", "1"), ("draw_odds", "1X2", "draw", "X"),
    ("away_odds", "1X2", "away", "2"), ("over15_odds", "2+", "over", "2+"),
    ("over25_odds", "3+", "over", "3+"), ("btts_yes_odds", "BTTS", "yes", "GG"),
    ("btts_no_odds", "BTTS", "no", "NG"),
)

def pick(record):
    sources = {}
    row = {"fixture_id": record["fixture_id"], "datetime": record.get("start_utc", ""),
           "match": f"{record.get('home', '')} - {record.get('away', '')}",
           "bookmakers_by_field": sources}
    for field, market, outcome, _ in SELECTIONS:
        row[field] = None
        for offer in record.get("odds_offers", []):
            prices = offer.get("markets", {}).get(market)
            price = prices.get(outcome) if isinstance(prices, dict) else None
            book = offer.get("bookmaker")
            if book and isinstance(price, (int, float)) and isfinite(price) and price > 1:
                row[field] = price
                sources[field] = book
                break
    if sources:
        row["bookmaker"] = next(iter(sources.values()))
        return row

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
    for item in report.get("matched_fixtures",report.get("fixtures",[]))+list(approved.values()):
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
    txt=["Br. | Datum/sat | Utakmica | " + " | ".join(entry[3] for entry in SELECTIONS)]
    for i, row in enumerate(result["fixtures"], 1):
        cells = [str(i), row["datetime"], row["match"]]
        for field, _, _, _ in SELECTIONS:
            cells.append(f"{row[field]} ({row['bookmakers_by_field'][field]})" if row[field] is not None else "-")
        txt.append(" | ".join(cells))
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
