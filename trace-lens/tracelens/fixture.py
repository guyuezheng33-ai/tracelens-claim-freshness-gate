"""Deterministic demo-trace generator.

No external data, no API key, no LLM. The trace tells one concrete story that a
judge can verify in under a minute:

  RUN bad-answer: an Agent answers a compliance question. Two retrievers pull a
  stale low-score document (score 0.12) from two different tools; an LLM span on
  a *sibling* branch produces the final Answer from root. G1 Q1 walks the full
  path Answer <- root -[:PARENT_OF*]-> retriever -[:RETRIEVED_FROM]-> Source.
  Q2 finds the *same* low-score Source converged from two retrievers (a real
  graph motif that a table GROUP BY cannot express as a path). One Claim has no
  SUPPORTED_BY edge; Q3 finds it by path anti-join. Q4 attributes cost to the
  expensive LLM subtree.

  RUN clean-answer: a control run with a high-score source and all claims
  supported, so the queries are proven to discriminate (not always-true).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def build_fixture() -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "story": "低分过期文档经两个检索分支污染最终答案；对照 run 无此问题",
        "runs": [
            {
                "run_id": "bad-answer",
                "model": "demo-agent-v3",
                "outcome": "wrong",
                "root_spans": ["ba-root"],
                "spans": [
                    {
                        "span_id": "ba-root", "parent_span_id": None,
                        "kind": "AGENT", "name": "compliance-answer",
                        "start": 0.0, "end": 2.40, "duration_ms": 2400,
                        "input_tokens": 120, "output_tokens": 40,
                        "cost": 0.002,
                    },
                    {
                        "span_id": "ba-ret-1", "parent_span_id": "ba-root",
                        "kind": "RETRIEVER", "name": "vector-search",
                        "start": 0.10, "end": 0.55, "duration_ms": 450,
                        "input_tokens": 30, "output_tokens": 0,
                        "cost": 0.0001,
                        "tool_calls": [
                            {"call_id": "ba-c1", "tool_name": "vector_search",
                             "arguments_hash": "h-vec", "ok": True}
                        ],
                        "retrieved_from": [
                            {"doc_id": "stale-policy-v2.pdf",
                             "uri": "fixtures://stale-policy-v2.pdf",
                             "snippet_hash": "h-stale", "score": 0.12, "rank": 1}
                        ],
                    },
                    {
                        "span_id": "ba-ret-2", "parent_span_id": "ba-root",
                        "kind": "RETRIEVER", "name": "keyword-search",
                        "start": 0.20, "end": 0.70, "duration_ms": 500,
                        "input_tokens": 28, "output_tokens": 0,
                        "cost": 0.0001,
                        "tool_calls": [
                            {"call_id": "ba-c2", "tool_name": "keyword_search",
                             "arguments_hash": "h-kw", "ok": True}
                        ],
                        "retrieved_from": [
                            {"doc_id": "stale-policy-v2.pdf",
                             "uri": "fixtures://stale-policy-v2.pdf",
                             "snippet_hash": "h-stale", "score": 0.12, "rank": 2}
                        ],
                    },
                    {
                        "span_id": "ba-noise", "parent_span_id": "ba-root",
                        "kind": "MONITOR", "name": "telemetry-cache-flush",
                        "start": 0.30, "end": 0.45, "duration_ms": 150,
                        "input_tokens": 0, "output_tokens": 0,
                        "cost": 0.0,
                        "retrieved_from": [
                            {"doc_id": "cache-tmp.bin",
                             "uri": "fixtures://cache-tmp.bin",
                             "snippet_hash": "h-cache", "score": 0.03, "rank": 1}
                        ],
                    },
                    {
                        "span_id": "ba-llm", "parent_span_id": "ba-root",
                        "kind": "LLM", "name": "gpt-answer-generation",
                        "start": 0.80, "end": 2.30, "duration_ms": 1500,
                        "input_tokens": 3800, "output_tokens": 620,
                        "cost": 0.0186,
                    },
                ],
                "answers": [
                    {
                        "answer_id": "ba-ans", "produced_by_span_id": "ba-root",
                        "text_hash": "h-wrong-answer",
                        "claims": [
                            {"claim_id": "ba-claim-ok", "text": "policy v2 exists",
                             "supported_by_docs": ["stale-policy-v2.pdf"]},
                            {"claim_id": "ba-claim-bad", "text": "deadline is March 1",
                             "supported_by_docs": []},
                        ],
                    }
                ],
            },
            {
                "run_id": "clean-answer",
                "model": "demo-agent-v3",
                "outcome": "correct",
                "root_spans": ["cl-root"],
                "spans": [
                    {
                        "span_id": "cl-root", "parent_span_id": None,
                        "kind": "AGENT", "name": "compliance-answer",
                        "start": 0.0, "end": 1.50, "duration_ms": 1500,
                        "input_tokens": 100, "output_tokens": 35,
                        "cost": 0.0015,
                    },
                    {
                        "span_id": "cl-ret", "parent_span_id": "cl-root",
                        "kind": "RETRIEVER", "name": "vector-search",
                        "start": 0.08, "end": 0.40, "duration_ms": 320,
                        "input_tokens": 25, "output_tokens": 0,
                        "cost": 0.0001,
                        "tool_calls": [
                            {"call_id": "cl-c1", "tool_name": "vector_search",
                             "arguments_hash": "h-vec2", "ok": True}
                        ],
                        "retrieved_from": [
                            {"doc_id": "current-policy-v9.pdf",
                             "uri": "fixtures://current-policy-v9.pdf",
                             "snippet_hash": "h-current", "score": 0.94, "rank": 1}
                        ],
                    },
                    {
                        "span_id": "cl-llm", "parent_span_id": "cl-root",
                        "kind": "LLM", "name": "gpt-answer-generation",
                        "start": 0.50, "end": 1.45, "duration_ms": 950,
                        "input_tokens": 2100, "output_tokens": 310,
                        "cost": 0.0092,
                    },
                ],
                "answers": [
                    {
                        "answer_id": "cl-ans", "produced_by_span_id": "cl-root",
                        "text_hash": "h-correct-answer",
                        "claims": [
                            {"claim_id": "cl-claim-ok", "text": "policy v9 is current",
                             "supported_by_docs": ["current-policy-v9.pdf"]},
                        ],
                    }
                ],
            },
        ],
    }


def write_fixture(path: str | Path) -> Path:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(
        json.dumps(build_fixture(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return p


if __name__ == "__main__":
    print(write_fixture("fixtures/demo-trace.json"))
