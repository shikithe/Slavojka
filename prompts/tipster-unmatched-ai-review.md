# ListaSix — AI fallback for ESPN ↔ TipsterArea identity matching

## Activation
When `shared/kvoter/tipster-status.json` for today's Europe/Sarajevo date has a nonempty `unpaired` list, the AI analyst must review **only** those fixtures. This document is an analyst instruction, not an executable GitHub AI agent. Do not state that a GitHub Actions job can reason from this prompt by itself.

## Inputs
- `shared/collector-feed.json` current ESPN event ID, home, away, league, kickoff timestamp
- `shared/kvoter/tipster-status.json` missing matches
- Current TipsterArea daily indexes for the ESPN UTC date, Europe/Sarajevo date, and adjacent date only where midnight explains the difference
- Direct TipsterArea match page title, date, league, teams and available odds, if discoverable

## Procedure for each unmatched fixture
1. Research both teams' original, abbreviated, transliterated, translated and historic names (e.g. Inter/Internazionale), city and club identity. Never assume two teams are identical based on spelling alone.
2. Search the source's daily listings and match pages using both teams, the competition and kickoff date; also check a justified adjacent date for timezone boundary.
3. Require unequivocal same **home** and **away** teams, competition and compatible kickoff/date. Never accept a reversed fixture, youth/reserve/women's team or a different competition without proof.
4. If a page is located, open it and verify its date and identity rather than merely trusting a search result. Record exact URL and evidence.
5. Only confirmed pages may be offered to the existing collector for parsing 1X2, Over 2.5 (3+) and BTTS yes/no, using real displayed prices. Never invent or interpolate prices.
6. If ambiguity remains, leave the fixture unmatched and log why; do not reduce identity thresholds globally or silently overwrite any quote.
7. Recheck completion and report ESPN total, matched, unmatched, quote coverage, and an explanation for each remaining exception.

## Output contract
Write structured review records with ESPN fixture_id, original ESPN names, TipsterArea names, source URL, local source date, decision (confirmed / rejected / unresolved), reason and evidence. Only confirmed records can be consumed by a separate verified importer, which must recheck URL allowlist, page title/date and team identity.

## Ownership
GitHub collects, stores and publishes; the AI analyst performs the research and identity judgments. This prompt does not schedule or launch the analyst. A separate task or AI event handoff must explicitly invoke it.
