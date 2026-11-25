"""A standards-shaped OTLP/JSON sample used by importer tests.

This is deliberately encoded the way a real OTel SDK exports spans
(AnyValue wrappers, unix-nanosecond timestamps, SPAN_KIND_* enums, events),
NOT pre-normalized. If the importer only worked on hand-crafted normalized
dicts, these tests would fail -- which is the point.
"""

from __future__ import annotations

from typing import Any


def s(value: Any) -> dict:
    """OTLP string AnyValue."""
    return {"stringValue": str(value)}


def i(value: int) -> dict:
    """OTLP int AnyValue (encoded as string in the wire format)."""
    return {"intValue": str(value)}


def d(value: float) -> dict:
    """OTLP double AnyValue."""
    return {"doubleValue": float(value)}


def b(value: bool) -> dict:
    """OTLP bool AnyValue."""
    return {"boolValue": bool(value)}


def arr(*values: dict) -> dict:
    """OTLP array AnyValue."""
    return {"arrayValue": {"values": list(values)}}


def attr(key: str, value: dict) -> dict:
    """One OTLP key/value attribute."""
    return {"key": key, "value": value}


def span(
    span_id: str,
    name: str,
    kind: str,
    start_ns: int,
    end_ns: int,
    parent: str | None = None,
    attributes: list[dict] | None = None,
    events: list[dict] | None = None,
    status: str = "STATUS_CODE_OK",
) -> dict:
    """One OTLP span with unix-nanosecond timing."""
    out: dict[str, Any] = {
        "traceId": "0af7651916cd43dd8448eb211c80319c",
        "spanId": span_id,
        "name": name,
        "kind": kind,
        "startTimeUnixNano": str(start_ns),
        "endTimeUnixNano": str(end_ns),
        "status": {"code": status},
        "attributes": attributes or [],
        "events": events or [],
    }
    if parent:
        out["parentSpanId"] = parent
    return out


def retrieval_event(doc_id: str, score: float, rank: int, uri: str = "", snippet: str = "") -> dict:
    """An OTel event carrying one retrieved source as attributes."""
    return {
        "name": "tracelens.retrieval",
        "timeUnixNano": "1730000001000000000",
        "attributes": [
            attr("tracelens.doc_id", s(doc_id)),
            attr("tracelens.uri", s(uri or "otlp://" + doc_id)),
            attr("tracelens.snippet_hash", s(snippet or ("h-" + doc_id))),
            attr("tracelens.score", d(score)),
            attr("tracelens.rank", i(rank)),
        ],
    }


def tool_event(call_id: str, tool_name: str, ok: bool = True) -> dict:
    """An OTel event carrying one tool call."""
    return {
        "name": "tracelens.tool_call",
        "timeUnixNano": "1730000002000000000",
        "attributes": [
            attr("tracelens.call_id", s(call_id)),
            attr("tracelens.tool_name", s(tool_name)),
            attr("tracelens.arguments_hash", s("h-" + call_id)),
            attr("tracelens.tool_ok", b(ok)),
        ],
    }


def claim_event(answer_id: str, claim_id: str, text: str, supported: list[str]) -> dict:
    """An OTel event carrying one answer claim."""
    return {
        "name": "tracelens.claim",
        "timeUnixNano": "1730000003000000000",
        "attributes": [
            attr("tracelens.answer_id", s(answer_id)),
            attr("tracelens.claim_id", s(claim_id)),
            attr("tracelens.claim_text", s(text)),
            attr("tracelens.supported_by_docs", arr(*[s(x) for x in supported])),
        ],
    }


def answer_event(answer_id: str, produced_by: str, text_hash: str) -> dict:
    """An OTel event declaring an answer produced by a root span."""
    return {
        "name": "tracelens.answer",
        "timeUnixNano": "1730000004000000000",
        "attributes": [
            attr("tracelens.answer_id", s(answer_id)),
            attr("tracelens.produced_by_span_id", s(produced_by)),
            attr("tracelens.answer_text_hash", s(text_hash)),
        ],
    }


def otlp_document(spans: list[dict], model: str = "demo-model", run_id: str | None = None) -> dict:
    """Wrap spans in the standard resourceSpans/scopeSpans envelope."""
    resource_attrs = [attr("service.name", s("tracelens-demo"))]
    if run_id:
        resource_attrs.append(attr("tracelens.run_id", s(run_id)))
    if model:
        resource_attrs.append(attr("gen_ai.request.model", s(model)))
    return {
        "resourceSpans": [
            {
                "resource": {"attributes": resource_attrs},
                "scopeSpans": [
                    {
                        "scope": {"name": "tracelens.otlp_fixture", "version": "1.0"},
                        "spans": spans,
                    }
                ],
            }
        ]
    }


def _base_spans(run_id: str, bad: bool) -> list[dict]:
    """Build an OTel span tree mirroring the deterministic demo fixture."""
    t0 = 1730000000_000000000
    root = "otlp-root-" + run_id
    ret1 = "otlp-ret1-" + run_id
    ret2 = "otlp-ret2-" + run_id
    noise = "otlp-noise-" + run_id
    answer_id = "otlp-ans-" + run_id
    true_doc = "obsolete-handbook-2020.pdf" if bad else "current-handbook-2026.pdf"
    noise_doc = "session-cache.tmp" if bad else "benign-notes.txt"
    spans = [
        span(root, "agent.root", "SPAN_KIND_INTERNAL", t0, t0 + 900_000_000,
             attributes=[attr("tracelens.kind", s("AGENT")),
                         attr("tracelens.cost", d(0.09 if bad else 0.04)),
                         attr("gen_ai.usage.input_tokens", i(1200)),
                         attr("gen_ai.usage.output_tokens", i(300))],
             events=[answer_event(answer_id, root, "h-answer-" + run_id),
                     claim_event(answer_id, "otlp-claim-ok-" + run_id,
                                 "handbook exists", [true_doc]),
                     claim_event(answer_id, "otlp-claim-bad-" + run_id,
                                 "deadline is May 1", [] if bad else [true_doc])]),
        span(ret1, "retrieve.vector", "SPAN_KIND_CLIENT", t0 + 100_000_000, t0 + 300_000_000,
             parent=root,
             attributes=[attr("tracelens.kind", s("RETRIEVER"))],
             events=[retrieval_event(true_doc, 0.11 if bad else 0.91, 1),
                     tool_event("otlp-c1-" + run_id, "vector_search")]),
        span(ret2, "retrieve.keyword", "SPAN_KIND_CLIENT", t0 + 320_000_000, t0 + 520_000_000,
             parent=root,
             attributes=[attr("tracelens.kind", s("RETRIEVER"))],
             events=[retrieval_event(true_doc, 0.11 if bad else 0.91, 2),
                     tool_event("otlp-c2-" + run_id, "keyword_search")]),
        span(noise, "monitor.sniff", "SPAN_KIND_INTERNAL", t0 + 540_000_000, t0 + 640_000_000,
             parent=root,
             attributes=[attr("tracelens.kind", s("MONITOR"))],
             events=[retrieval_event(noise_doc, 0.02 if bad else 0.88, 1)]),
    ]
    return spans


def bad_otlp_document() -> dict:
    """OTLP document for a run polluted by a stale, low-score source."""
    return otlp_document(_base_spans("bad", bad=True), run_id="otlp-run-bad")


def clean_otlp_document() -> dict:
    """OTLP control run with no low-score convergence signal."""
    return otlp_document(_base_spans("clean", bad=False), run_id="otlp-run-clean")
