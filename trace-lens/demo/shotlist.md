# Demo 视频分镜（1–2 分钟，逐帧可判定）

**主线**：The lockfile is clean. The sentence is not. —— 合并 coding agent 的话之前，先判断那句话声称的事实是不是"出生即过期"。

**录制方式**：终端 + `docs/graph-explorer.html` + `docs/scan-verdict.json` + `docs/EVIDENCE.md`，全部为本轮真实产物。口播给英文版（国际评委）与中文版（可选），画面字幕用英文 hook。

**本轮实测数字（禁用旧数字）**：8 个真实 OSV advisory / 8 条真实模型输出声明（6 个包）/ 111 条 Q6 变长路径（4–6 跳，含 Alias/Ref 身份链）/ 8 条 Q8 漂移 / 8 条 BLOCK_MERGE_TEXT；另有 9 条真实模型输出案例 + 5 条真实 SO 问答全拦截；Q9/Q10 合并 22 条答案、10 个模型；图 19/19、162/175、269/296 与 OSV 11,023/50,952；首个已过期跳点 4421.06 天；源文档早于 advisory 365 天；137 passed。

## 帧 1（0:00–0:12）钩子：两个判定，来自同一份代码库

- 口播 EN: "The lockfile is clean. The sentence is not. A scanner sees `requests==2.3.0` and passes. The agent's sentence says `2.2.0 is safe` — and that sentence was already stale when it was written."
- 口播 CN: "lockfile 是干净的，那句话不是。扫描器看到 2.3.0 放行，agent 却说 2.2.0 安全——那句话出生时就已过期。"
- 展示：`docs/EVIDENCE.md` 顶部对照表，`CLEAN` 与 `BLOCK_MERGE_TEXT` 两行并排定格。

## 帧 2（0:12–0:35）不是挑样本：8 个真实漏洞、批量自动扫描

- 口播 EN: "Eight real OSV advisories, eight declarations captured from real model outputs — no hand-built graph, no API key, no author-written prose."
- 口播 CN: "8 个真实 OSV 公告，8 条来自真实模型输出的版本声明——不手工建图，不需要 API key，没有自写文案。"
- 展示命令：
  `python -m tracelens.scan --text real-traces/scan/pr-answer.txt --lockfile real-traces/scan/requirements.lock --passport real-traces/scan/osv-batch-passport.json --store real-traces/scan/scan.rl --out docs/scan-verdict.json`
- 定格 `declarations_found: 8` / `Q8_drifts: 8` / `verdict: BLOCK_MERGE_TEXT`，以及 `sca_control` 全 clean。

## 帧 3（0:35–1:00）图是推理主体，不是存储层

- 口播 EN: "The graph is the reasoning: one variable-length path from the agent's answer, through the retrieved document, to the version the sentence cites."
- 口播 CN: "图本身就是推理：一条变长路径，从 agent 的答案经过检索到的文档，走到那句话引用的版本。"
- 展示：打开 `docs/graph-explorer.html`，切到"批量 8 包 · scan 图"，点 **Q6 多跳溯源路径**；点击 `pv:requests:2.31.0` 节点，右侧显示它真实的 `name/version/node_id` 属性与进出边。再切"跨答案 · Q9/Q10 收敛图"，点 **Q9 跨模型收敛**：claude 与 gemini 独立引用同一个 pillow 10.0.0；点 **Q10 爆炸半径**：一条 pillow 公告波及 5 个模型的 5 条答案。
- 定格：162 节点 / 175 关系、111 条 Q6 路径（4–6 跳）全部解析成功；Q9/Q10 检查全绿。

## 帧 3b（0:55–1:00）从判定到修复方案：一刀修几条

- 口播 EN: "It doesn't just say 'stale'. It solves the repair: a minimum set cover over producer-to-source paths. Eight independent chains need eight cuts — but one shared collector needs a single cut to cover all eight answers."
- 口播 CN: "它不止说'过期'，还求解修复方案：在 producer→source 路径上做最小集合覆盖。8 条独立链要 8 刀；但若 8 个包由一个采集器统一服务，1 刀就覆盖全部 8 条答案。"
- 展示：`docs/reasoning-shared-verdict.json`，定格 `intervention_spans = ["span:shared-ret"]`、`repair_size = 1`、`derived_answer_count = 8`、`sound = true`；对照 `docs/reasoning-verdict.json` 的 8 条独立链 `repair_size = 8`。
- 一句边界：这是**共享采集层反事实拓扑**——8 个真实公告、8 份真实源文档原样复用，只改拓扑，不伪造数据。

## 帧 4（1:00–1:30）逐跳时间审计 + 反证：不是恒真

- 口播 EN: "Each hop carries its own clock. The document was written before the advisory — it was right then. The 2026 agent that retrieved it was 4421 days late. Move only the answer clock: before publication, clean."
- 口播 CN: "每一跳都带自己的墙钟。文档写在漏洞公开之前，当时它是对的；2026 年检索它的 agent 晚了 4421 天。只改答案时间：公开前就干净。"
- 展示：点 **Q7 逐跳时间审计**，定格 `src:stale-doc.md = -365 天` 与首个 `Span = +4421.06 天`；再切 `docs/expiry-counterfactual.json` 五项全绿。

## 帧 5（1:30–1:55）可复现、可探索

- 口播 EN: "Clone, run one command, open one offline file: four graphs are there, every node and edge read back from the persisted store — and you can search the 11,000-node OSV graph and walk any path yourself."
- 口播 CN: "clone 后一条命令复跑，一个离线文件打开：四张图就在那里，每个节点和边都从持久化 store 读回——1.1 万节点的 OSV 全量图可以搜索、游走、任意两点查路径。"
- 展示：`.\verify.ps1`（或 `bash scripts/award-verify.sh`）尾部 `137 passed` 与 `evidence verdict PASS`；切到"OSV 全量"标签，搜索 `GHSA-4grg`，点邻域游走，再查一条路径；回"导出自检"显示四张 store 的 sha256。
- 结尾字幕：**TraceLens · Claim Freshness Gate · The lockfile is clean. The sentence is not.**

## 提交前一致性检查（避免旧数字回流）

- 测试数写 137（非 128、非 121、非 119、非 115、非 92、非 7）；图写 19/19、162/175、269/296 与 11,023/50,952；批量写 8 包、真实文本写 14 条（9 模型输出 + 5 SO）。
- 官方 ideas 库 385 篇（非 180）。
- 全片不出现 "agent trace 图诊断 / 参赛者用 / 答案保质期体检 / 冲榜" 等旧定位措辞。
- 不声称"原创 SCA"；只声称合并前的声明窗口与图多跳判定。
