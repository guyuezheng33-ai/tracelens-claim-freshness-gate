"""Falsifiable head-to-head: graph localization vs global-lowest-score baseline.

A claim that "the graph is more accurate" is only interesting if it can be
wrong. This module makes the comparison falsifiable on one store:

  * the baseline ranks all sources globally and always returns the single
    lowest-scored document, regardless of which answer is being inspected;
  * the graph asks Q1 for each answer and returns evidence paths only where
    a low-score retrieval branch converges on that answer.

The output shows, per answer, what each method would tell an operator. If the
graph returned the same document for every answer, the check would fail -- so
the demonstration is a real comparison, not a narrated conclusion.

stdout is JSON only; provenance is written alongside the JSON report.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

import relate

from .judge import judge
from .querypacks import run_pack

BASELINE_CYPHER = "MATCH (s:Source) RETURN s.doc_id AS doc ORDER BY s.score ASC LIMIT 1"
ANSWERS_CYPHER = "MATCH (a:Answer) RETURN a.answer_id AS id ORDER BY a.answer_id"


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def compare(store: str | Path, threshold: float = 0.5) -> dict[str, Any]:
    """Run both detectors on the same read-only store and return a report."""
    store_path = Path(store)
    db = relate.Database(str(store_path), read_only=True)
    try:
        baseline_rows = list(db.execute(BASELINE_CYPHER, {}).data)
        answer_ids = [r["id"] for r in db.execute(ANSWERS_CYPHER, {}).data]
        graph_rows = {
            aid: run_pack(db, "Q1", {"answer_id": aid, "threshold": threshold})
            for aid in answer_ids
        }
    finally:
        db.close()

    baseline_pick = baseline_rows[0]["doc"] if baseline_rows else None
    per_answer = []
    for aid in answer_ids:
        picks = sorted({r.get("bad_source") for r in graph_rows[aid] if r.get("bad_source")})
        per_answer.append({
            "answer_id": aid,
            "baseline_pick": baseline_pick,
            "baseline_localizes": bool(baseline_pick) and baseline_pick in picks,
            "graph_picks": picks,
            "graph_path_count": len(graph_rows[aid]),
            "graph_paths": [
                {
                    "path": r.get("path"),
                    "bad_source": r.get("bad_source"),
                    "score": r.get("score"),
                    "hops": r.get("hops"),
                }
                for r in graph_rows[aid]
            ],
        })

    verdict = judge(store_path, threshold=threshold)
    graph_pick_sets = [set(row["graph_picks"]) for row in per_answer]
    falsifiable = {
        "baseline_is_answer_blind": all(
            row["baseline_pick"] == baseline_pick for row in per_answer
        ) and len(per_answer) > 1,
        "graph_distinguishes_answers": any(graph_pick_sets) and any(
            not s for s in graph_pick_sets
        ),
        "baseline_wrong_on_at_least_one_answer": any(
            not row["baseline_localizes"] for row in per_answer
        ),
    }
    passed = all(falsifiable.values()) and verdict["passed"]

    return {
        "schema": "tracelens/falsifiable-comparison@1",
        "store": str(store_path),
        "store_sha256": _sha256(store_path) if store_path.exists() else None,
        "threshold": threshold,
        "baseline": {
            "method": "global lowest Source.score, same answer-independent pick",
            "pick": baseline_pick,
        },
        "graph": {
            "method": "Q1 per-answer evidence path with convergence motif",
            "answers": len(per_answer),
        },
        "per_answer": per_answer,
        "falsifiable_checks": falsifiable,
        "judge": verdict,
        "passed": passed,
        "verdict": "PASS" if passed else "FAIL",
        "caveat": (
            "Both methods run on the same store and the same threshold. "
            "The baseline is deliberately naive; this compares localization, "
            "not general retrieval quality."
        ),
    }


def report_markdown(record: dict[str, Any]) -> str:
    """A short, video-friendly Markdown summary generated from the same data."""
    lines = [
        "# 图定位 vs 全局最低分基线：同 store 反证",
        "",
        "- 判定：**%s**" % record["verdict"],
        "- 答案数：%d；阈值：%s" % (record["graph"]["answers"], record["threshold"]),
        "- 基线（对每个答案都一样）：`%s`" % record["baseline"]["pick"],
        "",
        "| 答案 | 基线指向 | 基线命中 | 图路径指向 | 路径条数 |",
        "|---|---|---|---|---|",
    ]
    for row in record["per_answer"]:
        lines.append("| %s | %s | %s | %s | %d |" % (
            row["answer_id"], row["baseline_pick"],
            "是" if row["baseline_localizes"] else "否",
            ", ".join(row["graph_picks"]) or "（无污染路径）",
            row["graph_path_count"],
        ))
    lines += [
        "",
        "## 可证伪判据",
        "",
    ]
    for key, value in record["falsifiable_checks"].items():
        lines.append("- %s: **%s**" % (key, "PASS" if value else "FAIL"))
    lines += [
        "",
        "基线的失败不是随机的：它对每条答案都给出同一个全局最低分，",
        "因此无法识别「哪条答案被污染」；图路径在有污染的答案上返回路径，",
        "在干净答案上返回空集。这一差异由 `per_answer` 逐行给出，可现场复算。",
        "",
    ]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(prog="python -m tracelens.falsify")
    p.add_argument("--store", required=True)
    p.add_argument("--out", required=True, help="JSON report path")
    p.add_argument("--md", default=None, help="optional Markdown summary path")
    p.add_argument("--threshold", type=float, default=0.5)
    args = p.parse_args(argv)

    record = compare(args.store, args.threshold)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if args.md:
        md = Path(args.md)
        md.parent.mkdir(parents=True, exist_ok=True)
        md.write_text(report_markdown(record), encoding="utf-8")
    print(json.dumps({
        "out": str(out), "verdict": record["verdict"],
        "checks": record["falsifiable_checks"],
        "answers": record["graph"]["answers"],
        "baseline_pick": record["baseline"]["pick"],
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
