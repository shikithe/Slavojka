"""Record every distinct OddsAPI team name without asserting team equivalence."""
import json,os
from datetime import datetime,timezone
from pathlib import Path
from kvoter.team_identity import normalize

def collect_names(offers, path):
    path=Path(path)
    data=json.loads(path.read_text()) if path.exists() else {"schema_version":1,"source":"the-odds-api-v4","names":[]}
    known={(x["league"],normalize(x["name"])) for x in data["names"]}
    now=datetime.now(timezone.utc).isoformat()
    added=0
    for offer in offers:
        league=offer.get("league")
        for side in ("home","away"):
            name=offer.get(side)
            if not league or not isinstance(name,str) or not normalize(name):continue
            key=(league,normalize(name))
            if key in known:continue
            data["names"].append({"league":league,"name":name,"normalized":key[1],"source":"the-odds-api-v4","first_seen_utc":now,"verified_identity":False})
            known.add(key);added+=1
    path.parent.mkdir(parents=True,exist_ok=True)
    tmp=path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    os.replace(tmp,path)
    return added
