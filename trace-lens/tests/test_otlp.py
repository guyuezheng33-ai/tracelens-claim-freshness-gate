"""Contract tests for the OTLP/OTel JSON trace importer.

These assert the importer reads the *standard wire format* (AnyValue wrappers,
unix-nanosecond timestamps, SPAN_KIND_* enums, events with attributes), not a
pre-normalized shortcut. The end-to-end test proves imported traces are
queryable by the same judge that runs on the hand-written fixture.
"""

import json
import subprocess
import sys
import tempfile
from pathlib import Path

import relate
from tracelens.otlp import (
    ATTR_KIND,
    EVENT_ANSWER,
    import_and_ingest,
    import_otlp,
)
from tracelens.otlp_fixture import (
    arr,
    attr,
    b,
    bad_otlp_document,
    clean_otlp_document,
    d,
    i,
    otlp_document,
    s,
    span,
)
from tracelens.schema import GraphMapper

ROOT = Path(__file__).resolve().parent.parent
PY = sys.executable


# --- AnyValue decoding -----------------------------------------------------

def test_attr_value_decodes_all_otlp_scalar_shapes():
    from tracelens.otlp import _attr_value
    assert _attr_value(s("hello")) == "hello"
    assert _attr_value(i("42")) == 42
    assert _attr_value(d("0.12")) == 0.12
    assert _attr_value(b(True)) is True
    assert _attr_value({"bytesValue": "eA=="}) is None       # unsupported -> skip
    assert _attr_value({}) is None
    assert _attr_value("not-a-dict") is None


def test_attr_value_decodes_array_with_skipped_unknowns():
    from tracelens.otlp import _attr_value
    got = _attr_value(arr(s("a.pdf"), {"bytesValue": "x"}, s("b.pdf")))
    assert got == ["a.pdf", None, "b.pdf"]


def test_malformed_numeric_values_do_not_raise():
    from tracelens.otlp import _attr_value
    assert _attr_value({"intValue": "not-an-int"}) is None
    assert _attr_value({"doubleValue": "NaN-ish"}) is None
    assert _attr_value("") is None


def test_attributes_flat_and_skip_malformed_items():
    from tracelens.otlp import _attributes
    raw = [
        attr("good", s("v")),
        {"key": "bad", "value": {"bytesValue": "x"}},
        "not-a-dict",
        {"value": s("no-key")},
    ]
    assert _attributes({"attributes": raw}) == {"good": "v"}


# --- timestamp / duration --------------------------------------------------

def test_nanos_to_seconds_and_duration_ms():
    from tracelens.otlp import _duration_ms, _nanos_to_seconds
    assert _nanos_to_seconds("1730000000000000000") == 1_730_000_000.0
    assert _nanos_to_seconds(None) == 0.0
    assert _nanos_to_seconds("bad") == 0.0
    assert _duration_ms("1000000000", "2500000000") == 1500.0
    assert _duration_ms("3000000000", "1000000000") == 0.0   # clamp negative
    assert _duration_ms("x", "y") == 0.0


# --- kind mapping ----------------------------------------------------------

def test_kind_map_covers_all_otel_enum_kinds():
    from tracelens.otlp import KIND_MAP
    for k in ("SPAN_KIND_INTERNAL", "SPAN_KIND_SERVER", "SPAN_KIND_CLIENT",
              "SPAN_KIND_PRODUCER", "SPAN_KIND_CONSUMER"):
        assert k in KIND_MAP


def test_span_kind_override_wins_over_otel_kind():
    from tracelens.otlp import _span_kind
    raw = span("s1", "n", "SPAN_KIND_CLIENT", 0, 1)
    assert _span_kind(raw, {}) == "TOOL"
    assert _span_kind(raw, {ATTR_KIND: "retriever"}) == "RETRIEVER"


def test_unknown_otel_kind_defaults_to_chain():
    from tracelens.otlp import _span_kind
    assert _span_kind({"kind": "SPAN_KIND_FUTURE"}, {}) == "CHAIN"


# --- span normalization ----------------------------------------------------

