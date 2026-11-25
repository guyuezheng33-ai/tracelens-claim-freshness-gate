"""Tests for real-trace intake, read-only MCP tools and the agent self-check loop.

These tests never pretend a synthetic file is real. They check that the
pipeline (a) rejects traces without real structure, (b) refuses write Cypher,
and (c) produces a falsifiable before/after record when an agent consumes the
diagnosis.
"""

from __future__ import annotations

import json

import pytest
import relate
from tracelens.agentloop import apply_self_check, run_loop
from tracelens.mcpserver import Session, handle, is_readonly
from tracelens.realagent import run as run_real
from tracelens.realtrace import inspect, sha256_file, verify_passport, write_passport
from tracelens.schema import GraphMapper


# --------------------------------------------------------------------------
# R4: read-only MCP interface
# --------------------------------------------------------------------------
def test_readonly_gate_accepts_reads_rejects_writes():
    ok, _ = is_readonly("MATCH (n:Answer) RETURN n.answer_id")
    assert ok
    for bad in (
        "MATCH (n) CREATE (m:X)",
        "MATCH (n) SET n.x=1",
        "MATCH (n) DELETE n",
        "MERGE (n:X {id:'a'})",
        "CALL db.labels()",
        "MATCH (n) RETURN n; DROP TABLE x",
        "MATCH (n) RETURN n; MATCH (m) DELETE m",
    ):
        ok, reason = is_readonly(bad)
        assert not ok, "must reject: %s" % bad
        assert reason


def test_mcp_tools_list_and_read_cypher(tmp_path):
    store = tmp_path / "m.rl"
    db = relate.Database(str(store))
    from tracelens.fixture import build_fixture
    GraphMapper(db).ingest_run(build_fixture()["runs"][0])
    db.flush()
    db.close()

    names = [t["name"] for t in handle(
        {"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}}, Session(store)
    )["result"]["tools"]]
    assert "tracelens_query_pack" in names
    assert "tracelens_judge" in names

    s = Session(store)
    reply = handle(
        {"jsonrpc": "2.0", "id": 2, "method": "tools/call",
         "params": {"name": "tracelens_readonly_cypher",
                    "arguments": {"cypher": "MATCH (n:Answer) RETURN count(n) AS c"}}},
        s,
    )
    assert reply["result"]["isError"] is False
    blocked = handle(
        {"jsonrpc": "2.0", "id": 3, "method": "tools/call",
         "params": {"name": "tracelens_readonly_cypher",
                    "arguments": {"cypher": "MATCH (n) DELETE n"}}},
        s,
    )
    assert blocked["result"]["isError"] is True


# --------------------------------------------------------------------------
# R1/R2: real trace intake
# --------------------------------------------------------------------------
def test_inspect_rejects_fixture_shaped_flat_trace():
    inspect_doc = {"resourceSpans": [{"scopeSpans": [{"spans": [
        {"spanId": "x", "name": "n", "kind": "SPAN_KIND_INTERNAL",
         "startTimeUnixNano": "0", "endTimeUnixNano": "0", "attributes": [], "events": []}
    ]}]}]}
    report = inspect(inspect_doc)
    assert report["ok"] is False
    assert not report["checks"]["real_timestamps"]


def test_passport_requires_self_run_caveat(tmp_path):
    good_report = {
        "ok": True, "reason": "", "spans": 3, "timed_spans": 3,
        "parents": 2, "events": 3, "event_names": ["tracelens.answer"],
        "checks": {"spans_present": True, "real_timestamps": True,
                   "positive_durations": True, "has_parent_edges": True,
                   "has_events": True, "has_tool_or_retrieval": True},
    }
    src = tmp_path / "real.otlp.json"
    src.write_text('{"resourceSpans": []}', encoding="utf-8")
    with pytest.raises(ValueError):
        write_passport(src, {}, good_report, origin="self-run",
                       caveat="production customer data", out=tmp_path / "bad.meta.json")
    meta = write_passport(src, {}, good_report, origin="self-run desktop agent",
                          caveat="self-run, no customer", out=tmp_path / "ok.meta.json")
    v = verify_passport(src, meta)
    assert v["ok"], v
    assert v["sha256"] == sha256_file(src)


def test_real_agent_emits_command_output_with_real_timestamps(tmp_path):
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "a.md").write_text("retrieval evidence path claim source score " * 5, encoding="utf-8")
    (docs / "b.md").write_text("unrelated cooking recipe pasta tomato basil " * 5, encoding="utf-8")
    out = tmp_path / "trace.json"
    doc = run_real("retrieval evidence path claim", docs, "unit-real", top_k=1)
    meta = doc.pop("_run_meta")
    out.write_text(json.dumps(doc), encoding="utf-8")
    report = inspect(doc)
    assert report["ok"], report
    assert report["spans"] >= 4
    assert meta["corpus_size"] == 2


# --------------------------------------------------------------------------
# R5: agent self-check loop
# --------------------------------------------------------------------------
def test_apply_self_check_drops_graph_flagged_sources():
    before = [
        {"claim_id": "c1", "source": "stale.pdf", "score": 0.1, "text": "bad"},
        {"claim_id": "c2", "source": "current.pdf", "score": 0.9, "text": "good"},
        {"claim_id": "c3", "source": "current.pdf", "score": 0.9, "text": "unsupported"},
    ]
    verdict = {"convergence_causes": ["stale.pdf"], "verdict": "PASS"}
    # c1 dropped by convergence source, c3 dropped by Q3, c2 kept.
    # c1's low score alone is NOT what triggers the drop: a high-score claim
    # with the same source would also be dropped.
    fix = apply_self_check(
        before, verdict, threshold=0.5,
        q3_claims=[{"claim_id": "c3"}],
    )
    assert [c["claim_id"] for c in fix["kept"]] == ["c2"]
    assert [c["claim_id"] for c in fix["dropped"]] == ["c1", "c3"]
    assert fix["drop_reasons"]["c1"].startswith("Q2")
    assert fix["drop_reasons"]["c3"].startswith("Q3")
    assert fix["unsupported_claims_from_q3"] == ["c3"]


def test_agent_loop_records_before_after_and_tool_calls(tmp_path):
    store = tmp_path / "loop.rl"
    db = relate.Database(str(store))
    from tracelens.fixture import build_fixture
    GraphMapper(db).ingest_run(build_fixture()["runs"][0])
    db.flush()
    db.close()
    before = [
        {"claim_id": "ba-claim-bad", "source": "stale-policy-v2.pdf", "score": 0.12, "text": "bad"},
        {"claim_id": "ba-claim-ok", "source": "stale-policy-v2.pdf", "score": 0.12, "text": "ok"},
    ]
    record = run_loop(store, before, threshold=0.5)
    assert record["schema"] == "tracelens/agent-self-check@1"
    assert len(record["answer_before"]) == 2
    assert len(record["tool_calls"]) >= 2
    assert set(record["checks"]) >= {"baseline_misidentifies", "has_signal"}
    assert "stale-policy-v2.pdf" in record["bad_sources_from_graph"]
    assert record["answer_after"] == []
    assert record["verdict"] in ("PASS", "FAIL")  # real verdict, never hardcoded
