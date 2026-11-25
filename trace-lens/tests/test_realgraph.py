"""Offline unit tests for the real OSV provenance graph.

The sample advisories below are constructed locally inside tmp_path. They are
NOT committed artifacts and are never written to fixtures/. These tests do no
network I/O: build_graph must work purely from the snapshot dict it is given.
"""

from __future__ import annotations

import json

import pytest
import relate
from tracelens.mcpserver import is_readonly
from tracelens.realgraph import build_graph, sha256_file


def _sample_snapshot() -> dict:
    """Three OSV-shaped records, built in memory with distinct public URLs."""
    vulns = []
    for i in range(1, 4):
        vid = "CVE-TEST-2024-%04d" % i
        vulns.append({
            "id": vid,
            "summary": "locally constructed sample advisory %d" % i,
            "aliases": ["GHSA-test-%04d" % i],
            "references": [
                {"type": "ADVISORY", "url": "https://nvd.nist.gov/vuln/detail/%s" % vid},
                {"type": "WEB", "url": "https://github.com/advisories/GHSA-test-%04d" % i},
            ],
            "published": "2024-01-%02dT00:00:00Z" % i,
            "modified": "2024-02-%02dT00:00:00Z" % i,
            "database_specific": {"severity": "HIGH"},
        })
    return {
        "schema": "tracelens/osv-snapshot@1",
        "source": "OSV.dev public API",
        "endpoint": "https://api.osv.dev/v1/query",
        "ecosystem": "PyPI",
        "query_commands": [
            {"method": "POST", "url": "https://api.osv.dev/v1/query",
             "package": "sample", "http_status": 200, "vulns_returned": 3}
        ],
        "vuln_count": 3,
        "vulns": vulns,
    }


def _write_sample(tmp_path):
    path = tmp_path / "sample-osv-snapshot.json"
    snapshot = _sample_snapshot()
    path.write_text(json.dumps(snapshot, ensure_ascii=False), encoding="utf-8")
    snapshot = json.loads(path.read_text(encoding="utf-8"))
    snapshot["sha256"] = sha256_file(path)
    return snapshot, path


def test_build_graph_counts_urls_and_passport(tmp_path):
    snapshot, snap_path = _write_sample(tmp_path)
    store = tmp_path / "sample.rl"

    passport = build_graph(snapshot, store)

    # 3 Vuln + 3 Alias + 6 distinct Ref = 12 nodes.
    assert passport["node_count"] == 12
    # 3 HAS_ALIAS + 6 Vuln->Ref + 6 Alias->Ref = 15 relationships.
    assert passport["relationship_count"] == 15
    assert passport["vuln_count"] == 3
    assert passport["url_coverage"] == 1.0

    # Passport provenance fields are all present and meaningful.
    assert passport["nature"] == "real-public"
    assert passport["source"] == "OSV.dev public API"
    assert passport["sha256"] == sha256_file(snap_path)
    assert passport["sha256"]
    assert isinstance(passport["query_commands"], list) and passport["query_commands"]
    assert "公开" in passport["caveat"]
    assert "非客户数据" in passport["caveat"]
    assert "非 agent trace" in passport["caveat"]
    assert set(passport) >= {
        "nature", "source", "query_commands", "sha256", "node_count",
        "relationship_count", "vuln_count", "url_coverage", "caveat",
    }

    # Every Vuln in the actual store has a public URL, and Alias->Ref paths exist.
    db = relate.Database(str(store))
    try:
        urls = [r["u"] for r in db.execute(
            "MATCH (v:Vuln) RETURN v.url AS u", {}
        ).data]
        assert len(urls) == 3
        assert all(u.startswith("https://") for u in urls)
        alias_paths = list(db.execute(
            "MATCH (v:Vuln)-[:HAS_ALIAS]->(:Alias)-[:REFERENCES]->(:Ref) "
            "RETURN count(*) AS c", {},
        ).data)
        assert alias_paths[0]["c"] == 6
    finally:
        db.close()


def test_build_graph_is_idempotent(tmp_path):
    snapshot, _ = _write_sample(tmp_path)
    store = tmp_path / "idem.rl"
    first = build_graph(snapshot, store)
    second = build_graph(snapshot, store)
    assert second["node_count"] == first["node_count"] == 12
    assert second["relationship_count"] == first["relationship_count"] == 15
    assert second["vuln_count"] == first["vuln_count"] == 3


def test_build_graph_requires_no_network_and_ignores_readonly_gate(tmp_path, monkeypatch):
    snapshot, _ = _write_sample(tmp_path)

    def _no_network(*args, **kwargs):
        raise AssertionError("build_graph must not perform network I/O")

    monkeypatch.setattr("tracelens.realgraph.urllib.request.urlopen", _no_network)

    # The read-only gate rejects writes, but this independent data source is
    # not subject to it -- build_graph must still write and return a passport.
    allowed, _ = is_readonly("MATCH (n) CREATE (m:X)")
    assert allowed is False

    store = tmp_path / "independent.rl"
    passport = build_graph(snapshot, store)
    assert store.exists()
    assert passport["vuln_count"] == 3
    assert passport["url_coverage"] == 1.0


def test_build_graph_rejects_empty_snapshot(tmp_path):
    with pytest.raises(ValueError):
        build_graph({"vulns": []}, tmp_path / "empty.rl")
