#!/usr/bin/env python3
"""FairXG daily list. No local probability model or Poisson fallback."""
import argparse
import hashlib
import json
import math
import re
import unicodedata
from datetime import datetime, timedelta, timezone
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin, urlsplit
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

TZ = ZoneInfo("Europe/Sarajevo")
BASE = "https://fairxg.com"
MARKETS = ("1", "X", "2", "3+", "GG", "NG")
ODDS_FIELDS = dict(zip(MARKETS, ("home_odds", "draw_odds", "away_odds",
                                "over25_odds", "btts_yes_odds", "btts_no_odds")))
# Verified public competition pages; unknown leagues stay explicitly unavailable.
LEAGUES = {
    "uefa.champions": ("CL", "Champions League"),
    "uefa.europa": ("EL", "Europa League"),
    "uefa.europa.conf": ("ECL", "Conference League"),
    "eng.1": ("E0", "Premier League"), "eng.2": ("E1", "Championship"),
    "esp.1": ("SP1", "La Liga"), "ger.1": ("D1", "Bundesliga"),
    "ita.1": ("I1", "Serie A"), "fra.1": ("F1", "Ligue 1"),
    "sco.1": ("SC0", "Scottish Premiership"),
    "ned.1": ("N1", "Eredivisie"), "por.1": ("P1", "Primeira Liga"),
    "bel.1": ("B1", "Belgian Pro League"), "tur.1": ("T1", "Süper Lig"),
    "aut.1": ("AUT", "Austrian Bundesliga"), "bra.1": ("BRA", "Brasileirão"),
    "nor.1": ("NOR", "Eliteserien"),
    "usa.1": ("USA", "MLS"),  # Verified FairXG competition=USA public listing.
}
# Explicit aliases, never fuzzy matching or reversed home/away.
ALIASES = (
    ("Mjällby AIF", "Mjallby", "Mjallby AIF"),
    ("Real Sociedad", "Sociedad"),
    ("Jagiellonia Bialystok", "Jagiellonia", "Jagiellonia Białystok"),
    ("FC Nordsjælland", "Nordsjaelland", "FC Nordsjaelland"),
    ("Olympiacos", "Olympiakos"), ("AC Milan", "Milan"),
    ("Ajax Amsterdam", "Ajax"), ("Brighton & Hove Albion", "Brighton"),
    ("CSU Craiova", "Univ. Craiova", "Universitatea Craiova"),
    ("Heart of Midlothian", "Hearts"), ("AS Monaco", "Monaco"),
    ("SC Freiburg", "Freiburg"), ("RB Salzburg", "Salzburg"),
    ("FC Midtjylland", "Midtjylland"), ("SK Brann", "Brann"),
    ("AGF", "Aarhus", "AGF Aarhus"), ("Braga", "Sp Braga", "Sporting Braga"),
    ("KuPS Kuopio", "KuPS"), ("Sint-Truidense", "St Truiden", "Sint Truiden"),
    ("F.C. København", "FC Copenhagen", "Copenhagen", "FC Kobenhavn"),
    ("KAA Gent", "Gent"), ("Red Star Belgrade", "Red Star", "Crvena Zvezda"),
    ("Celta Vigo", "Celta"), ("AFC Bournemouth", "Bournemouth"),
    ("Bayer Leverkusen", "Leverkusen"), ("Stade Rennais", "Rennes"),
    ("Union St.-Gilloise", "St. Gilloise", "Union Saint Gilloise"),
    ("TSG Hoffenheim", "Hoffenheim"), ("SK Sturm Graz", "Sturm Graz"),
    ("NEC Nijmegen", "Nijmegen", "NEC"), ("Lillestrom", "Lillestrøm"),
    ("Omonia Nicosia", "Omonia"), ("Viktoria Plzen", "Plzen"),
    ("Manchester United", "Man United", "Man Utd"), ("Manchester City", "Man City"),
    ("Nottingham Forest", "Nott'm Forest", "Nottm Forest"),
    ("Newcastle United", "Newcastle"), ("Wolverhampton Wanderers", "Wolves"),
    ("Tottenham Hotspur", "Tottenham"), ("West Ham United", "West Ham"),
    ("Leeds United", "Leeds"), ("Ipswich Town", "Ipswich"),
    ("Hull City", "Hull"), ("Coventry City", "Coventry"),
    ("Borussia Dortmund", "Dortmund"), ("Borussia Mönchengladbach", "M'gladbach"),
    ("Eintracht Frankfurt", "Ein Frankfurt", "Frankfurt"),
    ("1. FC Köln", "FC Koln", "Koln"), ("Internazionale", "Inter"),
    ("Paris Saint-Germain", "PSG", "Paris SG"), ("Bayern Munich", "Bayern München"),
    ("Sporting CP", "Sporting Lisbon", "Sporting"), ("FC Porto", "Porto"),
    ("Benfica", "SL Benfica"), ("Atlético Madrid", "Atletico Madrid", "Ath Madrid"),
    ("Athletic Club", "Athletic Bilbao", "Ath Bilbao"),
)
# Controlled second matching stage: only verified provider display-name aliases.
# Unlike the first pass, these are used ONLY when strict matching found no row.
SECOND_PASS_ALIASES = (
    ("Caykur Rizespor", "Rizespor", "Çaykur Rizespor"),
    ("OH Leuven", "Oud-Heverlee Leuven", "Oud Heverlee Leuven"),
    ("KV Kortrijk", "Kortrijk"),
    ("Racing Santander", "SA Santander", "Santander"),
    ("C.D. Nacional", "Nacional", "CD Nacional"),
    ("Inter Miami CF", "Inter Miami", "IM Inter Miami"),
)


