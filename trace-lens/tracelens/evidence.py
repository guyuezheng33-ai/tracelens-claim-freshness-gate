"""Programmatic evidence pack: every number read from THIS run's artefacts.

Every number here is READ FROM THIS RUN'S artefacts, never typed by hand. The
JSON and the Markdown are rendered from the same in-memory object, so they
cannot disagree. Checks are falsifiable: if the scan stops blocking the merge,
if the SCA control stops being clean, if the time counterfactual stops flipping,
or if the graph exports drift out of sync, the pack reports FAIL.

Usage:
    python -m tracelens.evidence
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent

FILES = {
    "scan": ROOT / "docs/scan-verdict.json",
    "provenance": ROOT / "docs/provenance-verdict.json",
    "counterfactual": ROOT / "docs/expiry-counterfactual.json",
    "export_prov": ROOT / "docs/graph-provenance.json",
    "export_scan": ROOT / "docs/graph-scan.json",
    "passport": ROOT / "real-traces/scan/osv-batch-passport.json",
    "osv_passport": ROOT / "real-traces/osv/osv-passport.json",
    "real_cases": ROOT / "docs/real-cases-check.json",
    "convergence": ROOT / "docs/convergence-verdict.json",
    "reasoning": ROOT / "docs/reasoning-verdict.json",
    "reasoning_shared": ROOT / "docs/reasoning-shared-verdict.json",
    "public_catch_source": ROOT / "public-catches/catch-001-minimax-flask-230/source.json",
    "public_catch_verdict": ROOT / "public-catches/catch-001-minimax-flask-230/scan-verdict.json",
    "benchmark": ROOT / "docs/first-place-benchmark.json",
}


def _load(key: str) -> dict[str, Any]:
    return json.loads(FILES[key].read_text(encoding="utf-8"))


def _latest_test_count() -> dict[str, Any]:
    """Take the most recent verification log, never a remembered number."""
    logs = sorted(ROOT.glob("logs/award-verify-*.log"),
                  key=lambda p: p.stat().st_mtime, reverse=True)
    if not logs:
        return {"log": None, "tests_passed": 0, "found": False}
    log = logs[0]
    matches = re.findall(r"(\d+) passed in [\d.]+s", log.read_text(encoding="utf-8"))
    return {"log": str(log.relative_to(ROOT)),
            "tests_passed": int(matches[-1]) if matches else 0,
            "found": bool(matches)}


def build() -> dict[str, Any]:
    scan = _load("scan")
    prov = _load("provenance")
    cf = _load("counterfactual")
    ex_p = _load("export_prov")
    ex_s = _load("export_scan")
    passport = _load("passport")
    osv_passport = _load("osv_passport")
    real_cases = _load("real_cases")
    convergence = _load("convergence")
    reasoning = _load("reasoning")
    reasoning_shared = _load("reasoning_shared")
    public_catch_source = _load("public_catch_source")
    public_catch_verdict = _load("public_catch_verdict")
    benchmark = _load("benchmark")
    tests = _latest_test_count()

    advisories = passport.get("advisories", [])
    sca_clean = all(not row.get("advisories_on_pinned")
                    for row in scan.get("sca_control", []))
    drifts = scan.get("Q8_declaration_drift", [])
    hops = prov.get("Q7_hop_audit", [])
    first_stale = (hops[0].get("first_hop_already_stale") or {}) if hops else {}

    checks = {
        "eight_real_advisories_loaded": len(advisories) >= 8,
        "declaration_count_matches_scenarios": (
            scan.get("declarations_found") == scan.get("scenarios_built")
        ),
        "every_declaration_produced_a_drift": (
            scan.get("declarations_found") == scan.get("Q8_drifts") == len(drifts)
        ),
        "sca_control_reports_pinned_clean": sca_clean,
        "graph_blocks_merge_text_where_sca_cannot": (
            scan.get("verdict") == "BLOCK_MERGE_TEXT" and sca_clean
        ),
        "provenance_checks_all_pass": (
            prov.get("verdict") == "PASS" and all(prov.get("checks", {}).values())
        ),
        "hop_audit_finds_already_stale_hop": bool(first_stale),
        "time_counterfactual_passes": (
            cf.get("verdict") == "PASS" and all(cf.get("checks", {}).values())
        ),
        "both_graph_exports_pass": ex_p.get("verdict") == "PASS"
        and ex_s.get("verdict") == "PASS",
        "osv_graph_scale_over_500": (
            osv_passport.get("node_count", 0) >= 500
            and osv_passport.get("relationship_count", 0) >= 500
        ),
        "real_cases_are_captured_text": (
            real_cases.get("ok") is True and real_cases.get("case_count", 0) >= 3
            and real_cases.get("nature") in {"real-agent-text", "real-user"}
        ),
        "cross_model_convergence_found": (
            convergence.get("verdict") == "PASS"
            and convergence.get("checks", {}).get("q9_finds_cross_model_convergence") is True
        ),
        "advisory_blast_radius_spans_models": (
            convergence.get("checks", {}).get("q10_blast_radius_spans_multiple_models") is True
        ),
        "verdict_path_resolves_advisory_identity": (
            scan.get("checks", {}).get("q6_traverses_advisory_identity_when_present") is True
            and any("Alias" in (r.get("labels") or [])
                    for r in scan.get("Q6_provenance", []))
        ),
        "fixpoint_reasoning_derives_born_stale": (
            reasoning.get("verdict") == "PASS"
            and reasoning.get("checks", {}).get("reasoning_agrees_with_cypher_q8") is True
            and reasoning.get("checks", {}).get("r3_propagates_along_parent_of") is True
        ),
        "shared_collector_repair_is_one_cut": (
            reasoning_shared.get("verdict") == "PASS"
            and (reasoning_shared.get("intervention") or {}).get("repair_size") == 1
            and (reasoning_shared.get("intervention") or {}).get("derived_answer_count", 0) >= 8
            and (reasoning_shared.get("intervention") or {}).get("sound") is True
        ),
        "real_public_catch_blocks_stale_model_output": (
            public_catch_verdict.get("verdict") == "BLOCK_MERGE_TEXT"
            and (public_catch_source.get("input") or {}).get("verbatim_line")
            and (public_catch_source.get("verdict") or {}).get("matched_advisory")
            == ((public_catch_verdict.get("Q8_declaration_drift") or [{}])[0].get("advisory_id"))
        ),
        "latest_full_suite_is_green": tests["found"] and tests["tests_passed"] > 0,
        "external_problem_scale_is_sourced": bool(
            benchmark.get("problem_scale_external_evidence", {})
            .get("verified_numbers", {})
        ),
    }

    return {
        "schema": "tracelens/first-place-evidence@1",
        "source_note": "all numbers read from this run's artefacts; JSON and "
                       "Markdown rendered from the same object",
        "decision": {
            "scanner_reads": "lockfile pins only",
            "scanner_verdict": "CLEAN" if sca_clean else "NOT CLEAN",
            "graph_reads": "answer text + evidence chain + advisory timeline + lockfile",
            "graph_verdict": scan.get("verdict"),
            "one_sentence": (
                "The dependency file is clean, but the agent's sentence is "
                "born stale: only the graph joins the declaration to the "
                "evidence chain and the advisory clock."
            ),
        },
        "measured": {
            "real_advisories": len(advisories),
            "advisories": [
                {"id": a.get("id"), "package": a.get("package"),
                 "fixed": a.get("fixed"), "published": a.get("published")}
                for a in advisories
            ],
            "text_declarations": scan.get("declarations_found"),
            "scenarios_built": scan.get("scenarios_built"),
            "q6_multihop_paths": scan.get("Q6_provenance_paths"),
            "q6_distinct_hop_lengths": sorted({int(r["hops"]) for r in scan.get("Q6_provenance", [])
                                               if r.get("hops") is not None}),
            "q7_hop_audits": scan.get("Q7_hop_audits"),
            "q8_drifts": scan.get("Q8_drifts"),
            "merge_actions": len(scan.get("merge_actions", [])),
            "single_scenario_graph": {
                "nodes": ex_p.get("counts", {}).get("nodes"),
                "relationships": ex_p.get("counts", {}).get("relationships"),
                "store_sha256": ex_p.get("store_sha256"),
            },
            "batch_graph": {
                "nodes": ex_s.get("counts", {}).get("nodes"),
                "relationships": ex_s.get("counts", {}).get("relationships"),
                "store_sha256": ex_s.get("store_sha256"),
            },
            "osv_graph": {
                "nodes": osv_passport.get("node_count"),
                "relationships": osv_passport.get("relationship_count"),
                "vulnerabilities": osv_passport.get("vuln_count"),
                "nature": osv_passport.get("nature"),
                "source": osv_passport.get("source"),
                "store": osv_passport.get("store"),
                "sha256": osv_passport.get("sha256"),
            },
            "first_stale_hop": {
                "node": first_stale.get("node"),
                "at_iso": first_stale.get("at_iso"),
                "already_stale_days": first_stale.get("already_stale_days"),
            },
            "full_suite_tests_passed": tests["tests_passed"],
            "verification_log": tests["log"],
            "real_cases": {
                "count": real_cases.get("case_count"),
                "nature": real_cases.get("nature"),
                "sha256": real_cases.get("sha256"),
            },
            "convergence": {
                "answers_merged": convergence.get("graph", {}).get("answers"),
                "distinct_models": len(convergence.get("graph", {}).get("distinct_models", [])),
                "q9_clusters": len(convergence.get("Q9_convergence", [])),
                "q10_advisories": len(convergence.get("Q10_blast_radius", [])),
                "top_cluster": (convergence.get("Q9_convergence") or [None])[0],
            },
            "reasoning": {
                "iterations": reasoning.get("iterations"),
                "derived_counts": reasoning.get("derived_counts"),
                "born_stale_derived": len(reasoning.get("derived_born_stale_answers", [])),
                "agrees_with_cypher_q8": reasoning.get("checks", {}).get("reasoning_agrees_with_cypher_q8"),
            },
        },
        "counterfactual": {
            "checks": cf.get("checks", {}),
            "verdict": cf.get("verdict"),
        },
        "problem_scale": benchmark.get("problem_scale_external_evidence", {}),
        "checks": checks,
        "verdict": "PASS" if all(checks.values()) else "FAIL",
    }


def to_markdown(doc: dict[str, Any]) -> str:
    m = doc["measured"]
    d = doc["decision"]
    lines = [
        "# TraceLens · 证据包（本轮实测）",
        "",
        "## 决定性对照",
        "",
        "| 读取的输入 | 判定 |",
        "|---|---|",
        "| %s | **%s** |" % (d["scanner_reads"], d["scanner_verdict"]),
        "| %s | **%s** |" % (d["graph_reads"], d["graph_verdict"]),
        "",
        d["one_sentence"],
        "",
        "## 本轮实测",
        "",
        "| 指标 | 数值 |",
        "|---|---:|",
        "| 真实 OSV advisory | %d |" % m["real_advisories"],
        "| 文本版本声明 / 自动建图场景 | %d / %d |" %
        (m["text_declarations"], m["scenarios_built"]),
        "| Q6 多跳路径 / Q7 逐跳审计 / Q8 声明漂移 | %d / %d / %d |" %
        (m["q6_multihop_paths"], m["q7_hop_audits"], m["q8_drifts"]),
        "| 合并动作 | %d |" % m["merge_actions"],
        "| 单场景图（节点 / 关系） | %d / %d |" %
        (m["single_scenario_graph"]["nodes"],
         m["single_scenario_graph"]["relationships"]),
        "| 批量图（节点 / 关系） | %d / %d |" %
        (m["batch_graph"]["nodes"], m["batch_graph"]["relationships"]),
        "| 真实 OSV 全量图（节点 / 关系 / 漏洞） | %d / %d / %d |" %
        (m["osv_graph"]["nodes"], m["osv_graph"]["relationships"],
         m["osv_graph"]["vulnerabilities"]),
        "| 真实文本案例（数量 / 性质） | %d / %s |" %
        (m["real_cases"]["count"], m["real_cases"]["nature"]),
        "| 跨答案合并（答案 / 模型） | %s / %s |" %
        (m["convergence"]["answers_merged"], m["convergence"]["distinct_models"]),
        "| Q9 收敛簇 / Q10 爆炸半径 advisory | %d / %d |" %
        (m["convergence"]["q9_clusters"], m["convergence"]["q10_advisories"]),
        "| 首个已过期跳点滞后 | %s 天 |" % m["first_stale_hop"]["already_stale_days"],
        "| 全量测试 | %d passed |" % m["full_suite_tests_passed"],
        "",
        "本轮复验日志：`%s`" % m["verification_log"],
        "",
        "## 反事实",
        "",
        "固定同一 advisory 与同一版本，只改答案墙钟：发布前不判过期，发布后判过期。"
        "五项检查：%s。总判定 **%s**。" %
        (", ".join("%s=%s" % (k, v) for k, v in
                   doc["counterfactual"]["checks"].items()),
         doc["counterfactual"]["verdict"]),
        "",
        "## 问题规模（外部第一手证据）",
        "",
        "- 论文：%s（arXiv %s，%s）" %
        (doc["problem_scale"].get("paper"), doc["problem_scale"].get("arxiv"),
         doc["problem_scale"].get("submitted")),
        "- 基准：%s" % doc["problem_scale"].get("benchmark"),
    ]
    for k, v in doc["problem_scale"].get("verified_numbers", {}).items():
        lines.append("- %s：%s" % (k, v))
    lines += [
        "",
        "## 自检",
        "",
        "| 检查 | 结果 |",
        "|---|---|",
    ]
    for k, v in doc["checks"].items():
        lines.append("| `%s` | %s |" % (k, "PASS" if v else "FAIL"))
    lines += ["", "总判定：**%s**" % doc["verdict"], ""]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(prog="python -m tracelens.evidence")
    p.add_argument("--out", default=str(ROOT / "docs/first-place-evidence.json"))
    p.add_argument("--md", default=str(ROOT / "docs/EVIDENCE.md"))
    args = p.parse_args(argv)

    doc = build()
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n",
                   encoding="utf-8")
    md = Path(args.md)
    md.write_text(to_markdown(doc), encoding="utf-8")
    print(json.dumps({
        "json": str(out), "markdown": str(md), "verdict": doc["verdict"],
        "checks": doc["checks"], "tests": doc["measured"]["full_suite_tests_passed"],
    }, ensure_ascii=False, indent=2))
    if doc["verdict"] != "PASS":
        raise SystemExit("evidence pack failed its own checks: %s" % doc["checks"])


if __name__ == "__main__":
    main()
