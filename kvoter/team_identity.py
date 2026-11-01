"""User-approved, league-scoped team identities. No fuzzy auto-approval."""
import json
import os
import unicodedata
from pathlib import Path

ALIASES_PATH=Path(__file__).with_name("team_aliases.json")

def normalize(value):
    value=unicodedata.normalize("NFKD",str(value or "").casefold())
    value="".join(c for c in value if not unicodedata.combining(c))
    return " ".join("".join(c if c.isalnum() else " " for c in value).split())

def load_aliases(path=ALIASES_PATH):
    data=json.loads(Path(path).read_text(encoding="utf-8"))
    groups={}
    for entry in data["teams"]:
        league=entry["league"]
        names=entry["names"]
        if len(names)<2: raise ValueError("Each approved identity needs at least two names")
        for name in names:
            key=(league,normalize(name))
            if not key[1]: raise ValueError("Empty team name")
            if key in groups: raise ValueError("Ambiguous approved team alias: "+str(key))
            groups[key]=entry["id"]
    return groups

def same_team(left,right,league,aliases=None):
    a,b=normalize(left),normalize(right)
    if not a or not b: return False
    if a==b: return True
    groups=load_aliases(os.getenv('KVOTER_ALIASES_PATH',str(ALIASES_PATH))) if aliases is None else aliases
    return bool(groups.get((league,a)) and groups.get((league,a))==groups.get((league,b)))
