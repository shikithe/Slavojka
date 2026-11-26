"""Explicit canonical club identities and strict one-to-one fixture matching."""
import re
import unicodedata
from collections import Counter
from datetime import datetime, timezone

ALIAS_GROUPS = (
    ('Red Star Belgrade', 'Crvena zvezda Belgrade', 'Crvena zvezda'),
    ('Universitatea Craiova', 'CSU Craiova', 'CS Universitatea Craiova'),
    ('AGF Aarhus', 'AGF', 'Aarhus GF'),
    ('Brann Bergen', 'SK Brann', 'Brann'),
    ('Olympiacos Piraeus', 'Olympiacos', 'Olympiakos Piraeus'),
    ('Red Bull Salzburg', 'RB Salzburg', 'FC Salzburg'),
    ('Ferencvaros', 'Ferencvarosi TC', 'Ferencvarosi'),
    ('Iberia 1999 Tbilisi', 'Iberia 1999', 'FC Iberia 1999'),
    ('Sao Paulo', 'Sao Paulo SP', 'Sao Paulo FC'),
    ('FC Copenhagen', 'F.C. København', 'København', 'FC København', 'Copenhagen', 'FC Kobenhavn'),
    ('Brighton', 'Brighton & Hove Albion', 'Brighton and Hove Albion'),
    ('Mjallby', 'Mjällby AIF', 'Mjallby AIF'),
    ('TSG Hoffenheim', 'Hoffenheim', '1899 Hoffenheim'),
    ('Sturm Graz', 'SK Sturm Graz'),
    ('FC Nordsjaelland', 'FC Nordsjælland', 'Nordsjaelland'),
    ('Union Saint-Gilloise', 'Union St.-Gilloise', 'Union St. Gilloise', 'Union SG'),
    ('KAA Gent', 'Gent'),
    ('NK Celje', 'Celje'),
    ('Kairat Almaty', 'FC Kairat Almaty', 'Kairat'),
    ('Remo', 'Remo PA', 'Clube do Remo'),
    ('Getafe', 'Getafe CF'),
    ('Egnatia', 'KF Egnatia', 'Egnatia Rrogozhine'),
    ('Besiktas', 'Beşiktaş JK', 'Besiktas JK'),
    ('Lech Poznan', 'KKS Lech Poznan'),
    ('AC Milan', 'Milan', 'AC Milano'),
    ('Hapoel Beer Sheva', "Hapoel Be'er", "Hapoel Be'er Sheva"),
    ("Inter Club d'Escaldes", "Inter D'Escaldes", 'Inter Escaldes'),
)
COUNTRY_TAGS = set('alb and arm aut aze bel bih bra bul cro cyp cze den eng esp est fin fra geo ger gib gre hun irl ire isl isr ita kaz ltu lva mda mne ned nir nor pol por rou sco srb sui svk swe tur ukr wal svn mkd lux mlt'.split())


def normalize(name):
    if not isinstance(name, str):
        return ''
    name = name.casefold().strip()
    suffix = re.search(r'\s*\(([a-z]{3})\)\s*$', name)
    if suffix and suffix.group(1) in COUNTRY_TAGS:
        name = name[:suffix.start()]
    name = name.translate(str.maketrans({'ø':'o', 'æ':'ae', 'œ':'oe', 'ł':'l', 'đ':'d', 'ß':'ss', '&':' and '}))
    name = ''.join(c for c in unicodedata.normalize('NFKD', name) if not unicodedata.combining(c))
    return ' '.join(re.findall(r'[a-z0-9]+', name))


def build_aliases(groups):
    result = {}
    for group in groups:
        canonical = normalize(group[0])
        for name in group:
            key = normalize(name)
            if key in result and result[key] != canonical:
                raise ValueError(f'Conflicting alias: {name}')
            result[key] = canonical
    return result


ALIASES = build_aliases(ALIAS_GROUPS)


def canonical(name):
    key = normalize(name)
    return ALIASES.get(key, key)


def same_team(a, b):
    return bool(canonical(a)) and canonical(a) == canonical(b)


def utc(value):
    dt = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if dt.tzinfo is None:
        raise ValueError('Kickoff must include timezone')
    return dt.astimezone(timezone.utc)


def match_fixtures(fixtures, candidates, tolerance_minutes=15):
    """Rows need id, home, away, canonical league and timezone-aware start_utc."""
    if not 0 <= tolerance_minutes <= 60:
        raise ValueError('Invalid kickoff tolerance')
    proposals, unresolved = {}, {}
    fixture_ids = Counter(f['id'] for f in fixtures)
    candidate_ids = Counter(c['id'] for c in candidates)
    for f in fixtures:
        fid = f['id']
        if fixture_ids[fid] != 1:
            unresolved[fid] = 'duplicate_fixture_id'
            continue
        try:
            start = utc(f['start_utc'])
            if not f['league'] or not canonical(f['home']) or not canonical(f['away']):
                raise ValueError('Missing identity')
        except (ValueError, TypeError, AttributeError, KeyError):
            unresolved[fid] = 'invalid_fixture_identity'
            continue
        options = []
        for c in candidates:
            try:
                if c['league'] != f['league']:
                    continue
                if not (same_team(f['home'], c['home']) and same_team(f['away'], c['away'])):
                    continue
                if abs((utc(c['start_utc']) - start).total_seconds()) > 60 * tolerance_minutes:
                    continue
                options.append(c)
            except (ValueError, TypeError, AttributeError, KeyError):
                continue
        if len(options) == 1 and candidate_ids[options[0]['id']] == 1:
            proposals[fid] = options[0]
        else:
            unresolved[fid] = 'no_verified_match' if not options else 'ambiguous_match'
    claims = Counter(c['id'] for c in proposals.values())
    matched = {}
    for fid, c in proposals.items():
        if claims[c['id']] == 1:
            matched[fid] = c
        else:
            unresolved[fid] = 'candidate_claimed_multiple_times'
    return matched, unresolved
