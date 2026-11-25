"""Real failure case pack: validate, render and expose developer-session evidence.

Each case is a failure that actually happened while building this product. The
pack is deliberately not an agent trace: it documents why the graph diagnosis
exists. Claims are checked structurally (symptom -> graph evidence -> fix ->
after -> reproduce) so an empty narrative cannot pass as a case.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CASES = ROOT / "real-cases" / "cases.json"
REQUIRED_FIELDS = (
    "case_id", "title", "symptom", "root_cause", "graph_evidence",
    "fix", "after", "reproduce", "source", "customer",
)


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def load(path: str | Path = DEFAULT_CASES) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def validate(doc: dict[str, Any]) -> dict[str, Any]:
    """Reject incomplete or mislabelled cases. Returns a structured check."""
    cases = doc.get("cases") or []
    errors: list[str] = []
    for i, case in enumerate(cases):
        for field in REQUIRED_FIELDS:
            value = case.get(field)
            if value is None or (isinstance(value, str) and not value.strip()):
                errors.append("case[%d].%s missing" % (i, field))
        if case.get("customer") is not False:
            errors.append("case[%d].customer must be false (no customer)" % i)
        if "graph" not in str(case.get("graph_evidence", "")).lower() and \
           "Q" not in str(case.get("graph_evidence", "")):
            errors.append("case[%d].graph_evidence has no graph reference" % i)
    if len(cases) < 3:
        errors.append("at least 3 real failures are required")
    ids = [c.get("case_id") for c in cases]
    if len(ids) != len(set(ids)):
        errors.append("duplicate case_id")
    caveat = str(doc.get("caveat", "")).lower()
    if not any(k in caveat for k in ("self-run", "developer", "non-customer",
                                     "not customer", "public")):
        errors.append("caveat must state non-customer origin")
    return {
        "ok": not errors,
        "errors": errors,
        "case_count": len(cases),
        "nature": doc.get("nature"),
        "sha256": None,
    }


def markdown(doc: dict[str, Any]) -> str:
    lines = [
        "# 真实失败案例集",
        "",
        "> %s" % doc.get("caveat", ""),
        "",
        "共 %d 条。每条都按「症状 → 图证据 → 修复 → 修复后 → 复现命令」记录。" % len(doc.get("cases", [])),
        "",
    ]
    for case in doc.get("cases", []):
        lines += [
            "## %s %s" % (case["case_id"], case["title"]),
            "",
            "- **症状**：%s" % case["symptom"],
            "- **根因**：%s" % case["root_cause"],
            "- **图证据**：%s" % case["graph_evidence"],
            "- **修复**：%s" % case["fix"],
            "- **修复后**：%s" % case["after"],
            "- **复现**：`%s`" % case["reproduce"],
            "- **来源**：%s" % case["source"],
            "",
        ]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(prog="python -m tracelens.realcases")
    p.add_argument("--input", default=str(DEFAULT_CASES))
    p.add_argument("--md", default=None, help="optional Markdown output path")
    p.add_argument("--out", default=None, help="optional validation JSON output path")
    args = p.parse_args(argv)

    src = Path(args.input)
    doc = load(src)
    check = validate(doc)
    check["sha256"] = _sha256(src)
    if args.md:
        md = Path(args.md)
        md.parent.mkdir(parents=True, exist_ok=True)
        md.write_text(markdown(doc), encoding="utf-8")
    if args.out:
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(check, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(check, ensure_ascii=False, indent=2))
    if not check["ok"]:
        raise SystemExit(3)


if __name__ == "__main__":
    main()
