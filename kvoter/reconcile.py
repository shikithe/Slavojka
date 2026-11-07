#!/usr/bin/env python3
"""Reconcile Agent fixtures against real provider events and approved identities.

Provider spellings are recorded first; unapproved spellings never imply identity.
Outputs are derived on each run, so removals from unmatched cannot be stale.
"""
import argparse, json, os
from pathlib import Path
from kvoter.kvoter import build
from kvoter.provider_team_names import collect_names

def atomic(path, data):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    temp=path.with_name(path.name+".tmp")
    temp.write_text(json.dumps(data,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    os.replace(temp,path)

def reconcile(history_path, offers_path, database_path, names_path, output_dir):
    history=json.loads(Path(history_path).read_text(encoding="utf-8"))
    source=json.loads(Path(offers_path).read_text(encoding="utf-8"))
    offers=source.get("offers",[]) if isinstance(source,dict) else source
    if not isinstance(offers,list): raise ValueError("Invalid provider offers")
    # First persist the actual spellings from the quoted odds provider.
    collect_names(offers,names_path)
    os.environ["KVOTER_ALIASES_PATH"]=str(Path(database_path).resolve())
    # Preserve actual odds provider provenance on manual re-reconciliation.
    # API-Football offers must never be mislabeled as legacy The Odds API.
    provider=source.get("source") if isinstance(source,dict) else None
    report=build(history,offers,source=provider or "the-odds-api-v4")
    out=Path(output_dir)
    atomic(out/"matched_fixtures.json",{"generated_at_utc":report["generated_at_utc"],"fixtures":report["matched_fixtures"],"total":report["matched"]})
    atomic(out/"unmatched_fixtures.json",{"generated_at_utc":report["generated_at_utc"],"fixtures":report["unmatched_fixtures"],"total":report["unavailable"]})
    atomic(out/"match-report.json",report)
    return report

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--history",default="/shared/agent/history-h2h.json")
    p.add_argument("--offers",default="/shared/kvoter/provider-offers.json")
    p.add_argument("--database",default=str(Path(__file__).with_name("team-database.json")))
    p.add_argument("--names",default="/shared/kvoter/team-database/provider-team-names.json")
    p.add_argument("--output-dir",default="/shared/kvoter")
    a=p.parse_args()
    r=reconcile(a.history,a.offers,a.database,a.names,a.output_dir)
    print("KVOTER_RECONCILED",r["matched"],r["unavailable"])
if __name__=="__main__": main()