def second_pass_variants(name):
    opts = variants(name)
    for group in SECOND_PASS_ALIASES:
        forms = {norm(value) for value in group}
        if opts & forms:
            opts.update(forms)
    return opts

def select_match_second_pass(fixture, rows):
    """Match only verified aliases, within the already parsed league page.

    Both ordered clubs, the original source row text, and UTC/local calendar
    date must agree. Never use substrings or infer source probabilities.
    """
    start = datetime.fromisoformat(fixture["start_utc"].replace("Z", "+00:00"))
    dates = {start.strftime("%m-%d"), start.astimezone(TZ).strftime("%m-%d")}
    home, away = second_pass_variants(fixture["home"]), second_pass_variants(fixture["away"])
    names = {h+a for h in home for a in away}
    found = [row for row in rows
             if row["display_date"] in dates
             and row["home_slug"] in home and row["away_slug"] in away
             and row["team_text"] in names]
    unique = {json.dumps(row, sort_keys=True): row for row in found}
    if len(unique) == 1:
        return next(iter(unique.values())), None
    return None, "ambiguous_second_pass" if unique else "not_covered_or_unverified_alias"


def norm(s):
    return "".join(c for c in unicodedata.normalize("NFKD", str(s).casefold())
                   if c.isascii() and c.isalnum())

def variants(name):
    value = norm(name)
    out = {value}
    # Only conventional standalone club prefixes/suffixes, not arbitrary substrings.
    stripped = re.sub(r"(?i)^(?:fc|afc|ac|sc|sk|fk|as|sv|vfb|vfl)\s+|\s+(?:fc|afc|ac|sc|sk|fk|as|sv)$", "", str(name)).strip()
    if stripped:
        out.add(norm(stripped))
    for group in ALIASES:
        group = {norm(x) for x in group}
        if value in group or out & group:
            out.update(group)
    return out

