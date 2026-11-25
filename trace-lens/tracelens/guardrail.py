"""Runtime guardrail: the graph decides, a real model explains.

Design constraint that makes this more than a demo: the allow/deny decision is
made exclusively by graph evidence (Q3 unsupported claims and Q2 convergence
causes). The model is called on every decision to produce a grounded
explanation, but it cannot release a claim the graph rejected. This is the
"graph as constrained truth for agents" pattern: a model participates in the
run, while the truth source is queryable and falsifiable.

Every model call carries a receipt with hashes, latency and token usage. If the
endpoint is unavailable the command fails loudly; there is no mock fallback.
"""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .agentloop import apply_self_check, diagnose
from .auditlog import log_event
from .llmclient import chat, explanation_prompt
from .mcpserver import Session
from .realtrace import sha256_file


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()


def run_guardrail(store: str | Path, answer_before: list[dict[str, Any]],
                  trace_file: str | Path | None = None, threshold: float = 0.5,
                  call_model: bool = True) -> dict[str, Any]:
    """Apply graph-only admission control, then ask a real model to explain it."""
    session = Session(store)
    diag = diagnose(session)
    fix = apply_self_check(
        answer_before, diag["verdict"], threshold, diag["q3_unsupported_claims"]
    )
    reasons = fix["drop_reasons"]
    q3_rows = diag["q3_unsupported_claims"]

    decisions: list[dict[str, Any]] = []
    llm_calls: list[dict[str, Any]] = []
    for claim in answer_before:
        cid = claim.get("claim_id", "")
        graph_reason = reasons.get(cid)
        admitted = graph_reason is None
        # Ground the explanation in the actual Q3 rows for this claim, plus the
        # convergence cause set when relevant.
        evidence = [r for r in q3_rows if r.get("claim_id") == cid]
        if not evidence and fix["bad_sources_from_graph"]:
            evidence = [{"source": s, "from": "Q2 convergence cause"}
                        for s in fix["bad_sources_from_graph"]]
        decision_reason = graph_reason or "no graph flag: Q3 returned no unsupported path and source is not a Q2 convergence cause"
        entry: dict[str, Any] = {
            "claim_id": cid,
            "text": claim.get("text"),
            "source": claim.get("source"),
            "score": claim.get("score"),
            "admitted": admitted,
            "decision_source": "graph",
            "graph_reason": decision_reason,
            "graph_evidence": evidence,
        }
        if call_model:
            result = chat(explanation_prompt(claim, decision_reason, evidence))
            entry["model_explanation"] = result["content"]
            llm_calls.append({
                "claim_id": cid,
                "admitted": admitted,
                "receipt": result["receipt"],
            })
        decisions.append(entry)

    after = [claim for claim, entry in zip(answer_before, decisions) if entry["admitted"]]
    record = {
        "schema": "tracelens/runtime-guardrail@1",
        "created_at_utc": _utc_now(),
        "store": str(store),
        "trace_sha256": sha256_file(trace_file) if trace_file else None,
        "decision_source": "graph only (Q3 unsupported path / Q2 convergence cause)",
        "explanation_source": "real model via OpenAI-compatible HTTP" if call_model else "disabled",
        "model_cannot_release_rejected_claim": True,
        "answer_before": answer_before,
        "answer_after": after,
        "decisions": decisions,
        "llm_calls": llm_calls,
        "tool_calls": diag["tool_calls"],
        "verdict": diag["verdict"]["verdict"],
        "checks": diag["verdict"]["checks"],
        "graph": diag["info"],
        "passport": {
            "nature": "real-model-call" if call_model else "graph-only",
            "model": llm_calls[0]["receipt"]["model_returned"] if llm_calls else None,
            "endpoint": llm_calls[0]["receipt"]["endpoint"] if llm_calls else None,
            "model_calls": len(llm_calls),
            "model_evidence": "receipts contain request/response sha256, latency and usage",
            "caveat": (
                "Graph evidence decides admission; the model only explains. "
                "Public inference endpoint, no paid customer, no private API key."
            ),
        },
    }
    log_event("guardrail", verdict=record["verdict"],
              before=len(answer_before), after=len(after),
              llm_calls=len(llm_calls))
    return record


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(prog="python -m tracelens.guardrail")
    p.add_argument("--store", required=True)
    p.add_argument("--answer-before", required=True)
    p.add_argument("--trace", default=None)
    p.add_argument("--out", required=True)
    p.add_argument("--threshold", type=float, default=0.5)
    p.add_argument("--no-model", action="store_true",
                   help="graph-only mode: skip the real model call")
    args = p.parse_args(argv)

    before = json.loads(Path(args.answer_before).read_text(encoding="utf-8"))
    record = run_guardrail(args.store, before, args.trace, args.threshold,
                           call_model=not args.no_model)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "out": str(out),
        "verdict": record["verdict"],
        "before": len(record["answer_before"]),
        "after": len(record["answer_after"]),
        "decision_source": record["decision_source"],
        "model_calls": len(record["llm_calls"]),
        "model": record["passport"]["model"],
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
