# TraceLens（工程实现）

**The lockfile is clean. The sentence is not.** TraceLens 是 born-stale claim 的合并前门禁：沿 Relate 图把 agent 的版本声明追到来源文档与真实漏洞时间轴。

产品定位、比赛口径与完整复现命令见仓库根目录 `README.md`（本文件的上级目录），以那份为准。本目录只收录可运行的工程代码、测试、持久化 store 与证据产物。

## 工程入口

| 命令 | 作用 |
|---|---|
| `python -m tracelens.scan` | 从任意文本 + lockfile 自动抽取声明，批量建真实 OSV 图，输出 `BLOCK_MERGE_TEXT` |
| `python -m tracelens.provenance` | 统一证据链与漏洞时间轴，Q6 变长多跳路径（4–6 跳，含 Advisory→Alias→Ref 身份链）/ Q7 逐跳时间审计 / Q8 声明漂移（含 CVE/PYSEC 别名解析） |
| `python -m tracelens.graphexport` | 用 Cypher 把持久化 `.rl` store 的节点、属性、关系读回为 JSON，带一致性自检 |
| `python -m tracelens.graphexplorer` | 生成单文件零外链图浏览器：`docs/graph-explorer.html` |
| `python -m tracelens.evidence` | 从本轮产物汇总证据包：JSON + `docs/EVIDENCE.md`，数字不手写 |
| `python -m tracelens.expiryagent` / `expiry build\|query` | Q5 答案保质期与 `--as-of` 时间反事实 |
| `python -m tracelens.cli build\|query\|judge\|report` | Q1–Q4 图诊断四查询包 |
| `python -m tracelens.dashboard` | 单文件零外链看板（含保质期时间轴） |
| `python -m tracelens.mcpserver` | 只读 MCP stdio server，写操作被拒 |
| `pytest tests/ -q` | 契约、反例与图导出回归测试 |

一条命令复跑全部证据：在仓库根执行 `bash scripts/award-verify.sh`（POSIX）或 `.\verify.ps1`（Windows 原生，无需 make/Git Bash）。脚本自己找/建 `trace-lens/.venv` 并 `pip install -e .[dev]`，不需要手填 `TRACELENS_PYTHON`。脚本最后运行全量测试，再从**本次日志**读取测试数生成证据包。

## 交付物速查

- `docs/graph-explorer.html` — 四张真实 store 的离线图浏览器（19/19、162/175、269/296 与 11,023/50,952 节点/关系）；OSV 全量图支持搜索、邻域游走与任意两点路径查询。
- `docs/EVIDENCE.md` / `docs/first-place-evidence.json` — 程序化证据包；`docs/first-place-benchmark.json` — 外部核实档案（官方规则原文/历史获奖画像/竞品边界），不是评分标尺。
- `docs/provenance-verdict.json` / `docs/scan-verdict.json` / `docs/convergence-verdict.json` / `docs/reasoning-verdict.json` / `docs/reasoning-shared-verdict.json` — Q6/Q7/Q8、8 包批量实证、Q9/Q10 跨答案聚合、Q11 不动点规则推理与最小修复求解（共享采集层 1 刀覆盖 8 答案）。
- `real-cases/cases.json` / `docs/real-cases.md` / `docs/real-cases-check.json` — **9 条真实模型输出**（PinTrace 公开评估数据，6 个包，保留 model 与 task id）；`real-cases/cases_user.json` 与 `real-user/` — **5 条真实 Stack Overflow 问答**（保留 URL 与 record id）。每条都跑出 `BLOCK_MERGE_TEXT`；不是自写 demo。
- `docs/expiry-counterfactual.json` — 固定 advisory 与版本、只改答案墙钟的判定翻转。
- `real-traces/provenance/provenance.rl` / `real-traces/scan/scan.rl` / `real-traces/convergence/convergence.rl` / `real-traces/osv/osv-graph.rl` — 持久化单文件 store，评委可 clone 后直接探索，或用 `python -m tracelens.ask --store <file.rl> --cypher "..."` 跑任意只读 Cypher；OSV 全量图是 11,023 节点 / 50,952 关系 / 873 漏洞。
