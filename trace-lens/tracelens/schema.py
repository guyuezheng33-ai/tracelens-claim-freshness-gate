"""TraceLens data model and idempotent OTLP-span -> property-graph mapper.

Design corrections vs. the v1 proposal (all verified against relate-db 1.2.0):
  1. Every node carries a uniform ``node_id`` property. Path projections use
     ``coalesce(n.node_id, n.span_id, n.answer_id, n.source_id)`` so no element
     is ever null (G1 hard requirement).
  2. RETRIEVED_FROM starts at the retriever *Span* (kind=RETRIEVER), not at a
     separate ``Retrieval`` node. The v1 proposal declared ``Retrieval -> Source``
     in section 3.2 but queried ``(r:Span)-[:RETRIEVED_FROM]->`` in Q1: that
     contradiction made Q1 structurally empty. One label, one edge.
  3. PRODUCED starts at the root Agent span, so ``Answer <- root -[:PARENT_OF*]->
     retriever -[:RETRIEVED_FROM]-> Source`` is a real walkable path. v1 hung
     Answer on the leaf LLM span, which has no child retriever, breaking the
     flagship path query.

Cypher is emitted with named parameters only ($id style). No string splicing.
"""

from __future__ import annotations

from typing import Any

# ---------------------------------------------------------------------------
# Node properties that every node must carry.
# ---------------------------------------------------------------------------
UNIQUE_ID = "node_id"

MERGE_NODE = "MERGE (n:{label} {{{key}: $id}}) SET n += $props RETURN n.{key} AS id"

MERGE_EDGE = (
    "MATCH (a:{a_label} {{{key}: $a_id}}), (b:{b_label} {{{key}: $b_id}}) "
    "MERGE (a)-[e:{rel}]->(b) SET e += $props RETURN type(e) AS rel"
)


class GraphMapper:
    """Idempotent writer. One instance owns one writer connection."""

    def __init__(self, db: Any) -> None:
        self.db = db

    def upsert_node(self, label: str, node_id: str, **props: Any) -> None:
        props[UNIQUE_ID] = node_id
        self.db.execute(
            MERGE_NODE.format(label=label, key=UNIQUE_ID),
            {"id": node_id, "props": _flatten(props)},
        )

    def upsert_edge(
        self,
        a_label: str,
        a_id: str,
        rel: str,
        b_label: str,
        b_id: str,
        **props: Any,
    ) -> None:
        self.db.execute(
            MERGE_EDGE.format(
                a_label=a_label, b_label=b_label, key=UNIQUE_ID, rel=rel
            ),
            {"a_id": a_id, "b_id": b_id, "props": _flatten(props)},
        )

    # -- higher-level mapping -------------------------------------------------
    def ingest_run(self, run: dict[str, Any]) -> None:
        """Ingest one normalized run dict (see fixtures/demo-trace.json)."""
        run_id = run["run_id"]
        self.upsert_node(
            "Run",
            f"run:{run_id}",
            run_id=run_id,
            model=run.get("model", ""),
            outcome=run.get("outcome", ""),
        )
        spans: dict[str, dict[str, Any]] = {}
        for s in run["spans"]:
            sid = s["span_id"]
            spans[sid] = s
            self.upsert_node(
                "Span",
                f"span:{sid}",
                span_id=sid,
                run_id=run_id,
                kind=s.get("kind", "CHAIN"),
                name=s.get("name", ""),
                start=float(s.get("start", 0.0)),
                end=float(s.get("end", 0.0)),
                duration_ms=float(s.get("duration_ms", 0.0)),
                input_tokens=int(s.get("input_tokens", 0)),
                output_tokens=int(s.get("output_tokens", 0)),
                cost=float(s.get("cost", 0.0)),
                status=s.get("status", "ok"),
            )
            if s.get("parent_span_id"):
                self.upsert_edge(
                    "Span",
                    f"span:{s['parent_span_id']}",
                    "PARENT_OF",
                    "Span",
                    f"span:{sid}",
                )
            for tc in s.get("tool_calls", []):
                cid = tc["call_id"]
                self.upsert_node(
                    "ToolCall",
                    f"tc:{cid}",
                    call_id=cid,
                    tool_name=tc.get("tool_name", ""),
                    arguments_hash=tc.get("arguments_hash", ""),
                    ok=bool(tc.get("ok", True)),
                )
                self.upsert_edge(
                    "Span", f"span:{sid}", "CALLED", "ToolCall", f"tc:{cid}"
                )
            for src in s.get("retrieved_from", []):
                doc = src["doc_id"]
                sid_src = f"src:{run_id}:{doc}"
                self.upsert_node(
                    "Source",
                    sid_src,
                    source_id=sid_src,
                    doc_id=doc,
                    uri=src.get("uri", ""),
                    snippet_hash=src.get("snippet_hash", ""),
                    score=float(src.get("score", 0.0)),
                )
                self.upsert_edge(
                    "Span", f"span:{sid}", "RETRIEVED_FROM", "Source", sid_src,
                    score=float(src.get("score", 0.0)),
                    rank=int(src.get("rank", 0)),
                )

        # PRODUCED: root Agent span -> Answer (NOT leaf LLM span).
        for ans in run.get("answers", []):
            aid = ans["answer_id"]
            root_sid = ans["produced_by_span_id"]
            self.upsert_node(
                "Answer",
                f"ans:{aid}",
                answer_id=aid,
                text_hash=ans.get("text_hash", ""),
                run_id=run_id,
            )
            self.upsert_edge(
                "Span", f"span:{root_sid}", "PRODUCED", "Answer", f"ans:{aid}"
            )
            for claim in ans.get("claims", []):
                cid = claim["claim_id"]
                self.upsert_node(
                    "Claim",
                    f"claim:{cid}",
                    claim_id=cid,
                    text=claim.get("text", ""),
                    run_id=run_id,
                )
                self.upsert_edge(
                    "Claim", f"claim:{cid}", "ASSERTED_IN", "Answer", f"ans:{aid}"
                )
                for doc in claim.get("supported_by_docs", []):
                    self.upsert_edge(
                        "Claim",
                        f"claim:{cid}",
                        "SUPPORTED_BY",
                        "Source",
                        f"src:{run_id}:{doc}",
                    )

        for root_sid in run.get("root_spans", []):
            self.upsert_edge(
                "Run", f"run:{run_id}", "CONTAINS", "Span", f"span:{root_sid}"
            )


def _flatten(props: dict[str, Any]) -> dict[str, Any]:
    """relate-db cannot bind bool/list into properties; coerce to primitives."""
    out: dict[str, Any] = {}
    for k, v in props.items():
        if isinstance(v, bool):
            out[k] = int(v)
        elif isinstance(v, (list, dict)):
            out[k] = str(v)
        else:
            out[k] = v
    return out
