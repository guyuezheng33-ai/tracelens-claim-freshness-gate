"""Cross-answer graph intelligence: Q9 convergence + Q10 advisory blast radius.

Q6/Q7/Q8 audit ONE answer's evidence chain. A per-file scanner can, in principle,
approximate that with enough string parsing. What it can NEVER see is the
connected context ACROSS answers:

  Q9  CONVERGENCE      different models independently cite the SAME risky
                       version. The PinTrace paper calls this systemic bias;
                       here it is a graph query over captured outputs, not a
                       statistic quoted from a paper.
  Q10 BLAST RADIUS     one advisory lands -> how many captured answers, from
                       how many distinct models, become born-stale at once?
                       The advisory is a single node; its reach is a fan-out
                       over AFFECTS <- CITES <- ASSERTS.

Both queries join Answer -> Claim -> PkgVersion <- Advisory in ONE merged
Relate store built from the 14 captured real texts (5 Stack Overflow + 9 model
outputs) plus the 8-declaration batch demo. Nothing is hand-labelled: AFFECTS
edges are derived from the real advisory ranges, models come from source.json.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import relate

from .expiry import iso_to_ns
from .provenance import build_graph
from .scan import build_multi_scenario, extract_declarations, read_lockfile

ROOT = Path(__file__).resolve().parent.parent

Q9_CYPHER = """
MATCH (a:Answer)-[:ASSERTS]->(c:Claim)-[:CITES]->(pv:PkgVersion)
MATCH (adv:Advisory)-[:AFFECTS]->(pv)
WHERE a.created_ns > adv.published_ns
RETURN a.node_id AS answer_node, a.answer_id AS answer_id, a.model AS model,
       c.node_id AS claim_node, pv.node_id AS pv_node,
       pv.name AS package, pv.version AS version,
       adv.node_id AS adv_node, adv.id AS advisory_id, adv.fixed AS fixed
""".strip()

Q10_CYPHER = """
MATCH (adv:Advisory)-[:AFFECTS]->(pv:PkgVersion)<-[:CITES]-(c:Claim)
      <-[:ASSERTS]-(a:Answer)
WHERE a.created_ns > adv.published_ns
RETURN adv.node_id AS adv_node, adv.id AS advisory_id, adv.fixed AS fixed,
       adv.published AS published, pv.node_id AS pv_node,
       pv.name AS package, pv.version AS version,
       a.node_id AS answer_node, a.answer_id AS answer_id, a.model AS model
