"""Build the shared-collector counterfactual topology from the real scan store.

The real store has 8 independent review chains (one retriever per package), so
the minimum repair is 8 cuts — one per chain. This topology asks the deployment
question instead: if ONE collection layer serves all 8 packages (a single
batch retriever shared by the review agent), what is the minimum repair?

It copies the real 8 advisories, 8 package versions and 8 source documents
verbatim out of `scan.rl`, re-parents them under one shared retriever / one
shared producer span, and emits 8 answers created after publication. Nothing is
fabricated: every advisory clock, every source `at_ns` and every package
version comes from the real scan graph. Only the *topology* is counterfactual,
and it is labelled as such in the verdict.

Run: python build_shared_topology.py --scan <scan.rl> --out <shared.rl>
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import relate

ROOT = Path(__file__).resolve().parent.parent.parent


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--scan", default=str(ROOT / "real-traces" / "scan" / "scan.rl"))
    p.add_argument("--out", default=str(ROOT / "real-traces" / "reasoning" / "shared-retriever.rl"))
    args = p.parse_args(argv)

    src = relate.Database(args.scan, read_only=True)
    advisories = src.execute(
        "MATCH (a:Advisory) RETURN a.node_id AS id, properties(a) AS p", {}).data
    sources = src.execute(
        "MATCH (s:Source) RETURN s.node_id AS id, properties(s) AS p", {}).data
    affects = src.execute(
        "MATCH (a:Advisory)-[:AFFECTS]->(v:PkgVersion) "
        "RETURN a.node_id AS a, v.node_id AS v, properties(v) AS p", {}).data
    mentions = src.execute(
        "MATCH (s:Source)-[:MENTIONS]->(v:PkgVersion) "
        "RETURN s.node_id AS s, v.node_id AS v", {}).data
    src.close()

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    if out.exists():
        out.unlink()
    db = relate.Database(str(out))

    # real advisories, real package versions, real source documents — verbatim
    for row in advisories:
        db.execute("MERGE (a:Advisory {node_id:$id}) SET a += $p", {"id": row["id"], "p": row["p"]})
    pv_props = {row["v"]: row["p"] for row in affects}
    for v, props in pv_props.items():
        db.execute("MERGE (v:PkgVersion {node_id:$id}) SET v += $p", {"id": v, "p": props})
    for row in affects:
        db.execute("MATCH (a:Advisory {node_id:$a}), (v:PkgVersion {node_id:$v}) "
                   "MERGE (a)-[:AFFECTS]->(v)", {"a": row["a"], "v": row["v"]})
    for row in sources:
        db.execute("MERGE (s:Source {node_id:$id}) SET s += $p", {"id": row["id"], "p": row["p"]})
    for row in mentions:
        db.execute("MATCH (s:Source {node_id:$s}), (v:PkgVersion {node_id:$v}) "
                   "MERGE (s)-[:MENTIONS]->(v)", {"s": row["s"], "v": row["v"]})

    # counterfactual topology: one collector, one producer, N answers
    latest = max(int(row["p"]["published_ns"]) for row in advisories)
    ret, root = "span:shared-ret", "span:shared-root"
    for sid, kind, name, parent, at_ns in (
            (root, "AGENT", "agent.answer", None, latest + 3_000_000_000),
            (ret, "RETRIEVER", "batch-collector", root, latest + 2_000_000_000)):
        db.execute("MERGE (s:Span {node_id:$id}) SET s += $p",
                   {"id": sid, "p": {"kind": kind, "name": name,
                                     "node_id": sid, "at_ns": at_ns}})
        if parent:
            db.execute("MATCH (p:Span {node_id:$p}), (c:Span {node_id:$c}) "
                       "MERGE (p)-[:PARENT_OF]->(c)", {"p": parent, "c": sid})
    for row in sources:
        db.execute("MATCH (s:Span {node_id:$s}), (d:Source {node_id:$d}) "
                   "MERGE (s)-[:RETRIEVED_FROM]->(d)", {"s": ret, "d": row["id"]})
    affects_by_adv = {row["a"]: row["v"] for row in affects}
    latest = max(int(row["p"]["published_ns"]) for row in advisories)
    for i, row in enumerate(sorted(advisories, key=lambda r: r["id"])):
        aid = f"ans:shared-{i}"
        db.execute("MERGE (a:Answer {node_id:$id}) SET a += $p",
                   {"id": aid, "p": {"created_ns": latest + 1_000_000_000, "node_id": aid}})
        db.execute("MATCH (s:Span {node_id:$s}), (a:Answer {node_id:$a}) "
                   "MERGE (s)-[:PRODUCED]->(a)", {"s": root, "a": aid})
        # the answer asserts a claim that cites its own advisory's package version
        clm = f"claim:shared-{i}"
        db.execute("MERGE (c:Claim {node_id:$id}) SET c += $p",
                   {"id": clm, "p": {"node_id": clm}})
        db.execute("MATCH (a:Answer {node_id:$a}), (c:Claim {node_id:$c}) "
                   "MERGE (a)-[:ASSERTS]->(c)", {"a": aid, "c": clm})
        db.execute("MATCH (c:Claim {node_id:$c}), (v:PkgVersion {node_id:$v}) "
                   "MERGE (c)-[:CITES]->(v)", {"c": clm, "v": affects_by_adv[row["id"]]})
    db.close()
    print(f"wrote {out} · {len(advisories)} advisories · {len(sources)} sources · 1 shared retriever")


if __name__ == "__main__":
    main()
