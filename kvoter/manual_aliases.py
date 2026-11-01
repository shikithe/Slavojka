"""Persist manually approved team aliases, scoped by league, without unsafe merges."""
from kvoter.team_identity import normalize

def approve(db, row, source):
    if row.get("decision")!="matched":
        return db
    entries=db.setdefault("teams",[])
    league=row["league"]
    pairs=[(row["collector_home"],row["odds_home"]),(row["collector_away"],row["odds_away"])]
    index={(e["league"],normalize(n)):e for e in entries for n in e["names"]}
    for left,right in pairs:
        a,b=normalize(left),normalize(right)
        if not a or not b or a==b:
            continue
        left_entry=index.get((league,a))
        right_entry=index.get((league,b))
        if left_entry is not None and right_entry is not None and left_entry is not right_entry:
            raise ValueError("Conflicting approved aliases for "+left+" / "+right)
        target=left_entry or right_entry
        if target is None:
            target={"id":league+"-"+a.replace(" ","-"),"league":league,"names":[],"sources":[],"verified":True}
            entries.append(target)
        for name in (left,right):
            if normalize(name) not in {normalize(x) for x in target["names"]}:
                target["names"].append(name)
            index[(league,normalize(name))]=target
        target["sources"]=list(dict.fromkeys(target.get("sources",[])+[source]))
        target["verified"]=True
    return db
