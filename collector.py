#!/usr/bin/env python3
"""MEMARA Fixture Collector v1 — standalone; NEVER publishes or edits tickets/bank.

Uses ESPN public scoreboard endpoints on a best-effort, unofficial basis.
Can alternatively process local fixture JSON completely offline.
Python 3.10+; standard library only.
"""
import argparse
import json
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

ZONE = ZoneInfo("Europe/Sarajevo")
ROOT = "https://site.api.espn.com/apis/site/v2/sports"
FOOTBALL = ("eng.1", "esp.1", "ger.1", "ita.1", "fra.1", "ned.1",
            "por.1", "bel.1", "tur.1", "sco.1", "uefa.champions",
            "uefa.europa", "uefa.europa.conf", "usa.1", "bra.1", "arg.1")
BASKETBALL = ("nba",)


def timestamp(value):
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("kickoff timestamp requires timezone")
    return parsed.astimezone(timezone.utc)


def normalized(event, sport, league, target):
    try:
        competition = event["competitions"][0]
        opponents = competition["competitors"]
        home = next(c for c in opponents if c["homeAway"] == "home")["team"]
        away = next(c for c in opponents if c["homeAway"] == "away")["team"]
        start = timestamp(event.get("date") or competition["date"])
        if start.astimezone(ZONE).date() != target:
            return None
        event_id = str(event["id"]).strip()
        home_name = (home.get("displayName") or home.get("name") or "").strip()
        away_name = (away.get("displayName") or away.get("name") or "").strip()
        if not event_id or not home_name or not away_name:
            return None
        state = (event.get("status") or {}).get("type", {}).get("state", "unknown")
        return {
            "id": f"espn:{sport}:{league}:{event_id}",
            "provider": "espn-public-unofficial", "sport": sport,
            "league": league, "home": home_name, "away": away_name,
            "start_utc": start.isoformat().replace("+00:00", "Z"),
            "start_sarajevo": start.astimezone(ZONE).isoformat(),
            "status": state if state in ("pre", "in", "post") else "unknown"
        }
    except (KeyError, TypeError, IndexError, StopIteration, ValueError, AttributeError):
        return None


def from_local(path, target, sport):
    doc = json.loads(Path(path).read_text(encoding="utf-8"))
    rows = doc.get("fixtures") if isinstance(doc, dict) else doc
    if not isinstance(rows, list):
        raise ValueError("local JSON must contain a list or a fixtures list")
    fixtures, errors = [], []
    for index, row in enumerate(rows, 1):
        try:
            if not isinstance(row, dict):
                raise ValueError("fixture must be an object")
            kind = row["sport"]
            if kind not in ("football", "basketball"):
                raise ValueError("unsupported sport")
            if sport != "all" and kind != sport:
                continue
            start = timestamp(row["start_utc"])
            if start.astimezone(ZONE).date() != target:
                continue
            for field in ("league", "home", "away"):
                if not isinstance(row[field], str) or not row[field].strip():
                    raise ValueError(f"missing {field}")
            fixtures.append({
                "id": str(row.get("id") or f"local:{index}"),
                "provider": "local-json", "sport": kind,
                "league": row["league"].strip(), "home": row["home"].strip(),
                "away": row["away"].strip(),
                "start_utc": start.isoformat().replace("+00:00", "Z"),
                "start_sarajevo": start.astimezone(ZONE).isoformat(),
                "status": row.get("status", "unknown")
            })
        except (KeyError, ValueError, TypeError) as exc:
            errors.append(f"local record #{index}: {exc}")
    return fixtures, errors


