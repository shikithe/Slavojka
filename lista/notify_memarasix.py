#!/usr/bin/env python3
"""Signal MemaraSix as soon as a fully verified ListaSix list is committed.

The GitHub repository_dispatch API requires a secret fine-grained token with
Contents: write on shikithe/Memara-tip; GITHUB_TOKEN for Slavojka cannot trigger
another repository. Re-dispatch until the exact active-list hash is ACKed.
Subsequent regular ListaSix workflow runs retry the ACK, without re-collecting.
"""
import base64
import hashlib
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

TARGET_REPO = "shikithe/Memara-tip"
SAR = ZoneInfo("Europe/Sarajevo")


def parse_dt(value):
    stamp = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if stamp.tzinfo is None:
        raise ValueError("No timezone")
    return stamp.astimezone(timezone.utc)


def fingerprint(data):
    payload = json.dumps(data, ensure_ascii=False, sort_keys=True,
                         separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def verify_source(root, now):
    """Only send a signal when ALL committed ListaSix inputs are consistent."""
    def read(relative):
        return json.loads((root / relative).read_text(encoding="utf-8"))
    active = read("shared/active-list.json")
    history = read("shared/agent/history-h2h.json")
    provider = read("shared/kvoter/provider-offers.json")
    matched = read("shared/kvoter/matched_fixtures.json")
    today = now.astimezone(SAR).date().isoformat()
    if active.get("date") != today or history.get("date") != today:
        raise ValueError("No completed same-day source offer and history")
    if not active.get("publication_allowed") or parse_dt(active.get("expires_at")) <= now:
        raise ValueError("Source list is unapproved or expired")
    fixtures = active.get("fixtures")
    if not isinstance(fixtures, list) or not fixtures:
        raise ValueError("No ready fixtures")
    if not history.get("fixtures") or not history.get("leagues"):
        raise ValueError("Missing completed source history")
    if not provider.get("offers") or not matched.get("fixtures"):
        raise ValueError("Missing confirmed source odds matching")
    ids = [row.get("fixture_id") for row in fixtures if isinstance(row, dict)]
    matched_ids = {row.get("fixture_id") for row in matched["fixtures"]}
    if len(ids) != len(fixtures) or any(not fid for fid in ids):
        raise ValueError("Invalid source fixture IDs")
    if len(set(ids)) != len(ids) or not set(ids).issubset(matched_ids):
        raise ValueError("ListaSix is not completely reconciled")
    return {"date": today, "active_sha256": fingerprint(active),
            "fixture_count": len(fixtures)}


def request_json(method, url, token, data=None):
    headers = {"Authorization": "Bearer " + token,
               "Accept": "application/vnd.github+json",
               "X-GitHub-Api-Version": "2022-11-28",
               "User-Agent": "ListaSix-ready-event-relay"}
    payload = None if data is None else json.dumps(data).encode("utf-8")
    if payload is not None:
        headers["Content-Type"] = "application/json"
    with urlopen(Request(url, data=payload, headers=headers, method=method), timeout=20) as response:
        body = response.read()
        return json.loads(body) if body else {}


def acknowledged(expected, token, requester=request_json):
    url = "https://api.github.com/repos/" + TARGET_REPO + "/contents/listasix-data/sync-receipt.json?ref=main"
    try:
        doc = requester("GET", url, token)
        if doc.get("encoding") != "base64":
            return False
        receipt = json.loads(base64.b64decode(doc["content"]))
        if receipt.get("date") != expected["date"] or receipt.get("active_sha256") != expected["active_sha256"]:
            return False
        # Independently verify MemaraSix actually committed the full source list.
        url2 = "https://api.github.com/repos/" + TARGET_REPO + "/contents/listasix-data/active-list.json?ref=main"
        active_doc = requester("GET", url2, token)
        if active_doc.get("encoding") != "base64":
            return False
        active = json.loads(base64.b64decode(active_doc["content"]))
        return active.get("date") == expected["date"] and fingerprint(active) == expected["active_sha256"]
    except (HTTPError, URLError, ValueError, KeyError, TypeError, TimeoutError):
        return False


def dispatch(signal, token, requester=request_json):
    url = "https://api.github.com/repos/" + TARGET_REPO + "/dispatches"
    requester("POST", url, token, {
        "event_type": "listasix-active-list-ready",
        "client_payload": signal})


def relay(root, token, now, requester=request_json, nap=time.sleep, rounds=3, checks=5):
    try:
        signal = verify_source(root, now)
    except (OSError, KeyError, ValueError, TypeError) as exc:
        print("LISTASIX_NOT_READY_NO_DISPATCH", str(exc)[:150])
        return "not_ready"
    if not token:
        print("::warning::MISSING_MEMARASIX_DISPATCH_TOKEN: configure a fine-grained GitHub token for Memara-tip (Contents write). No cross-repository event dispatched.")
        return "missing_credentials"
    for attempt in range(1, rounds+1):
        if acknowledged(signal, token, requester):
            print("MEMARASIX_SYNC_CONFIRMED", json.dumps(signal))
            return "confirmed"
        try:
            dispatch(signal, token, requester)
            print("LISTASIX_READY_DISPATCHED", "attempt=", attempt, json.dumps(signal))
        except (HTTPError, URLError, TimeoutError, ValueError) as exc:
            print("::warning::LISTASIX_DISPATCH_FAILED", type(exc).__name__, str(exc)[:150])
        for check in range(checks):
            nap(15)
            if acknowledged(signal, token, requester):
                print("MEMARASIX_SYNC_CONFIRMED", json.dumps(signal))
                return "confirmed"
    print("::warning::LISTASIX_SYNC_NOT_ACKNOWLEDGED; next ListaSix workflow run will retry until exact receipt is committed")
    return "retry_required"


def main():
    now = datetime.now(timezone.utc)
    token = os.environ.get("MEMARASIX_DISPATCH_TOKEN", "")
    state = relay(Path("."), token, now)
    print("LISTASIX_MEMARASIX_RELAY_STATE", state)
    return 0  # do not break ListaSix publishing if MemaraSix is unavailable


if __name__ == "__main__":
    sys.exit(main())
