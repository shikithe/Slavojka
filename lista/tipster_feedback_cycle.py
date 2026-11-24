#!/usr/bin/env python3
"""One-shot TipsterArea feedback: initial matching -> optional review/retry -> final READY.

Only fresh ESPN fixtures are allowed. A prompt alone does not execute an AI.
Unmatched fixtures remain explicitly unquoted; real verified prices survive.
"""
import json
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo
from lista.odds_feedback import evaluate

TZ = ZoneInfo("Europe/Sarajevo")
FIELDS = ("home_odds", "draw_odds", "away_odds", "over25_odds", "btts_yes_odds", "btts_no_odds")


def complete(feedback, retry_attempted):
    if feedback["status"] not in ("ready_for_scout", "ai_review_required"):
        raise ValueError("Unrecognized preliminary coverage result")
    if feedback["without_quote"] and not retry_attempted:
        raise ValueError("Cannot finalize missing fixtures before additional matching attempt")
    if feedback["with_at_least_one_quote"] + feedback["without_quote"] != feedback["espn_total"]:
        raise ValueError("ESPN odds coverage totals inconsistent")
    result = dict(feedback)
    missing=feedback["without_quote"]
    # ODDS_READY remains the existing Scout handoff; coverage_status is the
    # separate, truthful sensor signal. A partial day is NEVER called complete.
    result.update(
        feedback="ODDS_READY",
        coverage_feedback="ODDS_PARTIAL_READY" if missing else "ODDS_COMPLETE",
        coverage_status="partial" if missing else "complete",
        sensor_action_required=bool(missing),
        sensor_missing_fixtures=feedback.get("missing_fixtures",[]) if missing else [],
        status="ready_for_scout",
        final=True,
        retry_attempted=bool(retry_attempted),
        matched_with_quotes=feedback["with_at_least_one_quote"],
        skipped_unmatched=feedback["without_quote"],
        incomplete_markets_allowed=True,
        next_action="scout_6of6_if_history_ready",
        finished_at_utc=datetime.now(timezone.utc).isoformat(),
    )
    return result


def main(root=Path(".")):
    day = datetime.now(TZ).date().isoformat()
    feed = json.loads((root / "shared/collector-feed.json").read_text(encoding="utf-8"))
    active = json.loads((root / "shared/active-list.json").read_text(encoding="utf-8"))
    initial = json.loads((root / "shared/kvoter/coverage-feedback.json").read_text(encoding="utf-8"))
    current = evaluate(feed, active, day)
    if initial.get("date") != day or initial.get("espn_total") != current["espn_total"]:
        raise ValueError("Feedback for different ESPN day/count")
    # Initial feedback is captured before retry; checking the status ensures
    # the fallback is not silently skipped.
    retried = (initial.get("feedback") == "ODDS_MISSING_AI_REVIEW"
               or (initial.get("feedback") == "ODDS_READY" and initial.get("retry_attempted") is True))
    if current["without_quote"] and not retried:
        raise ValueError("Missing odds without preliminary identity-review feedback")
    final = complete(current, retried)
    p = root / "shared/kvoter/coverage-feedback.json"
    p.write_text(json.dumps(final, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(final["coverage_feedback"], final["matched_with_quotes"], "/", final["espn_total"],
          "unmatched_skipped=", final["skipped_unmatched"])
    return final


if __name__ == "__main__":
    main()
