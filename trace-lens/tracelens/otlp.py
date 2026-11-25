"""OTLP/OTel JSON trace importer.

Turns a standard OpenTelemetry OTLP/JSON export into the normalized run dict
that ``GraphMapper.ingest_run`` consumes. This is the real data entry point:
any OTel SDK that can emit ``resourceSpans[].scopeSpans[].spans[]`` can feed
TraceLens without hand-writing a fixture.

Design rules (all deterministic, no LLM, no network):
  * Span identity comes from the OTel ``spanId``; parent from ``parentSpanId``.
  * Timestamps are unix-nanosecond strings -> seconds (float), duration in ms.
  * OTel span kinds map to TraceLens kinds; retrieval/tool/answer facts are
    read from well-known attribute and event names (see ATTR_* below).
  * Unknown attributes are ignored, never guessed into a fact.
  * The output is a plain dict of primitives, so it is JSON-round-trippable
    and safe to bind into relate properties.
"""

from __future__ import annotations

from typing import Any

# --- OTel span kind -> TraceLens kind --------------------------------------
# OTel: INTERNAL / SERVER / CLIENT / PRODUCER / CONSUMER; agent frameworks add
# semantic attributes (gen_ai.*, tracelens.*) that refine the coarse kind.
KIND_MAP: dict[str, str] = {
    "SPAN_KIND_INTERNAL": "CHAIN",
    "SPAN_KIND_SERVER": "CHAIN",
    "SPAN_KIND_CLIENT": "TOOL",
    "SPAN_KIND_PRODUCER": "CHAIN",
    "SPAN_KIND_CONSUMER": "CHAIN",
}

ATTR_KIND = "tracelens.kind"           # override: AGENT/RETRIEVER/LLM/MONITOR
ATTR_RUN_ID = "tracelens.run_id"
ATTR_MODEL = "gen_ai.request.model"
ATTR_OUTCOME = "tracelens.outcome"
ATTR_ROOT_SPANS = "tracelens.root_spans"
ATTR_ANSWER_ID = "tracelens.answer_id"
ATTR_ANSWER_TEXT_HASH = "tracelens.answer_text_hash"
ATTR_PRODUCED_BY = "tracelens.produced_by_span_id"
ATTR_INPUT_TOKENS = "gen_ai.usage.input_tokens"
ATTR_OUTPUT_TOKENS = "gen_ai.usage.output_tokens"
ATTR_COST = "tracelens.cost"
ATTR_DOC_ID = "tracelens.doc_id"
ATTR_URI = "tracelens.uri"
ATTR_SNIPPET_HASH = "tracelens.snippet_hash"
ATTR_SCORE = "tracelens.score"
ATTR_RANK = "tracelens.rank"
ATTR_TOOL_NAME = "tracelens.tool_name"
ATTR_ARGUMENTS_HASH = "tracelens.arguments_hash"
ATTR_TOOL_OK = "tracelens.tool_ok"
ATTR_CLAIM_ID = "tracelens.claim_id"
ATTR_CLAIM_TEXT = "tracelens.claim_text"
ATTR_SUPPORTED_BY = "tracelens.supported_by_docs"

EVENT_RETRIEVAL = "tracelens.retrieval"
EVENT_TOOL_CALL = "tracelens.tool_call"
EVENT_ANSWER = "tracelens.answer"
EVENT_CLAIM = "tracelens.claim"

NANOS_PER_SECOND = 1_000_000_000


def _attr_value(value: Any) -> Any:
    """Unwrap an OTLP AnyValue into a Python primitive.

    OTLP encodes values as ``{"stringValue": ...}`` / ``{"intValue": "..."}``
    / ``{"doubleValue": ...}`` / ``{"boolValue": ...}`` / arrays / kvlists.
    Unknown shapes return None so they can be skipped rather than guessed.
    """
    if not isinstance(value, dict) or not value:
        return None
    if "stringValue" in value:
        return value["stringValue"]
    if "intValue" in value:
        try:
            return int(value["intValue"])
        except (TypeError, ValueError):
            return None
    if "doubleValue" in value:
        try:
            return float(value["doubleValue"])
        except (TypeError, ValueError):
            return None
    if "boolValue" in value:
        return bool(value["boolValue"])
    if "arrayValue" in value:
        items = value["arrayValue"].get("values", []) if isinstance(value["arrayValue"], dict) else []
        return [_attr_value(v) for v in items]
    return None


