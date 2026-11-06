#!/usr/bin/env python3
"""API-Football v3 pre-match bookmaker adapter for ListaSix.

Only join ESPN fixtures to API-Football fixtures if league, BOTH team identities,
and kickoff agree; never guess identities or fabricate prices.
API credentials are sent only in the HTTP header, never in URLs or reports.
"""
import argparse
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from kvoter.kvoter import match, utc
from kvoter.reconcile import reconcile

BASE = "https://v3.football.api-sports.io"
# Explicit league identity mapping; unrelated leagues must never be joined.
LEAGUE_IDS = {
    "eng.1": 39, "ger.1": 78, "esp.1": 140, "ita.1": 135,
    "fra.1": 61, "ned.1": 88, "por.1": 94, "bel.1": 144,
    "sco.1": 179, "tur.1": 203,
    "uefa.champions": 2, "uefa.europa": 3, "uefa.europa.conf": 848,
    "bra.1": 71, "arg.1": 128, "usa.1": 253,
}
API_TO_ESPN = {value: key for key, value in LEAGUE_IDS.items()}


def api_get(path, params, key):
    url = BASE + "/" + path + ("?" + urlencode(params) if params else "")
    request = Request(url, headers={
        "x-apisports-key": key, "User-Agent": "ListaSix-Kvoter-API-Football/1.0"
    })
    with urlopen(request, timeout=25) as response:
        data = json.load(response)
    if not isinstance(data, dict):
        raise ValueError("API-Football did not return a JSON object")
    errors = data.get("errors")
    if errors:
        raise ValueError("API-Football service returned an error: " + str(errors)[:200])
    if not isinstance(data.get("response"), list):
        raise ValueError("API-Football response was not a list")
    return data


def bookmaker_markets(bookmaker):
    markets = {}
    if not isinstance(bookmaker, dict):
        return markets
    for bet in bookmaker.get("bets", []):
        label = str(bet.get("name", "")).strip().casefold()
        if label in ("match winner", "1x2", "fulltime result", "full time result"):
            key = "1X2"
        elif label in ("goals over/under", "over/under", "total goals"):
            key = "goals"
        elif label in ("both teams score", "both teams to score"):
            key = "BTTS"
        else:
            continue
        for item in bet.get("values", []):
            value = str(item.get("value", "")).strip().casefold()
            try:
                odd = float(item.get("odd"))
            except (TypeError, ValueError):
                continue
            if not 1.0 < odd < 1001.0:
                continue
            if key == "1X2":
                outcome = {"home": "home", "1": "home",
                           "draw": "draw", "x": "draw",
                           "away": "away", "2": "away"}.get(value)
                if outcome:
                    markets.setdefault("1X2", {})[outcome] = odd
            elif key == "goals":
                over = re.fullmatch(r"over\\s+(1\\.5|2\\.5)", value)
                if over:
                    markets["2+" if over.group(1) == "1.5" else "3+"] = {"over": odd}
            elif key == "BTTS" and value in ("yes", "no"):
                markets.setdefault("BTTS", {})[value] = odd
    return markets


def find_fixture_pairs(history, api_fixture_rows):
    """Map only unambiguous, user-approved/exact team identities."""
    fixtures = history.get("fixtures", [])
    indexed = {}
    for event in api_fixture_rows:
        league_id = event.get("league", {}).get("id")
        try:
            league_id = int(league_id)
        except (TypeError, ValueError):
            continue
        league = API_TO_ESPN.get(league_id)
        if league is None:
            continue
        teams = event.get("teams", {})
        fixture = event.get("fixture", {})
        if not fixture.get("id"):
            continue
        offer = {
            "league": league,
            "home": teams.get("home", {}).get("name"),
            "away": teams.get("away", {}).get("name"),
            "start_utc": fixture.get("date"),
        }
        indexed.setdefault(league, []).append((event, offer))
    pairs = []
    for item in fixtures:
        league = item.get("league")
        hits = [
            event for event, offer in indexed.get(league, [])
            if match(item, offer)
        ]
        if len(hits) == 1:
            pairs.append((item, hits[0]))
    # Guard against a single API event being assigned to two ESPN fixtures.
    counts = {}
    for _, event in pairs:
        ident = event["fixture"]["id"]
        counts[ident] = counts.get(ident, 0) + 1
    return [(f, e) for f, e in pairs if counts[e["fixture"]["id"]] == 1]


