"""Read-only Cypher console: judges can ask the real store anything."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tracelens.ask import ask
from tracelens.scan import scan

ADV = {
    "id": "PYSEC-2014-14", "package": "requests", "fixed": "2.3.0",
    "published": "2014-10-15T14:55:00Z", "published_ns": 1413384900000000000,
    "osv_modified_ns": 1699415854820933120, "fix_available_ns": -1,
    "url": "https://github.com/kennethreitz/requests/issues/1885",
    "summary": "real OSV record",
}


def _store(tmp_path):
    text = tmp_path / "pr.txt"
    text.write_text("requests 2.2.0 is safe to use\n", encoding="utf-8")
    lock = tmp_path / "requirements.lock"
    lock.write_text("requests==2.3.0\n", encoding="utf-8")
    store = tmp_path / "ask.rl"
    scan(text, lock, {"advisories": [ADV]}, 1795364590000000000, store)
    return store


def test_ask_returns_real_rows(tmp_path):
    store = _store(tmp_path)
    result = ask(store, "MATCH (a:Answer)-[:ASSERTS]->(c:Claim)-[:CITES]->(v:PkgVersion) "
                        "RETURN a.answer_id AS answer, v.name AS package, v.version AS version")
    assert result["row_count"] == 1
    assert result["rows"][0]["package"] == "requests"
    assert result["rows"][0]["version"] == "2.2.0"
    assert result["node_count"] > 0


def test_ask_refuses_writes(tmp_path):
    store = _store(tmp_path)
    with pytest.raises(ValueError):
        ask(store, "MATCH (n) DELETE n")
    with pytest.raises(ValueError):
        ask(store, "MERGE (x:Answer {node_id:'x'})")


def test_ask_refuses_non_query(tmp_path):
    store = _store(tmp_path)
    with pytest.raises(ValueError):
        ask(store, "SHOW TABLES")