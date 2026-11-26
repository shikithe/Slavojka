"""Compatibility reader for FairXG feedback; no Poisson or inferred probabilities."""
import json
from pathlib import Path
from lista.scout_six_markets import canonical_hash, feedback, save

def inspect(feed, active, history, scout, today):
    if any(d.get("date") != today for d in (feed, active, scout)) or scout.get("model") != "FairXG":
        raise ValueError("FairXG and source dates must match")
    if scout.get("source_feed_sha256") != canonical_hash(feed) or scout.get("source_active_sha256") != canonical_hash(active):
        raise ValueError("FairXG source fingerprint mismatch")
    return feedback(scout)

def main():
    root=Path(".")
    def read(p): return json.loads((root/p).read_text(encoding="utf-8"))
    report=read("shared/agent/scout-six-markets.json")
    first,second=inspect(read("shared/collector-feed.json"),read("shared/active-list.json"),{},report,report["date"])
    save(root/"shared/agent/scout-feedback.json",first)
    save(root/"shared/agent/top10-feedback.json",second)
    return first,second
if __name__=="__main__":
    main()
