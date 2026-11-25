"""Real-scale, traceable vulnerability graph built from the OSV.dev public API.

This is an independent data source: it does NOT go through TraceLens's run
schema and does NOT touch fixtures. Every node is derived from a real HTTP
response and every Vuln carries a public URL, so the resulting store is
connection-context evidence rather than another synthetic demo.

Nothing here fabricates data. If the network or the API fails, or if the
collected real records do not reach ``min_nodes``, the build FAILS loudly.

Reusable entry points::

    snapshot = fetch_snapshot(packages, min_nodes)   # real HTTPS via urllib
    passport = build_graph(snapshot, store)          # relate store + passport

CLI::

    python -m tracelens.realgraph --out-dir <dir> [--min-nodes 500] [--packages a,b,c]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import urllib.error
import urllib.request
from collections.abc import Iterable
from pathlib import Path
from typing import Any

import relate

# ---------------------------------------------------------------------------
# Provenance constants
# ---------------------------------------------------------------------------
OSV_ENDPOINT = "https://api.osv.dev/v1/query"
OSV_VULN_URL = "https://osv.dev/vulnerability/"
SOURCE = "OSV.dev public API"
SNAPSHOT_SCHEMA = "tracelens/osv-snapshot@1"
PASSPORT_SCHEMA = "tracelens/real-osv-graph-passport@1"
ECOSYSTEM = "PyPI"
USER_AGENT = "TraceLens-RealGraph/1.0 (Neo4j hackathon provenance evidence)"

# Real PyPI package names. OSV returns dozens-to-hundreds of advisories each.
DEFAULT_PACKAGES = [
    "requests", "urllib3", "django", "flask", "cryptography", "pillow",
    "numpy", "pandas", "setuptools", "pyyaml", "jinja2", "sqlalchemy",
    "openssl",
]
# Only used if DEFAULT_PACKAGES cannot reach min_nodes (insurance, never filler).
EXTRA_PACKAGES = [
    "aiohttp", "tensorflow", "scikit-learn", "matplotlib", "pytest",
    "redis", "psutil", "opencv-python", "transformers", "beautifulsoup4",
]

# Raw response fields retained in the compact snapshot (nothing invented).
KEEP_FIELDS = (
    "id", "summary", "aliases", "references", "published", "modified",
    "database_specific",
)

CAVEAT = (
    "公开漏洞数据库数据（OSV.dev / GitHub Advisory / NVD 等公开来源），"
    "非客户数据、非生产流量、非 agent trace；仅用作真实规模与连接上下文的"
    "可溯源证据，不代表任何真实客户的系统或运行结果。"
)

_BATCH = 500


# ---------------------------------------------------------------------------
# Serialization helpers (shared by CLI and build_graph so hashes agree)
# ---------------------------------------------------------------------------
def canonical_json(snapshot: dict) -> bytes:
    """Deterministic, compact JSON bytes. The on-disk 'compressed snapshot'."""
    return json.dumps(
        snapshot, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def sha256_file(path: str | Path) -> str:
    h = hashlib.sha256()
    with Path(path).open("rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


# ---------------------------------------------------------------------------
# Fetch: real HTTPS only
# ---------------------------------------------------------------------------
def _post_json(url: str, payload: dict, timeout: float = 45.0) -> tuple[int, dict]:
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json", "User-Agent": USER_AGENT},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            status = int(resp.getcode())
            raw = resp.read()
    except urllib.error.HTTPError as exc:
        raise RuntimeError(
            "OSV query failed: HTTP %s from %s (%s)"
            % (exc.code, url, exc.reason)
        ) from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise RuntimeError(
            "OSV query failed: cannot reach %s: %s" % (url, exc)
        ) from exc
    try:
        data = json.loads(raw)
    except (ValueError, UnicodeDecodeError) as exc:
        raise RuntimeError("OSV query failed: invalid JSON from %s: %s" % (url, exc)) from exc
    if not isinstance(data, dict):
        raise RuntimeError("OSV query failed: expected a JSON object from %s" % url)  # noqa: TRY004 - remote malformed response
    return status, data


def _project(raw: dict) -> dict:
    """Keep only KEEP_FIELDS from a genuine OSV record, with stable types."""
    rec: dict[str, Any] = {}
    for field in KEEP_FIELDS:
        value = raw.get(field)
        if field == "aliases":
            rec[field] = [str(x) for x in (value or []) if str(x).strip()]
        elif field == "references":
            refs = []
            for item in (value or []):
                if isinstance(item, dict) and str(item.get("url") or "").strip():
                    refs.append({
                        "type": str(item.get("type") or "WEB"),
                        "url": str(item["url"]).strip(),
                    })
            rec[field] = refs
        elif field == "database_specific":
            rec[field] = value if isinstance(value, dict) else {}
        elif field == "id":
            rec[field] = "" if value is None else str(value).strip()
        else:
            rec[field] = "" if value is None else str(value)
    return rec


def _id_key(rec: dict) -> str | None:
    """Canonical dedup key: the primary ID plus all aliases of one advisory."""
    ids = {rec["id"]} | set(rec["aliases"])
    ids = {x for x in ids if x}
    return "||".join(sorted(ids)) if ids else None


def _merge(existing: dict, incoming: dict) -> None:
    """Fold a duplicate advisory's real URLs/aliases into the kept record."""
    for alias in incoming["aliases"]:
        if alias not in existing["aliases"]:
            existing["aliases"].append(alias)
    for ref in incoming["references"]:
        if ref not in existing["references"]:
            existing["references"].append(ref)
    for field in ("summary", "published", "modified", "database_specific"):
        if not existing.get(field) and incoming.get(field):
            existing[field] = incoming[field]