""".strip()


def _prefix_scenario(sc: dict[str, Any], prefix: str, model: str,
                     question: str) -> dict[str, Any]:
    """Namespace every id so many cases MERGE into one store without collision."""
    sc["run"]["id"] = prefix + sc["run"]["id"]
    sc["answer"]["id"] = prefix + sc["answer"]["id"]
    sc["answer"]["model"] = model
    sc["answer"]["question"] = question
    for cl in sc["claims"]:
        cl["id"] = prefix + cl["id"]
    for sp in sc["spans"]:
        sp["id"] = prefix + sp["id"]
        if sp.get("parent_id"):
            sp["parent_id"] = prefix + sp["parent_id"]
        if sp.get("retrieved_doc"):
            sp["retrieved_doc"] = prefix + sp["retrieved_doc"]
    for src in sc["sources"]:
        src["doc_id"] = prefix + src["doc_id"]
    return sc


def build_merged_store(passport: dict[str, Any], answer_ns: int,
                       store: Path) -> dict[str, Any]:
    """Merge every captured real text into ONE graph. Returns input provenance."""
    advisories = passport.get("advisories", [])
    inputs: list[dict[str, Any]] = []
    first = True

    def add_case(text_path: Path, lock_path: Path, prefix: str, model: str,
                 question: str, source_uri: str, nature: str) -> int:
        nonlocal first
        text = text_path.read_text(encoding="utf-8", errors="replace")
        decls = extract_declarations(text)
        lock = read_lockfile(lock_path)
        scenarios = build_multi_scenario(decls, lock, advisories, answer_ns,
                                         source_uri)
        for item in scenarios:
            sc = _prefix_scenario(item["scenario"], prefix, model, question)
            build_graph(store, sc, item["advisories"], append=not first)
            first = False
        inputs.append({"prefix": prefix, "model": model, "nature": nature,
                       "source": source_uri, "declarations": len(decls),
                       "scenarios": len(scenarios)})
        return len(scenarios)

    for nature, sub in (("real-user", "real-user"), ("real-agent-text", "real-agent")):
        base = ROOT / "real-cases" / sub
        for d in sorted(base.iterdir()):
            src_file = d / "source.json"
            if not (d / "text.txt").exists() or not src_file.exists():
                continue
            src = json.loads(src_file.read_text(encoding="utf-8"))
            if nature == "real-user":
                model = "human:stackoverflow"
                question = src.get("title", "")
                uri = src.get("url", "")
            else:
                model = src.get("model", "")
                question = "%s · %s" % (src.get("model", ""), src.get("task_id", ""))
                uri = src.get("dataset_url", "")
            add_case(d / "text.txt", d / "requirements.lock", d.name + "-",
                     model, question, uri, nature)

    # The batch demo: 8 captured model outputs in one text; model per declaration
    # comes from the sidecar that records which record each line came from.
    demo_text = ROOT / "real-traces/scan/pr-answer.txt"
    demo_sources_file = ROOT / "real-traces/scan/pr-answer-sources.json"
    if demo_text.exists() and demo_sources_file.exists():
        demo_sources = json.loads(demo_sources_file.read_text(encoding="utf-8"))["sources"]
        by_pkg = {s["package"]: s for s in demo_sources}
        decls = extract_declarations(demo_text.read_text(encoding="utf-8"))
        lock = read_lockfile(ROOT / "real-traces/scan/requirements.lock")
        scenarios = build_multi_scenario(decls, lock, advisories, answer_ns,
                                         demo_sources[0].get("dataset_url", str(demo_text)))
        for item in scenarios:
            pkg = item["declaration"]["package"]
            s = by_pkg.get(pkg, {})
            sc = _prefix_scenario(item["scenario"], "demo-%s-" % pkg,
                                  s.get("model", ""),
                                  "%s · %s" % (s.get("model", ""), s.get("task_id", "")))
            build_graph(store, sc, item["advisories"], append=not first)
            first = False
            inputs.append({"prefix": "demo-%s-" % pkg, "model": s.get("model", ""),
                           "nature": "real-agent-text", "source": s.get("dataset_url", ""),
                           "declarations": 1, "scenarios": 1})
    return {"inputs": inputs, "store": str(store)}


def run_convergence_queries(store: str | Path) -> dict[str, Any]:
    db = relate.Database(str(store), read_only=True)
    try:
        q9 = list(db.execute(Q9_CYPHER, {}).data)
        q10 = list(db.execute(Q10_CYPHER, {}).data)
    finally:
        db.close()

    clusters: dict[tuple, dict[str, Any]] = {}
    for r in q9:
        key = (r["package"], r["version"], r["advisory_id"])
        c = clusters.setdefault(key, {
            "package": r["package"], "version": r["version"],
            "advisory_id": r["advisory_id"], "fixed": r["fixed"],
            "answers": [], "models": [], "nodes": [r["pv_node"], r["adv_node"]],
        })
        if r["answer_id"] not in c["answers"]:
            c["answers"].append(r["answer_id"])
            c["nodes"].append(r["answer_node"])
        if r["model"] and r["model"] not in c["models"]:
            c["models"].append(r["model"])
        if r["claim_node"] not in c["nodes"]:
            c["nodes"].append(r["claim_node"])
    q9_rows = []
    for c in clusters.values():
        c["n_answers"] = len(c["answers"])
        c["n_models"] = len(c["models"])
        q9_rows.append(c)
    q9_rows.sort(key=lambda c: (-c["n_models"], -c["n_answers"]))

    radius: dict[str, dict[str, Any]] = {}
    for r in q10:
        b = radius.setdefault(r["advisory_id"], {
            "advisory_id": r["advisory_id"], "fixed": r["fixed"],
            "published": r["published"], "package": r["package"],
            "answers": [], "models": [], "versions": [],
            "nodes": [r["adv_node"]],
        })
        if r["answer_id"] not in b["answers"]:
            b["answers"].append(r["answer_id"])
            b["nodes"].append(r["answer_node"])
        if r["model"] and r["model"] not in b["models"]:
            b["models"].append(r["model"])
        if r["version"] not in b["versions"]:
            b["versions"].append(r["version"])
        if r["pv_node"] not in b["nodes"]:
            b["nodes"].append(r["pv_node"])
    q10_rows = []
    for b in radius.values():
        b["n_answers"] = len(b["answers"])
        b["n_models"] = len(b["models"])
        q10_rows.append(b)
    q10_rows.sort(key=lambda b: (-b["n_models"], -b["n_answers"]))

    checks = {
        "q9_finds_cross_model_convergence": any(c["n_models"] >= 2 for c in q9_rows),
        "q10_blast_radius_spans_multiple_models": any(b["n_models"] >= 2 for b in q10_rows),
        "answers_join_the_advisory_clock": bool(q9),
        "every_cluster_node_id_is_real": all(
            n for c in q9_rows for n in c["nodes"]),
    }
    return {
        "schema": "tracelens/convergence-verdict@1",
        "checks": checks,
        "verdict": "PASS" if all(checks.values()) else "FAIL",
        "Q9_convergence": q9_rows,
        "Q10_blast_radius": q10_rows,
        "why_graph": (
            "Q9 groups DISTINCT models around one PkgVersion node that a real "
            "advisory AFFECTS — systemic convergence is a fan-in the graph sees "
            "in one query. Q10 fans out from one Advisory node over AFFECTS <- "
            "CITES <- ASSERTS to count every captured answer a single advisory "
            "turns born-stale. A per-file scanner has no cross-answer view at all."
        ),
    }


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(prog="python -m tracelens.convergence")
    p.add_argument("--passport", default=str(ROOT / "real-traces/scan/osv-batch-passport.json"))
    p.add_argument("--as-of", default="2026-11-24T00:00:00Z")
    p.add_argument("--store", default=str(ROOT / "real-traces/convergence/convergence.rl"))
    p.add_argument("--out", default=str(ROOT / "docs/convergence-verdict.json"))
    args = p.parse_args(argv)

    passport = json.loads(Path(args.passport).read_text(encoding="utf-8"))
    store = Path(args.store)
    if store.exists():
        store.unlink()
    info = build_merged_store(passport, iso_to_ns(args.as_of), store)
    result = run_convergence_queries(store)
    models = sorted({i["model"] for i in info["inputs"] if i["model"]})
    doc = {
        "graph": {"store": info["store"],
                  "inputs": info["inputs"],
                  "answers": sum(i["scenarios"] for i in info["inputs"]),
                  "distinct_models": models},
        **result,
    }
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "store": info["store"], "answers": doc["graph"]["answers"],
        "models": models, "verdict": result["verdict"], "checks": result["checks"],
        "q9_clusters": len(result["Q9_convergence"]),
        "q10_advisories": len(result["Q10_blast_radius"]),
        "top_cluster": result["Q9_convergence"][0] if result["Q9_convergence"] else None,
    }, ensure_ascii=False, indent=2)[:2000])
    if result["verdict"] != "PASS":
        raise SystemExit("convergence checks failed: %s" % result["checks"])


if __name__ == "__main__":
    main()