# TraceLens · 证据包（本轮实测）

## 决定性对照

| 读取的输入 | 判定 |
|---|---|
| lockfile pins only | **CLEAN** |
| answer text + evidence chain + advisory timeline + lockfile | **BLOCK_MERGE_TEXT** |

The dependency file is clean, but the agent's sentence is born stale: only the graph joins the declaration to the evidence chain and the advisory clock.

## 本轮实测

| 指标 | 数值 |
|---|---:|
| 真实 OSV advisory | 8 |
| 文本版本声明 / 自动建图场景 | 8 / 8 |
| Q6 多跳路径 / Q7 逐跳审计 / Q8 声明漂移 | 111 / 8 / 8 |
| 合并动作 | 8 |
| 单场景图（节点 / 关系） | 19 / 19 |
| 批量图（节点 / 关系） | 162 / 175 |
| 真实 OSV 全量图（节点 / 关系 / 漏洞） | 11023 / 50952 / 873 |
| 真实文本案例（数量 / 性质） | 9 / real-agent-text |
| 跨答案合并（答案 / 模型） | 22 / 10 |
| Q9 收敛簇 / Q10 爆炸半径 advisory | 17 / 8 |
| 首个已过期跳点滞后 | 4421.06 天 |
| 全量测试 | 137 passed |

本轮复验日志：`logs\award-verify-20261124T110936.log`

## 反事实

固定同一 advisory 与同一版本，只改答案墙钟：发布前不判过期，发布后判过期。五项检查：before_publication_not_stale=True, after_publication_is_stale=True, verdict_flips_with_time=True, answer_time_is_supplied=True, same_advisory_and_version=True。总判定 **PASS**。

## 问题规模（外部第一手证据）

- 论文：Correct Code, Vulnerable Dependencies: A Large Scale Measurement Study of LLM-Specified Library Versions（arXiv 2605.06279，2026-05-07）
- 基准：PinTrace: 1,000 curated Stack Overflow tasks, 10 LLMs, 267 distinct PyPI libraries
- tasks_with_known_cve：36.70%-55.70%
- critical_or_high_severity：62.75%-74.51%
- cve_public_before_model_knowledge_cutoff：72.27%-91.37%
- systemic_bias：all models converge on the same small set of risky release versions

## 自检

| 检查 | 结果 |
|---|---|
| `eight_real_advisories_loaded` | PASS |
| `declaration_count_matches_scenarios` | PASS |
| `every_declaration_produced_a_drift` | PASS |
| `sca_control_reports_pinned_clean` | PASS |
| `graph_blocks_merge_text_where_sca_cannot` | PASS |
| `provenance_checks_all_pass` | PASS |
| `hop_audit_finds_already_stale_hop` | PASS |
| `time_counterfactual_passes` | PASS |
| `both_graph_exports_pass` | PASS |
| `osv_graph_scale_over_500` | PASS |
| `real_cases_are_captured_text` | PASS |
| `cross_model_convergence_found` | PASS |
| `advisory_blast_radius_spans_models` | PASS |
| `verdict_path_resolves_advisory_identity` | PASS |
| `fixpoint_reasoning_derives_born_stale` | PASS |
| `shared_collector_repair_is_one_cut` | PASS |
| `real_public_catch_blocks_stale_model_output` | PASS |
| `latest_full_suite_is_green` | PASS |
| `external_problem_scale_is_sourced` | PASS |

总判定：**PASS**