def _attributes(span: dict) -> dict[str, Any]:
    """Flatten a span's OTLP attribute list into a {key: primitive} dict."""
    out: dict[str, Any] = {}
    for item in span.get("attributes", []) or []:
        if not isinstance(item, dict) or "key" not in item:
            continue
        val = _attr_value(item.get("value"))
        if val is not None:
            out[item["key"]] = val
    return out


def _events(span: dict) -> list[dict]:
    """Return well-formed OTLP events (skip malformed entries)."""
    return [e for e in (span.get("events", []) or []) if isinstance(e, dict) and "name" in e]


def _event_attrs(event: dict) -> dict[str, Any]:
    """Attributes of an event use the same AnyValue encoding."""
    out: dict[str, Any] = {}
    for item in event.get("attributes", []) or []:
        if not isinstance(item, dict) or "key" not in item:
            continue
        val = _attr_value(item.get("value"))
        if val is not None:
            out[item["key"]] = val
    return out


def _nanos_to_seconds(raw: Any) -> float:
    """Convert a unix-nanosecond string/int to seconds; 0 if absent/bad."""
    if raw in (None, ""):
        return 0.0
    try:
        return int(raw) / NANOS_PER_SECOND
    except (TypeError, ValueError):
        return 0.0


def _duration_ms(start_ns: Any, end_ns: Any) -> float:
    """Compute duration in milliseconds from OTLP nanosecond timestamps."""
    try:
        return max(0.0, (int(end_ns) - int(start_ns)) / 1_000_000)
    except (TypeError, ValueError):
        return 0.0


def _as_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _as_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _as_bool(value: Any, default: bool = True) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return bool(value)
    if isinstance(value, str):
        return value.lower() in ("1", "true", "yes", "ok")
    return default


def _as_list(value: Any) -> list:
    if isinstance(value, list):
        return [v for v in value if v is not None]
    if value in (None, ""):
        return []
    return [value]


def _iter_spans(doc: dict):
    """Yield (resource, scope, span) for every span in an OTLP document."""
    for resource in doc.get("resourceSpans", []) or []:
        if not isinstance(resource, dict):
            continue
        for scope in resource.get("scopeSpans", []) or []:
            if not isinstance(scope, dict):
                continue
            for span in scope.get("spans", []) or []:
                if isinstance(span, dict) and span.get("spanId"):
                    yield resource, scope, span


def _resource_attrs(resource: dict) -> dict[str, Any]:
    """Flatten resource-level attributes (service.name, model, etc.)."""
    out: dict[str, Any] = {}
    for item in resource.get("resource", {}).get("attributes", []) or []:
        if isinstance(item, dict) and "key" in item:
            val = _attr_value(item.get("value"))
            if val is not None:
                out[item["key"]] = val
    return out


def _span_kind(span: dict, attrs: dict) -> str:
    """Resolve the TraceLens kind: explicit override, then OTel kind map."""
    override = attrs.get(ATTR_KIND)
    if isinstance(override, str) and override:
        return override.upper()
    return KIND_MAP.get(span.get("kind", ""), "CHAIN")


def _retrieved_from(span: dict, attrs: dict) -> list[dict]:
    """Collect sources from retrieval events (primary) and attributes (fallback)."""
    sources: list[dict] = []
    for event in _events(span):
        if event.get("name") != EVENT_RETRIEVAL:
            continue
        ea = _event_attrs(event)
        doc_id = ea.get(ATTR_DOC_ID)
        if not doc_id:
            continue
        sources.append({
            "doc_id": str(doc_id),
            "uri": str(ea.get(ATTR_URI, "")),
            "snippet_hash": str(ea.get(ATTR_SNIPPET_HASH, "")),
            "score": _as_float(ea.get(ATTR_SCORE), 0.0),
            "rank": _as_int(ea.get(ATTR_RANK), 0),
        })
    # Fallback: a RETRIEVER span may encode a single source in its attributes.
    if not sources and _span_kind(span, attrs) == "RETRIEVER" and attrs.get(ATTR_DOC_ID):
        sources.append({
            "doc_id": str(attrs[ATTR_DOC_ID]),
            "uri": str(attrs.get(ATTR_URI, "")),
            "snippet_hash": str(attrs.get(ATTR_SNIPPET_HASH, "")),
            "score": _as_float(attrs.get(ATTR_SCORE), 0.0),
            "rank": _as_int(attrs.get(ATTR_RANK), 0),
        })
    return sources