def parse_odds_response(espn_fixture, api_fixture, odds_response, observed_at):
    fixture_id = api_fixture["fixture"]["id"]
    league_id = int(api_fixture["league"]["id"])
    result = []
    for row in odds_response:
        if not isinstance(row, dict):
            continue
        if row.get("fixture", {}).get("id") != fixture_id:
            continue
        if int(row.get("league", {}).get("id", -1)) != league_id:
            continue
        provider_updated = row.get("update")
        # If API does not supply an update field, record observation time
        # separately rather than claiming to know provider's last update.
        timestamp = provider_updated or observed_at
        for bookmaker in row.get("bookmakers", []):
            markets = bookmaker_markets(bookmaker)
            name = bookmaker.get("name")
            if not name or not markets:
                continue
            result.append({
                "event_id": "api-football:" + str(fixture_id),
                "league": espn_fixture["league"],
                "home": api_fixture["teams"]["home"]["name"],
                "away": api_fixture["teams"]["away"]["name"],
                "start_utc": api_fixture["fixture"]["date"],
                "bookmaker": str(name).strip(),
                "updated_at_utc": timestamp,
                "observed_at_utc": observed_at,
                "timestamp_basis": "provider_update" if provider_updated else "api_retrieval",
                "source": "api-football-v3",
                "markets": markets,
            })
    return result


def collect(history, key, get=api_get, max_event_requests=40):
    """Fetch fixture identities, then only query odds for safe ESPN matches.

    One fixtures request per UTC date, then one odds request per verified event.
    Never paginate the entire global bookmaker catalogue at 15-min intervals.
    """
    fixtures = [f for f in history.get("fixtures", [])
                if f.get("league") in LEAGUE_IDS and utc(f.get("start_utc"))]
    dates = sorted({utc(f["start_utc"]).date().isoformat() for f in fixtures})
    errors, fixture_rows, offers = [], [], []
    for day in dates:
        try:
            payload = get("fixtures", {"date": day, "timezone": "UTC"}, key)
            fixture_rows += payload["response"]
        except Exception as err:
            errors.append({"stage": "fixtures", "date": day,
                           "error": type(err).__name__})
    pairs = find_fixture_pairs({"fixtures": fixtures}, fixture_rows)
    # Never use an ambiguous, unidentified team/league or kickoff.
    observed_at = datetime.now(timezone.utc).isoformat()
    checked, available = 0, 0
    for espn, event in pairs[:max_event_requests]:
        checked += 1
        fixture_id = event["fixture"]["id"]
        try:
            payload = get("odds", {"fixture": fixture_id, "page": 1}, key)
            rows = parse_odds_response(espn, event, payload["response"], observed_at)
            offers += rows
            if rows:
                available += 1
        except Exception as err:
            errors.append({"stage": "odds", "fixture_id": str(fixture_id),
                           "error": type(err).__name__})
    return offers, {
        "espn_fixtures": len(fixtures), "api_fixtures": len(fixture_rows),
        "verified_fixture_pairs": len(pairs), "odds_checked": checked,
        "fixtures_with_odds": available,
        "request_cap": max_event_requests,
    }, errors


def write_json(path, value):
    dest = Path(path)
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".tmp")
    tmp.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n",
                   encoding="utf-8")
    os.replace(tmp, dest)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--feed", required=True)
    parser.add_argument("--offers-output", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--max-event-requests", type=int, default=35)
    args = parser.parse_args()
    key = os.getenv("API_FOOTBALL_KEY", "").strip()
    if not key:
        raise SystemExit("API_FOOTBALL_KEY missing in GitHub Secrets")
    history = json.loads(Path(args.feed).read_text(encoding="utf-8"))
    offers, coverage, errors = collect(
        history, key, max_event_requests=max(0, min(args.max_event_requests, 45))
    )
    write_json(args.offers_output, {"source": "api-football-v3", "offers": offers,
                                   "coverage": coverage, "errors": errors})
    report = reconcile(
        args.feed, args.offers_output,
        os.getenv("KVOTER_ALIASES_PATH", str(Path(__file__).with_name("team-database.json"))),
        os.getenv("KVOTER_PROVIDER_NAMES_PATH", "shared/kvoter/team-database/provider-team-names.json"),
        str(Path(args.output).parent),
    )
    report.update({
        "source": "api-football-v3", "provider_status": "api_fetched",
        "provider_coverage": coverage, "provider_errors": errors,
        "provider_cached_fallback": {},
    })
    write_json(args.output, report)
    print("API_FOOTBALL_KVOTER", json.dumps({
        "total": report["total"], "matched": report["matched"],
        "verified_identity_pairs": coverage["verified_fixture_pairs"],
        "events_with_odds": coverage["fixtures_with_odds"],
        "errors": len(errors)
    }))
    if not offers or report["matched"] < 1:
        raise SystemExit("NO_VERIFIED_API_FOOTBALL_ODDS; no public odds published")


if __name__ == "__main__":
    main()
