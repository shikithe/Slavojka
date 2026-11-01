#!/usr/bin/env python3
"""Kvoter: database -> manual aliases -> optional researched aliases -> partition.
No odds refetch, no betting, no publication. Manual records are league-scoped.
"""
import argparse
import json
import os
import re
from pathlib import Path
from urllib.request import Request, urlopen
from kvoter import build, utc
from team_identity import normalize
from category_filter import excluded, category

ROOT = Path(__file__).resolve().parent

def read(path, default):
    p = Path(path)
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else default

def write(path, data):
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name(p.name + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, p)

def safe_identity(db, league, names, sources=None, verified=True):
    names = list(dict.fromkeys(n.strip() for n in names if isinstance(n, str) and n.strip()))
    if any(category(n) for n in names):
        return False
    if len({normalize(n) for n in names}) < 2:
        return False
    entries = db["teams"]
    existing = {(e["league"], normalize(n)): e for e in entries for n in e["names"]}
    hits = {id(existing[(league, normalize(n))]) for n in names if (league, normalize(n)) in existing}
    if len(hits) > 1:
        return False
    target = next((e for e in entries if id(e) in hits), None)
    if target is None:
        target = {"id": league + "-" + normalize(names[0]).replace(" ", "-"), "league": league, "names": [], "sources": [], "verified": verified}
        if any(e["id"] == target["id"] for e in entries):
            return False
        entries.append(target)
    target["names"] = list(dict.fromkeys(target["names"] + names))
    target["sources"] = list(dict.fromkeys(target.get("sources", []) + (sources or [])))
    return True

def unresolved(history, offers, report):
    ids = {f["fixture_id"] for f in report["unmatched_fixtures"]}
    for f in history["fixtures"]:
        if (f.get("fixture_id") or f.get("id")) not in ids:
            continue
        if excluded(f.get('home'), f.get('away'), f.get('league')):
            continue
        for offer in offers:
            if excluded(offer.get('home'), offer.get('away'), offer.get('league')):
                continue
            if offer.get("league") != f.get("league"):
                continue
            a, b = utc(f.get("start_utc")), utc(offer.get("start_utc"))
            if not a or not b or abs((a-b).total_seconds()) > 5400:
                continue
            for side in ("home", "away"):
                if normalize(f.get(side)) != normalize(offer.get(side)):
                    yield {"fixture_id": f.get("fixture_id") or f.get("id"), "league": f["league"],
                           "side": side, "collector_name": f.get(side), "provider_name": offer.get(side),
                           "event_id": offer.get("event_id")}

def run_match(history, offers, db, database_path):
    write(database_path, db)
    os.environ["KVOTER_ALIASES_PATH"] = str(Path(database_path).resolve())
    return build(history, offers)

def online_research(queries, api_key, model):
    """Optional OpenAI Responses web search; unverified output goes to review, never auto-approved."""
    if not api_key or not queries:
        return []
    results = []
    for q in queries:
        prompt = ("Research whether these are the exact same professional football team, not reserves, U21, or women. "
                  "Find independent credible source URLs and alternate names. Do not invent URLs. "
                  "Return a brief assessment, names, and URLs. LEAGUE: " + str(q["league"]) +
                  "; COLLECTOR: " + str(q["collector_name"]) + "; ODDS PROVIDER: " + str(q["provider_name"]))
        body = json.dumps({"model": model, "tools": [{"type": "web_search_preview"}],
                           "input": prompt, "max_output_tokens": 550}).encode()
        req = Request("https://api.openai.com/v1/responses", data=body,
                      headers={"Authorization": "Bearer " + api_key, "Content-Type": "application/json"})
        try:
            with urlopen(req, timeout=45) as response:
                data = json.load(response)
            results.append({"query": q, "response": data.get("output", []), "status": "needs_verification"})
        except Exception as exc:
            results.append({"query": q, "status": "research_error", "error": str(exc)[:180]})
    return results

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--history", required=True)
    p.add_argument("--offers", required=True)
    p.add_argument("--database", default=str(ROOT / "team-database.json"))
    p.add_argument("--manual", default=str(ROOT / "unesi rucno" / "aliases.json"))
    p.add_argument("--matched-output", required=True)
    p.add_argument("--unmatched-output", required=True)
    p.add_argument("--research-output", required=True)
    p.add_argument("--report", required=True)
    p.add_argument("--model", default="gpt-4.1-mini")
    args = p.parse_args()
    history = read(args.history, {"fixtures": []})
    raw = read(args.offers, {"offers": []})
    offers = raw.get("offers", []) if isinstance(raw, dict) else raw
    db = read(args.database, {"schema_version": 1, "teams": []})
    first = run_match(history, offers, db, args.database)
    # Manual aliases take precedence over online research; they are never guessed.
    manual = read(args.manual, {"aliases": []})
    accepted_manual = 0
    for item in manual.get("aliases", []):
        if item.get("league") and item.get("collector_name") and item.get("provider_name"):
            if safe_identity(db, item["league"], [item["collector_name"], item["provider_name"]],
                             sources=["manual"], verified=True):
                accepted_manual += 1
    second = run_match(history, offers, db, args.database)
    remaining = list({(q["league"], q["collector_name"], q["provider_name"]): json.dumps(q, ensure_ascii=False)
                      for q in unresolved(history, offers, second)}.values())
    queue = [json.loads(x) for x in remaining]
    # Web research creates proposals only; never silently merge unverified identities.
    researched = online_research(queue, os.getenv("OPENAI_API_KEY", ""), args.model)
    third = run_match(history, offers, db, args.database)
    matched, unmatched = third["matched_fixtures"], third["unmatched_fixtures"]
    assert len(matched) + len(unmatched) == len(history["fixtures"])
    assert not ({x["fixture_id"] for x in matched} & {x["fixture_id"] for x in unmatched})
    metadata = {"generated_at_utc": third["generated_at_utc"]}
    write(args.matched_output, dict(metadata, total=len(matched), fixtures=matched))
    write(args.unmatched_output, dict(metadata, total=len(unmatched), fixtures=unmatched))
    write(args.research_output, {"queries": queue, "research": researched,
                                 "notice": "Research results require identity verification before database import."})
    write(args.report, dict(third, stages={"first_matched": first["matched"],
                                            "after_manual_matched": second["matched"],
                                            "manual_entries_accepted": accepted_manual,
                                            "online_research_queries": len(queue),
                                            "online_research_attempts": len(researched)}))
    print(json.dumps({"first": first["matched"], "after_manual": second["matched"],
                      "final_matched": len(matched), "unmatched": len(unmatched),
                      "research_pending_review": len(researched)}))

if __name__ == "__main__":
    main()
