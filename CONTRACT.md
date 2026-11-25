# CONTRACT — TraceLens 产品边界 v1

本文件声明本产品"是什么 / 不是什么 / 输入什么 / 输出什么 / 靠什么成立 / 如何验收"。所有字段都能在本仓库落盘文件中核对，不是为凑齐文件而定。内部原始 scope 见 `soldieros/scope.json`（`soldieros/scope@1`，含样本 sha256 与 digest）。

## 1. 定义（是什么）

本产品是一个**给开发者和 coding agent 用的事实有效期门禁**：合并前沿 Relate 图把 agent 说出口的版本声明追溯到事实变化时刻，在"出生即过期"时拦截；判定经 137 条回归测试校验，以 8 个真实 OSV 公告为对照实测。

一句话：`The lockfile is clean. The sentence is not.` —— 审的是 agent 的文本声明，不是已落地的依赖文件。

## 2. 不是什么（明确不做）

- **不是又一个 SCA。** 不读 manifest/lockfile/SBOM 做依赖审计，不与 `pip-audit` / Dependabot / OSV-Scanner 竞争；它们是本产品的**对照组**（`sca_control`），不是替代品。
- **不冒充原创 SCA。** 品类是 born-stale claim，不是"带 AI 的 SCA"；相邻方向（FossID Agentic SCA、Sonatype、Labrador）已在 `docs/first-place-benchmark.json` 如实列出。
- **不冒充真实生产流量。** agent trace 是 self-run（真实 TF-IDF 打分、真实墙钟），8 个 OSV 公告是真实数据，演示 PR 文本是可复现场景（`scan-verdict.json` 的 `data_nature`），三者性质分别标注，不混写。
- **不做写入。** MCP server 只读，写操作被拒；模型只能写解释文本，不能覆盖图的拦截判定。

## 3. 输入

| 输入 | 来源 | 真实性 |
| --- | --- | --- |
| agent 文本声明 | `--text` 任意文本；内置 `real-traces/scan/pr-answer.txt` | 内置为可复现场景；真实文本走 `--text` 注入 |
| lockfile | `--lockfile`，如 `real-traces/scan/requirements.lock` | 场景 pin，sha256 记录于 verdict |
| OSV 漏洞数据 | `--passport`，如 `real-traces/scan/osv-batch-passport.json` | 8 条真实 OSV 公告，含 affected ranges、source URL、sha256 |
| 答案墙钟 | `--as-of`（可选） | 调用方给定；缺省取当前时刻，反事实由给定时间驱动 |

## 4. 输出字段

与 `soldieros/scope.json` 的 `output.fields` 对齐：`verdict`、`checks`、`path`、`bad_source`、`score`、`hops`。批量 verdict（`scan-verdict.json`）额外给出：`declarations_found`、`Q6_provenance_paths`、`Q7_hop_audits`、`Q8_drifts`、`merge_actions`、`sca_control`、`data_nature`。判定值域：`BLOCK_MERGE_TEXT`（出生即过期，拦截）/ `PASS`（无法拒绝项时如实报 FAIL 或 PASS，见各 verdict 的 `checks`）。

## 5. 靠什么成立（可证伪边界）

- **图是推理主体**：Q6 变长路径 `PARENT_OF*0..8`、Q7 `ALL(nodes(path))` 逐跳时间审计、Q8 三路 join 声明漂移，均返可解释有序路径，不是单值查表；Q9 跨模型收敛（fan-in）与 Q10 advisory 爆炸半径（fan-out）在 22 条真实答案的合并图上跨答案聚合。
- **边不手工标注**：`AFFECTS` 由每条真实 advisory 的 affected ranges 自动推导（`version_affected`）；SCA 对照组干净是因为 pin 未被覆盖，不是因为漏连边。
- **判定非恒真**：固定 advisory 与版本、只移答案墙钟（`--as-of`），2013 答案为 clean、2026 答案为 born-stale（`docs/expiry-counterfactual.json` 五项检查）。
- **导出可回读**：`docs/graph-explorer.html` 每个节点/属性/边由 Cypher 从持久化 `.rl` 读回；导出快照哈希与磁盘不符时渲染器拒绝出文件。

## 6. 验收

一条命令重建全部产物并跑全量测试：POSIX `bash scripts/award-verify.sh`（或 `make verify`），Windows 原生 `.\verify.ps1`；脚本自己找/建 `trace-lens/.venv` 并 `pip install -e .[dev]`，`TRACELENS_PYTHON` 只是可选覆盖。本轮基线：**8 真实 advisory → 8 条真实模型输出声明 → 111 条 Q6 变长路径（4–6 跳，含 Advisory→Alias→Ref 身份链）/ 8 条 Q7 / 8 条 Q8 → 8 `BLOCK_MERGE_TEXT`**，SCA 对照全 clean，**137 tests passed**，四张 store 导出 PASS，Q9/Q10 收敛与爆炸半径检查 PASS，Q11 不动点规则推理（R1–R4，40 条派生事实）与 Cypher Q8 交叉校验 PASS；R5/R6 最小修复求解在共享采集层反事实上 1 刀覆盖 8 条答案。证据数字由 `python -m tracelens.evidence` 从本次日志生成（`docs/EVIDENCE.md` / `first-place-evidence.json`），不手写、不沿用旧值。
