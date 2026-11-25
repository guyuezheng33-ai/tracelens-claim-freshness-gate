"""Answer Expiry: was an answer already stale on the day it was born?

This is the creative reconstruction of TraceLens. The official idea library
contains `agent-trace-warehouse` (where did the answer go wrong) and
`dependency-radar` (is this package affected), but no project joins them on
one timeline. Expiry adds the missing question:

    an agent answers at time T citing package P version V;
    the advisory for V was published at time T0 < T and the fix at T1 < T;
    the answer was therefore ALREADY wrong when it was produced.

The graph models validity in time, not just score:

    (:Answer {created_ns})-[:ASSERTS]->(:Claim)-[:CITES]->(:PkgVersion)
    (:Advisory {published_ns, osv_modified_ns, fix_available_ns, url})
        -[:AFFECTS]->(:PkgVersion)

Q5 walks Answer -> Claim -> PkgVersion <- Advisory and compares real
wall-clock answer time against real OSV timestamps. All times come from data,
never from constants in this file.

Field semantics (a previous version mislabelled ``osv_modified_ns`` as a fix
time; that is a category error and was corrected):

  * ``published_ns``    : when the advisory became public (real OSV published)
  * ``osv_modified_ns`` : when OSV last edited the record (NOT a fix time)
  * ``fix_available_ns``: when a fixed release first became available, read
                          from ``fix_available`` in the source record. When
                          the source has no such timestamp it is stored as the
                          sentinel -1 (unknown), never substituted with
                          ``modified``.

Stale rule: an answer is born-stale only if the advisory was public BEFORE the
answer AND a fixed release was already available BEFORE the answer (or its fix
time is genuinely unknown). A public advisory whose fix arrives AFTER the
answer does not make that answer born-stale: at birth there was no safe
version to pin. Clean is the exact complement of stale over all cited rows.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import relate

OSV_VULN = "https://api.osv.dev/v1/vulns/"
ROOT = Path(__file__).resolve().parent.parent
# Committed raw OSV records: verification runs offline-first. A cache hit is
# the same real record the live API returned when it was captured; the id is
# re-validated on every read. Live fetch remains the fallback for new ids.
RECORDS_DIR = ROOT / "real-traces" / "osv" / "records"

Q5_CYPHER = """
MATCH (a:Answer)-[:ASSERTS]->(c:Claim)-[:CITES]->(pv:PkgVersion)
MATCH (adv:Advisory)-[:AFFECTS]->(pv)
WHERE a.created_ns > adv.published_ns
  AND (adv.fix_available_ns < 0 OR a.created_ns >= adv.fix_available_ns)
RETURN a.answer_id AS answer_id, a.created_ns AS created_ns,
       c.claim_id AS claim_id, c.text AS claim_text,
       pv.name AS package, pv.version AS version,
       adv.id AS advisory_id, adv.published_ns AS published_ns,
       adv.fix_available_ns AS fix_available_ns, adv.url AS advisory_url,
       a.created_ns - adv.published_ns AS late_ns
ORDER BY late_ns DESC
""".strip()

# Clean is the exact complement of stale over every cited row: a version with
# no advisory, OR an advisory that was not yet public at answer time, OR a fix
# that had not yet shipped at answer time (no safe version existed to pin).
Q5_CLEAN_CYPHER = """
MATCH (a:Answer)-[:ASSERTS]->(c:Claim)-[:CITES]->(pv:PkgVersion)
OPTIONAL MATCH (adv:Advisory)-[:AFFECTS]->(pv)
WITH a, c, pv, adv
WHERE adv IS NULL
   OR a.created_ns <= adv.published_ns
   OR (adv.fix_available_ns >= 0 AND a.created_ns < adv.fix_available_ns)
RETURN DISTINCT a.answer_id AS answer_id, c.claim_id AS claim_id,
       pv.name AS package, pv.version AS version
