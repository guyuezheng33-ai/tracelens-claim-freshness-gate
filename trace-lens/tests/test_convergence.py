"""Q9/Q10: cross-model convergence and advisory blast radius on a real store."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tracelens.convergence import run_convergence_queries
from tracelens.provenance import build_graph

ROOT = Path(__file__).resolve().parent.parent

ADV = {
    "id": "PYSEC-2014-14", "package": "requests", "fixed": "2.3.0",
    "published": "2014-10-15T14:55:00Z", "published_ns": 1413384900000000000,
    "osv_modified_ns": 1699415854820933120, "fix_available_ns": -1,
    "url": "https://github.com/kennethreitz/requests/issues/1885",
    "summary": "real OSV record",
}


def _scenario(prefix: str, model: str, answer_ns: int) -> dict:
    return {
        "run": {"id": prefix + "run", "started_ns": answer_ns - 2_000_000_000},
        "answer": {"id": prefix + "ans", "created_ns": answer_ns,
                   "question": "which requests?", "text": "requests 2.2.0 is safe",
                   "model": model},
        "claims": [{"id": prefix + "cl", "text": "requests 2.2.0 is safe",
                    "package": "requests", "version": "2.2.0"}],
        "spans": [
            {"id": prefix + "root", "kind": "AGENT", "name": "agent.answer",
             "at_ns": answer_ns - 1_000_000_000},
            {"id": prefix + "ret", "kind": "RETRIEVER", "name": "vector-search",
             "at_ns": answer_ns - 500_000_000, "parent_id": prefix + "root",
             "retrieved_doc": prefix + "doc"},
        ],
        "sources": [{"doc_id": prefix + "doc", "uri": "https://example.test/doc",
                     "at_ns": ADV["published_ns"] - 365 * 86400 * 1_000_000_000,
                     "mentions": [{"package": "requests", "version": "2.2.0"}]}],
        "lockfile": {"path": prefix + "requirements.lock",
                     "pinned_ns": answer_ns - 10_000_000_000, "sha256": "x",
                     "pins": [{"package": "requests", "version": "2.3.0"}]},
    }


def test_two_models_one_risky_version_is_a_convergence_cluster(tmp_path):
    store = tmp_path / "conv.rl"
    ns = 1795364590000000000
    build_graph(store, _scenario("a-", "model-a", ns), [ADV])
    build_graph(store, _scenario("b-", "model-b", ns), [ADV], append=True)
    result = run_convergence_queries(store)
    assert result["verdict"] == "PASS", result["checks"]
    cluster = result["Q9_convergence"][0]
    assert cluster["package"] == "requests"
    assert cluster["version"] == "2.2.0"
    assert cluster["n_models"] == 2
    assert set(cluster["models"]) == {"model-a", "model-b"}
    radius = result["Q10_blast_radius"][0]
    assert radius["advisory_id"] == "PYSEC-2014-14"
    assert radius["n_answers"] == 2
    assert radius["n_models"] == 2
    # every highlighted node id must be a real node id, not a label
    assert all(n.startswith(("pv:", "adv:", "ans:", "claim:"))
               for n in cluster["nodes"])


def test_single_model_is_not_cross_model_convergence(tmp_path):
    store = tmp_path / "one.rl"
    ns = 1795364590000000000
    build_graph(store, _scenario("a-", "model-a", ns), [ADV])
    result = run_convergence_queries(store)
    assert result["checks"]["q9_finds_cross_model_convergence"] is False
    assert result["verdict"] == "FAIL"


def test_committed_convergence_store_passes():
    store = ROOT / "real-traces/convergence/convergence.rl"
    if not store.exists():
        pytest.skip("convergence store not built yet (run make verify)")
    result = run_convergence_queries(store)
    assert result["verdict"] == "PASS", result["checks"]
    assert any(c["n_models"] >= 2 for c in result["Q9_convergence"])
    assert any(b["n_models"] >= 2 for b in result["Q10_blast_radius"])