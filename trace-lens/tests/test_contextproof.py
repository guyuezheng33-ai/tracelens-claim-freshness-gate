"""Context-connected check must reject a graph-only narrative."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from tracelens.contextproof import verify

ROOT = Path(__file__).resolve().parent.parent
STORE = ROOT / "store" / "demo-run.rl"

GOOD_GUARD = {
    "decision_source": "graph only (Q3 unsupported path / Q2 convergence cause)",
    "model_cannot_release_rejected_claim": True,
    "decisions": [
        {"claim_id": "c1", "graph_reason": "Q3: no SUPPORTED_BY evidence path",
         "graph_evidence": [{"claim_id": "c1"}]}
    ],
    "passport": {"model": "test-model"},
}
GOOD_PASSPORT = {
    "nature": "real-public", "node_count": 600, "url_coverage": 1.0,
}


def _write(tmp_path: Path, name: str, data: dict) -> Path:
    p = tmp_path / name
    p.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return p


def test_all_three_evidence_sources_are_required(tmp_path):
    if not STORE.exists():
        pytest.skip("demo store not built yet")
    g = _write(tmp_path, "guard.json", GOOD_GUARD)
    rp = _write(tmp_path, "realgraph.json", GOOD_PASSPORT)
    record = verify(STORE, g, rp)
    assert record["verdict"] == "PASS"
    assert all(record["checks"].values())
    assert all(p["passed"] for p in record["packs"].values())


def test_missing_guardrail_fails(tmp_path):
    if not STORE.exists():
        pytest.skip("demo store not built yet")
    rp = _write(tmp_path, "realgraph.json", GOOD_PASSPORT)
    record = verify(STORE, None, rp)
    assert record["verdict"] == "FAIL"
    assert record["checks"]["guardrail_decision_is_graph_only"] is False


def test_model_override_claim_fails(tmp_path):
    if not STORE.exists():
        pytest.skip("demo store not built yet")
    guard = dict(GOOD_GUARD)
    guard["model_cannot_release_rejected_claim"] = False
    g = _write(tmp_path, "guard.json", guard)
    rp = _write(tmp_path, "realgraph.json", GOOD_PASSPORT)
    record = verify(STORE, g, rp)
    assert record["verdict"] == "FAIL"
    assert record["checks"]["model_cannot_release_rejected_claim"] is False


def test_untraceable_real_graph_fails(tmp_path):
    if not STORE.exists():
        pytest.skip("demo store not built yet")
    g = _write(tmp_path, "guard.json", GOOD_GUARD)
    bad = dict(GOOD_PASSPORT)
    bad["url_coverage"] = 0.4
    rp = _write(tmp_path, "realgraph.json", bad)
    record = verify(STORE, g, rp)
    assert record["verdict"] == "FAIL"
    assert record["checks"]["real_graph_is_traceable_at_scale"] is False


def test_decision_without_graph_reason_fails(tmp_path):
    if not STORE.exists():
        pytest.skip("demo store not built yet")
    guard = dict(GOOD_GUARD)
    guard["decisions"] = [{"claim_id": "c1", "graph_reason": "", "graph_evidence": []}]
    g = _write(tmp_path, "guard.json", guard)
    rp = _write(tmp_path, "realgraph.json", GOOD_PASSPORT)
    record = verify(STORE, g, rp)
    assert record["checks"]["every_decision_cites_graph_evidence"] is False
