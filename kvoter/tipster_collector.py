#!/usr/bin/env python3
"""TipsterArea HTML collector for ESPN ListaSix fixtures.

Reads publicly visible pages, no odds API or bookmaker comparison.
Fills ONLY missing markets in today's AI snapshot and preserves provenance.
No fabricated odds, no matches with ambiguous home/away identity.
"""
import argparse
import json
import re
import sys
import time
import unicodedata
from datetime import datetime, timezone, timedelta
from difflib import SequenceMatcher
from pathlib import Path
from urllib.parse import urljoin, urlparse
from zoneinfo import ZoneInfo

import requests
from bs4 import BeautifulSoup

TZ = ZoneInfo("Europe/Sarajevo")
BASE = "https://tipsterarea.com"
REQUEST_HEADERS = {
    "User-Agent": "ListaSixTipsterCollector/1.0 (+public football odds; no login)",
    "Accept": "text/html,application/xhtml+xml",
}
MARKET_KEYS = {"1X2": ("home", "draw", "away"), "3+": ("over",), "BTTS": ("yes", "no")}
MONTHS = ["", "January", "February", "March", "April", "May", "June",
          "July", "August", "September", "October", "November", "December"]
ALIASES = {
    "paris saint germain": "psg", "paris saint german": "psg",
    "fc paris saint germain": "psg", "racing genk": "genk",
    "royal charleroi": "charleroi", "sint truidense": "st truiden",
    "saint truiden": "st truiden", "sint truiden": "st truiden",
    "kvc westerlo": "westerlo", "royal antwerp": "antwerp",
    "zulte waregem": "zulte waregem", "club brugge kv": "club brugge",
    "mechelen": "mechelen", "kv mechelen": "mechelen",
    "heart of midlothian": "hearts", "nottingham forest": "nottingham",
    "deportivo la coruna": "deportivo", "deportivo alaves": "alaves",
    "rayo vallecano": "rayo vallecano", "borussia monchengladbach": "monchengladbach",
    "borussia m gladbach": "monchengladbach", "borussia dortmund": "dortmund",
    "caykur rizespor": "rizespor", "genclerbirligi sk": "genclerbirligi",
    "1 fc union berlin": "union berlin", "rb leipzig": "leipzig",
    "vfb stuttgart": "stuttgart", "sc paderborn 07": "paderborn",
    "sv elversberg": "elversberg", "sc freiburg": "freiburg",
    "fc utrecht": "utrecht", "sc cambuur": "cambuur",
    "nec nijmegen": "nec", "psv eindhoven": "psv",
    "feyenoord rotterdam": "feyenoord", "fc groningen": "groningen",
    "inter miami cf": "inter miami", "new england revolution": "new england",
    "leeds united": "leeds", "coventry city": "coventry",
    "newcastle united": "newcastle", "tottenham hotspur": "tottenham",
    "lyonnais": "lyon", "olympique lyonnais": "lyon",
    "telstar velsen": "telstar", "fc zwolle": "pec zwolle",
    "bahia ba": "bahia", "coritiba pr": "coritiba",
    "palmeiras sp": "palmeiras", "flamengo rj": "flamengo",
    "chapecoense sc": "chapecoense", "cruzeiro mg": "cruzeiro",
    "philadelphia union": "philadelphia", "fc dallas": "dallas",
    "columbus crew": "columbus", "portland timbers": "portland",
    "chapecoense": "chapecoense", "bahia": "bahia",
    # ESPN / TipsterArea verified 2026-11-22 same-match identity aliases.
    # Exact normalized names only: retain home/away and date verification.
    "erzurum bb": "erzurumspor", "erzurumspor": "erzurumspor",
    "willem ii tilburg": "willem ii",
    "waasland beveren": "sk beveren", "sk beveren": "sk beveren",
    "brighton and hove albion": "brighton", "brighton": "brighton",
    "stade rennais": "rennais", "rennais": "rennais",
    "hamburg sv": "hamburg", "hamburger": "hamburg",
    "oh leuven": "oud heverlee leuven",
    "athletico pr": "atletico pr", "atletico pr": "atletico pr",
    "remo pa": "remo",
    "internazionale": "inter",
    "fluminense rj": "fluminense", "mirassol sp": "mirassol",
    "red bull bragantino": "bragantino", "bragantino sp": "bragantino",
    "vasco da gama rj": "vasco da gama",
    "chicago fire": "chicago fire", "chicago fire fc": "chicago fire",
    "instituto cordoba": "instituto ac cordoba",
    "instituto ac cordoba": "instituto ac cordoba",
    "huracan": "huracan buenos aires",
    "huracan buenos aires": "huracan buenos aires",
}
def normalized(name):
    text = unicodedata.normalize("NFKD", name.casefold())
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = text.replace("ß", "ss").replace("&", " and ")
    text = re.sub(r"[^a-z0-9 ]+", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    if text in ALIASES:
        return ALIASES[text]
    text = re.sub(r"^(?:fc|afc|fk|ac|as|sv|sc|kv|kvc) ", "", text)
    text = re.sub(r" (?:fc|fk|sc|cf|afc)$", "", text)
    return ALIASES.get(text, text)

def similarity(a, b):
    a, b = normalized(a), normalized(b)
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0
    ratio = SequenceMatcher(None, a, b).ratio()
    aset, bset = set(a.split()), set(b.split())
    common = len(aset & bset)
    token = 2 * common / (len(aset) + len(bset))
    return max(ratio, 0.65 * token + 0.35 * ratio)

# Secondary identity pass: only known *trailing* source country tags are removed.
# It does not loosen primary thresholds or assume country == competition.
COUNTRY_TAGS = frozenset((
    "alb","arm","aut","aze","bel","bih","bul","cro","cyp","cze","den","eng",
    "esp","est","fin","fra","geo","ger","gre","hun","ire","isl","ita","kaz",
    "ltu","lva","mda","mne","ned","nir","nor","pol","por","rou","rus","sco",
    "srb","sui","svk","swe","tur","ukr","wal","svn","mkd","lux","mlt"
))

def secondary_key(name):
    """Canonical team identity for the independent second matching pass."""
    text = str(name).strip()
    suffix = re.search(r"\s+\(([A-Za-z]{3})\)\s*$", text)
    if suffix and suffix.group(1).casefold() in COUNTRY_TAGS:
        text = text[:suffix.start()]
    return normalized(text)

def assign_links_secondary(fixtures, matches):
    """Exact canonical home+away pairs; reject ambiguous or reversed links."""
    proposals = {}
    for fixture in fixtures:
        home, away = secondary_key(fixture["home"]), secondary_key(fixture["away"])
        if not home or not away:
            continue
        candidates = [m for m in matches
                      if secondary_key(m["home"]) == home and secondary_key(m["away"]) == away]
        if len(candidates) != 1:
            continue
        proposal = candidates[0]
        # Two ESPN fixtures must never claim the same source match page.
        proposals[fixture["fixture_id"]] = proposal
    claims = {}
    for proposal in proposals.values():
        url = proposal["url"]
        claims[url] = claims.get(url, 0) + 1
    return {fid: candidate for fid, candidate in proposals.items()
            if claims[candidate["url"]] == 1}

def acceptable_price(text):
    if not text:
        return None
    text = str(text).strip().replace(",", ".")
    if not re.fullmatch(r"\d{1,2}\.\d{1,3}", text):
        return None
    val = float(text)
    return val if 1.01 < val < 50 else None

def content_cells(tr):
    cells = tr.find_all(["th", "td"], recursive=False)
    return [c.get_text(" ", strip=True) for c in cells], cells

def fetch_page(session, url):
    parsed = urlparse(url)
    if parsed.scheme != "https" or parsed.netloc not in ("tipsterarea.com", "www.tipsterarea.com"):
        raise ValueError("Untrusted TipsterArea URL " + url)
    resp = session.get(url, headers=REQUEST_HEADERS, timeout=20)
    resp.raise_for_status()
    if "text/html" not in resp.headers.get("Content-Type", "text/html"):
        raise ValueError("Not HTML: " + url)
    if len(resp.content) > 4_000_000:
        raise ValueError("Page too large")
    return BeautifulSoup(resp.text, "html.parser")

def parse_daily(soup, day):
    expected = rf"\b{day.day}\s+{MONTHS[day.month]},?\s+{day.year}\b"
    title = soup.get_text(" ", strip=True)[:2000]
    if not re.search(expected, title, re.IGNORECASE):
        raise ValueError("TipsterArea daily page date mismatch, expected " + day.isoformat())
    matches = []
    seen = set()
    for a in soup.select('a[href*="/match/"]'):
        url = urljoin(BASE, a.get("href", ""))
        if urlparse(url).netloc not in ("tipsterarea.com", "www.tipsterarea.com"):
            continue
        if url in seen:
            continue
        text = a.get_text(" ", strip=True)
        # Some layouts wrap the full row in the anchor, others only teams.
        candidate = text
        if " - " not in candidate:
            tr = a.find_parent("tr")
            if tr is not None:
                candidate = tr.get_text(" ", strip=True)
        candidate = re.sub(r"^\s*\d{1,2}:\d{2}\s+", "", candidate)
        # Strip only trailing three decimal prices, never team digits.
        candidate = re.sub(r"(?:\s+\d{1,2}[.,]\d{1,3}){3}\s*$", "", candidate).strip()
        if " - " not in candidate:
            continue
        home, away = (x.strip() for x in candidate.split(" - ", 1))
        if not home or not away or len(home) > 100 or len(away) > 100:
            continue
        seen.add(url)
        matches.append({"home": home, "away": away, "url": url})
    return matches

def assign_links(fixtures, matches):
    """Unambiguous one-to-one home/away mapping. Fail closed on uncertain pairs."""
    results = {}
    used = set()
    for fixture in fixtures:
        scored = []
        for candidate in matches:
            hs = similarity(fixture["home"], candidate["home"])
            aws = similarity(fixture["away"], candidate["away"])
            if min(hs, aws) < 0.78:
                continue
            score = (hs + aws) / 2
            if score >= 0.865:
                scored.append((score, candidate))
        scored.sort(key=lambda x: -x[0])
        if not scored:
            continue
        if len(scored) > 1 and scored[0][0] - scored[1][0] < 0.06:
            continue
        best = scored[0][1]
        if best["url"] in used:
            continue
        used.add(best["url"])
        results[fixture["fixture_id"]] = best
    return results

def parse_markets(soup):
    """Read bookmaker odds tables only, not historical results or predictions."""
    result = {}
    sources = {}
    for table in soup.find_all("table"):
        market = None
        for tr in table.find_all("tr"):
            texts, cells = content_cells(tr)
            if not texts:
                continue
            header = " ".join(texts).casefold()
            first = texts[0].casefold()
            if first.startswith("standard 1x2") and (" x " in " " + header + " "):
                market = "1X2"
                continue
            if first.startswith("over/under") and "under" in header and "over" in header:
                market = "3+"
                continue
            if (first == "bts" or first.startswith("both teams to score")) and "yes" in header and "no" in header:
                market = "BTTS"
                continue
            # Ignore every unrelated table/market once a new header appears.
            if any(p in first for p in ("double chance", "draw no bet", "correct score", "handicap")):
                market = None
                continue
            if market is None or len(texts) < 3:
                continue
            bookmaker = None
            if cells:
                img = cells[0].find("img", alt=True)
                bookmaker = (img["alt"] if img else cells[0].get_text(" ", strip=True)).strip()
            bookmaker = bookmaker or "TipsterArea displayed bookmaker"
            if market == "1X2" and len(texts) >= 4:
                vals = [acceptable_price(x) for x in texts[-3:]]
                keys = ("home", "draw", "away")
            elif market == "3+" and len(texts) >= 4 and texts[-3].strip() in ("2.5", "2,5"):
                vals = [acceptable_price(texts[-1])]
                keys = ("over",)
            elif market == "BTTS" and len(texts) >= 3:
                vals = [acceptable_price(x) for x in texts[-2:]]
                keys = ("yes", "no")
            else:
                continue
            for key, price in zip(keys, vals):
                if price is not None and key not in result.get(market, {}):
                    result.setdefault(market, {})[key] = price
                    sources.setdefault(market, {})[key] = bookmaker
    return result, sources

def verified_match_page(soup, daily, fixture, day, secondary=False):
    heading = soup.title.get_text(" ", strip=True) if soup.title else ""
    if f"{day.day} {MONTHS[day.month]} {day.year}".casefold() not in heading.casefold():
        return False
    if fixture.get("league") == "uefa.champions" and "champions league" not in heading.casefold():
        return False
    pair = heading.split(",", 1)[0]
    if " - " not in pair:
        return False
    home, away = pair.split(" - ", 1)
    if secondary:
        # Second pass is strict on team identity, rather than more permissive.
        return (secondary_key(fixture["home"]) == secondary_key(home)
                and secondary_key(fixture["away"]) == secondary_key(away)
                and secondary_key(daily["home"]) == secondary_key(home)
                and secondary_key(daily["away"]) == secondary_key(away))
    return (similarity(fixture["home"], home) >= 0.78
            and similarity(fixture["away"], away) >= 0.78
            and similarity(daily["home"], home) >= 0.78
            and similarity(daily["away"], away) >= 0.78)

# Date-scoped direct page recovered from TipsterArea search when its daily
# index omitted the link. The page title/date/home/away MUST still verify.
VERIFIED_PAGE_FALLBACKS = {
    ("2026-11-22", "chicago fire", "charlotte"): 
        "https://tipsterarea.com/match/chicago-fire-charlotte-fc-playoff-usa-956702",
}

def recover_verified_page_links(fixtures, links, linked_day):
    for fixture in fixtures:
        fid = fixture["fixture_id"]
        if fid in links:
            continue
        kickoff_utc = datetime.fromisoformat(fixture["start_utc"].replace("Z", "+00:00"))
        # The TipsterArea index and ESPN local-date boundary can differ near midnight.
        # Try the explicitly verified UTC date as well, never accept an unchecked title.
        for match_day in (kickoff_utc.astimezone(TZ).date(), kickoff_utc.date()):
            key = (match_day.isoformat(), normalized(fixture["home"]), normalized(fixture["away"]))
            url = VERIFIED_PAGE_FALLBACKS.get(key)
            if url:
                links[fid] = {"home": fixture["home"], "away": fixture["away"], "url": url}
                linked_day[fid] = match_day
                break
    return links

def save_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)

