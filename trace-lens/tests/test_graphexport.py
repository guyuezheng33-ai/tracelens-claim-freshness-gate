"""See-your-graph gate: the explorer must show the REAL persisted store.

Reject conditions (each has a test that can fail):
  * node/edge counts disagree with the live Relate database;
  * any node loses its properties, any edge loses its type or endpoint;
  * any highlighted Q6/Q7/Q8 path node is not present in the exported graph;
  * the HTML loads ANY external resource or hides hardcoded/synthetic nodes;
  * the batch scan verdict exposes only counts instead of walkable paths.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import relate
from tracelens.graphexplorer import render
from tracelens.graphexport import export_graph
from tracelens.provenance import build_graph, build_scenario, run_queries

ROOT = Path(__file__).resolve().parent.parent

REAL_ADVISORY = {
    "id": "PYSEC-2014-14",
    "package": "requests",
    "fixed": "2.3.0",
    "published": "2014-10-15T14:55:00Z",
    "published_ns": 1413384900000000000,
    "osv_modified_ns": 1699415854820933120,
    "fix_available_ns": -1,
    "url": "https://github.com/kennethreitz/requests/issues/1885",
    "summary": "requests 2.2.0 vulnerability (real OSV record)",
}

EXTERNAL_RESOURCE = re.compile(
    r"(<script[^>]+src=|<link[^>]+href=|<img[^>]+src=|@import|url\(https?://)",
    re.IGNORECASE,
)


def _build(tmp_path: Path) -> tuple[Path, dict]:
    scenario = build_scenario(REAL_ADVISORY, 1795364590000000000,
                              "requirements.lock", "sha-export-test")
    store = tmp_path / "export.rl"
    build_graph(store, scenario, [REAL_ADVISORY])
    return store, run_queries(store)


def test_export_matches_live_store_counts(tmp_path):
    store, _ = _build(tmp_path)
    doc = export_graph(store, title="unit")
    assert doc["verdict"] == "PASS", doc["checks"]
    assert all(doc["checks"].values()), doc["checks"]
    assert doc["counts"]["nodes"] == len(doc["nodes"])
    assert doc["counts"]["relationships"] == len(doc["edges"])
    assert doc["store_sha256"] and len(doc["store_sha256"]) == 64
    assert doc["store_bytes"] > 0


def test_export_is_read_back_from_cypher_not_a_hardcoded_diagram(tmp_path):
    """Independently re-query the store; the export must be identical.
    Node keys follow the exporter's coalesce(node_id, id, url): Ref nodes are
    keyed by url exactly as in the full OSV graph."""
    store, _ = _build(tmp_path)
    doc = export_graph(store)
    db = relate.Database(str(store), read_only=True)
    try:
        live = {str(r["props"].get("node_id") or r["props"].get("id")
                    or r["props"].get("url")) for r in
                db.execute("MATCH (n) RETURN properties(n) AS props", {}).data}
        live_edges = {
            (str(r["source"]), str(r["rel"]), str(r["target"]))
            for r in db.execute(
                "MATCH (a)-[r]->(b) RETURN coalesce(a.node_id, a.id, a.url) AS source, "
                "type(r) AS rel, coalesce(b.node_id, b.id, b.url) AS target", {}).data
        }
    finally:
        db.close()
    assert {n["id"] for n in doc["nodes"]} == live
    assert {(e["source"], e["type"], e["target"]) for e in doc["edges"]} == live_edges
    answers = [n for n in doc["nodes"] if n["label"] == "Answer"]
    assert answers and "text" in answers[0]["props"], (
        "full node properties must survive the export"
    )


def test_highlight_paths_resolve_in_exported_graph(tmp_path):
    store, verdict = _build(tmp_path)
    doc = export_graph(store, verdict)
    assert doc["highlights"]["Q6_provenance"], "Q6 highlight must not be empty"
    ids = {n["id"] for n in doc["nodes"]}
    for p in doc["highlights"]["Q6_provenance"]:
        assert p["resolved"] is True
        assert set(p["nodes"]) <= ids
        assert len(p["rels"]) >= 2
    assert doc["highlights"]["Q7_hop_audit"][0]["first_hop_already_stale"]
    q8 = doc["highlights"]["Q8_declaration_drift"][0]
    assert q8["cited_version"] != q8["pinned_version"]
    assert all(n in ids for n in q8["claim_chain"] + q8["lockfile_chain"])


def test_explorer_is_single_file_with_zero_external_resources(tmp_path):
    store, verdict = _build(tmp_path)
    doc = export_graph(store, verdict)
    page = render([doc])
    assert not EXTERNAL_RESOURCE.search(page), "HTML must not load external resources"
    assert "<svg" in page and "viewBox" in page
    assert doc["nodes"][0]["id"] in page, "a real node id must be in the page"
    assert all(k in page for k in ("Q6", "Q7", "Q8", "节点属性"))
    assert "data-i=\"0\"" in page


def test_batch_scan_verdict_exposes_walkable_paths(tmp_path):
    """Regression: batch scan used to expose only counts, so the 73-node
    explorer had nothing to highlight. Every Q6/Q7/Q8 row must be walkable."""
    from tracelens.scan import scan

    text = ROOT / "real-traces/scan/pr-answer.txt"
    lock = ROOT / "real-traces/scan/requirements.lock"
    passport = json.loads((ROOT / "real-traces/scan/osv-batch-passport.json")
                          .read_text(encoding="utf-8"))
    from tracelens.expiry import iso_to_ns
    store = tmp_path / "scan.rl"
    result = scan(text, lock, passport,
                  iso_to_ns("2026-11-22T16:23:10Z"), store)
    assert result["verdict"] == "BLOCK_MERGE_TEXT"
    assert len(result["Q6_provenance"]) == result["Q6_provenance_paths"] >= 8
    assert len(result["Q7_hop_audit"]) == result["Q7_hop_audits"] >= 8
    assert len(result["Q8_declaration_drift"]) == result["Q8_drifts"] >= 8

    doc = export_graph(store, result)
    assert doc["verdict"] == "PASS", doc["checks"]
    ids = {n["id"] for n in doc["nodes"]}
    assert all(p["resolved"] for p in doc["highlights"]["Q6_provenance"])
    assert all(set(p["nodes"]) <= ids for p in doc["highlights"]["Q6_provenance"])
