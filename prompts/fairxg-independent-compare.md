# FairXG kao pomoćni nezavisni kontrolor TOP10 (obavezni pokušaj, nikad blokada)

Izvor: https://fairxg.com/sport/football i stranice utakmica https://fairxg.com/sport/football/match/...
Čitaj samo JAVNO dostupne podatke; bez prijave, zaobilaženja zaštita ili nagađanja.

Za svaki meč ESPN TOP10 (identitet je samo ESPN fixture_id), pronađi FairXG meč tako što ideš prvo po ligi i datumu, zatim prepoznaješ oba tima. Pri uparivanju AI smije predložiti alias tipa 'FC Augsburg' = 'Augsburg', ali MORA provjeriti: (1) datum u Europe/Sarajevo, (2) takmičenje, (3) oba tima u tačnom redoslijedu domaćin/gost, (4) nema konkurentskog meča. Ne upisuj automatski AI nagađanje kao potvrđen identitet. Ambiguous/unavailable ostaje odvojeno, bez podatka o xG i bez kvote.

U validnom meču preuzmi:
- FairXG 1/X/2 procenti (navedi da je ovo bookmaker-adjusted, nije čisto nezavisan model);
- zasebni 'Goals model' 1/X/2 ako je prikazan; ne zamjenjuj ga sa FairXG bookmaker-based procentima;
- model expected goals za domaćina i gosta, zbroj xG;
- 'Over 2.5 goals' procenat (= naš 3+), 'Both teams score' (= naš GG), komplementarni NG;
- link izvora, datum utakmice i vrijeme provjere.
Važno: FairXG-ove 'fair odds' su izvedene iz vjerovatnoća; NISU ponuđene kladioničarske kvote. Kladioničarske kvote ostaju iz našeg TipsterArea active-list.json.

Uporedi procenat ISTOG tržišta našeg Matematičkog Scouta 6/6 i FairXG. delta_pp = nas_model_pct - fairxg_pct. Naš EV se računa pomoću NAŠE stvarne kvote s TipsterArea, ne FairXG fair odds. Prikaži i zaseban hipotetički FairXG EV samo uz jasno označenu istu stvarnu kvotu. Za razliku veću ili jednaku 10 procentnih poena napiši eksplicitno 'MODEL DISAGREEMENT', razloge neizvjesnosti, dodatnu provjeru ili odbijanje tipa. Nema automatskog povećanja ili smanjenja našeg modela: prosudi dokaze.

Ako FairXG nema utakmicu, ne podudara se datum, liga, domaćin ili gost, ili pristup nije moguć: označi unavailable/ambiguous i nastavi sedam drugih faktora te naš Scout bez čekanja. Sve TOP10 analiziraj i prijavi pokrivenost (matched/ambiguous/unavailable), bez prisilnog odabira tiketa.

Primjer potvrđenog poređenja 22.11.2026 (ne koristiti kao sutrašnju prognozu):
Augsburg–Mainz: naš 3+ 71.7%, FairXG 3+ 62%, razlika +9.7 pp. FairXG xG domaćin 1.84, gost 1.38.
Kasimpasa–Alanyaspor: naš 1 65.2%, FairXG 1 49% (bookmaker-adjusted), zasebni Goals model 1 54%, razlika +16.2 pp prema FairXG glavnoj procjeni.
Ova dva podudaranja su dokaziva na https://fairxg.com/sport/football/match/augsburg-vs-mainz i https://fairxg.com/sport/football/match/kasimpasa-vs-alanyaspor.
