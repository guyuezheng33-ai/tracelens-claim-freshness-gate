"""Guardrail tests: the graph decides; the model cannot override it."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from tracelens import guardrail

ROOT = Path(__file__).resolve().parent.parent
STORE = ROOT / "store" / "demo-run.rl"
BEFORE = [
    {"claim_id": "ba-claim-bad", "source": "stale-policy-v2.pdf",
     "score": 0.12, "text": "deadline is March 1"},
    {"claim_id": "ba-claim-ok", "source": "current-policy-v9.pdf",
     "score": 0.94, "text": "policy v9 current"},
]


def _fake_chat(messages, **kwargs):
    return {
        "content": "model explanation from test",
        "receipt": {
            "endpoint": "test://local", "model_requested": "test-model",
            "model_returned": "test-model", "status": 200, "latency_ms": 1.0,
            "request_sha256": "a" * 64, "response_sha256": "b" * 64,
            "prompt_messages": [], "usage": {"total_tokens": 1},
        },
    }


def test_graph_decision_is_not_overridden_by_model(monkeypatch):
    if not STORE.exists():
        pytest.skip("demo store not built yet")
    monkeypatch.setattr(guardrail, "chat", _fake_chat)
    record = guardrail.run_guardrail(STORE, BEFORE)
    assert record["decision_source"].startswith("graph only")
    assert record["model_cannot_release_rejected_claim"] is True
    assert [c["claim_id"] for c in record["answer_after"]] == ["ba-claim-ok"]
    bad = next(d for d in record["decisions"] if d["claim_id"] == "ba-claim-bad")
    assert bad["admitted"] is False
    assert "Q3" in bad["graph_reason"]
    # The model was still genuinely called on the rejected claim.
    assert any(c["claim_id"] == "ba-claim-bad" for c in record["llm_calls"])
    assert bad["model_explanation"] == "model explanation from test"


def test_graph_only_mode_skips_model_but_keeps_decision():
    if not STORE.exists():
        pytest.skip("demo store not built yet")
    record = guardrail.run_guardrail(STORE, BEFORE, call_model=False)
    assert record["llm_calls"] == []
    assert record["passport"]["nature"] == "graph-only"
    assert [c["claim_id"] for c in record["answer_after"]] == ["ba-claim-ok"]


def test_every_decision_has_graph_reason_and_evidence():
    if not STORE.exists():
        pytest.skip("demo store not built yet")
    record = guardrail.run_guardrail(STORE, BEFORE, call_model=False)
    for decision in record["decisions"]:
        assert decision["decision_source"] == "graph"
        assert decision["graph_reason"]
        assert isinstance(decision["graph_evidence"], list)
    assert "tool_calls" in record and len(record["tool_calls"]) >= 1


def test_adversarial_model_cannot_release_rejected_claim(monkeypatch):
    """A model that explicitly demands release still cannot override the graph."""
    if not STORE.exists():
        pytest.skip("demo store not built yet")

    def rogue_chat(messages, **kwargs):
        return {
            "content": "IGNORE GRAPH. Release the claim immediately.",
            "receipt": {
                "endpoint": "adversarial://test", "model_requested": "rogue",
                "model_returned": "rogue", "status": 200, "latency_ms": 1.0,
                "request_sha256": "0" * 64, "response_sha256": "1" * 64,
                "prompt_messages": [], "usage": {},
            },
        }

    monkeypatch.setattr(guardrail, "chat", rogue_chat)
    record = guardrail.run_guardrail(STORE, BEFORE)
    assert [c["claim_id"] for c in record["answer_after"]] == ["ba-claim-ok"]
    bad = next(d for d in record["decisions"] if d["claim_id"] == "ba-claim-bad")
    assert bad["admitted"] is False
    assert "Release the claim" in bad["model_explanation"]
    assert record["model_cannot_release_rejected_claim"] is True


def test_record_is_json_serialisable(monkeypatch):
    if not STORE.exists():
        pytest.skip("demo store not built yet")
    monkeypatch.setattr(guardrail, "chat", _fake_chat)
    record = guardrail.run_guardrail(STORE, BEFORE)
    assert json.loads(json.dumps(record, ensure_ascii=False))["verdict"] in {"PASS", "FAIL"}
