# 第二轮隔离评委复评与修复交接

## 复评方式

三位新评委（主审 `judge-award2`、图技术 `judge-tech2`、有用性 `judge-product2`、文档叙事 `judge-docs2`）互相看不到彼此草稿，均被要求亲自跑命令、不引用历史评测。主审结论未送达，按纪律不编造；以下为实际收到的三位完整结论。

## 三位评委结论（本轮新命令，未引用旧结论）

| 评委 | Creativity | Relate 30% | Functionality | Usefulness | Documentation | 加权总分 | 第一档判定 |
|---|---:|---:|---:|---:|---:|---:|---|
| 文档叙事 | 8.0 | 8.5 | 8.0 | 7.0 | 8.0 | **7.95** | 接近 |
| 图技术 | 见原文 | 核心 8.0 区间 | — | — | — | **7.50** | 接近 |
| 有用性 | 7.0 | 8.0 | 6.5 | 6.5 | 7.5 | **7.15** | 接近 |

三者收敛：**图作为推理主体、一键可复现、外部问题规模证据均达标；距"无可争议第一"的差距不在图结构，而在演示输入是手写的、抽取器是窄的、部分证据是自证的。**

## 四位评委指出的致命缺陷 → 本轮修复（全部有本轮命令证据）

1. **窄正则静默放行**（有用性评委实测 `"The best choice is urllib3 2.5.0." → []`）
   - 根因：`scan.py` 的 3 条正则要求"版本 + 安全形容词"同句，4 种自然措辞 100% 漏检 → `NO_MATCH/PASS`，对已知漏洞版本静默放行。
   - 修复：解耦"包名 + 版本 token"抽取与风险词语义；风险词只写进 `risk_cue` 供证据着色，不作抽取门槛。加 6 条硬负例测试。
   - 本轮证据：8 条无安全词（`risk_cue=False`）的自然措辞全部命中，`declarations=8 / Q6=8 / Q7=8 / Q8=8 / BLOCK_MERGE_TEXT / SCA 全 clean`。

2. **手写样本冒充真实 agent 输出**（文档与有用性评委均指出）
   - 根因：`pr-answer.txt` 首行自称 "Agent-generated"，实为手写；`-365 天` 是 `published - 365d` 常量。
   - 修复：文件改为 `reproducible-scenario (author-written, not captured)` 标注；scan verdict 新增 `data_nature` 明确 advisory 真实、文本/lockfile 为可复现场景；派生时间戳在 `build_scenario` 中已有 `at_ns_origin: derived:...` 标注。
   - 边界：真实 agent 答案由本人用 `--text` 注入（用户可获取真实数据，助手不编造）。

3. **MCP 回归测试是空门禁**（图技术评委指出）
   - 根因：`if not STORE.exists(): return` 使缺 store 直接通过；Q4 返回 `[]` 也通过。
   - 修复：改用有完整 Q1–Q4 数据的 `store/demo-run.rl`；缺 store 明确失败；断言 Q1/Q4 返回行数 > 0。3 passed。

4. **图浏览器哈希陈旧**（图技术评委实测内嵌 `b903…` vs 磁盘 `0704…`）
   - 根因：评委各自跑命令重建 `.rl`，导出快照哈希过期，页面仍宣称一致。
   - 修复：渲染时用 `hashlib` 重算当前磁盘 store，注入 `store_hash_matches_disk`；不一致则 `SystemExit(1)` 且**不产 HTML**（先验证后写）。本轮复验：两张 store 哈希全匹配。

5. **文档两处可验证不实**（文档评委指出）
   - AI 回执 latency 写 659.663ms，但当前 `guardrail-run.json` 是 1455.509ms（旧文件值，被全链路刷新）→ 从当前回执重读，并补全第二个 response_id。
   - one-line pitch 标 "≤100 字符"却实际 153 → 改为 100 字符精简版 + 展开版，`≤100` 标注只在核实后使用。
   - `measured-metrics.json` 的 21/22 属 `demo-run.rl`，加 `store`/`scope` 归属字段，避免被误判为旧数字回流。

## 本轮最终验收（全部新命令重跑）

- `scripts/award-verify.sh` → `EXIT=0`，**121 passed**（119 + 抽取负例 + MCP 强断言）
- 8 真实 advisory → 8 自然措辞声明 → 8 Q6/Q7/Q8 → 8 BLOCK_MERGE_TEXT，SCA 全 clean
- 反事实五项全绿；证据包 verdict PASS；两张 store 哈希全匹配；HTML 零外链 + 内联 JS 语法 OK
- 全包数字一致：121 / 10+9 / 73+72 / 8 包，无旧数字回流
- 日志 `trace-lens/logs/award-verify-20261123T231304.log`

## 仍需你本人完成（资格项，材料已备）

public GitHub repo + `relate` topic、`.rl` store 入仓、1–2 分钟视频（shotlist 五帧）、Devpost 提交、AI 申报开发时用途自填。以上补齐后，"入围"资格才成立；本轮把非资格维度推到接近第一档水位，但**没有任何评委给出"确定第一"**——诚实结论是"接近，且可再提升"，最后一道门槛是把手写演示输入替换为你能拿到的真实 agent 答案并用 `--text` 重跑。
