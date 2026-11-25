"""Context-connected proof: one graph serves both diagnosis and runtime control.

The competition dimension asks whether context is *connected*, not merely
stored. This module verifies that claim across three independent artefacts:

  1. the diagnostic store: all four query packs pass their own assertions;
  2. the runtime guardrail: admission decisions cite graph evidence and the
     model never releases a rejected claim;
  3. the real-scale public graph: nodes carry traceable public URLs.

If any of the three is missing or inconsistent the verdict is FAIL. Nothing is
inferred from documentation text.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import relate

from .querypacks import QUERIES, run_pack

ROOT = Path(__file__).resolve().parent.parent


def _load(path: str | Path | None) -> dict[str, Any] | None:
    if not path:
        return None
    p = Path(path)
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None


def verify(store: str | Path, guardrail_record: str | Path | None = None,
           realgraph_passport: str | Path | None = None,
           min_nodes: int = 500) -> dict[str, Any]:
    packs: dict[str, Any] = {}
    db = relate.Database(str(store), read_only=True)
    try:
        for key in ("Q1", "Q2", "Q3", "Q4"):
            rows = run_pack(db, key)
            packs[key] = {
                "rows": len(rows),
                "passed": bool(QUERIES[key]["assert"](rows)),
            }
    finally:
        db.close()

    guard = _load(guardrail_record)
    graph_decided = False
    model_no_override = False
    evidence_cited = False
    if guard:
        graph_decided = str(guard.get("decision_source", "")).startswith("graph only")
        model_no_override = bool(guard.get("model_cannot_release_rejected_claim"))
        evidence_cited = all(
            d.get("graph_reason") and isinstance(d.get("graph_evidence"), list)
            for d in guard.get("decisions", [])
        ) and bool(guard.get("decisions"))

    passport = _load(realgraph_passport)
    real_scale = False
    url_coverage = None
    node_count = None
    if passport:
        node_count = passport.get("node_count")
        url_coverage = passport.get("url_coverage")
        real_scale = (
            isinstance(node_count, int) and node_count >= min_nodes
            and url_coverage == 1.0
            and passport.get("nature") == "real-public"
        )

    checks = {
        "all_four_packs_assert_on_diagnostic_store": all(
            p["passed"] for p in packs.values()
        ) and len(packs) == 4,
        "guardrail_decision_is_graph_only": graph_decided,
        "model_cannot_release_rejected_claim": model_no_override,
        "every_decision_cites_graph_evidence": evidence_cited,
        "real_graph_is_traceable_at_scale": real_scale,
    }
    passed = all(checks.values())
    return {
        "schema": "tracelens/context-connected@1",
        "checks": checks,
        "packs": packs,
        "guardrail": {
            "present": bool(guard),
            "decision_source": guard.get("decision_source") if guard else None,
            "model": (guard or {}).get("passport", {}).get("model"),
        },
        "real_graph": {
            "present": bool(passport),
            "node_count": node_count,
            "url_coverage": url_coverage,
            "nature": passport.get("nature") if passport else None,
        },
        "passed": passed,
        "verdict": "PASS" if passed else "FAIL",
    }


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(prog="python -m tracelens.contextproof")
    p.add_argument("--store", required=True)
    p.add_argument("--guardrail", default=None)
    p.add_argument("--realgraph", default=None)
    p.add_argument("--out", required=True)
    p.add_argument("--min-nodes", type=int, default=500)
    args = p.parse_args(argv)

    record = verify(args.store, args.guardrail, args.realgraph, args.min_nodes)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"out": str(out), "verdict": record["verdict"],
                      "checks": record["checks"]}, ensure_ascii=False, indent=2))
    if not record["passed"]:
        raise SystemExit(4)


if __name__ == "__main__":
    main()
