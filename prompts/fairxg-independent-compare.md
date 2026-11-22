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

NOVO OBAVEZNO PRAVILO — KONAČNA VJEROVATNOĆA PO TRŽIŠTU (22.11.2026):
Za SVAKO pojedinačno tržište od 1, X, 2, 3+, GG, NG odredi:
- p_math = vjerovatnoća iz originalnog Matematičkog Scouta 6/6 (ne mijenjati izvornu datoteku).
- p_fairxg = odgovarajući FairXG procenat SAMO kada je potvrđen identičan ESPN meč (liga, datum, domaćin/gost), identično tržište i dostupan eksplicitan broj; ne zaključuj/procjenjuj nedostajući podatak osim NG = 100 - eksplicitni FairXG GG, ako su oba istog modela i iste definicije tržišta.
- Ako p_fairxg postoji: p_final = (p_math + p_fairxg) / 2.
- Ako p_fairxg ne postoji za to tržište ili podudaranje nije sigurno: p_final = p_math.
Izračun radi PO TRŽIŠTU nezavisno; ne smiješ proglasiti cijelu utakmicu nedostupnom ako FairXG ima samo neka tržišta. Čuvaj polja math_probability_pct, fairxg_probability_pct (ili null), final_probability_pct, fairxg_status, source_url, model_basis, delta_pp. Prikaži ta tri procenta jasno, da korisnik vidi porijeklo konačne brojke. Za 1/X/2 koristi isti glavni FairXG skup procjena, NE miješaj nasumično bookmaker-based i poseban Goals model; Goals model prikaži odvojeno kao kontekst.

KONAČNI EV za TipsterArea kvotu O iz active-list.json: ev_final_pct = (p_final/100 * O - 1)*100. Na osnovu ove konačne vjerovatnoće i konačnog EV rangiraj tipove i donesi završnu A/B odluku uz ostalih sedam obaveznih AI faktora. Ne miješaj FairXG modelsku 'fair odds' sa ponudom kladionice. Ako p_fairxg nije dostupan, koristi originalni p_math i izračunaj finalni EV na toj osnovi.

Ako apsolutna razlika p_math i p_fairxg iznosi >=10 procentnih poena, obavezno označi MODEL DISAGREEMENT i objasni rizik; PRAVILO PROSJEKA ipak važi kada su oba podatka za isto tržište validna. Ne miješaj izvornu modelsku vjerovatnoću i ranije dodatno konzervativno prilagođenu vjerovatnoću: za p_math koristi originalni market probability iz all_six_probabilities_pct; obje druge vrijednosti prikaži odvojeno kao kontekst.

Napomena: aritmetički prosjek je korisnikovo operativno pravilo, nije statistički dokaz da je procjena preciznija; izvori mogu biti korelisani. Održavaj ovu ogradu u analizi.

Ako FairXG nema utakmicu, ne podudara se datum, liga, domaćin ili gost, ili pristup nije moguć: označi unavailable/ambiguous i nastavi sedam drugih faktora te naš Scout bez čekanja. Sve TOP10 analiziraj i prijavi pokrivenost (matched/ambiguous/unavailable), bez prisilnog odabira tiketa.

Primjer potvrđenog poređenja 22.11.2026 (ne koristiti kao sutrašnju prognozu):
Augsburg–Mainz: naš 3+ 71.7%, FairXG 3+ 62%, razlika +9.7 pp. FairXG xG domaćin 1.84, gost 1.38.
Kasimpasa–Alanyaspor: naš 1 65.2%, FairXG 1 49% (bookmaker-adjusted), zasebni Goals model 1 54%, razlika +16.2 pp prema FairXG glavnoj procjeni.
Ova dva podudaranja su dokaziva na https://fairxg.com/sport/football/match/augsburg-vs-mainz i https://fairxg.com/sport/football/match/kasimpasa-vs-alanyaspor.