def fetch_snapshot(packages: list[str], min_nodes: int) -> dict:
    """Fetch genuine OSV records until ``min_nodes`` distinct advisories exist.

    Uses only the standard library. A network/API failure raises RuntimeError;
    if real data is insufficient it raises instead of inventing filler.
    """
    if not packages:
        raise ValueError("packages must not be empty")
    if min_nodes < 1:
        raise ValueError("min_nodes must be >= 1")

    kept: dict[str, dict] = {}
    commands: list[dict[str, Any]] = []
    queue = list(packages) + [p for p in EXTRA_PACKAGES if p not in packages]

    for pkg in queue:
        if len(kept) >= min_nodes:
            break
        payload = {"package": {"name": pkg, "ecosystem": ECOSYSTEM}}
        status, data = _post_json(OSV_ENDPOINT, payload)
        raw_vulns = data.get("vulns") or []
        if not isinstance(raw_vulns, list):
            raise RuntimeError("OSV query failed: 'vulns' is not a list for %s" % pkg)  # noqa: TRY004 - remote malformed response
        new_before = len(kept)
        for raw in raw_vulns:
            if not isinstance(raw, dict):
                continue
            rec = _project(raw)
            key = _id_key(rec)
            if key is None:
                continue
            if key in kept:
                _merge(kept[key], rec)
            else:
                kept[key] = rec
        commands.append({
            "method": "POST",
            "url": OSV_ENDPOINT,
            "package": pkg,
            "ecosystem": ECOSYSTEM,
            "request_body": payload,
            "http_status": status,
            "vulns_returned": len(raw_vulns),
            "new_distinct_advisories": len(kept) - new_before,
        })

    if len(kept) < min_nodes:
        raise RuntimeError(
            "OSV returned only %d distinct real advisories from %d packages; "
            "need >= %d. Refusing to fabricate data."
            % (len(kept), len(commands), min_nodes)
        )

    return {
        "schema": SNAPSHOT_SCHEMA,
        "source": SOURCE,
        "endpoint": OSV_ENDPOINT,
        "ecosystem": ECOSYSTEM,
        "min_nodes_target": min_nodes,
        "query_commands": commands,
        "vuln_count": len(kept),
        "vulns": list(kept.values()),
    }


# ---------------------------------------------------------------------------
# Graph build
# ---------------------------------------------------------------------------
def _severity(rec: dict) -> str:
    """Real qualitative severity from database_specific, never guessed."""
    ds = rec.get("database_specific") or {}
    if isinstance(ds, dict):
        value = ds.get("severity")
        if value:
            return str(value)
    return "UNSPECIFIED"


