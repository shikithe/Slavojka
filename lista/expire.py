#!/usr/bin/env python3
"""Remove expired PUBLIC ListaSix offer only; preserve collector history and aliases."""
import json
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

TZ=ZoneInfo("Europe/Sarajevo")
PUBLIC=Path("docs/active-list.json")
def expire(now=None):
    now=(now or datetime.now(timezone.utc)).astimezone(TZ)
    if not PUBLIC.exists():
        return False
    try:
        data=json.loads(PUBLIC.read_text(encoding="utf-8"))
        expires=datetime.fromisoformat(data["expires_at"])
        if expires.tzinfo is None:
            raise ValueError("Expiry must have timezone")
        if now >= expires.astimezone(TZ):
            PUBLIC.unlink()
            print("EXPIRED_PUBLIC_LIST_DELETED")
            return True
    except (ValueError,KeyError,TypeError,json.JSONDecodeError) as e:
        raise RuntimeError("Invalid public list: refusing silent deletion") from e
    print("PUBLIC_LIST_NOT_EXPIRED")
    return False
if __name__=="__main__":
    expire()
