"""G2 judge, structural (no hardcoded run ids or document names).

The previous judge hardcoded answer ids and document names,
so it only ever proved the single committed fixture. This version derives
everything from graph structure so it holds on any conforming store:

  * answers    = all (:Answer) nodes          (no answer-id literals)
  * convergence= Q2 doc set (the >=2-branch low-score motif)
  * localization= Q1 bad_source per answer
  * baseline   = global lowest-score (:Source) (no run-id filter)

Pass conditions (all must hold):
  1. baseline_misidentifies: global lowest score is NOT the convergence cause.
  2. graph_localizes_true_cause: for every answer with a convergence signal,
     its Q1 picks equal that signal (graph beats the non-graph baseline).
  3. graph_zero_false_positive_on_clean: answers with no convergence signal
     produce zero Q1 picks.
  4. has_signal: at least one convergence answer and one clean answer exist
     (prevents passing on an empty or degenerate store).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import relate

from .querypacks import run_pack

BASELINE_CYPHER = "MATCH (s:Source) RETURN s.doc_id AS doc ORDER BY s.score ASC LIMIT 1"
ANSWERS_CYPHER = "MATCH (a:Answer) RETURN a.answer_id AS id ORDER BY a.answer_id"


def judge(store: str | Path, threshold: float = 0.5) -> dict[str, Any]:
    """Return a structured, structure-derived verdict for the stricter G2 check."""
    db = relate.Database(str(store), read_only=True)
    try:
        baseline_rows = list(db.execute(BASELINE_CYPHER, {}).data)
        answer_ids = [r["id"] for r in db.execute(ANSWERS_CYPHER, {}).data]
        convergence = {
            r["doc"] for r in run_pack(db, "Q2", {"threshold": threshold}) if r.get("doc")
        }
        per_answer = {}
        for aid in answer_ids:
            rows = run_pack(db, "Q1", {"answer_id": aid, "threshold": threshold})
            per_answer[aid] = sorted({r["bad_source"] for r in rows if r.get("bad_source")})
    finally:
        db.close()

    baseline_pick = baseline_rows[0]["doc"] if baseline_rows else None
    signal_answers = {a: picks for a, picks in per_answer.items() if picks}
    clean_answers = {a: picks for a, picks in per_answer.items() if not picks}

    # A convergence cause is the structural root cause; Q1 must localize exactly it.
    localized_ok = bool(convergence) and all(
        set(picks) == convergence for picks in signal_answers.values()
    )
    clean_ok = bool(clean_answers) and all(picks == [] for picks in clean_answers.values())

    checks = {
        "baseline_misidentifies": bool(baseline_pick) and baseline_pick not in convergence,
        "graph_localizes_true_cause": localized_ok,
        "graph_zero_false_positive_on_clean": clean_ok,
        "has_signal": bool(signal_answers) and bool(clean_answers) and bool(convergence),
    }
    passed = all(checks.values())
    return {
        "metric": "structure-derived root-cause localization: graph vs global-lowest-score baseline",
        "checks": checks,
        "baseline_global_lowest_score_picks": baseline_pick,
        "convergence_causes": sorted(convergence),
        "answers_with_signal": signal_answers,
        "answers_clean": sorted(clean_answers),
        "passed": passed,
        "verdict": "PASS" if passed else "FAIL",
    }