def test_normalize_span_maps_parent_tokens_cost_and_status():
    raw = span(
        "s1", "llm.call", "SPAN_KIND_INTERNAL", 1_000_000_000, 1_250_000_000,
        parent="root",
        attributes=[
            attr("gen_ai.usage.input_tokens", i("900")),
            attr("gen_ai.usage.output_tokens", i("120")),
            attr("tracelens.cost", d("0.07")),
        ],
        status="STATUS_CODE_ERROR",
    )
    out = import_otlp(otlp_document([raw]), run_id="r")["spans"][0]
    assert out["span_id"] == "s1" and out["parent_span_id"] == "root"
    assert out["duration_ms"] == 250.0
    assert out["input_tokens"] == 900 and out["output_tokens"] == 120
    assert out["cost"] == 0.07 and out["status"] == "STATUS_CODE_ERROR"
    assert out["name"] == "llm.call"


def test_bad_fixture_spans_have_retrieval_and_tools():
    run = import_otlp(bad_otlp_document())
    retrievers = [s for s in run["spans"] if s["kind"] == "RETRIEVER"]
    assert len(retrievers) == 2
    for r in retrievers:
        assert r["retrieved_from"][0]["doc_id"] == "obsolete-handbook-2020.pdf"
        assert r["tool_calls"] and r["tool_calls"][0]["tool_name"] in ("vector_search", "keyword_search")
    noise = next(s for s in run["spans"] if s["kind"] == "MONITOR")
    assert noise["retrieved_from"][0]["doc_id"] == "session-cache.tmp"


def test_attribute_fallback_retrieval_when_no_event():
    raw = span("ret", "r", "SPAN_KIND_CLIENT", 0, 1, attributes=[
        attr(ATTR_KIND, s("RETRIEVER")),
        attr("tracelens.doc_id", s("fallback.pdf")),
        attr("tracelens.score", d("0.3")),
        attr("tracelens.rank", i("2")),
    ])
    out = import_otlp(otlp_document([raw]), run_id="r")["spans"][0]
    assert out["retrieved_from"] == [{
        "doc_id": "fallback.pdf", "uri": "", "snippet_hash": "",
        "score": 0.3, "rank": 2,
    }]


def test_tool_fallback_on_tool_kind():
    raw = span("tc", "search", "SPAN_KIND_CLIENT", 0, 1, attributes=[
        attr("tracelens.tool_name", s("http_get")),
        attr("tracelens.tool_ok", b(False)),
    ])
    out = import_otlp(otlp_document([raw]), run_id="r")["spans"][0]
    assert out["tool_calls"][0]["tool_name"] == "http_get"
    assert out["tool_calls"][0]["ok"] is False


def test_malformed_events_are_skipped():
    raw = span("s", "n", "SPAN_KIND_INTERNAL", 0, 1)
    raw["events"] = ["bad", {"no_name": 1}, {"name": EVENT_ANSWER}]
    out = import_otlp(otlp_document([raw]), run_id="r")["spans"][0]
    assert out["retrieved_from"] == [] and out["tool_calls"] == []


# --- answers / claims ------------------------------------------------------

def test_answer_and_claims_built_from_events():
    run = import_otlp(bad_otlp_document())
    assert len(run["answers"]) == 1
    ans = run["answers"][0]
    assert ans["answer_id"] == "otlp-ans-bad"
    assert ans["produced_by_span_id"] == "otlp-root-bad"
    assert ans["text_hash"] == "h-answer-bad"
    claims = {c["claim_id"]: c for c in ans["claims"]}
    assert claims["otlp-claim-ok-bad"]["supported_by_docs"] == ["obsolete-handbook-2020.pdf"]
    assert claims["otlp-claim-bad-bad"]["supported_by_docs"] == []


def test_claim_event_without_answer_id_is_ignored():
    from tracelens.otlp_fixture import claim_event
    raw = span("s", "n", "SPAN_KIND_INTERNAL", 0, 1, events=[
        claim_event("", "c1", "orphan", [])
    ])
    run = import_otlp(otlp_document([raw]), run_id="r")
    assert run["answers"] == []


# --- run-level -------------------------------------------------------------

