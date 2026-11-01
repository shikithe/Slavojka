#!/usr/bin/env python3
"""Build evidence-based manual candidate queue from persisted fixtures and Odds API offers."""
import argparse,json
from pathlib import Path
from difflib import SequenceMatcher
from datetime import datetime,timezone
from kvoter import utc
from team_identity import normalize

def build(history,offers,unmatched):
    result=[]
    for f in unmatched['fixtures']:
        options=[]
        for o in offers['offers']:
            if o.get('league')!=f.get('league'): continue
            a,b=utc(f.get('start_utc')),utc(o.get('start_utc'))
            if not a or not b or abs((a-b).total_seconds())>5400: continue
            h=SequenceMatcher(None,normalize(f['home']),normalize(o.get('home'))).ratio()
            aw=SequenceMatcher(None,normalize(f['away']),normalize(o.get('away'))).ratio()
            score=round((h+aw)/2,3)
            if score<0.35: continue
            options.append({'event_id':str(o.get('event_id','')),'home':o.get('home'),'away':o.get('away'),'start_utc':o.get('start_utc'),'league':o.get('league'),'similarity':score})
        options.sort(key=lambda x:x['similarity'],reverse=True)
        unique=list({x['event_id']:x for x in options if x['event_id']}.values())
        result.append({**f,'candidates':unique[:5]})
    return {'generated_at_utc':datetime.now(timezone.utc).isoformat(),'total':len(result),'fixtures':result}
if __name__=='__main__':
    p=argparse.ArgumentParser()
    for k in ['history','offers','unmatched','output']:p.add_argument('--'+k,required=True)
    a=p.parse_args()
    data=build(json.loads(Path(a.history).read_text()),json.loads(Path(a.offers).read_text()),json.loads(Path(a.unmatched).read_text()))
    decisions=Path('kvoter/manual/decisions.json')
    recorded=json.loads(decisions.read_text()).get('decisions',[]) if decisions.exists() else []
    approved_ids={d['fixture_id'] for d in recorded if d.get('decision')=='matched'}
    rejected={(d['fixture_id'],d['event_id']) for d in recorded if d.get('decision')=='rejected'}
    data['fixtures']=[f for f in data['fixtures'] if f['fixture_id'] not in approved_ids]
    for fixture in data['fixtures']:
        fixture['candidates']=[x for x in fixture['candidates'] if (fixture['fixture_id'],x['event_id']) not in rejected]
    no_offer=sum(not f['candidates'] for f in data['fixtures'])
    data['fixtures']=[f for f in data['fixtures'] if f['candidates']]
    data['total']=len(data['fixtures'])
    print('MANUAL_NO_ODDS_CANDIDATE_EXCLUDED',no_offer)
    print('MANUAL_APPROVED_HIDDEN',len(approved_ids))
    Path(a.output).write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n')
    print('MANUAL_CANDIDATES',data['total'],sum(len(f['candidates']) for f in data['fixtures']))
