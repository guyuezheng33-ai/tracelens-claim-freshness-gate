"""Read the REAL Relate graph back out of a persisted store for judges to explore.

Official Devpost requirement: "Judges should be able to clone it, run it, and
see your graph without asking you anything." A hand-drawn diagram in a slide is
not that. Every node, every property and every edge in the output of this module
is read back from the ``.rl`` store with Cypher; nothing is drawn from a fixture,
a hardcoded node list, or a screenshot.

The export also carries its own falsifiable checks, so a reviewer can reject it
if the numbers do not match the live store:

  * node/relationship counts must equal ``Database.node_count()`` /
    ``relationship_count()``;
  * every edge endpoint must resolve to an exported node;
  * every Q6 provenance path node must resolve to an exported node.

Highlights are taken from the verdict JSON produced by ``provenance.py`` /
``scan.py`` in the SAME run, so the paths a judge clicks in the explorer are
exactly the paths the Cypher queries returned.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any

import relate

ROOT = Path(__file__).resolve().parent.parent

NODES_CYPHER = "MATCH (n) RETURN labels(n)[0] AS label, properties(n) AS props"
EDGES_CYPHER = (
    "MATCH (a)-[r]->(b) "
    "RETURN coalesce(a.node_id, a.id, a.url) AS source, type(r) AS rel, "
    "coalesce(b.node_id, b.id, b.url) AS target"
)


def _key(index: int, label: str, props: dict[str, Any]) -> str:
    """Stable node id: prefer node_id, then id, then url, else derive one."""
    raw = props.get("node_id") or props.get("id") or props.get("url")
    if raw:
        return str(raw)
    return "%s:%d" % (label, index)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _highlights(verdict: dict[str, Any], node_ids: set[str]) -> dict[str, Any]:
    """Turn this run's query results into clickable paths over real nodes."""
    out: dict[str, Any] = {"Q6_provenance": [], "Q7_hop_audit": [],
                           "Q8_declaration_drift": [], "merge_actions": [],
                           "Q9_convergence": [], "Q10_blast_radius": []}

    for row in verdict.get("Q6_provenance", []):
        path = [str(x) for x in row.get("path", [])]
        out["Q6_provenance"].append({
            "nodes": path, "rels": row.get("rels", []),
            "hops": row.get("hops"), "package": row.get("package"),
            "version": row.get("version"), "advisory_id": row.get("advisory_id"),
            "claim_text": row.get("claim_text"),
            "resolved": all(n in node_ids for n in path),
        })

    for row in verdict.get("Q7_hop_audit", []):
        hops = row.get("hops", [])
        out["Q7_hop_audit"].append({
            "nodes": [h["node"] for h in hops if h["node"] in node_ids],
            "stale_days": [h.get("already_stale_days") for h in hops],
            "at_iso": [h.get("at_iso") for h in hops],
            "labels": [h.get("label") for h in hops],
            "first_hop_already_stale": row.get("first_hop_already_stale"),
            "advisory_id": row.get("advisory_id"),
            "verdict": row.get("verdict"),
        })

    for row in verdict.get("Q8_declaration_drift", []):
        pkg = row.get("package")
        chain = [
            "ans:%s" % row.get("answer_id"),
            "claim:%s" % row.get("claim_id"),
            "pv:%s:%s" % (pkg, row.get("cited_version")),
        ]
        drift = [
            "lf:%s" % row.get("lockfile"),
            "pv:%s:%s" % (pkg, row.get("pinned_version")),
        ]
        affected = [
            "adv:%s" % row.get("advisory_id"),
            "pv:%s:%s" % (pkg, row.get("cited_version")),
        ]
        out["Q8_declaration_drift"].append({
            "claim_chain": [n for n in chain if n in node_ids],
            "lockfile_chain": [n for n in drift if n in node_ids],
            "advisory_chain": [n for n in affected if n in node_ids],
            "claim_text": row.get("claim_text"),
            "cited_version": row.get("cited_version"),
            "pinned_version": row.get("pinned_version"),
            "advisory_id": row.get("advisory_id"),
            "advisory_url": row.get("advisory_url"),
        })

    for action in verdict.get("merge_actions", []):
        out["merge_actions"].append({
            "reject_text": action.get("reject_text"),
            "cited_version": action.get("cited_version"),
            "pinned_version": action.get("pinned_version"),
            "action": action.get("action"),
        })

    # Cross-answer graph queries (convergence.py): keep the node ids so the
    # explorer can highlight exactly the cluster / blast radius the Cypher hit.
    for key in ("Q9_convergence", "Q10_blast_radius"):
        for row in verdict.get(key, []):
            nodes = [str(x) for x in row.get("nodes", [])]
            out[key].append({**row, "nodes": nodes,
                             "resolved": all(n in node_ids for n in nodes)})
    return out


