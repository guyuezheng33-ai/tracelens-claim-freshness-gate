"""Q11 fixpoint reasoning gate: derived facts, recursive propagation, and
agreement with the independent Cypher Q8 computation. Offline, no network.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tracelens.provenance import build_graph, build_scenario, run_queries
from tracelens.reasoning import run_reasoning

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
AS_OF = 1795364590000000000


def _store(tmp_path, spans=None):
    sc = build_scenario(REAL_ADVISORY, AS_OF, "requirements.lock", "sha-reason")
    if spans is not None:
        sc["spans"] = spans
    store = tmp_path / "reason.rl"
    build_graph(store, sc, [REAL_ADVISORY])
    return store


def test_fixpoint_derives_born_stale_with_premises(tmp_path):
    store = _store(tmp_path)
    sv = run_queries(store)
    res = run_reasoning(store, sv)
    assert res["verdict"] == "PASS", res["checks"]
    assert res["checks"]["fixpoint_reached"]
    assert res["derived_born_stale_answers"], "R4 must derive the born-stale answer"
    assert res["checks"]["reasoning_agrees_with_cypher_q8"], (
        "independent fixpoint reasoning must flag the same answers as Cypher Q8")
    for rules in res["facts"].values():
        for f in rules:
            assert f["premises"] and f["rule"]


def test_r3_propagates_recursively_through_deeper_chain(tmp_path):
    # three-span chain: retriever -> mid -> root; staleness must propagate
    # from the retriever up to the root via recursive R3, not a fixed pattern.
    spans = [
        {"id": "pr-root", "kind": "AGENT", "name": "agent.answer",
         "at_ns": AS_OF - 1_000_000_000},
        {"id": "pr-mid", "kind": "CHAIN", "name": "rerank",
         "at_ns": AS_OF - 700_000_000, "parent_id": "pr-root"},
        {"id": "pr-retriever", "kind": "RETRIEVER", "name": "vector-search",
         "at_ns": AS_OF - 500_000_000, "parent_id": "pr-mid",
         "retrieved_doc": "stale-doc.md"},
    ]
    store = _store(tmp_path, spans=spans)
    res = run_reasoning(store, run_queries(store))
    assert res["verdict"] == "PASS", res["checks"]
    assert res["checks"]["r3_propagates_along_parent_of"]
    r3_subjects = {f["subject"] for f in res["facts"]["R3"]}
    assert "span:pr-root" in r3_subjects and "span:pr-mid" in r3_subjects
    assert res["iterations"] >= 2, "recursive propagation needs >1 iteration"


def test_no_derivation_before_advisory_publication(tmp_path):
    sc = build_scenario(REAL_ADVISORY, 1356998400000000000,  # 2013-01-01
                        "requirements.lock", "sha-early")
    store = tmp_path / "early.rl"
    build_graph(store, sc, [REAL_ADVISORY])
    res = run_reasoning(store, run_queries(store))
    assert res["derived_born_stale_answers"] == [], (
        "an answer written before publication must not be derived born-stale")
    assert res["checks"]["r4_derives_born_stale_answers"] is False


def _shared_retriever_store(tmp_path):
    """Two answers, one shared retriever: the real repair target is the
    collection layer, not the two answers."""
    import relate
    store = tmp_path / "shared.rl"
    db = relate.Database(str(store))
    adv, pv, src, ret = "adv:shared", "pv:requests:2.2.0", "src:doc", "span:ret"
    db.execute("MERGE (a:Advisory {node_id:$id}) SET a += $p",
               {"id": adv, "p": {"published_ns": 1000}})
    db.execute("MERGE (v:PkgVersion {node_id:$id}) SET v += $p",
               {"id": pv, "p": {"name": "requests", "version": "2.2.0"}})
    db.execute("MATCH (a:Advisory {node_id:$a}), (v:PkgVersion {node_id:$v}) "
               "MERGE (a)-[:AFFECTS]->(v)", {"a": adv, "v": pv})
    db.execute("MERGE (s:Source {node_id:$id}) SET s += $p",
               {"id": src, "p": {"at_ns": 500}})
    db.execute("MATCH (s:Source {node_id:$s}), (v:PkgVersion {node_id:$v}) "
               "MERGE (s)-[:MENTIONS]->(v)", {"s": src, "v": pv})
    db.execute("MERGE (s:Span {node_id:$id}) SET s += $p",
               {"id": ret, "p": {"kind": "RETRIEVER", "at_ns": 2000}})
    db.execute("MATCH (s:Span {node_id:$s}), (d:Source {node_id:$d}) "
               "MERGE (s)-[:RETRIEVED_FROM]->(d)", {"s": ret, "d": src})
    for i in ("a", "b"):
        root, ans, clm = f"span:root-{i}", f"ans:{i}", f"claim:{i}"
        db.execute("MERGE (s:Span {node_id:$id}) SET s += $p",
                   {"id": root, "p": {"kind": "AGENT", "at_ns": 3000}})
        db.execute("MATCH (p:Span {node_id:$p}), (c:Span {node_id:$c}) "
                   "MERGE (p)-[:PARENT_OF]->(c)", {"p": root, "c": ret})
        db.execute("MERGE (a:Answer {node_id:$id}) SET a += $p",
                   {"id": ans, "p": {"created_ns": 4000}})
        db.execute("MATCH (s:Span {node_id:$s}), (a:Answer {node_id:$a}) "
                   "MERGE (s)-[:PRODUCED]->(a)", {"s": root, "a": ans})
        db.execute("MERGE (c:Claim {node_id:$id})", {"id": clm})
        db.execute("MATCH (a:Answer {node_id:$a}), (c:Claim {node_id:$c}) "
                   "MERGE (a)-[:ASSERTS]->(c)", {"a": ans, "c": clm})
        db.execute("MATCH (c:Claim {node_id:$c}), (v:PkgVersion {node_id:$v}) "
                   "MERGE (c)-[:CITES]->(v)", {"c": clm, "v": pv})
    db.close()
    return store


def test_r5_single_cut_on_shared_retriever_blocks_two_answers(tmp_path):
    store = _shared_retriever_store(tmp_path)
    res = run_reasoning(store, None)
    iv = res["intervention"]
    assert res["verdict"] == "PASS", res["checks"]
    assert iv["repair_size"] == 1, "one shared retriever must be cut once, not twice"
    assert iv["intervention_spans"] == ["span:ret"]
    assert iv["derived_answer_count"] == 2
    assert iv["uncovered_derived_answers"] == []
    # the cover is a path-pair solve: both producer->source paths are blocked
    assert set(iv["blocked_paths"]) == {
        "span:root-a-[adv:shared]->span:ret",
        "span:root-b-[adv:shared]->span:ret",
    }


def test_r6_rejects_a_cut_that_leaves_the_other_answer_exposed(tmp_path):
    store = _shared_retriever_store(tmp_path)
    res = run_reasoning(store, None)
    iv = res["intervention"]
    # sanity: a root-only cut would not block the sibling root's path
    exposed = [p for p in iv["blocked_paths"] if "root-a" in p]
    assert iv["repair_size"] == 1 and len(iv["blocked_paths"]) == 2
    assert iv["intervention_spans"] != ["span:root-a"] or exposed
    assert all(n == "span:ret" for n in iv["intervention_spans"]), (
        "the only one-cut solution covering both answers is the shared retriever")