def collect(target, sport="all", leagues=None, offline=False, input_path=None):
    fixtures, sources, errors = [], [], []
    if input_path:
        try:
            rows, issues = from_local(input_path, target, sport)
            fixtures.extend(rows)
            errors.extend(issues)
            sources.append({"provider": "local-json", "status": "ok", "count": len(rows)})
        except (OSError, ValueError, TypeError) as exc:
            errors.append(f"local input failed: {exc}")
            sources.append({"provider": "local-json", "status": "error", "count": 0})
    if not offline:
        selected = []
        if sport in ("football", "all"):
            selected += [("football", "soccer", s) for s in (leagues or FOOTBALL)]
        if sport in ("basketball", "all"):
            selected += [("basketball", "basketball", s) for s in (leagues or BASKETBALL)]
        # One calendar day per request: several ESPN leagues reject a date range.
        # Local Sarajevo date may include events from preceding UTC calendar day.
        days = [(target - timedelta(days=1)).strftime("%Y%m%d"),
                target.strftime("%Y%m%d")]
        for kind, api_kind, league in selected:
          for utc_day in days:
            url = (f"{ROOT}/{api_kind}/{league}/scoreboard?" +
                   urlencode({"dates": utc_day, "limit": 500}))
            try:
                req = Request(url, headers={"User-Agent": "MEMARA-Collector/1.0",
                                            "Accept": "application/json"})
                with urlopen(req, timeout=20) as response:
                    raw = response.read(8 * 1024 * 1024 + 1)
                if len(raw) > 8 * 1024 * 1024:
                    raise ValueError("response too large")
                events = json.loads(raw)["events"]
                if not isinstance(events, list):
                    raise ValueError("events must be a list")
                found = [normalized(e, kind, league, target) for e in events]
                found = [e for e in found if e]
                fixtures.extend(found)
                sources.append({"provider": "espn-public-unofficial",
                                "sport": kind, "league": league,
                                "status": "ok", "count": len(found), "url": url})
            except (OSError, ValueError, KeyError, TypeError) as exc:
                errors.append(f"ESPN {kind}/{league}: {type(exc).__name__}: {exc}")
                sources.append({"provider": "espn-public-unofficial",
                                "sport": kind, "league": league,
                                "status": "error", "count": 0, "url": url})
    unique = {}
    for item in fixtures:
        key = (item["sport"], item["league"].casefold(),
               item["home"].casefold(), item["away"].casefold(), item["start_utc"])
        unique.setdefault(key, item)
    sorted_rows = sorted(unique.values(),
                         key=lambda r: (r["start_utc"], r["sport"], r["league"]))
    return {
        "schema_version": "1.0", "date": target.isoformat(),
        "timezone": "Europe/Sarajevo",
        "collected_at_utc": datetime.now(timezone.utc).isoformat(),
        "scope": "configured leagues only, not all global fixtures",
        "publication_allowed": False, "status": "partial" if errors else "ok",
        "fixture_count": len(sorted_rows),
        "duplicate_count": len(fixtures) - len(sorted_rows),
        "sources": sources, "errors": errors, "fixtures": sorted_rows
    }


def main():
    p = argparse.ArgumentParser(description="Standalone MEMARA fixture collector")
    p.add_argument("--date", default=datetime.now(ZONE).date().isoformat())
    p.add_argument("--sport", choices=["all", "football", "basketball"], default="all")
    p.add_argument("--league", action="append", help="Repeat for multiple league IDs")
    p.add_argument("--input", help="JSON file containing local fixtures")
    p.add_argument("--regional", action="store_true", help="Add limited Serbia/Bosnia fixtures")
    p.add_argument("--nba-players", action="store_true", help="Include separate manually curated NBA watchlist (no odds)")
    p.add_argument("--offline", action="store_true", help="Use only --input, no internet")
    p.add_argument("--output", default="collector-output/fixtures.json")
    a = p.parse_args()
    try:
        day = date.fromisoformat(a.date)
    except ValueError:
        p.error("--date must be YYYY-MM-DD")
    if a.offline and not a.input:
        p.error("--offline requires --input")
    result = collect(day, a.sport, a.league, a.offline, a.input)
    if a.regional and not a.offline and a.sport in ("all", "football"):
        from memara_regional import fetch_regional
        rows, sources, errors = fetch_regional(day)
        existing = {(f["sport"], f["league"].casefold(), f["home"].casefold(),
                     f["away"].casefold(), f["start_utc"]) for f in result["fixtures"]}
        for fixture in rows:
            key = (fixture["sport"], fixture["league"].casefold(),
                   fixture["home"].casefold(), fixture["away"].casefold(),
                   fixture["start_utc"])
            if key not in existing:
                result["fixtures"].append(fixture)
                existing.add(key)
        result["fixtures"].sort(key=lambda f: f["start_utc"])
        result["sources"].extend(sources)
        result["errors"].extend(errors)
        result["fixture_count"] = len(result["fixtures"])
        result["status"] = "partial" if result["errors"] else "ok"
        result["regional_coverage"] = "INCOMPLETE: TheSportsDB free plan one next fixture per league"
    if a.nba_players and a.sport in ("all", "basketball"):
        try:
            from memara_nba_players import load_nba_players
            result["nba_players"] = load_nba_players()
            result["nba_player_count"] = len(result["nba_players"])
            result["nba_player_note"] = "Manual candidate watchlist only; game availability, player status, points lines and odds are unverified"
        except (OSError, ValueError, TypeError) as exc:
            result["nba_players"] = []
            result["nba_player_count"] = 0
            result["errors"].append(f"NBA watchlist: {exc}")
            result["status"] = "partial"
    output = Path(a.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n",
                      encoding="utf-8")
    print(f"Saved {result['fixture_count']} fixtures and {len(result['errors'])} errors to {output}")
    return 2 if result["errors"] else 0


if __name__ == "__main__":
    sys.exit(main())
