#!/usr/bin/env python3
"""Watch history, provider offers, approved identities and unmatched changes."""
import argparse, hashlib, time
from pathlib import Path
from kvoter.reconcile import reconcile

def run_once(history, offers, database, names, out, state):
    paths=(history,offers,database,out/"unmatched_fixtures.json")
    try:
        chunks=[p.read_bytes() if p.exists() else b"" for p in paths]
        if not all(chunks[:3]):
            return "waiting: missing history, offers or approved team database"
        digest=hashlib.sha256(b"".join(len(c).to_bytes(8,"big")+c for c in chunks)).hexdigest()
        if state.exists() and state.read_text().strip()==digest:
            return "waiting: no change"
        report=reconcile(history,offers,database,names,out)
        # Record the post-reconciliation state, avoiding repeated runs on own output.
        chunks=[p.read_bytes() if p.exists() else b"" for p in paths]
        final=hashlib.sha256(b"".join(len(c).to_bytes(8,"big")+c for c in chunks)).hexdigest()
        state.parent.mkdir(parents=True,exist_ok=True)
        tmp=state.with_suffix(".tmp");tmp.write_text(final+"\n");tmp.replace(state)
        return "reconciled: %d matched, %d unmatched"%(report["matched"],report["unavailable"])
    except (ValueError, OSError, KeyError) as exc:
        return "retry: "+str(exc)[:120]

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--history",default="/shared/agent/history-h2h.json")
    p.add_argument("--offers",default="/shared/kvoter/provider-offers.json")
    p.add_argument("--database",default=str(Path(__file__).with_name("team-database.json")))
    p.add_argument("--names",default="/shared/kvoter/team-database/provider-team-names.json")
    p.add_argument("--output-dir",default="/shared/kvoter")
    p.add_argument("--state",default="/shared/kvoter/.reconcile-state")
    p.add_argument("--interval",type=int,default=15)
    p.add_argument("--once",action="store_true")
    a=p.parse_args()
    while True:
        print(run_once(Path(a.history),Path(a.offers),Path(a.database),Path(a.names),Path(a.output_dir),Path(a.state)),flush=True)
        if a.once: break
        time.sleep(a.interval)
if __name__=="__main__": main()
