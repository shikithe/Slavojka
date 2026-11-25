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

## Tiket B: matematička gradacija 3+ unutar TOP10 (od 25.11.2026)

1. Za **svih deset utakmica iz TOP10** uzmi postojeći matematički procenat
   `probability_pct["3+"]` bez preračunavanja ili miješanja s drugim tržištima.
2. Filtriraj samo utakmice koje još nisu počele, imaju stvarnu kvotu za 3+
   i nisu već izabrane za tiket A. **Ne filtriraj B po EV-u ni po tome da li
   je 3+ najbolje, drugo ili treće tržište.**
3. Rangiraj po matematičkoj vjerovatnoći 3+ opadajuće.
   B mora imati **tačno dva** različita para, ukupna kvota **2,00–3,00**.
   Ako najjača dva para imaju npr. ukupno 1,94, traži sljedeću najjaču
   kombinaciju od dva uz zadržavanje što većih procenata, a ne proglasiti
   automatski da B nema kandidata.
4. EV ostaje odvojena, transparentno izračunata procjena i upozorenje
   (naročito kada je negativan); konačni AI pregled provjerava FairXG,
   povrede, izostanke, stvarne kvote, identitet i rizik prije odobrenja.
   Matematička vjerovatnoća nije kalibrisani dokaz preciznosti modela.
5. GitHub izdvaja **prijedlog**, ne izvršava analitičko odobrenje i ne
   objavljuje nijedan tiket bez eksplicitnog AI approved dokumenta.
   Postojeće objave i banka se ne mijenjaju naknadno zbog novog rangiranja.
