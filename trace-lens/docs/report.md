# TraceLens 诊断报告

- store: `D:\桌面\Relate by Neo4j Hackathon\trace-lens\store\demo-run.rl`
- 结构判定: **PASS**
- 指标: structure-derived root-cause localization: graph vs global-lowest-score baseline

## 判定检查

| 检查项 | 结果 |
| --- | --- |
| `baseline_misidentifies` | 通过 |
| `graph_localizes_true_cause` | 通过 |
| `graph_zero_false_positive_on_clean` | 通过 |
| `has_signal` | 通过 |

## 分数基线 vs 图定位

| 判定方式 | 选中来源 |
| --- | --- |
| 全局最低分基线 | `cache-tmp.bin`（误判） |
| 收敛 motif 真因 | `stale-policy-v2.pdf` |

## Q1 证据路径

- `ans:ba-ans -> span:ba-root -> span:ba-ret-2 -> src:bad-answer:stale-policy-v2.pdf` · 0.12 分 · 3 跳
- `ans:ba-ans -> span:ba-root -> span:ba-ret-1 -> src:bad-answer:stale-policy-v2.pdf` · 0.12 分 · 3 跳

## 四个查询包

| 包 | 回答的问题 | 行数 |
| --- | --- | --- |
| Q1 | 哪个低分来源污染了这个答案？ | 2 |
| Q2 | Agent 是否在多个分支上重复检索同一个（低分）来源——打转？ | 1 |
| Q3 | 哪些断言没有任何证据路径支撑？ | 1 |
| Q4 | 这次运行哪个子树烧掉了预算？ | 1 |

---

由 tracelens.render 生成；与 docs/report.html 同源。
