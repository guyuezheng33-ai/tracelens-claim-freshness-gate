"""Agent self-check loop through the read-only MCP tool surface.

The loop is deliberately simple and auditable, because the point is not the
agent's cleverness -- it is that a real agent *consumes* the graph diagnosis
and changes its behaviour. Sequence:

  1. an agent answers a question from a real trace (pre-check answer),
  2. it calls the TraceLens MCP tools through the same JSON-RPC surface an
     external agent uses (not by importing judge directly),
  3. it applies a fix rule: drop claims whose evidence trace ends at a
     low-score source that converges from more than one retrieval branch,
  4. it emits the before/after answers plus the tool calls that caused it.

Every tool call is logged through auditlog. The output is a JSON record with
``answer_before`` / ``answer_after`` / ``tool_calls`` so the loop is falsifiable.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .auditlog import log_event
from .mcpserver import Session, handle
from .realtrace import sha256_file

ROOT = Path(__file__).resolve().parent.parent


def rpc_call(session: Session, method: str, params: dict, rid: int) -> dict:
    """Invoke the MCP surface exactly as a stdio client would."""
    msg = {"jsonrpc": "2.0", "id": rid, "method": method, "params": params}
    reply = handle(msg, session)
    if reply is None or "result" not in reply:
        raise RuntimeError("MCP call failed: %s" % reply)
    return reply["result"]


def list_tools(session: Session) -> list[str]:
    result = rpc_call(session, "tools/list", {}, 1)
    return [t["name"] for t in result["tools"]]


def _content_text(result: dict) -> str:
    parts = result.get("content") or []
    return "".join(p.get("text", "") for p in parts if p.get("type") == "text")


def diagnose(session: Session) -> dict:
    """Run the tools an agent needs: graph info, verdict, and Q3 claim forensics.

    Q3 is the graph-native answer to 'which of my claims have no evidence
    path?'. Its claim ids are what the agent acts on -- a score threshold alone
    would not prove the agent consumed the graph diagnosis.
    """
    tools = list_tools(session)
    calls: list[dict] = []
    info = json.loads(_content_text(rpc_call(
        session, "tools/call",
        {"name": "tracelens_graph_info", "arguments": {}}, 2,
    )))
    calls.append({"tool": "tracelens_graph_info", "result": info})
    verdict = json.loads(_content_text(rpc_call(
        session, "tools/call",
        {"name": "tracelens_judge", "arguments": {}}, 3,
    )))
    calls.append({"tool": "tracelens_judge", "result": verdict["verdict"],
                  "checks": verdict["checks"]})
    q3 = json.loads(_content_text(rpc_call(
        session, "tools/call",
        {"name": "tracelens_query_pack",
         "arguments": {"pack": "Q3"}}, 4,
    )))
    calls.append({"tool": "tracelens_query_pack", "pack": "Q3", "rows": len(q3),
                  "claim_ids": [r.get("claim_id") for r in q3 if r.get("claim_id")]})
    return {"tools_available": tools, "info": info, "verdict": verdict,
            "q3_unsupported_claims": q3, "tool_calls": calls}


def apply_self_check(answer_before: list[dict], verdict: dict, threshold: float = 0.5,
                     q3_claims: list[dict] | None = None) -> dict:
    """Fix rule driven by graph evidence, not by a local score heuristic.

    A claim is dropped only when the GRAPH says so: either Q3 returned it as
    having no SUPPORTED_BY evidence path, or the judge's structure-derived
    convergence set names its source. Score is never the deciding factor.
    """
    bad = set(verdict.get("convergence_causes") or [])
    unsupported = {r.get("claim_id") for r in (q3_claims or []) if r.get("claim_id")}
    kept: list[dict] = []
    dropped: list[dict] = []
    reasons: dict[str, str] = {}
    for claim in answer_before:
        cid = claim.get("claim_id", "")
        source = claim.get("source", "")
        why = ""
        if cid in unsupported:
            why = "Q3: no SUPPORTED_BY evidence path"
        elif source in bad:
            why = "Q2 convergence cause: %s" % source
        if why:
            dropped.append(claim)
            reasons[cid] = why
        else:
            kept.append(claim)
    return {
        "kept": kept,
        "dropped": dropped,
        "drop_reasons": reasons,
        "rule": "drop claims the graph flags (Q3 unsupported path or Q2 convergence source)",
        "bad_sources_from_graph": sorted(bad),
        "unsupported_claims_from_q3": sorted(unsupported),
    }


def run_loop(store: str | Path, answer_before: list[dict], trace_file: str | Path | None = None,
             threshold: float = 0.5) -> dict:
    session = Session(store)
    diag = diagnose(session)
    fix = apply_self_check(answer_before, diag["verdict"], threshold,
                           diag["q3_unsupported_claims"])
    record = {
        "schema": "tracelens/agent-self-check@1",
        "store": str(store),
        "trace_sha256": sha256_file(trace_file) if trace_file else None,
        "answer_before": answer_before,
        "answer_after": fix["kept"],
        "claims_dropped": fix["dropped"],
        "drop_reasons": fix["drop_reasons"],
        "fix_rule": fix["rule"],
        "bad_sources_from_graph": fix["bad_sources_from_graph"],
        "unsupported_claims_from_q3": fix["unsupported_claims_from_q3"],
        "verdict": diag["verdict"]["verdict"],
        "checks": diag["verdict"]["checks"],
        "tool_calls": diag["tool_calls"],
        "tools_available": diag["tools_available"],
        "graph": diag["info"],
    }
    log_event("agent_loop", verdict=record["verdict"],
              dropped=len(record["claims_dropped"]),
              tool_calls=len(record["tool_calls"]))
    return record


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(prog="python -m tracelens.agentloop")
    p.add_argument("--store", required=True)
    p.add_argument("--answer-before", required=True, help="JSON file: [{claim_id, source, score, text}]")
    p.add_argument("--trace", default=None, help="optional real trace file for the hash")
    p.add_argument("--out", required=True)
    p.add_argument("--threshold", type=float, default=0.5)
    args = p.parse_args(argv)
    before = json.loads(Path(args.answer_before).read_text(encoding="utf-8"))
    record = run_loop(args.store, before, args.trace, args.threshold)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "out": str(out),
        "verdict": record["verdict"],
        "claims_before": len(record["answer_before"]),
        "claims_after": len(record["answer_after"]),
        "dropped": len(record["claims_dropped"]),
        "tool_calls": len(record["tool_calls"]),
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