def _tool_calls(span: dict, attrs: dict) -> list[dict]:
    """Collect tool calls from tool_call events plus the span's own tool attrs."""
    calls: list[dict] = []
    for event in _events(span):
        if event.get("name") != EVENT_TOOL_CALL:
            continue
        ea = _event_attrs(event)
        tool_name = ea.get(ATTR_TOOL_NAME)
        if not tool_name:
            continue
        calls.append({
            "call_id": str(ea.get("tracelens.call_id", event.get("name", "tc") + ":" + str(len(calls)))),
            "tool_name": str(tool_name),
            "arguments_hash": str(ea.get(ATTR_ARGUMENTS_HASH, "")),
            "ok": _as_bool(ea.get(ATTR_TOOL_OK), True),
        })
    if not calls and _span_kind(span, attrs) == "TOOL" and attrs.get(ATTR_TOOL_NAME):
        calls.append({
            "call_id": str(attrs.get("tracelens.call_id", "tc:" + str(span.get("spanId")))),
            "tool_name": str(attrs[ATTR_TOOL_NAME]),
            "arguments_hash": str(attrs.get(ATTR_ARGUMENTS_HASH, "")),
            "ok": _as_bool(attrs.get(ATTR_TOOL_OK), True),
        })
    return calls


def _normalize_span(span: dict, attrs: dict, run_id: str) -> dict:
    """Map one OTel span into the TraceLens span dict consumed by GraphMapper."""
    return {
        "span_id": str(span.get("spanId")),
        "parent_span_id": str(span["parentSpanId"]) if span.get("parentSpanId") else None,
        "kind": _span_kind(span, attrs),
        "name": str(span.get("name", "")),
        "start": _nanos_to_seconds(span.get("startTimeUnixNano")),
        "end": _nanos_to_seconds(span.get("endTimeUnixNano")),
        "duration_ms": _duration_ms(span.get("startTimeUnixNano"), span.get("endTimeUnixNano")),
        "input_tokens": _as_int(attrs.get(ATTR_INPUT_TOKENS), 0),
        "output_tokens": _as_int(attrs.get(ATTR_OUTPUT_TOKENS), 0),
        "cost": _as_float(attrs.get(ATTR_COST), 0.0),
        "status": str((span.get("status") or {}).get("code", "ok")),
        "tool_calls": _tool_calls(span, attrs),
        "retrieved_from": _retrieved_from(span, attrs),
    }


def _answers_from(
    events_by_id: dict[str, list[dict]],
    attrs_by_id: dict[str, dict],
) -> list[dict]:
    """Build Answer/Claim nodes from raw OTLP events and span attributes.

    ``events_by_id`` holds the original OTel events (which ``_normalize_span``
    intentionally drops from the normalized span dict), so answer and claim
    declarations are read here from the source of truth.
    """
    answers: dict[str, dict] = {}
    for sid, events in events_by_id.items():
        a = attrs_by_id.get(sid, {})
        answer_id = a.get(ATTR_ANSWER_ID)
        produced_by = a.get(ATTR_PRODUCED_BY, sid)
        if answer_id:
            answers[str(answer_id)] = {
                "answer_id": str(answer_id),
                "produced_by_span_id": str(produced_by),
                "text_hash": str(a.get(ATTR_ANSWER_TEXT_HASH, "")),
                "claims": [],
            }
        for event in events:
            ea = _event_attrs(event)
            if event.get("name") == EVENT_ANSWER and ea.get(ATTR_ANSWER_ID):
                aid = str(ea[ATTR_ANSWER_ID])
                answers.setdefault(aid, {
                    "answer_id": aid,
                    "produced_by_span_id": str(ea.get(ATTR_PRODUCED_BY, sid)),
                    "text_hash": str(ea.get(ATTR_ANSWER_TEXT_HASH, "")),
                    "claims": [],
                })
            elif event.get("name") == EVENT_CLAIM and ea.get(ATTR_CLAIM_ID):
                aid = str(ea.get(ATTR_ANSWER_ID, answer_id or ""))
                if not aid:
                    continue
                ans = answers.setdefault(aid, {
                    "answer_id": aid,
                    "produced_by_span_id": str(ea.get(ATTR_PRODUCED_BY, sid)),
                    "text_hash": "",
                    "claims": [],
                })
                ans["claims"].append({
                    "claim_id": str(ea[ATTR_CLAIM_ID]),
                    "text": str(ea.get(ATTR_CLAIM_TEXT, "")),
                    "supported_by_docs": [str(d) for d in _as_list(ea.get(ATTR_SUPPORTED_BY))],
                })
    return list(answers.values())


