# ListaSix — AI fallback for ESPN ↔ TipsterArea identity matching

## Activation
When today's `shared/kvoter/coverage-feedback.json` has `status=ai_review_required`, the AI analyst must review **only** its `missing_fixtures`: every ESPN fixture without ANY valid quote, including fixtures that were paired but whose odds were not available or parsed. This document is an analyst instruction, not an executable GitHub AI agent. Do not state that a GitHub Actions job can reason from this prompt by itself.

## Inputs
- `shared/collector-feed.json` current ESPN event ID, home, away, league, kickoff timestamp
- `shared/kvoter/coverage-feedback.json` missing_fixtures (source of truth for feedback)
- `shared/kvoter/tipster-status.json` optional diagnostics about unpaired links and parser failures
- Current TipsterArea daily indexes for the ESPN UTC date, Europe/Sarajevo date, and adjacent date only where midnight explains the difference
- Direct TipsterArea match page title, date, league, teams and available odds, if discoverable

## Procedure for each unmatched fixture
1. Research both teams' original, abbreviated, transliterated, translated and historic names (e.g. Inter/Internazionale), city, team table/standings and club identity. Compare ESPN league, kickoff time and date; one matching team name may help find candidates but is NEVER sufficient proof on its own. Never assume two teams are identical based on spelling alone.
2. Search the source's daily listings and match pages using both teams, the competition and kickoff date; also check a justified adjacent date for timezone boundary.
3. Require unequivocal same **home** and **away** teams, competition and compatible kickoff/date. Never accept a reversed fixture, youth/reserve/women's team or a different competition without proof.
4. If a page is located, open it and verify its date and identity rather than merely trusting a search result. Record exact URL and evidence.
5. Only confirmed pages may be offered to the existing collector for parsing 1X2, Over 2.5 (3+) and BTTS yes/no, using real displayed prices. Never invent or interpolate prices.
6. If ambiguity remains, leave the fixture unmatched and log why; do not reduce identity thresholds globally or silently overwrite any quote.
7. Recheck completion: ALL ESPN fixture IDs require >=1 real odds field, then feedback becomes `ready_for_scout` and the already existing Scout 6/6 can run. Otherwise keep `ai_review_required`. Report ESPN total, matched, unmatched, quote coverage, and reasons for remaining exceptions.

## Output contract
Write structured review records with ESPN fixture_id, original ESPN names, TipsterArea names, source URL, local source date, decision (confirmed / rejected / unresolved), reason and evidence. Only confirmed records can be consumed by a separate verified importer, which must recheck URL allowlist, page title/date and team identity.

## Ownership
GitHub collects, stores and publishes; the AI analyst performs the research and identity judgments. This prompt does not schedule or launch the analyst. The existing scheduled MEMARA A/B AI task now checks the feedback and may execute this review at its next scheduled run; GitHub additionally opens a deduplicated review issue as a visible handoff. This is not an immediate GitHub-to-ChatGPT webhook.