def export_graph(store: str | Path, verdict: dict[str, Any] | None = None,
                 title: str = "Relate graph") -> dict[str, Any]:
    """Export one persisted store. Read-only; never writes to the ``.rl`` file."""
    path = Path(store)
    if not path.exists():
        raise FileNotFoundError("persistent Relate store not found: %s" % path)

    db = relate.Database(str(path), read_only=True)
    try:
        node_rows = list(db.execute(NODES_CYPHER, {}).data)
        edge_rows = list(db.execute(EDGES_CYPHER, {}).data)
        live_nodes = db.node_count()
        live_edges = db.relationship_count()
    finally:
        db.close()

    nodes: list[dict[str, Any]] = []
    for i, row in enumerate(node_rows):
        label = str(row["label"])
        props = dict(row["props"] or {})
        nodes.append({"id": _key(i, label, props), "label": label, "props": props})
    node_ids = {n["id"] for n in nodes}

    edges: list[dict[str, str]] = [
        {"source": str(r["source"]), "target": str(r["target"]),
         "type": str(r["rel"])}
        for r in edge_rows
    ]

    highlights = _highlights(verdict or {}, node_ids)
    q6_paths = highlights["Q6_provenance"]
    checks = {
        "store_is_persisted_on_disk": path.stat().st_size > 0,
        "nodes_match_live_db_count": len(nodes) == live_nodes,
        "relationships_match_live_db_count": len(edges) == live_edges,
        "every_node_has_properties": all(n["props"] for n in nodes),
        "every_edge_has_type": all(e["type"] for e in edges),
        "every_edge_endpoint_resolves": all(
            e["source"] in node_ids and e["target"] in node_ids for e in edges
        ),
        "q6_path_nodes_resolve_in_export": (
            all(p["resolved"] for p in q6_paths) if q6_paths else True
        ),
    }

    return {
        "schema": "tracelens/graph-export@1",
        "title": title,
        "store": str(path),
        "store_bytes": path.stat().st_size,
        "store_sha256": _sha256(path),
        "source": "live Cypher read-back from the persisted Relate .rl store",
        "queries": {"nodes": NODES_CYPHER, "edges": EDGES_CYPHER},
        "counts": {
            "nodes": len(nodes), "relationships": len(edges),
            "labels": dict(sorted(Counter(n["label"] for n in nodes).items())),
            "rel_types": dict(sorted(Counter(e["type"] for e in edges).items())),
        },
        "checks": checks,
        "verdict": "PASS" if all(checks.values()) else "FAIL",
        "nodes": nodes, "edges": edges, "highlights": highlights,
        "verdict_summary": {
            "graph_verdict": (verdict or {}).get("verdict"),
            "checks": (verdict or {}).get("checks", {}),
            "declarations_found": (verdict or {}).get("declarations_found"),
            "scenarios_built": (verdict or {}).get("scenarios_built"),
            "merge_verdict": (verdict or {}).get("verdict"),
        },
    }


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(prog="python -m tracelens.graphexport")
    p.add_argument("--store", required=True, help="persisted Relate .rl store")
    p.add_argument("--verdict", default=None, help="provenance/scan verdict JSON")
    p.add_argument("--out", required=True, help="export JSON destination")
    p.add_argument("--title", default="Relate graph")
    args = p.parse_args(argv)

    verdict = (json.loads(Path(args.verdict).read_text(encoding="utf-8"))
               if args.verdict else None)
    result = export_graph(args.store, verdict, args.title)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n",
                   encoding="utf-8")
    print(json.dumps({
        "store": result["store"], "store_sha256": result["store_sha256"],
        "counts": result["counts"], "checks": result["checks"],
        "verdict": result["verdict"],
    }, ensure_ascii=False, indent=2))
    # A failed consistency check must stop the one-command verification, not
    # merely print a red badge. Judges can reject the artefact programmatically.
    if result["verdict"] != "PASS":
        raise SystemExit("graph export consistency check failed: %s" % result["checks"])


if __name__ == "__main__":
    main()