def import_otlp(doc: dict, run_id: str | None = None) -> dict:
    """Convert one OTLP/JSON document into a normalized TraceLens run dict.

    ``run_id`` may be supplied by the caller; otherwise it is read from a
    resource/span attribute ``tracelens.run_id`` or the first traceId.
    """
    if not isinstance(doc, dict):
        raise ValueError("OTLP document must be a JSON object")  # noqa: TRY004 - callers assert this exact type
    spans: list[dict] = []
    attrs_by_id: dict[str, dict] = {}
    events_by_id: dict[str, list[dict]] = {}
    trace_ids: list[str] = []
    resource_model = ""
    for _resource, _scope, raw in _iter_spans(doc):
        attrs = _attributes(raw)
        sid = str(raw["spanId"])
        attrs_by_id[sid] = attrs
        events_by_id[sid] = _events(raw)
        spans.append(_normalize_span(raw, attrs, run_id or ""))
        if raw.get("traceId"):
            trace_ids.append(str(raw["traceId"]))
        if not resource_model:
            resource_model = str(attrs.get(ATTR_MODEL, ""))
        ra = _resource_attrs(_resource)
        if not resource_model and ra.get(ATTR_MODEL):
            resource_model = str(ra[ATTR_MODEL])

    resolved_run = run_id or _guess_run_id(doc, attrs_by_id, trace_ids)
    roots = [s["span_id"] for s in spans if s["parent_span_id"] is None]
    explicit_roots: list[str] = []
    for sid, a in attrs_by_id.items():
        explicit_roots.extend(str(x) for x in _as_list(a.get(ATTR_ROOT_SPANS)))
    if explicit_roots:
        roots = list(dict.fromkeys(explicit_roots))

    outcome = ""
    for a in attrs_by_id.values():
        if a.get(ATTR_OUTCOME):
            outcome = str(a[ATTR_OUTCOME])
            break

    return {
        "run_id": resolved_run,
        "model": resource_model,
        "outcome": outcome,
        "root_spans": roots,
        "spans": spans,
        "answers": _answers_from(events_by_id, attrs_by_id),
    }


def _guess_run_id(doc: dict, attrs_by_id: dict[str, dict], trace_ids: list[str]) -> str:
    """Derive a stable run id from attributes or the trace id (never random)."""
    for a in attrs_by_id.values():
        if a.get(ATTR_RUN_ID):
            return str(a[ATTR_RUN_ID])
    for resource in doc.get("resourceSpans", []) or []:
        if not isinstance(resource, dict):
            continue
        ra = _resource_attrs(resource)
        if ra.get(ATTR_RUN_ID):
            return str(ra[ATTR_RUN_ID])
    return "trace:" + trace_ids[0] if trace_ids else "trace:unknown"


def import_and_ingest(doc: dict, mapper: Any, run_id: str | None = None) -> dict:
    """Import an OTLP document and ingest it through an explicit mapper.

    Returns the normalized run dict so callers can verify what was written.
    Ingestion is idempotent (GraphMapper MERGEs by node_id), so re-importing
    the same trace cannot duplicate nodes or edges.
    """
    run = import_otlp(doc, run_id=run_id)
    mapper.ingest_run(run)
    return run