def run(args):
    now = datetime.now(TZ)
    day = now.date()
    feed_path = Path(args.root) / "shared/collector-feed.json"
    feed = json.loads(feed_path.read_text(encoding="utf-8"))
    if feed.get("date") != day.isoformat() or not feed.get("football_candidates"):
        print("TIPSTER_WAIT_ESPN: no current, nonempty ESPN feed")
        return
    exp = feed.get("expires_at_utc")
    if exp and datetime.fromisoformat(exp.replace("Z", "+00:00")) <= datetime.now(timezone.utc):
        print("TIPSTER_WAIT_ESPN: feed expired")
        return
    if not args.force and not (9 <= now.hour < 12):
        print("TIPSTER_OUTSIDE_WINDOW", now.isoformat(), "9-12 Europe/Sarajevo")
        return
    root = Path(args.root)
    target = root / "shared/kvoter" / ("ai-verified-" + day.isoformat() + ".json")
    doc = json.loads(target.read_text(encoding="utf-8")) if target.exists() else {
        "date": day.isoformat(), "feed_generated_at_utc": feed.get("generated_at_utc"),
        "source": "AI or TipsterArea verified public prices", "fixtures": []
    }
    if doc.get("date") != day.isoformat():
        raise ValueError("Existing odds snapshot is from a different day")
    fixtures = feed["football_candidates"]
    existing = {x["fixture_id"]: x for x in doc.get("fixtures", [])}
    session = requests.Session()
    links = {}
    linked_day = {}
    total_matches = 0
    # ESPN can include late fixtures after local midnight, e.g. Brazil 00:00 UTC.
    local_days = {datetime.fromisoformat(f["start_utc"].replace("Z", "+00:00")).astimezone(TZ).date()
                  for f in fixtures}
    for fixture_day in sorted(local_days):
        if fixture_day < day or fixture_day > day + timedelta(days=1):
            continue
        url = BASE + "/matches/date-" + fixture_day.strftime("%d-%m-%Y")
        daily = fetch_page(session, url)
        matches = parse_daily(daily, fixture_day)
        total_matches += len(matches)
        day_fixtures = [f for f in fixtures
                        if datetime.fromisoformat(f["start_utc"].replace("Z", "+00:00")).astimezone(TZ).date() == fixture_day]
        mapped = (assign_links_secondary(day_fixtures, matches) if args.secondary
                  else assign_links(day_fixtures, matches))
        links.update(mapped)
        linked_day.update({fid: fixture_day for fid in mapped})
    recover_verified_page_links(fixtures, links, linked_day)
    if not total_matches:
        raise RuntimeError("TipsterArea returned no match links; possible block or site change")
    updated = 0
    attempted = 0
    failures = []
    for fixture in sorted(fixtures, key=lambda x: x.get("start_utc", "")):
        fid = fixture["fixture_id"]
        link = links.get(fid)
        if not link:
            continue
        # Already listed matches may be past kick-off; do not overwrite previous verified quotes.
        kickoff = datetime.fromisoformat(fixture["start_utc"].replace("Z", "+00:00"))
        if kickoff <= datetime.now(timezone.utc) + timedelta(minutes=10):
            continue
        row = existing.get(fid)
        if row:
            for key in ("home", "away", "league", "start_utc"):
                if row.get(key) != fixture.get(key):
                    raise ValueError("Stored ESPN identity conflict for " + fid)
        else:
            row = {k: fixture[k] for k in ("fixture_id", "league", "home", "away", "start_utc")}
            row.update(bookmaker="TipsterArea public bookmaker", markets={}, source_urls=[], market_sources={})
        needed = [(m, k) for m, keys in MARKET_KEYS.items() for k in keys if k not in row.get("markets", {}).get(m, {})]
        if not needed:
            continue
        if args.max_pages and attempted >= args.max_pages:
            break
        attempted += 1
        try:
            page = fetch_page(session, link["url"])
            if not verified_match_page(page, link, fixture, linked_day[fid], secondary=args.secondary):
                failures.append(fid + ": mismatched page title/date/teams")
                continue
            prices, bookmakers = parse_markets(page)
            modified = False
            for market, keys in MARKET_KEYS.items():
                for key in keys:
                    value = prices.get(market, {}).get(key)
                    if value is None or key in row.get("markets", {}).get(market, {}):
                        continue
                    row.setdefault("markets", {}).setdefault(market, {})[key] = value
                    row.setdefault("market_sources", {}).setdefault(market, {})[key] = {
                        "url": link["url"], "bookmaker": bookmakers[market][key]
                    }
                    modified = True
            if modified:
                row["source_urls"] = list(dict.fromkeys(row.get("source_urls", []) + [link["url"]]))
                if not row.get("bookmaker"):
                    row["bookmaker"] = "TipsterArea public bookmaker"
                existing[fid] = row
                updated += 1
                doc["fixtures"] = list(existing.values())
                save_json(target, doc)  # save immediately after each match
                print("TIPSTER_UPDATED", fixture["home"], "-", fixture["away"], json.dumps(row["markets"]))
            else:
                failures.append(fid + ": no new listed 1X2/3+/BTTS markets")
        except (requests.RequestException, ValueError) as error:
            failures.append(fid + ": " + str(error)[:160])
        time.sleep(max(0.8, args.delay))
    report = {
        "date": day.isoformat(), "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "matching_pass": "secondary_exact_canonical" if args.secondary else "primary_fuzzy",
        "espn": len(fixtures), "daily_tipster_links": total_matches,
        "paired": len(links), "pages_checked": attempted,
        "updated": updated, "with_any_quotes": len(existing),
        "unpaired": [f["home"] + " - " + f["away"] for f in fixtures if f["fixture_id"] not in links],
        "failures": failures[:70],
    }
    save_json(root / "shared/kvoter/tipster-status.json", report)
    print("TIPSTER_REPORT", json.dumps(report, ensure_ascii=False))
    if attempted and not updated and not existing:
        raise RuntimeError("No TipsterArea prices extracted; inspect parser and logs")

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--root", default=".")
    p.add_argument("--force", action="store_true", help="Manual diagnostics; skips 9-12 collection window only")
    p.add_argument("--secondary", action="store_true", help="Independent exact canonical home/away matching, no threshold relaxation")
    p.add_argument("--max-pages", type=int, default=0, help="limit for test/debug; 0 means all")
    p.add_argument("--delay", type=float, default=1.0)
    run(p.parse_args())

if __name__ == "__main__":
    main()
