# ListaSix Scout TOP10 — trajno pravilo (2026-11-24)

- U TOP10 idu prvih deset utakmica iz postojeceg value/EV rankinga
  koje tek treba da pocnu i imaju bar jednu potvrdjenu kvotu.
  Ako dostupnih utakmica ima manje od deset, ne izmisljati dodatne.
- TOP10 je **lista za detaljno AI istrazivanje**, ne lista automatski
  odobrenih tipova. Oznaka `research_only` vazi pojedinacno za
  svakog kandidata koji nije prosao stroge uslove za tiket A/B.
- Svih sest matematickih trzista racuna se za svaki ESPN mec,
  a postojece sigurnosne granice (kvota, konzervativni EV, kvalitet
  uzorka, pocetak utakmice) i dalje vrijede za predlog tiketa.
- Forma kluba: posljednjih pet **zavrsenih** utakmica iz stvarnih
  ESPN podataka. Uz rezultate takmicenja mecâ, History smije traziti
  UEFA i domace utakmice putem ESPN `all/teams/<id>/schedule`, ali
  samo kada je ID kluba prethodno nedvosmisleno potvrdjen iz
  izvornog ESPN event ID-a i domacin/gost odgovaraju.
- Rasporedi u ESPN-u imaju `competitions[0].status.type.completed`;
  scoreboard ima `event.status.type.completed`. Nikada ne smatrati
  samo datum ili prisutan rezultat dokazom zavrsetka.
- Duplikate ukloniti preko ESPN event ID-a, sortirati po stvarnom
  datumu, nista ne zakljucivati o nepostojecem xG-u.
  Liga-prosjeci se racunaju samo iz iste lige, ne iz kombinovanih
  domacih i UEFA rezultata.
- Kada bilo koji izvor nema pet rezultata, zadrzati stvarno nadjene
  i navesti ogranicenje; ne blokirati istrazivanje TOP10, ali ne
  lazno odobravati tiket. Nijedna funkcija ne objavljuje tikete.
- Po promjeni sheme Historyja mora se ponovo pokrenuti History,
  pa tek po `HISTORY_READY` Scout i `TOP10_READY`. Svi izvjestaji
  moraju odgovarati danasnjem ESPN feedu i kvotama.

## Tiket B: 3+ među dva najbolje rangirana tržišta

- Matematika Scout 6/6 i dalje obrađuje svih šest tržišta za A i B.
- Za tiket B razmatra se **3+ golova ako je po postojećem value/EV skoru 1. ili 2. najbolje tržište** u utakmici, čak i kada je prvo mjesto GG ili neki drugi tip.
- B se uvijek sastavlja na tržištu **3+**, s njegovom vlastitom stvarnom kvotom, prilagođenom vjerovatnoćom, konzervativnim EV-om i skautovskim skorom. Ne smije uzeti kvotu/pogodak prvog tržišta.
- I dalje se za B traže pozitivan konzervativni EV za 3+, prilagođena vjerovatnoća najmanje 50%, kvota 3+ ispod 3,00, najmanje 4 potvrđene prethodne utakmice oba kluba i najmanje 20 minuta do početka.
- B i A ne smiju koristiti istu utakmicu na oba tiketa; ukupna kvota tiketa ostaje 2,00–3,00. Izbor je samo preliminaran do zasebne detaljne AI provjere.
