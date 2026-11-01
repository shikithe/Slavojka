#!/usr/bin/env python3
"""Create a manual review queue whenever Kvoter reports at least one unmatched fixture.
Compare unmatched Agent fixtures with similar Odds API events, never auto-approve.
"""
import argparse
import hashlib
import json
import os
import time
from pathlib import Path
from kvoter.manual_candidates import build
from kvoter.category_filter import excluded

def run_once(report_path, history_path, offers_path, output_path, state_path):
    try:
        sources=[report_path,history_path,offers_path]
        first=[p.read_bytes() for p in sources]
        time.sleep(1)
        if first!=[p.read_bytes() for p in sources]:
            return "waiting: inputs changing"
        report,history,offers=[json.loads(x) for x in first]
        unmatched=report.get("unmatched_fixtures",[])
        if not isinstance(unmatched,list) or not unmatched:
            return "waiting: no unmatched fixtures"
        fixtures=history.get("fixtures",[])
        ids={f.get("fixture_id") for f in fixtures}
        pending=[f for f in unmatched if f.get("fixture_id") in ids and not excluded(f.get("home"),f.get("away"),f.get("league"))]
        if not pending:
            return "waiting: no eligible unmatched fixtures"
        digest=hashlib.sha256(b"".join(first)).hexdigest()
        if state_path.exists() and state_path.read_text().strip()==digest:
            return "waiting: unchanged queue"
        candidates=build(history,offers,{"fixtures":pending})
        decisions_path=Path(__file__).parent/"manual"/"decisions.json"
        decisions=json.loads(decisions_path.read_text()).get("decisions",[]) if decisions_path.exists() else []
        approved={d.get("fixture_id") for d in decisions if d.get("decision")=="matched"}
        rejected={(d.get("fixture_id"),d.get("event_id")) for d in decisions if d.get("decision")=="rejected"}
        candidates["fixtures"]=[f for f in candidates["fixtures"] if f.get("fixture_id") not in approved]
        for f in candidates["fixtures"]:
            f["candidates"]=[c for c in f["candidates"] if (f.get("fixture_id"),c.get("event_id")) not in rejected]
        candidates["total"]=len(candidates["fixtures"])
        candidates["review_required"]=True
        candidates["auto_approved"]=False
        output_path.parent.mkdir(parents=True,exist_ok=True)
        tmp=output_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(candidates,ensure_ascii=False,indent=2)+"\n")
        os.replace(tmp,output_path)
        state_path.parent.mkdir(parents=True,exist_ok=True)
        tmp=state_path.with_suffix(".tmp")
        tmp.write_text(digest+"\n")
        os.replace(tmp,state_path)
        return f"manual_queue: {len(pending)} unmatched, {sum(bool(f['candidates']) for f in candidates['fixtures'])} with suggestions"
    except FileNotFoundError:
        return "waiting: missing report, history or offers"
    except (ValueError,TypeError,KeyError) as exc:
        return f"failed: invalid input ({type(exc).__name__})"

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--report",default="/shared/kvoter/match-report.json")
    p.add_argument("--history",default="/shared/agent/history-h2h.json")
    p.add_argument("--offers",default="/shared/kvoter/provider-offers.json")
    p.add_argument("--output",default="/shared/kvoter/manual-candidates.json")
    p.add_argument("--state",default="/shared/kvoter/.manual-queue-sha256")
    p.add_argument("--interval",type=int,default=15)
    p.add_argument("--once",action="store_true")
    a=p.parse_args()
    while True:
        print(run_once(*(Path(x) for x in (a.report,a.history,a.offers,a.output,a.state))),flush=True)
        if a.once: break
        time.sleep(a.interval)

if __name__=="__main__":
    main()