""".strip()


def iso_to_ns(text: str) -> int:
    """Parse a real OSV/OTel ISO-8601 timestamp to nanoseconds."""
    dt = datetime.fromisoformat(text.replace("Z", "+00:00"))  # noqa: FURB162 - explicit Z->+00:00 keeps py3.10 compat
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return int(dt.timestamp() * 1_000_000_000)


def ns_to_iso(ns: int) -> str:
    return datetime.fromtimestamp(ns / 1_000_000_000, tz=UTC).isoformat()


def parse_version(text: str) -> tuple[int, ...]:
    """Numeric dotted version for range comparison; non-numeric -> zeros."""
    parts = re.findall(r"\d+", str(text))
    return tuple(int(p) for p in parts[:4]) if parts else (0,)


def fetch_advisory(advisory_id: str) -> dict[str, Any]:
    """Fetch a REAL OSV record including affected ranges. No fabrication.

    Offline-first: a committed capture under real-traces/osv/records/ is used
    when present (id re-validated), so `award-verify` needs no network. Unknown
    ids fall back to the live API.
    """
    cached = RECORDS_DIR / ("%s.json" % advisory_id)
    if cached.is_file():
        data = json.loads(cached.read_text(encoding="utf-8"))
        if data.get("id") != advisory_id:
            raise RuntimeError("OSV cache id mismatch: expected %s got %s"
                               % (advisory_id, data.get("id")))
        return data
    req = urllib.request.Request(OSV_VULN + advisory_id,
                                 headers={"Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=40) as resp:
        data = json.loads(resp.read().decode("utf-8", errors="replace"))
    if data.get("id") != advisory_id:
        raise RuntimeError("OSV id mismatch: expected %s got %s" % (advisory_id, data.get("id")))
    return data


def advisory_view(data: dict[str, Any]) -> dict[str, Any]:
    """Reduce a real OSV record to the fields the graph needs."""
    affected = data.get("affected") or []
    if not affected:
        raise RuntimeError("advisory %s has no affected versions" % data.get("id"))
    first = affected[0]
    pkg = first.get("package") or {}
    if not pkg.get("name"):
        raise RuntimeError("advisory %s has no affected package" % data.get("id"))
    fixed = ""
    for rng in first.get("ranges") or []:
        for ev in rng.get("events") or []:
            if ev.get("fixed"):
                fixed = str(ev["fixed"])
                break
        if fixed:
            break
    urls = [r.get("url") for r in data.get("references") or [] if r.get("url")]
    # A fix timestamp must come from a real "fix available" field in the data.
    # OSV's `modified` is when the record was last edited, NOT when a fixed
    # release shipped. Using `modified` as a fix time is a category error; when
    # no fix timestamp exists we keep the -1 sentinel (unknown) explicitly.
    fix_available = data.get("fix_available")
    return {
        "id": data["id"],
        "aliases": data.get("aliases") or [],
        "references": data.get("references") or [],
        "package": pkg.get("name"),
        "ecosystem": pkg.get("ecosystem"),
        "purl": pkg.get("purl"),
        "published": data.get("published"),
        "published_ns": iso_to_ns(data["published"]) if data.get("published") else 0,
        "fixed": fixed,
        "fix_available": fix_available,
        "fix_available_ns": iso_to_ns(fix_available) if fix_available else -1,
        # osv_modified_ns is OSV's last-edit clock, kept under its honest name.
        # It never enters the stale decision.
        "osv_modified_ns": iso_to_ns(data["modified"]) if data.get("modified") else 0,
        "modified": data.get("modified"),
        "url": urls[0] if urls else "https://osv.dev/vulnerability/%s" % data["id"],
        "summary": (data.get("summary") or "").strip(),
    }


def version_affected(view: dict[str, Any], version: str) -> bool:
    """Exact-affect decision from real advisory data, before the fix exists."""
    if not view.get("fixed"):
        return True
    return parse_version(version) < parse_version(view["fixed"])


def build_store(store: str | Path, advisories: list[dict[str, Any]],
                answers: list[dict[str, Any]]) -> dict[str, Any]:
    """Create the expiry graph from real advisory records and answer records."""
    path = Path(store)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        path.unlink()
    db = relate.Database(str(path))
    for adv in advisories:
        # The advisory node stores the fix version as metadata only. It must
        # NOT get an AFFECTS edge to that fixed version: doing so would mark
        # the safe release as vulnerable and make Q5 flag clean answers.
        db.execute("MERGE (a:Advisory {id:$id}) SET a.published_ns=$p, "
                   "a.osv_modified_ns=$m, a.fix_available_ns=$fa, "
                   "a.url=$u, a.published=$pd, a.fixed=$fx, a.summary=$s, a.ecosystem=$e",
                   {"id": adv["id"], "p": adv["published_ns"],
                    "m": adv["osv_modified_ns"], "fa": adv["fix_available_ns"],
                    "u": adv["url"], "pd": adv["published"], "fx": adv["fixed"],
                    "s": adv["summary"], "e": adv["ecosystem"]})
    for ans in answers:
        aid = ans["answer_id"]
        db.execute("MERGE (a:Answer {answer_id:$id}) SET a.created_ns=$t, a.question=$q",
                   {"id": aid, "t": ans["created_ns"], "q": ans.get("question", "")})
        for claim in ans.get("claims", []):
            cid = claim["claim_id"]
            db.execute("MERGE (c:Claim {claim_id:$id}) SET c.text=$t",
                       {"id": cid, "t": claim.get("text", "")})
            db.execute("MATCH (a:Answer {answer_id:$aid}), (c:Claim {claim_id:$cid}) "
                       "MERGE (a)-[:ASSERTS]->(c)", {"aid": aid, "cid": cid})
            pv = claim.get("package")
            if pv:
                ver = str(claim.get("version", ""))
                db.execute("MERGE (p:PkgVersion {name:$n, version:$v})",
                           {"n": pv, "v": ver})
                db.execute("MATCH (c:Claim {claim_id:$cid}), (p:PkgVersion {name:$n, version:$v}) "
                           "MERGE (c)-[:CITES]->(p)",
                           {"cid": cid, "n": pv, "v": ver})
                for adv in advisories:
                    if adv["package"] == pv and version_affected(adv, ver):
                        db.execute("MATCH (a:Advisory {id:$id}), "
                                   "(p:PkgVersion {name:$n, version:$v}) "
                                   "MERGE (a)-[:AFFECTS]->(p)",
                                   {"id": adv["id"], "n": pv, "v": ver})
    db.flush()
    nodes, edges = db.node_count(), db.relationship_count()
    db.close()
    return {"store": str(path), "nodes": nodes, "relationships": edges}


def run_q5(store: str | Path) -> dict[str, Any]:
    db = relate.Database(str(store), read_only=True)
    try:
        stale = list(db.execute(Q5_CYPHER, {}).data)
        clean = list(db.execute(Q5_CLEAN_CYPHER, {}).data)
    finally:
        db.close()
    return {
        "stale": stale,
        "clean": clean,
        "stale_count": len(stale),
        "clean_count": len(clean),
        "verdict": "PASS" if stale and clean else "FAIL",
    }


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(prog="python -m tracelens.expiry")
    sub = p.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build", help="build expiry graph from real OSV advisories")
    b.add_argument("--advisories", required=True, nargs="+", help="real OSV advisory ids")
    b.add_argument("--answers", required=True, help="JSON: answers with real created_ns")
    b.add_argument("--store", default=str(ROOT / "real-traces" / "expiry" / "expiry.rl"))
    b.add_argument("--out", default=str(ROOT / "real-traces" / "expiry" / "advisories.json"))
    q = sub.add_parser("query", help="run Q5 born-stale query")
    q.add_argument("--store", default=str(ROOT / "real-traces" / "expiry" / "expiry.rl"))
    q.add_argument("--out", default=None)
    args = p.parse_args(argv)

    if args.cmd == "build":
        views = []
        for aid in args.advisories:
            raw = fetch_advisory(aid)
            views.append(advisory_view(raw))
        doc = json.loads(Path(args.answers).read_text(encoding="utf-8"))
        answers = doc["answers"] if isinstance(doc, dict) and "answers" in doc else doc
        if not isinstance(answers, list):
            raise RuntimeError("answers file must contain a JSON list of answers")
        info = build_store(args.store, views, answers)
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps({
            "schema": "tracelens/expiry-advisories@1",
            "source": OSV_VULN,
            "advisories": views,
            "answers_file": str(args.answers),
            "answers_sha256": hashlib.sha256(Path(args.answers).read_bytes()).hexdigest(),
        }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(json.dumps({**info, "advisory_passport": str(out),
                          "advisories": [v["id"] for v in views]}, ensure_ascii=False, indent=2))
    else:
        result = run_q5(args.store)
        if args.out:
            out = Path(args.out)
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(json.dumps({k: result[k] for k in ("verdict", "stale_count", "clean_count")},
                         ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
