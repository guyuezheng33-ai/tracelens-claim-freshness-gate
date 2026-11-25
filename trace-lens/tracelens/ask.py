"""Ask the REAL store anything: read-only Cypher console for judges.

The explorer is a guided view; this is the unguided one. A judge can run any
Cypher against any persisted ``.rl`` store and read the raw rows back:

    python -m tracelens.ask --store real-traces/scan/scan.rl \
        --cypher "MATCH (a:Answer)-[:ASSERTS]->(c:Claim)-[:CITES]->(v) RETURN a.answer_id, v.name, v.version"

Read-only by construction: the database is opened with read_only=True, and the
command refuses anything that is not a read query, so a judge cannot mutate the
evidence store by accident. No network, no fixtures: rows come from the store.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

import relate

ROOT = Path(__file__).resolve().parent.parent

_WRITE = re.compile(
    r"\b(CREATE|MERGE|SET|DELETE|DETACH|REMOVE|DROP|LOAD\s+CSV|CALL)\b",
    re.IGNORECASE)


def ask(store: str | Path, cypher: str, limit: int = 200) -> dict[str, Any]:
    text = cypher.strip().rstrip(";")
    if _WRITE.search(text):
        raise ValueError("read-only console: write clauses are not allowed")
    if not re.match(r"^\s*(MATCH|RETURN|WITH|UNWIND|OPTIONAL)\b", text, re.IGNORECASE):
        raise ValueError("read-only console: query must start with MATCH/RETURN/WITH/UNWIND")
    db = relate.Database(str(store), read_only=True)
    try:
        rows = list(db.execute(text, {}).data)
        total = len(rows)
        return {
            "schema": "tracelens/ask-result@1",
            "store": str(store),
            "cypher": text,
            "row_count": total,
            "returned": min(total, limit),
            "rows": rows[:limit],
            "node_count": db.node_count(),
            "relationship_count": db.relationship_count(),
        }
    finally:
        db.close()


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(prog="python -m tracelens.ask")
    p.add_argument("--store", required=True, help="persisted Relate .rl store")
    p.add_argument("--cypher", required=True, help="read-only Cypher query")
    p.add_argument("--limit", type=int, default=200)
    p.add_argument("--out", default=None, help="optional JSON output path")
    args = p.parse_args(argv)
    result = ask(args.store, args.cypher, args.limit)
    text = json.dumps(result, ensure_ascii=False, indent=2, default=str)
    if args.out:
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text + "\n", encoding="utf-8")
    print(text[:4000])


if __name__ == "__main__":
    main()