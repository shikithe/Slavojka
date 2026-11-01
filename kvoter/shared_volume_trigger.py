#!/usr/bin/env python3
"""Watch Agent history; fetch real Odds API offers once per validated new daily history."""
import argparse
import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path

def eligible(raw):
    try:
        doc=json.loads(raw)
        return isinstance(doc,dict) and bool(doc.get("date")) and isinstance(doc.get("fixtures"),list) and bool(doc["fixtures"]) and all(f.get("fixture_id") and f.get("league") and f.get("start_utc") for f in doc["fixtures"])
    except (ValueError,TypeError,UnicodeDecodeError):
        return False

def run_once(history, state, script, output_dir, api_key=None):
    try:
        first=history.read_bytes()
        if not eligible(first):
            return "waiting: history missing, incomplete or empty"
        time.sleep(2)
        second=history.read_bytes()
        if first!=second or not eligible(second):
            return "waiting: history still changing"
        digest=hashlib.sha256(second).hexdigest()
        if state.exists() and state.read_text(encoding="utf-8").strip()==digest:
            return "waiting: history already processed"
        if not (api_key if api_key is not None else os.getenv("THE_ODDS_API_KEY","").strip()):
            return "waiting: THE_ODDS_API_KEY not configured"
        output_dir.mkdir(parents=True,exist_ok=True)
        snapshot=output_dir/".validated-history-h2h.json"
        temp=snapshot.with_suffix(".tmp")
        temp.write_bytes(second)
        os.replace(temp,snapshot)
        env=os.environ.copy()
        if api_key is not None: env["THE_ODDS_API_KEY"]=api_key
        subprocess.run([sys.executable,str(script),"--feed",str(snapshot),"--output",str(output_dir/"match-report.json"),"--raw-output",str(output_dir/"league-odds-raw.json"),"--offers-output",str(output_dir/"provider-offers.json")],check=True,env=env)
        report=json.loads((output_dir/"match-report.json").read_text(encoding="utf-8"))
        if report.get("provider_status")!="api_fetched" or report.get("provider_errors"):
            return "failed: provider incomplete; retry on next check"
        state.parent.mkdir(parents=True,exist_ok=True)
        tmp=state.with_suffix(".tmp")
        tmp.write_text(digest+"\n",encoding="utf-8")
        os.replace(tmp,state)
        return "processed: Kvoter Odds API completed"
    except FileNotFoundError:
        return "waiting: history not available"
    except (subprocess.CalledProcessError,ValueError,KeyError) as exc:
        return f"failed: {type(exc).__name__}; will retry"

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--history",default="/shared/agent/history-h2h.json")
    p.add_argument("--state",default="/shared/kvoter/.last-processed-sha256")
    p.add_argument("--output-dir",default="/shared/kvoter")
    p.add_argument("--script",default=str(Path(__file__).with_name("the_odds_api.py")))
    p.add_argument("--interval",type=int,default=15)
    p.add_argument("--once",action="store_true")
    a=p.parse_args()
    while True:
        print(run_once(Path(a.history),Path(a.state),Path(a.script),Path(a.output_dir)),flush=True)
        if a.once:break
        time.sleep(a.interval)

if __name__=="__main__":
    main()