def _public_url(rec: dict) -> str:
    """A public OSV/NVD/GitHub URL taken from references (fallback = OSV id page)."""
    for ref in rec.get("references") or []:
        url = str(ref.get("url") or "")
        if url.lower().startswith(("http://", "https://")):
            return url
    return OSV_VULN_URL + rec["id"]


def _chunks(seq: list, size: int = _BATCH) -> Iterable[list]:
    for i in range(0, len(seq), size):
        yield seq[i:i + size]


def _scalar_cypher(db: Any, cypher: str) -> int:
    rows = list(db.execute(cypher, {}).data)
    return int(rows[0]["c"]) if rows else 0


def build_graph(snapshot: dict, store: Path) -> dict:
    """Build an independent relate graph from a real OSV snapshot.

    Returns the passport dict. Idempotent: re-running MERGEs the same nodes.
    ``is_readonly`` gates are irrelevant here -- this is a separate, private
    data source, not a TraceLens read session.
    """
    store = Path(store)
    store.parent.mkdir(parents=True, exist_ok=True)
    vulns = snapshot.get("vulns")
    if not isinstance(vulns, list) or not vulns:
        raise ValueError("snapshot contains no vulns; refusing to build an empty graph")

    vuln_rows: list[dict[str, str]] = []
    alias_rows: list[dict[str, str]] = []
    ref_rows: list[dict[str, str]] = []
    has_alias: list[dict[str, str]] = []
    vuln_refs: list[dict[str, str]] = []
    alias_refs: list[dict[str, str]] = []
    seen_aliases: set[str] = set()
    seen_urls: set[str] = set()

    for rec in vulns:
        if not isinstance(rec, dict):
            continue
        vid = str(rec.get("id") or "").strip()
        if not vid:
            continue
        url = _public_url(rec)
        vuln_rows.append({
            "id": vid,
            "summary": str(rec.get("summary") or "")[:1000],
            "severity": _severity(rec),
            "published": str(rec.get("published") or ""),
            "url": url,
        })

        aliases = [str(a).strip() for a in (rec.get("aliases") or []) if str(a).strip()]
        urls: list[str] = []
        for ref in rec.get("references") or []:
            candidate = str(ref.get("url") or "").strip()
            if candidate.lower().startswith(("http://", "https://")) and candidate not in urls:
                urls.append(candidate)
        # The public URL recorded on the Vuln is always a real Ref node too.
        if url not in urls:
            urls.append(url)
        for u in urls:
            if u not in seen_urls:
                seen_urls.add(u)
                ref_rows.append({"url": u})
            vuln_refs.append({"a": vid, "b": u})

        for alias in aliases:
            if alias not in seen_aliases:
                seen_aliases.add(alias)
                # Namespace the Alias key: an alias string can equal another
                # Vuln's id (e.g. a GHSA that is both fetched and aliased).
                # Without the prefix two different nodes would share one id
                # and the export/explorer could not tell them apart.
                alias_rows.append({"id": "alias:" + alias, "alias": alias})
            has_alias.append({"a": vid, "b": "alias:" + alias})
            for u in urls:
                alias_refs.append({"a": "alias:" + alias, "b": u})

    if not vuln_rows:
        raise ValueError("no usable vulnerability records in snapshot")

    db = relate.Database(str(store))
    try:
        for rows in _chunks(vuln_rows):
            db.execute(
                "UNWIND $rows AS r MERGE (v:Vuln {id: r.id}) "
                "SET v.summary = r.summary, v.severity = r.severity, "
                "v.published = r.published, v.url = r.url",
                {"rows": rows},
            )
        for rows in _chunks(alias_rows):
            db.execute("UNWIND $rows AS r MERGE (a:Alias {id: r.id}) "
                       "SET a.alias = r.alias", {"rows": rows})
        for rows in _chunks(ref_rows):
            db.execute("UNWIND $rows AS r MERGE (x:Ref {url: r.url})", {"rows": rows})
        for rows in _chunks(has_alias):
            db.execute(
                "UNWIND $rows AS r MATCH (v:Vuln {id: r.a}), (a:Alias {id: r.b}) "
                "MERGE (v)-[e:HAS_ALIAS]->(a)",
                {"rows": rows},
            )
        for rows in _chunks(vuln_refs):
            db.execute(
                "UNWIND $rows AS r MATCH (v:Vuln {id: r.a}), (x:Ref {url: r.b}) "
                "MERGE (v)-[e:REFERENCES]->(x)",
                {"rows": rows},
            )
        for rows in _chunks(alias_refs):
            db.execute(
                "UNWIND $rows AS r MATCH (a:Alias {id: r.a}), (x:Ref {url: r.b}) "
                "MERGE (a)-[e:REFERENCES]->(x)",
                {"rows": rows},
            )
        db.flush()

        node_count = _scalar_cypher(db, "MATCH (n) RETURN count(n) AS c")
        relationship_count = _scalar_cypher(db, "MATCH ()-[r]->() RETURN count(r) AS c")
        vuln_count = _scalar_cypher(db, "MATCH (v:Vuln) RETURN count(v) AS c")
        with_url = _scalar_cypher(
            db,
            "MATCH (v:Vuln) WHERE v.url IS NOT NULL AND v.url <> '' "
            "RETURN count(v) AS c",
        )
    finally:
        db.close()

    if vuln_count == 0:
        raise RuntimeError("graph has no Vuln nodes")
    url_coverage = round(with_url / vuln_count, 6)

    # The CLI writes the snapshot bytes first, then stores the file hash in
    # snapshot['sha256']; a dict built in-memory still gets a deterministic hash.
    snapshot_hash = snapshot.get("sha256") or sha256_bytes(canonical_json(snapshot))

    passport = {
        "schema": PASSPORT_SCHEMA,
        "nature": "real-public",
        "source": SOURCE,
        "endpoint": OSV_ENDPOINT,
        "ecosystem": ECOSYSTEM,
        "query_commands": snapshot.get("query_commands") or [],
        "sha256": str(snapshot_hash),
        "node_count": node_count,
        "relationship_count": relationship_count,
        "vuln_count": vuln_count,
        "url_coverage": url_coverage,
        "caveat": CAVEAT,
        "graph_model": (
            "(:Vuln {id,summary,severity,published,url})-[:HAS_ALIAS]->"
            "(:Alias {id,alias})-[:REFERENCES]->(:Ref {url}); "
            "also (:Vuln)-[:REFERENCES]->(:Ref) for direct provenance"
        ),
        "store": str(store),
        "allowed_use": "可用作真实规模与连接上下文证据；不得声称来自客户数据或 agent trace",
    }
    return passport


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Build a real OSV.dev vulnerability graph with a provenance passport."
    )
    parser.add_argument("--out-dir", required=True, help="directory for all output artifacts")
    parser.add_argument("--min-nodes", type=int, default=500,
                        help="minimum number of distinct real advisories to fetch (default 500)")
    parser.add_argument("--packages", default=None,
                        help="comma-separated PyPI package names (default: built-in real package list)")
    args = parser.parse_args(argv)

    packages = (
        [p.strip() for p in args.packages.split(",") if p.strip()]
        if args.packages else list(DEFAULT_PACKAGES)
    )
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    try:
        snapshot = fetch_snapshot(packages, args.min_nodes)
    except (RuntimeError, ValueError) as exc:
        print("ERROR: %s" % exc, file=sys.stderr)
        return 2

    snapshot_path = out_dir / "osv-snapshot.json"
    snapshot_path.write_bytes(canonical_json(snapshot))
    snapshot["sha256"] = sha256_file(snapshot_path)

    store_path = out_dir / "osv-graph.rl"
    # Regenerate cleanly: stale records from a previous smaller run would
    # otherwise inflate the counts reported in the passport.
    if store_path.exists():
        store_path.unlink()

    try:
        passport = build_graph(snapshot, store_path)
    except (RuntimeError, ValueError) as exc:
        print("ERROR: %s" % exc, file=sys.stderr)
        return 3

    passport_path = out_dir / "osv-passport.json"
    passport_path.write_text(
        json.dumps(passport, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    print(json.dumps({
        "out_dir": str(out_dir),
        "snapshot": str(snapshot_path),
        "store": str(store_path),
        "passport": str(passport_path),
        "node_count": passport["node_count"],
        "relationship_count": passport["relationship_count"],
        "vuln_count": passport["vuln_count"],
        "url_coverage": passport["url_coverage"],
        "source": passport["source"],
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
