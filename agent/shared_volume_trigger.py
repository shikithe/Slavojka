#!/usr/bin/env python3
"""Isolated shared-volume trigger. Never publishes or changes the bank."""
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
        feed = json.loads(raw)
    except (ValueError, UnicodeDecodeError):
        return False
    if not isinstance(feed, dict) or not isinstance(feed.get("football_candidates"), list):
        return False
    return bool(feed["football_candidates"]) and all(
        isinstance(f, dict) and f.get("id") and f.get("home") and f.get("away")
        and f.get("sport") == "football" and f.get("status") == "pre"
        for f in feed["football_candidates"]
    )

def run_once(feed_path, output_path, state_path, agent_script):
    try:
        first = feed_path.read_bytes()
        if not eligible(first):
            return "waiting: feed missing, invalid or empty"
        # Ensure the writer has finished and the file is stable before consuming.
        time.sleep(2)
        second = feed_path.read_bytes()
        if first != second or not eligible(second):
            return "waiting: feed still changing"
        digest = hashlib.sha256(second).hexdigest()
        if state_path.exists() and state_path.read_text(encoding="utf-8").strip() == digest:
            return "waiting: feed already processed"
        # Agent reads a validated immutable snapshot, never a partially rewritten feed.
        snapshot = output_path.parent / ".validated-collector-feed.json"
        output_path.parent.mkdir(parents=True, exist_ok=True)
        temp = snapshot.with_suffix(".tmp")
        temp.write_bytes(second)
        os.replace(temp, snapshot)
        subprocess.run([sys.executable, str(agent_script), "--input", str(snapshot),
                        "--output", str(output_path)], check=True)
        state_path.parent.mkdir(parents=True, exist_ok=True)
        tmp_state = state_path.with_suffix(".tmp")
        tmp_state.write_text(digest + "\n", encoding="utf-8")
        os.replace(tmp_state, state_path)
        return "processed: agent completed successfully"
    except FileNotFoundError:
        return "waiting: feed not available"
    except subprocess.CalledProcessError as exc:
        return f"failed: agent exited {exc.returncode}; will retry"

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--feed", default="/shared/collector-feed.json")
    p.add_argument("--output", default="/shared/agent/history-h2h.json")
    p.add_argument("--state", default="/shared/agent/.last-processed-sha256")
    p.add_argument("--agent-script", default=str(Path(__file__).with_name("cross_competition_history.py")))
    p.add_argument("--interval", type=int, default=15)
    p.add_argument("--once", action="store_true")
    a = p.parse_args()
    if a.interval < 1: p.error("interval must be >=1")
    while True:
        status = run_once(Path(a.feed), Path(a.output), Path(a.state), Path(a.agent_script))
        print(status, flush=True)
        if a.once: break
        time.sleep(a.interval)

if __name__ == "__main__":
    main()
