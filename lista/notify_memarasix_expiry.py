#!/usr/bin/env python3
"""Use ListaSix EXISTING 08:55 expiry cron to request MemaraSix stale-list cleanup.

Idempotent: stop retrying after same-day expiry ACK is committed on MemaraSix.
Requires existing MEMARASIX_DISPATCH_TOKEN secret (Memara-tip Contents write).
"""
import base64
import json
import os
import sys
from datetime import datetime, time, timezone
from urllib.error import HTTPError, URLError
from zoneinfo import ZoneInfo

from lista.notify_memarasix import request_json, TARGET_REPO

SAR = ZoneInfo("Europe/Sarajevo")


def local_day(now):
    local = now.astimezone(SAR)
    if local.time() < time(8, 55):
        return None
    return local.date().isoformat()


def acknowledged(day, token, requester=request_json):
    url = "https://api.github.com/repos/" + TARGET_REPO + "/contents/listasix-data/expiry-receipt.json?ref=main"
    try:
        doc = requester("GET", url, token)
        if doc.get("encoding") != "base64":
            return False
        receipt = json.loads(base64.b64decode(doc["content"]))
        return receipt.get("date") == day and receipt.get("status") in (
            "expired_previous_day", "no_active_list", "current_day_preserved"
        )
    except (HTTPError, URLError, TimeoutError, ValueError, TypeError, KeyError):
        return False


def relay(token, now=None, requester=request_json):
    now = now or datetime.now(timezone.utc)
    day = local_day(now)
    if not day:
        print("LISTASIX_MEMARA_EXPIRY_NOT_DUE")
        return "not_due"
    if not token:
        print("::warning::MEMARASIX_DISPATCH_TOKEN missing; MemaraSix expiry not sent")
        return "missing_token"
    if acknowledged(day, token, requester):
        print("MEMARASIX_EXPIRY_CONFIRMED", day)
        return "confirmed"
    url = "https://api.github.com/repos/" + TARGET_REPO + "/dispatches"
    try:
        requester("POST", url, token, {
            "event_type": "listasix-expire-import",
            "client_payload": {"date": day, "source": "listasix-expire-cron"}
        })
    except (HTTPError, URLError, TimeoutError) as exc:
        print("::warning::LISTASIX_MEMARA_EXPIRY_DISPATCH_FAILED", type(exc).__name__, str(exc)[:200])
        return "retry_required"
    print("LISTASIX_MEMARA_EXPIRY_DISPATCHED", day)
    return "dispatched"


def main():
    status = relay(os.environ.get("MEMARASIX_DISPATCH_TOKEN", ""))
    print("LISTASIX_MEMARA_EXPIRY_RELAY_STATE", status)
    # Retry next existing five-minute ListaSix expiry cron, never break source cleanup.
    return 0


if __name__ == "__main__":
    sys.exit(main())
