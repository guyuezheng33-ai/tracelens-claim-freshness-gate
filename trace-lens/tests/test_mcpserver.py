"""Regression: read-only MCP query-pack tool must discover params on real stores.

Previously mcpserver passed ``args.get('params') or {}`` to run_pack. An empty
dict is truthy-distinct from None in run_pack's discovery branch, so Q1/Q3/Q4
fell back to fixture-only defaults and returned zero rows on any real store.

The ORIGINAL regression test was itself hollow: it used a store where Q1/Q3
legitimately return [], asserted only "no error + content present", and skipped
entirely (``if not STORE.exists(): return``) when the file was missing — so an
all-empty or absent store passed. This version asserts non-empty rows.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import relate
from tracelens.mcpserver import Session
from tracelens.querypacks import discover_params

ROOT = Path(__file__).resolve().parent.parent
# demo-run.rl is the store with a complete Q1-Q4 evidence chain. self-run-1.rl
# has no Q1/Q3 rows by construction and cannot prove parameter discovery.
STORE = ROOT / "store" / "demo-run.rl"


def _text(result: dict) -> str:
    content = result.get("content")
    assert isinstance(content, list) and content, "MCP tool must return content"
    return content[0]["text"]


def test_query_pack_discovers_params_when_caller_omits_them():
    """With no explicit params the MCP tool must derive them from the graph."""
    assert STORE.exists(), "regression store missing: %s" % STORE
    db = relate.Database(str(STORE), read_only=True)
    try:
        discovered = discover_params(db)
    finally:
        db.close()
    assert any(discovered.get(k) for k in ("Q1", "Q3", "Q4")), (
        "a real store must yield discoverable params for at least one pack"
    )


def test_mcp_session_query_pack_runs_without_explicit_params():
    """No params must not be an error AND must return at least one real row."""
    assert STORE.exists(), "regression store missing: %s" % STORE
    session = Session(str(STORE))
    result = session.call("tracelens_query_pack", {"pack": "Q4"})
    assert result.get("isError") is False, "omitting params must not be an error"
    rows = json.loads(_text(result))
    assert isinstance(rows, list) and len(rows) > 0, (
        "Q4 must return real rows from demo-run.rl, not an empty array"
    )


def test_mcp_q1_returns_nonempty_on_demo_store():
    """Q1 must find a path on the complete diagnostic store."""
    assert STORE.exists(), "regression store missing: %s" % STORE
    session = Session(str(STORE))
    result = session.call("tracelens_query_pack", {"pack": "Q1"})
    assert result.get("isError") is False
    rows = json.loads(_text(result))
    assert isinstance(rows, list) and len(rows) > 0, "Q1 must return a real path"
