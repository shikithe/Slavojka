"""Validate and atomically record one or more Kvoter Manual decisions."""
import json
import os
import re
from pathlib import Path
from kvoter.manual_aliases import approve

def process(body, issue_number):
    marker = "KVOTER_MANUAL_BATCH_V1"
    if not body.startswith(marker):
        raise ValueError("Incorrect batch marker")
    match = re.search(r"```json\s*(\{.*?\})\s*```", body, re.S)
    if not match:
        raise ValueError("Missing JSON payload")
    payload = json.loads(match.group(1))
    rows = payload.get("decisions")
    if not isinstance(rows, list) or not 1 <= len(rows) <= 500:
        raise ValueError("Invalid batch size")
    queue = json.loads(Path("shared/kvoter/manual-candidates.json").read_text())
    fixtures = {f["fixture_id"]: f for f in queue["fixtures"]}
    decisions_path = Path("kvoter/manual/decisions.json")
    db_path = Path("kvoter/team-database.json")
    decisions_doc = json.loads(decisions_path.read_text())
    db = json.loads(db_path.read_text())
    old = decisions_doc.setdefault("decisions", [])
    seen_fixtures, seen_events, seen_pairs = set(), set(), set()
    updates = []
    required = ("fixture_id","event_id","league","collector_home","collector_away","odds_home","odds_away","decision")
    for row in rows:
        if not isinstance(row, dict) or any(not isinstance(row.get(k),str) or not 0 < len(row[k]) <= 250 for k in required):
            raise ValueError("Invalid decision fields")
        if row["decision"] not in ("matched","rejected") or not re.fullmatch(r"[a-z]{2,5}\.\d+",row["league"]):
            raise ValueError("Invalid decision or league")
        fixture = fixtures.get(row["fixture_id"])
        if not fixture or (fixture["league"],fixture["home"],fixture["away"]) != (row["league"],row["collector_home"],row["collector_away"]):
            raise ValueError("Unrecognized fixture")
        if not any((c["event_id"],c["home"],c["away"]) == (row["event_id"],row["odds_home"],row["odds_away"]) for c in fixture["candidates"]):
            raise ValueError("Unrecognized candidate")
        if row["fixture_id"] in seen_fixtures:
            raise ValueError("More than one selection for same fixture")
        seen_fixtures.add(row["fixture_id"])
        key=(row["fixture_id"],row["event_id"])
        if key in seen_pairs:
            raise ValueError("Duplicate selection")
        seen_pairs.add(key)
        if row["decision"]=="matched":
            if row["event_id"] in seen_events:
                raise ValueError("Same OddsAPI event matched twice")
            seen_events.add(row["event_id"])
        if any((d["fixture_id"],d["event_id"])==key and d["decision"]!=row["decision"] for d in old):
            raise ValueError("Contradicts recorded decision")
        if row["decision"]=="matched" and any(d.get("decision")=="matched" and (d["fixture_id"]==row["fixture_id"] or d["event_id"]==row["event_id"]) and (d["fixture_id"],d["event_id"])!=key for d in old):
            raise ValueError("Fixture or provider event already assigned")
        if not any((d["fixture_id"],d["event_id"])==key for d in old):
            updates.append(row)
    # All validation and alias updates happen in memory before writing either file.
    for row in updates:
        saved={**row,"issue_number":int(issue_number)}
        if row["decision"]=="matched":
            approve(db,saved,"github-issue-"+str(issue_number))
        old.append(saved)
    if updates:
        db_path.write_text(json.dumps(db,ensure_ascii=False,indent=2)+"\n")
        decisions_path.write_text(json.dumps(decisions_doc,ensure_ascii=False,indent=2)+"\n")
    print("KVOTER_BATCH_VALIDATED",len(rows),"NEW_DECISIONS",len(updates))

if __name__=="__main__":
    process(os.environ["ISSUE_BODY"],os.environ["ISSUE_NUMBER"])
