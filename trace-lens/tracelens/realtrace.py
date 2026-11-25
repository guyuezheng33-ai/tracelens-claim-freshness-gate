"""Real agent trace intake with a provenance gate.

Synthetic fixtures are the control group, never the conclusion. This module
accepts a real OTel/OTLP JSON export, checks that it carries the signals a
trace diagnosis needs (real nanosecond timestamps, non-zero durations, tool
calls or retrieval events), and writes a passport that records where it came
from and what it may be used for.

Nothing here invents data: if the export lacks the required structure the
intake FAILS with a named reason, rather than degrading into a fixture.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REAL_DIR = ROOT / "real-traces"

PASSPORT_SCHEMA = "tracelens/real-trace-passport@1"
REQUIRED_CAVEAT = "self-run"  # must be stated, so nobody mistakes it for customer data


def sha256_file(path: str | Path) -> str:
    h = hashlib.sha256()
    with Path(path).open("rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _iter_spans(doc: dict):
    for resource in doc.get("resourceSpans", []) or []:
        if not isinstance(resource, dict):
            continue
        for scope in resource.get("scopeSpans", []) or []:
            if not isinstance(scope, dict):
                continue
            for span in scope.get("spans", []) or []:
                if isinstance(span, dict) and span.get("spanId"):
                    yield span


def inspect(doc: dict) -> dict:
    """Structural check of a real OTLP export. Returns a report, never raises."""
    spans = list(_iter_spans(doc)) if isinstance(doc, dict) else []
    if not spans:
        return {"ok": False, "reason": "no spans in resourceSpans[].scopeSpans[].spans[]",
                "spans": 0, "checks": {}}

    def _nonzero(span: dict, key: str) -> bool:
        raw = span.get(key)
        if raw in (None, "", 0, "0"):
            return False
        try:
            return int(raw) > 0
        except (TypeError, ValueError):
            return False

    timed = [s for s in spans if _nonzero(s, "startTimeUnixNano") and _nonzero(s, "endTimeUnixNano")]
    durations = []
    for s in timed:
        try:
            d = (int(s["endTimeUnixNano"]) - int(s["startTimeUnixNano"])) / 1_000_000
            durations.append(d)
        except (TypeError, ValueError, KeyError):
            pass
    positive_duration = [d for d in durations if d > 0]
    parents = sum(1 for s in spans if s.get("parentSpanId"))
    events = sum(len(s.get("events", []) or []) for s in spans)
    named_events = {
        e.get("name")
        for s in spans for e in (s.get("events", []) or [])
        if isinstance(e, dict) and e.get("name")
    }
    has_tool = any("tool" in str(n).lower() for n in named_events)
    has_retrieval = any("retriev" in str(n).lower() for n in named_events)

    checks = {
        "spans_present": len(spans) > 0,
        "real_timestamps": len(timed) == len(spans),
        "positive_durations": len(positive_duration) >= 1,
        "has_parent_edges": parents > 0,
        "has_events": events > 0,
        "has_tool_or_retrieval": has_tool or has_retrieval,
    }
    reason = ""
    if not checks["real_timestamps"]:
        reason = "some spans lack real unix-nanosecond timestamps"
    elif not checks["positive_durations"]:
        reason = "no span has a positive duration"
    elif not checks["has_parent_edges"]:
        reason = "no parentSpanId: trace is a flat list, not an agent run"
    elif not checks["has_tool_or_retrieval"]:
        reason = "no tool/retrieval event: nothing to diagnose as evidence path"
    return {
        "ok": all(checks.values()),
        "reason": reason,
        "spans": len(spans),
        "timed_spans": len(timed),
        "parents": parents,
        "events": events,
        "event_names": sorted(named_events),
        "checks": checks,
    }


def write_passport(source: str | Path, doc: dict, report: dict,
                   *, origin: str, caveat: str, out: str | Path | None = None) -> Path:
    """Write the real-trace passport. Fails loudly if caveat hides self-run status."""
    if not report.get("ok"):
        raise ValueError("refuse to passport a trace that failed intake: %s" % report.get("reason"))
    if REQUIRED_CAVEAT not in caveat.lower():
        raise ValueError("caveat must state '%s' so real data is not mistaken for customer data" % REQUIRED_CAVEAT)
    src = Path(source)
    dest = Path(out) if out else REAL_DIR / (src.stem + ".meta.json")
    dest.parent.mkdir(parents=True, exist_ok=True)
    passport = {
        "schema": PASSPORT_SCHEMA,
        "nature": "real",
        "source_file": src.name,
        "sha256": sha256_file(src),
        "origin": origin,
        "caveat": caveat,
        "intake": report,
        "allowed_use": "对外结论可用；不得声称来自付费客户或生产流量",
    }
    dest.write_text(json.dumps(passport, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return dest


def verify_passport(source: str | Path, passport_path: str | Path) -> dict:
    """Recompute the hash and check provenance fields. Used by tests and CLI."""
    p = json.loads(Path(passport_path).read_text(encoding="utf-8"))
    expected = sha256_file(source)
    checks = {
        "schema_ok": p.get("schema") == PASSPORT_SCHEMA,
        "nature_real": p.get("nature") == "real",
        "hash_ok": p.get("sha256") == expected,
        "origin_present": bool(str(p.get("origin", "")).strip()),
        "caveat_self_run": REQUIRED_CAVEAT in str(p.get("caveat", "")).lower(),
        "intake_ok": bool((p.get("intake") or {}).get("ok")),
    }
    return {"ok": all(checks.values()), "checks": checks, "sha256": expected}
