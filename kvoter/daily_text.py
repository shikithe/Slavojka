#!/usr/bin/env python3
"""Daily read-only football list, from this exact isolated collector+odds run."""
import argparse,json
from datetime import datetime
from zoneinfo import ZoneInfo
from pathlib import Path

p=argparse.ArgumentParser()
p.add_argument('--history',required=True)
p.add_argument('--matched',required=True)
p.add_argument('--output',required=True)
a=p.parse_args()
history=json.loads(Path(a.history).read_text())
matched=json.loads(Path(a.matched).read_text())
by_id={x['fixture_id']:x for x in matched['fixtures']}
generated=history.get('generated_at_utc','')
lines=['KVOTER - KLADIONICARSKA PONUDA (TXT)',
       'Preuzeto: '+generated+' UTC | vrijeme: Europe/Sarajevo',
       'Ukupno: '+str(len(history['fixtures']))+' | automatski upareno: '+str(len(by_id)),
       'Kvote iz posljednjeg API preuzimanja; nisu uzivo. Crtica = nema kvote.','',
       'BR  DATUM SAT    UTAKMICA                                    1      X      2     3+  IZVOR',
       '-'*110]
def price(value):
    if value is None: return '-'
    try: return f'{float(value):.2f}'
    except (TypeError,ValueError): return '-'
for i,f in enumerate(history['fixtures'],1):
    when=datetime.fromisoformat(f['start_utc'].replace('Z','+00:00')).astimezone(ZoneInfo('Europe/Sarajevo'))
    m=by_id.get(f['fixture_id'])
    offers=m.get('odds_offers',[]) if m else []
    pref=next((o for o in offers if o.get('bookmaker')=='pinnacle' and o.get('markets',{}).get('1X2')),None)
    if pref is None: pref=next((o for o in offers if o.get('markets',{}).get('1X2')),None)
    if pref is None and offers: pref=offers[0]
    markets=pref.get('markets',{}) if pref else {}
    one=markets.get('1X2',{})
    over=markets.get('3+',{})
    match_name=str(f['home'])+' - '+str(f['away'])
    lines.append(f"{i:02d}  {when:%d.%m. %H:%M}  {match_name:<44.44} {price(one.get('home')):>6} {price(one.get('draw')):>6} {price(one.get('away')):>6} {price(over.get('over')):>6}  {pref.get('bookmaker','N/P') if pref else 'N/P'}")
lines.extend(['','1=domacin | X=nerijeseno | 2=gost | 3+=vise od 2.5 golova',
              'N/P = bez potvrdenih kvota u ovom ciklusu.'])
Path(a.output).parent.mkdir(parents=True,exist_ok=True)
Path(a.output).write_text('\n'.join(lines)+'\n',encoding='utf-8')
print('DAILY_TEXT_CREATED',len(history['fixtures']))
