"""Use case: pre-merge dependency-expiry check for AI-generated code.

The intended user is no longer "a hackathon entrant" (that is the judge).
It is a developer or student who accepts code from a coding agent and needs
to know, before merging, whether a cited dependency version was already
known-vulnerable when the agent produced that code.

This module turns the Q5 result into an actionable report: which claim is
stale, how long the advisory predates the answer, the public evidence URL,
and the concrete fix version. Every number is read from the run artefacts;
nothing is asserted from documentation.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent

USER = {
    "persona": "developer or student accepting code from a coding agent",
    "moment": "before merging the agent's suggestion",
    "question": "was the cited version already known-vulnerable when the agent answered?",
    "action": "reject the stale version and pin the advisory's fix version",
    "not_a_persona": ["hackathon entrant", "judge", "customer incidence"],
}


def days(ns: int) -> float:
    return round(ns / 1_000_000_000 / 86400, 2)


def render_report(q5: dict[str, Any], answers_doc: dict[str, Any],
                  advisory_doc: dict[str, Any]) -> dict[str, Any]:
    adv = {a["id"]: a for a in advisory_doc.get("advisories", [])}
    answers = answers_doc.get("answers", [])
    by_answer = {a["answer_id"]: a for a in answers}
    findings = []
    for row in q5.get("stale", []):
        meta = adv.get(row["advisory_id"], {})
        answer = by_answer.get(row["answer_id"], {})
        findings.append({
            "answer_id": row["answer_id"],
            "claim_id": row["claim_id"],
            "claim_text": row["claim_text"],
            "cited": "%s %s" % (row["package"], row["version"]),
            "known_vulnerable_since": meta.get("published"),
            "answer_created": answer.get("created_iso"),
            "advisory_aged_days_at_answer": days(int(row["late_ns"])),
            "public_evidence_url": row["advisory_url"] or meta.get("url"),
            "fix_version": meta.get("fixed"),
            "action": "reject %s; pin %s %s or later"
                      % (row["version"], row["package"], meta.get("fixed")),
        })
    clean = []
    for row in q5.get("clean", []):
        clean.append({
            "answer_id": row["answer_id"],
            "claim_id": row["claim_id"],
            "cited": "%s %s" % (row["package"], row["version"]),
            "status": "no advisory covers this version",
        })
    return {
        "schema": "tracelens/dependency-expiry-report@1",
        "user": USER,
        "summary": {
            "answers_checked": len(by_answer),
            "stale_claims": len(findings),
            "clean_claims": len(clean),
            "verdict": "PASS" if findings and clean else "FAIL",
        },
        "stale_findings": findings,
        "clean_findings": clean,
        "evidence": {
            "advisory_source": advisory_doc.get("source"),
            "advisory_ids": [a.get("id") for a in advisory_doc.get("advisories", [])],
            "answers_sha256": hashlib.sha256(
                json.dumps(answers, ensure_ascii=False, sort_keys=True).encode("utf-8")
            ).hexdigest(),
        },
    }


def markdown(report: dict[str, Any]) -> str:
    u = report["user"]
    s = report["summary"]
    lines = [
        "# 依赖保质期体检报告",
        "",
        "**使用者**：%s　**时机**：%s" % (u["persona"], u["moment"]),
        "",
        "**要回答的问题**：%s" % u["question"],
        "",
        "检查 %d 条答案：%d 条出生即过期，%d 条干净。判定：**%s**" % (
            s["answers_checked"], s["stale_claims"], s["clean_claims"], s["verdict"]
        ),
        "",
        "## 需要拒绝的声明",
        "",
    ]
    for f in report["stale_findings"]:
        lines += [
            "- 声明：`%s`（%s）" % (f["claim_text"], f["claim_id"]),
            "- 引用版本：**%s**；漏洞自 **%s** 起公开，答案生成于 %s，滞后 **%s 天**" % (
                f["cited"], f["known_vulnerable_since"],
                f["answer_created"], f["advisory_aged_days_at_answer"]
            ),
            "- 公开证据：%s" % f["public_evidence_url"],
            "- 动作：%s" % f["action"],
            "",
        ]
    lines += ["## 通过的声明", ""]
    for f in report["clean_findings"]:
        lines.append("- `%s` → %s（%s）" % (f["claim_id"], f["cited"], f["status"]))
    lines += [
        "",
        "数据来源：%s。答案为自运行产物（self-run，无付费客户）。" % (
            report["evidence"]["advisory_source"]
        ),
        "",
    ]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(prog="python -m tracelens.usecase")
    p.add_argument("--q5", default=str(ROOT / "real-traces" / "expiry" / "q5-result.json"))
    p.add_argument("--answers", default=str(ROOT / "real-traces" / "expiry" / "answers.json"))
    p.add_argument("--advisories", default=str(ROOT / "real-traces" / "expiry" / "advisories.json"))
    p.add_argument("--out", default=str(ROOT / "real-traces" / "expiry" / "report.json"))
    p.add_argument("--md", default=str(ROOT / "real-traces" / "expiry" / "report.md"))
    args = p.parse_args(argv)
    q5 = json.loads(Path(args.q5).read_text(encoding="utf-8"))
    ans = json.loads(Path(args.answers).read_text(encoding="utf-8"))
    adv = json.loads(Path(args.advisories).read_text(encoding="utf-8"))
    report = render_report(q5, ans, adv)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    Path(args.md).write_text(markdown(report), encoding="utf-8")
    print(json.dumps({"out": str(out), "md": args.md,
                      "verdict": report["summary"]["verdict"],
                      "stale": report["summary"]["stale_claims"],
                      "clean": report["summary"]["clean_claims"]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