def test_run_id_from_resource_attribute_and_override():
    doc = bad_otlp_document()
    assert import_otlp(doc)["run_id"] == "otlp-run-bad"
    assert import_otlp(doc, run_id="explicit")["run_id"] == "explicit"


def test_run_id_falls_back_to_trace_id():
    raw = span("s", "n", "SPAN_KIND_INTERNAL", 0, 1)
    doc = otlp_document([raw], run_id=None)
    run = import_otlp(doc)
    assert run["run_id"].startswith("trace:")


def test_root_spans_default_to_parentless_spans():
    run = import_otlp(bad_otlp_document())
    assert run["root_spans"] == ["otlp-root-bad"]


def test_model_outcome_and_json_round_trip():
    run = import_otlp(bad_otlp_document())
    assert run["model"] == "demo-model"
    assert json.loads(json.dumps(run, ensure_ascii=False)) == run


def test_rejects_non_object_document():
    try:
        import_otlp([1, 2, 3])
    except ValueError:
        pass
    else:
        raise AssertionError("importer accepted a non-object document")


def test_empty_document_yields_empty_run():
    run = import_otlp({"resourceSpans": []}, run_id="empty")
    assert run["spans"] == [] and run["answers"] == [] and run["root_spans"] == []


# --- ingestion (graph side) ------------------------------------------------

def test_import_and_ingest_is_idempotent():
    with tempfile.TemporaryDirectory() as d:
        store = str(Path(d) / "idem.rl")
        db = relate.Database(store, read_only=False)
        mapper = GraphMapper(db)
        import_and_ingest(bad_otlp_document(), mapper)
        db.flush()
        n1, e1 = db.node_count(), db.relationship_count()
        import_and_ingest(bad_otlp_document(), mapper)   # same trace again
        db.flush()
        n2, e2 = db.node_count(), db.relationship_count()
        db.close()
    assert (n2, e2) == (n1, e1), (n1, e1, n2, e2)


def test_imported_graph_has_walkable_q1_path():
    from tracelens.judge import judge
    with tempfile.TemporaryDirectory() as d:
        store = Path(d) / "walk.rl"
        db = relate.Database(str(store), read_only=False)
        mapper = GraphMapper(db)
        import_and_ingest(bad_otlp_document(), mapper)
        import_and_ingest(clean_otlp_document(), mapper)
        db.flush()
        db.close()
        verdict = judge(store)
    assert verdict["verdict"] == "PASS", verdict
    assert verdict["checks"]["graph_localizes_true_cause"] is True
    assert verdict["checks"]["graph_zero_false_positive_on_clean"] is True
    assert verdict["convergence_causes"] == ["obsolete-handbook-2020.pdf"]


# --- CLI end-to-end --------------------------------------------------------

def test_cli_import_multiple_otlp_files_then_judge_passes():
    """Generate OTLP documents into a temp dir; keep product fixtures frozen."""
    with tempfile.TemporaryDirectory() as d:
        out = Path(d) / "from-otlp.rl"
        bad_path = Path(d) / "otlp-bad.json"
        clean_path = Path(d) / "otlp-clean.json"
        bad_path.write_text(json.dumps(bad_otlp_document(), ensure_ascii=False), encoding="utf-8")
        clean_path.write_text(json.dumps(clean_otlp_document(), ensure_ascii=False), encoding="utf-8")
        env = dict(__import__("os").environ)
        env["PYTHONPATH"] = str(ROOT)
        r = subprocess.run(
            [PY, "-m", "tracelens.cli", "import", "--fresh",
             "--input", str(bad_path), str(clean_path),
             "--store", str(out)],
            cwd=str(ROOT), env=env, capture_output=True, text=True, check=False,
        )
        assert r.returncode == 0, r.stderr
        summary = json.loads(r.stdout)       # logging must not pollute stdout
        assert len(summary["runs"]) == 2
        assert summary["nodes"] > 0 and summary["relationships"] > 0

        j = subprocess.run(
            [PY, "-m", "tracelens.cli", "judge", "--store", str(out)],
            cwd=str(ROOT), env=env, capture_output=True, text=True, check=False,
        )
        assert j.returncode == 0, j.stderr
        verdict = json.loads(j.stdout)
        assert verdict["verdict"] == "PASS", verdict