class MatchLinks(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.rows = []
        self.href = None
        self.parts = []
    def handle_starttag(self, tag, attrs):
        if tag == "a":
            href = dict(attrs).get("href", "")
            self.href = href if urlsplit(href).path.startswith("/sport/football/match/") else None
            self.parts = []
    def handle_data(self, data):
        if self.href and data.strip():
            self.parts.append(data.strip())
    def handle_endtag(self, tag):
        if tag == "a" and self.href:
            self.rows.append((urljoin(BASE, self.href), " ".join(self.parts)))
            self.href, self.parts = None, []

PCT = re.compile(r"(?<![\d.])(\d+(?:\.\d+)?)\s*%")
def parse_list(html, league_label):
    parser = MatchLinks()
    parser.feed(html)
    rows = []
    for url, line in parser.rows:
        if urlsplit(url).hostname != "fairxg.com":
            continue
        date = re.match(r"^\s*(\d{2}-\d{2})\s+", line)
        matches = list(PCT.finditer(line))
        if not date or len(matches) != 5 or re.search(r"[<>]\s*\d+(?:\.\d+)?\s*%", line):
            continue
        team_text = norm(line[date.end():matches[0].start()])
        league = norm(league_label)
        if not team_text.endswith(league):
            continue
        team_text = team_text[:-len(league)]
        slug = urlsplit(url).path.rsplit("/", 1)[-1]
        if "-vs-" not in slug:
            continue
        home_slug, away_slug = slug.split("-vs-", 1)
        p = [float(x.group(1)) for x in matches]
        if any(not 0 <= x <= 100 for x in p) or not 99 <= sum(p[:3]) <= 101:
            continue
        rows.append({"url": url, "display_date": date.group(1), "team_text": team_text,
                     "home_slug": norm(home_slug), "away_slug": norm(away_slug),
                     "probability_pct": dict(zip(MARKETS, p + [round(100-p[4], 6)]))})
    return rows

def select_match(fixture, rows):
    start = datetime.fromisoformat(fixture["start_utc"].replace("Z", "+00:00"))
    dates = {start.strftime("%m-%d"), start.astimezone(TZ).strftime("%m-%d")}
    home, away = variants(fixture["home"]), variants(fixture["away"])
    # Both ordered names, competition and displayed date must agree. No substring matching.
    matches = [r for r in rows if r["display_date"] in dates
               and r["home_slug"] in home and r["away_slug"] in away
               and r["team_text"] in {h+a for h in home for a in away}]
    # Duplicate links are fine only when the actual data are identical.
    unique = {json.dumps(r, sort_keys=True): r for r in matches}
    if len(unique) != 1:
        return None, "ambiguous_match" if unique else "not_covered_or_unverified_alias"
    return next(iter(unique.values())), None

def canonical_hash(obj):
    return hashlib.sha256(json.dumps(obj, ensure_ascii=False, sort_keys=True,
                       separators=(",", ":"), allow_nan=False).encode()).hexdigest()

def download(url):
    request = Request(url, headers={"User-Agent": "ListaSix FairXG daily public list/1.0",
                                    "Accept": "text/html", "Cache-Control": "no-cache"})
    with urlopen(request, timeout=30) as response:
        if urlsplit(response.geturl()).hostname != "fairxg.com":
            raise ValueError("Unexpected provider redirect")
        return response.read().decode("utf-8")

def valid_odd(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) and 1.01 < value < 50

def rank_fixture(f, quote, match, now):
    p = match["probability_pct"]
    odds = {m: quote.get(k) if valid_odd(quote.get(k)) else None for m,k in ODDS_FIELDS.items()}
    value = {}
    for market in MARKETS:
        odd = odds[market]
        ev = round(p[market]*odd-100, 4) if odd else None
        score = round(.42*p[market]+.43*max(-25,min(30,ev)), 6) if ev is not None else None
        value[market] = {"raw_probability_pct":p[market], "adjusted_probability_pct":p[market],
                         "odds":odd, "raw_ev_pct":ev, "ev_pct":ev, "score":score,
                         "conservative_ev_pct":None}
    ordered = sorted(MARKETS, key=lambda m: (-p[m], MARKETS.index(m)))
    available = sorted((m for m in MARKETS if odds[m]), key=lambda m: (-value[m]["score"], -p[m], MARKETS.index(m)))
    best = available[0] if available else None
    ev = value[best]["ev_pct"] if best else None
    start = datetime.fromisoformat(f["start_utc"].replace("Z","+00:00"))
    future = start > now + timedelta(minutes=20)
    a = bool(best and future and odds[best]<3 and p[best]>=50 and ev>0)
    b = bool(future and odds["3+"] and odds["3+"]<3)
    return {"fixture_id":f["fixture_id"], "match":f["home"]+" - "+f["away"],
            "datetime":f["start_utc"], "league":f["league"], "model":"FairXG",
            "source_url":match["url"], "checked_at_utc":now.isoformat(),
            "model_basis":{"1X2":"FairXG published headline, may be bookmaker-based",
                           "3+":"FairXG published goals model", "GG":"FairXG published goals model",
                           "NG":"100 minus published GG"},
            "probability_pct":p, "odds":odds, "market_value":value,
            "strongest_market":ordered[0], "strongest_pct":p[ordered[0]],
            "strongest_odds":odds[ordered[0]], "second_market":ordered[1],
            "second_pct":p[ordered[1]], "third_pct":p[ordered[2]],
            "recommended_market":best, "recommended_pct":p[best] if best else None,
            "recommended_odds":odds[best] if best else None,
            "recommended_score":value[best]["score"] if best else None,
            "recommended_adjusted_pct":p[best] if best else None,
            "recommended_ev_pct":ev, "data_quality_index_pct":None,
            "candidate_A":a, "candidate_B":b, "b_market":"3+" if b else None,
            "b_odds":odds["3+"] if b else None, "b_probability_pct":p["3+"],
            "b_market_rank":available.index("3+")+1 if "3+" in available else None,
            "b_ev_pct":value["3+"]["ev_pct"],
            "b_value_warning":"Negative EV; independent review required" if b and value["3+"]["ev_pct"]<0 else None,
            "eligible_for_A":a, "eligible_for_B":b, "requires_independent_ai_review":True}

def detailed_ai_handoff(rows, now):
    chosen = [r for r in rows if r.get("recommended_odds") and r.get("recommended_market")
              and datetime.fromisoformat(r["datetime"].replace("Z","+00:00"))>now+timedelta(minutes=20)][:10]
    candidates = []
    for rank, row in enumerate(chosen, 1):
        candidates.append(dict(row, rank=rank, research_only=not (row["candidate_A"] or row["candidate_B"]),
                               all_six_probabilities_pct=row["probability_pct"],
                               recommended_probability_pct=row["recommended_pct"],
                               top_market=row["strongest_market"], top_probability_pct=row["strongest_pct"],
                               b_market_probability_pct=row["b_probability_pct"],
                               ai_review_status="pending_independent_review"))
    return {"count":len(candidates), "limit":10, "candidates":candidates,
            "independent_ai_review_required":True, "selection_rule":"FairXG p and TipsterArea EV; no local probability model"}

def analyze(feed, active, now, fetch=download):
    day=now.astimezone(TZ).date().isoformat()
    if feed.get("date") != day or active.get("date") != day:
        raise ValueError("ESPN and odds must be current")
    fixtures=feed.get("football_candidates", [])
    official={f["fixture_id"]:f for f in fixtures}
    quotes={q["fixture_id"]:q for q in active.get("fixtures", [])}
    if not official or len(official)!=len(fixtures) or len(quotes)!=len(active.get("fixtures", [])) or set(official)!=set(quotes):
        raise ValueError("Missing or duplicate ESPN/odds fixture IDs")
    pages, errors = {}, {}
    for league in sorted({f["league"] for f in fixtures}):
        if league not in LEAGUES:
            errors[league]="competition_not_mapped"
            continue
        code, label = LEAGUES[league]
        url=BASE+"/sport/football?competition="+code
        try:
            pages[league]=parse_list(fetch(url), label)
            if not pages[league]:
                errors[league]="no_valid_public_prediction_rows"
        except (OSError, ValueError, UnicodeError) as e:
            errors[league]=type(e).__name__+": "+str(e)
    # Primary exact identity pass. It must complete for ALL ESPN fixtures first.
    selected, missing = {}, []
    first_pass_count = 0
    second_pass_attempts = 0
    second_pass_count = 0
    for f in fixtures:
        q = quotes[f["fixture_id"]]
        if q.get("match") != f["home"]+" - "+f["away"] or q.get("datetime") != f["start_utc"]:
            raise ValueError("ESPN quote identity discrepancy: "+f["fixture_id"])
        match, why = select_match(f, pages.get(f["league"], []))
        if match:
            first_pass_count += 1
            selected[f["fixture_id"]] = (match, "primary_exact")
        else:
            missing.append((f, why))

    # Additional identity check BEFORE writing TOP10_READY. Only known aliases;
    # competition page, kick-off date and ordered teams must all match.
    unresolved = []
    for f, first_reason in missing:
        match, second_reason = None, first_reason
        if first_reason != "ambiguous_match" and f["league"] in pages:
            second_pass_attempts += 1
            match, second_reason = select_match_second_pass(f, pages[f["league"]])
        if match:
            selected[f["fixture_id"]] = (match, "secondary_verified_alias")
            second_pass_count += 1
        else:
            unresolved.append((f, second_reason or first_reason))

    rows, unmatched = [], []
    for f, reason in unresolved:
        unmatched.append({"fixture_id":f["fixture_id"],
                          "match":quotes[f["fixture_id"]]["match"], "league":f["league"],
                          "status":"ambiguous" if "ambiguous" in reason else "unavailable",
                          "reason":errors.get(f["league"], reason),
                          "matching_pass":"second_checked" if f["league"] in pages else "competition_unavailable"})
    for f in fixtures:
        selection = selected.get(f["fixture_id"])
        if selection is None:
            continue
        match, pass_name = selection
        ranked = rank_fixture(f, quotes[f["fixture_id"]], match, now)
        ranked["matching_pass"] = pass_name
        rows.append(ranked)
    # A provider link can never be assigned to multiple ESPN fixture identities.
    from collections import Counter
    duplicates=Counter(r["source_url"] for r in rows)
    keep=[]
    for r in rows:
        if duplicates[r["source_url"]]>1:
            unmatched.append({"fixture_id":r["fixture_id"],"match":r["match"],"league":r["league"],
                              "status":"ambiguous","reason":"provider_url_maps_to_multiple_ESPN_matches"})
        else:
            keep.append(r)
    rows=keep
    rows.sort(key=lambda r:(-(r["recommended_score"] if r["recommended_score"] is not None else -1e9),
                            -(r["recommended_pct"] or 0),r["fixture_id"]))
    handoff=detailed_ai_handoff(rows,now)
    ids=[r["fixture_id"] for r in handoff["candidates"]]
    active_sha=canonical_hash(active)
    fp=canonical_hash({"date":day,"model":"FairXG","feed":canonical_hash(feed),"active":active_sha,
                       "predictions":[[r["fixture_id"],r["probability_pct"],r["source_url"]] for r in rows],
                       "top10":ids})
    coverage={"espn_total":len(official),"matched":len(rows),"unmatched":len(unmatched),
              "competition_errors":errors,"full":len(rows)==len(official)}
    identity_checks={
        "status":"SECOND_PASS_COMPLETE",
        "first_pass_checked":len(fixtures),
        "first_pass_matched":first_pass_count,
        "second_pass_attempted":second_pass_attempts,
        "second_pass_matched":second_pass_count,
        "unmatched_after_second_pass":len(unmatched),
        "checked_unique_source_urls":True,
        "verification_basis":"league + UTC/local date + ordered home/away + full name/verified alias",
        "validation_complete": (
            len(rows)+len(unmatched)==len(fixtures)
            and all(row["matching_pass"] in ("primary_exact","secondary_verified_alias") for row in rows)
            and len({row["source_url"] for row in rows})==len(rows)),
    }
    if not identity_checks["validation_complete"]:
        raise ValueError("FairXG identity verification incomplete; block TOP10_READY")
    return {"schema_version":3,"date":day,"model":"FairXG","generated_at_utc":now.isoformat(),
            "identity_checks":identity_checks,
            "checked_at_utc":now.isoformat(),"source_feed_generated_at_utc":feed.get("generated_at_utc"),
            "source_feed_sha256":canonical_hash(feed),"source_active_sha256":active_sha,
            "source_fingerprint":fp,"coverage":coverage,"all_six_markets":list(MARKETS),
            "total_espn_fixtures":len(official),"all_fixtures_evaluated":len(rows),
            "total_market_probabilities":6*len(rows),"ranked_fixtures":rows,"unmatched":unmatched,
            "detailed_ai_handoff":handoff,"detailed_ai_top_ten_fixture_ids":ids,
            "candidate_A_count":sum(r["candidate_A"] for r in rows),
            "candidate_B_count":sum(r["candidate_B"] for r in rows),
            "score_formula":"0.42*FairXG_pct + 0.43*clamp(EV_pct,-25,30)",
            "probabilities_are_calibrated":False,"publication_allowed":False,
            "ticket_proposals":{"A":None,"B":None,"reason":"Only independent AI approves virtual A/B."}}

def feedback(doc):
    handoff=doc["detailed_ai_handoff"]
    audit=doc.get("identity_checks",{})
    if audit.get("status")!="SECOND_PASS_COMPLETE" or not audit.get("validation_complete"):
        raise ValueError("FairXG second identity pass not complete: no READY signal")
    ready=bool(handoff["count"])
    common={"date":doc["date"],"model":"FairXG","source_fingerprint":doc["source_fingerprint"],
            "generated_at_utc":doc["generated_at_utc"],"coverage":doc["coverage"],
            "identity_checks":audit}
    scout=dict(common, feedback="FAIRXG_LIST_READY" if doc["ranked_fixtures"] else "FAIRXG_LIST_UNAVAILABLE",
               status="complete" if doc["coverage"]["full"] else "partial",
               all_fixtures_evaluated=doc["all_fixtures_evaluated"],
               market_probabilities=doc["total_market_probabilities"])
    top=dict(common,feedback="TOP10_READY" if ready else "TOP10_UNAVAILABLE",
             status="ready" if ready else "unavailable",count=handoff["count"],
             fixture_ids=doc["detailed_ai_top_ten_fixture_ids"],candidates=handoff["candidates"],
             scout_report="shared/agent/scout-six-markets.json",ai_approval_required=True,
             publication_allowed=False)
    return scout,top

def save(path,data):
    path.parent.mkdir(parents=True,exist_ok=True)
    temp=path.with_name(path.name+".tmp")
    temp.write_text(json.dumps(data,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    temp.replace(path)

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--root",default=".")
    root=Path(parser.parse_args().root)
    now=datetime.now(timezone.utc)
    def read(path):
        return json.loads((root/path).read_text(encoding="utf-8"))
    feed,active=read("shared/collector-feed.json"),read("shared/active-list.json")
    day=now.astimezone(TZ).date().isoformat()
    # A completed current list is a stable handoff; avoid repetitive provider requests.
    try:
        existing=read("shared/agent/fairxg-scout-"+day+".json")
    except (OSError,ValueError):
        existing={}
    if (existing.get("model")=="FairXG" and existing.get("date")==day
            and existing.get("source_feed_sha256")==canonical_hash(feed)
            and existing.get("source_active_sha256")==canonical_hash(active)
            and existing.get("identity_checks",{}).get("validation_complete") is True
            and existing.get("coverage",{}).get("full") is True
            and existing.get("detailed_ai_handoff",{}).get("count")==10):
        result=existing
        print("FAIRXG_DAILY_LIST_ALREADY_READY")
    else:
        result=analyze(feed,active,now)
        # A temporary provider outage cannot erase a better snapshot of identical inputs.
        if (existing.get("model")=="FairXG" and existing.get("date")==day
                and existing.get("source_feed_sha256")==result["source_feed_sha256"]
                and existing.get("source_active_sha256")==result["source_active_sha256"]
                and existing.get("identity_checks",{}).get("validation_complete") is True
                and existing.get("coverage",{}).get("matched",0)>result["coverage"]["matched"]):
            result=existing
            print("FAIRXG_RETAINED_CURRENT_VERIFIED_SNAPSHOT")
    scout,top=feedback(result)
    save(root/"shared/agent"/("fairxg-scout-"+day+".json"),result)
    save(root/"shared/agent"/("fairxg-top10-"+day+".json"),dict(top,feedback="FAIRXG_TOP10_READY" if top["feedback"]=="TOP10_READY" else "FAIRXG_TOP10_UNAVAILABLE"))
    for name in ("shared/agent/scout-six-markets.json","docs/scout-six-markets.json"):
        save(root/name,result)
    save(root/"shared/agent/scout-feedback.json",scout)
    save(root/"shared/agent/top10-feedback.json",top)
    lines=["FAIRXG DAILY LIST | "+day,
           "Covered ESPN matches: "+str(result["coverage"]["matched"])+"/"+str(result["coverage"]["espn_total"]),
           "FIXTURE | 1 | X | 2 | 3+ | GG | NG | RANKED MARKET | EV %"]
    for row in result["ranked_fixtures"]:
        lines.append(row["match"]+" | "+" | ".join(str(row["probability_pct"][m]) for m in MARKETS)
                     +" | "+str(row["recommended_market"])+" | "+str(row["recommended_ev_pct"]))
    (root/"docs/scout-six-markets.txt").write_text("\n".join(lines)+"\n",encoding="utf-8")
    print(scout["feedback"],result["coverage"])
    print(top["feedback"],top["count"])

if __name__=="__main__":
    main()
