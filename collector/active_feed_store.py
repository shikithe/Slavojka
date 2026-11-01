#!/usr/bin/env python3
"""Validate isolated Collector active feed; never touches production state."""
import argparse
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

TTL = timedelta(hours=23, minutes=59)

def timestamp(value):
    if not isinstance(value, str):
        raise ValueError("Missing timestamp")
    result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if result.tzinfo is None:
        raise ValueError("Timestamp must include timezone")
    return result.astimezone(timezone.utc)

def validate(feed, raw, now=None):
    now = now or datetime.now(timezone.utc)
    start = timestamp(raw["window_start_utc"])
    end = timestamp(raw["window_end_utc"])
    if end - start != TTL:
        raise ValueError("Collector window must be exactly 23h59m")
    if not (start <= now < end):
        raise ValueError("Active feed expired or not yet valid")
    if not isinstance(feed.get("football_candidates"), list):
        raise ValueError("Missing football candidates")
    if not isinstance(feed.get("nba_games"), list):
        raise ValueError("Missing NBA games")
    if not feed["football_candidates"] and not feed["nba_games"]:
        raise ValueError("Refusing to publish empty active feed")
    generated = timestamp(feed["generated_at_utc"])
    if generated < start or generated > now:
        raise ValueError("Feed generated timestamp is outside valid period")
    if feed.get("date") != raw.get("date"):
        raise ValueError("Feed and raw dates differ")
    return {"active": True, "valid_from_utc": start.isoformat(), "expires_at_utc": end.isoformat(),
            "football": len(feed["football_candidates"]), "nba": len(feed["nba_games"])}

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["validate"])
    parser.add_argument("--feed", required=True)
    parser.add_argument("--raw", required=True)
    args = parser.parse_args()
    print(json.dumps(validate(json.loads(Path(args.feed).read_text()),
                              json.loads(Path(args.raw).read_text()))))

if __name__ == "__main__":
    main()
