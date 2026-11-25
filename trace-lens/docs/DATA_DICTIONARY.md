# TraceLens 数据字典

本字典逐字段对应 `tracelens/schema.py`（写入）、`tracelens/querypacks.py`（查询输出）与 `tracelens/judge.py`（判定输出）。实际字段以代码为准；本文件是检索用的字段索引，不引入代码里不存在的字段。

## 一、节点类型与字段类型

所有节点都带统一主键 `node_id`（字符串）。路径投影统一用 `coalesce(n.node_id, n.span_id, n.answer_id, n.source_id)`，保证任一节点投影都不是 null。

| 标签 | 字段名 | 字段类型 | 含义 |
|---|---|---|---|
| Run | node_id | string | `run:<run_id>`，统一主键 |
| Run | run_id | string | 一次 Agent 运行的标识 |
| Run | model | string | 使用的模型名 |
| Run | outcome | string | 运行结论标记 |
| Span | node_id | string | `span:<span_id>`，统一主键 |
| Span | span_id | string | span 标识 |
| Span | run_id | string | 所属运行 |
| Span | kind | string | CHAIN / RETRIEVER / LLM 等类型 |
| Span | name | string | span 名 |
| Span | start / end | float | 起止时间 |
| Span | duration_ms | float | 持续时间（毫秒） |
| Span | input_tokens / output_tokens | int | 输入 / 输出 token 数 |
| Span | cost | float | 该 span 花费 |
| Span | status | string | ok / error 等状态 |
| ToolCall | node_id | string | `tc:<call_id>`，统一主键 |
| ToolCall | call_id | string | 工具调用标识 |
| ToolCall | tool_name | string | 工具名 |
| ToolCall | arguments_hash | string | 参数哈希（不存原文） |
| ToolCall | ok | int | 是否成功（bool 写入时转 0/1） |
| Source | node_id | string | `src:<run_id>:<doc_id>`，统一主键 |
| Source | source_id | string | 来源节点标识 |
| Source | doc_id | string | 文档名（判定输出里的最小定位单位） |
| Source | uri | string | 来源地址 |
| Source | snippet_hash | string | 片段哈希 |
| Source | score | float | 检索相关性分数（过滤条件，不是唯一判据） |
| Answer | node_id | string | `ans:<answer_id>`，统一主键 |
| Answer | answer_id | string | 答案标识 |
| Answer | text_hash | string | 答案文本哈希 |
| Answer | run_id | string | 所属运行 |
| Claim | node_id | string | `claim:<claim_id>`，统一主键 |
| Claim | claim_id | string | 断言标识 |
| Claim | text | string | 断言文本 |
| Claim | run_id | string | 所属运行 |

## 二、关系类型与字段类型

| 关系 | 起点 → 终点 | 字段名 | 字段类型 | 含义 |
|---|---|---|---|---|
| PARENT_OF | Span → Span | — | — | 父子调用子树，Q1/Q2/Q4 做变长路径 `PARENT_OF*1..8` / `*0..8` |
| CALLED | Span → ToolCall | — | — | span 触发的工具调用 |
| RETRIEVED_FROM | Span(RETRIEVER) → Source | score | float | 检索边上的分数 |
| RETRIEVED_FROM | Span(RETRIEVER) → Source | rank | int | 检索排名 |
| PRODUCED | Span(root) → Answer | — | — | 根 Agent span 产出答案（Q1 路径起点） |
| ASSERTED_IN | Claim → Answer | — | — | 断言属于哪个答案 |
| SUPPORTED_BY | Claim → Source | — | — | 断言的证据来源；Q3 用路径反连接找无支撑断言 |
| CONTAINS | Run → Span | — | — | 运行包含的根 span |

## 三、查询包输出字段

| 查询包 | 输出字段 | 字段类型 | 含义 |
|---|---|---|---|
| Q1 path-to-evidence | path | list[string] | 有序节点路径：`ans:… → span:root → … → src:…` |
| Q1 | bad_source | string | 路径终点的污染来源 doc_id |
| Q1 | score | float | 该来源分数 |
| Q1 | hops | int | 路径跳数 |
| Q2 evidence-convergence-loop | doc | string | 多分支收敛到的同一低分文档 |
| Q2 | branches / common_ancestor / paths | list/string | 分支名、共同祖先、收敛路径 |
| Q3 unsupported-claim-forensics | claim_id / text / answer_id | string | 无证据路径支撑的断言 |
| Q4 cost-attribution | root_span / cost / descendants | string/float/int | 花费最高的子树与其开销 |

## 四、判定输出字段（judge）

| 字段名 | 字段类型 | 含义 |
|---|---|---|
| verdict | string | PASS / FAIL |
| passed | bool | 全部检查是否通过 |
| checks.baseline_misidentifies | bool | 全局最低分基线是否误判 |
| checks.graph_localizes_true_cause | bool | 图是否命中收敛真因 |
| checks.graph_zero_false_positive_on_clean | bool | clean run 是否零误报 |
| checks.has_signal | bool | 是否存在可判定信号（防空跑恒真） |
| metric | string | 判定口径 |
| convergence_causes | list[string] | 从 Q2 结构推导出的真因文档名 |
| baseline_global_lowest_score_picks | string | 全局最低分基线选中的文档 |
| answers_with_signal / answers_clean | list[string] | 有信号 / 干净的 answer_id |

## 五、真实数据接入与闭环字段

| 文件 / 字段 | 字段类型 | 含义 |
|---|---|---|
| `real-traces/*.otlp.json` | OTLP/JSON | 真实运行导出的 trace；spans 带墙钟纳秒时间戳 |
| `real-traces/*.meta.json` → nature | string | 固定 `real` |
| → source_file / sha256 | string | 来源文件与内容哈希 |
| → origin / caveat | string | 来源说明；必须含 self-run，不得冒充客户数据 |
| → intake.checks | object | spans/时间戳/正时长/父边/事件/工具或检索 六项结构检查 |
| `self-check-*.json` → answer_before / answer_after | list[object] | agent 自查前后的声明集合 |
| → drop_reasons | object | `{claim_id: 图给出理由}`；理由只来自 Q2/Q3 路径结果 |
| → tool_calls | list[object] | agent 实际调用的 MCP 工具与返回摘要 |
| → trace_sha256 | string | 被诊断 trace 的哈希，证明前后对应同一次运行 |

MCP 只读工具（`tracelens.mcpserver`）：`tracelens_query_pack`、`tracelens_judge`、`tracelens_graph_info`、`tracelens_readonly_cypher`；后者的 Cypher 先过 `is_readonly()` 白名单（写动词/多语句直接拒），再以 `read_only=True` 打开 store。

## 六、六维证据模块字段

| 文件 / 字段 | 字段类型 | 含义 |
|---|---|---|
| `docs/falsification.json` → per_answer[] | list[object] | 每条答案的 baseline_pick / baseline_localizes / graph_picks / graph_paths；基线与图在同一 store 同一阈值下对比 |
| → falsifiable_checks | object | baseline_is_answer_blind / graph_distinguishes_answers / baseline_wrong_on_at_least_one_answer，三项全真才 PASS |
| `real-cases/cases.json` → cases[] | list[object] | 开发过程真实失败：case_id / symptom / root_cause / graph_evidence / fix / after / reproduce / customer=false |
| → validate.errors | list[string] | 缺字段、非图证据、少于三条、客户数据、重复 ID 均被程序拒绝 |
| `real-traces/osv/osv-passport.json` → nature | string | 固定 `real-public`（OSV.dev 公开数据，非客户、非 agent trace） |
| → vuln_count / node_count / relationship_count | int | 真实拉取与真实入库的三个计数 |
| → url_coverage | float | 带公开 URL 的漏洞节点占比；1.0 才达完整性门槛 |
| → source / query_commands / sha256 | string/list/string | 数据来源、真实执行的请求、快照哈希 |
| `docs/award-dashboard.html` | single HTML | 零外部资源；四包折叠区 + 答案自查时间线，删改理由来自图证据 |
| `real-traces/guardrail-run.json` → decisions[] | list[object] | 每条声明的 admitted / decision_source=graph / graph_reason / graph_evidence / model_explanation |
| → llm_calls[].receipt | object | endpoint / model_returned / latency_ms / request_sha256 / response_sha256 / usage；模型调用可外部复算 |
| → model_cannot_release_rejected_claim | bool | 恒真；模型文字即使要求放行，图拒绝的声明仍不进入 after |
| `docs/context-proof.json` → checks | object | 四包断言 / 图独占决策 / 逐条图证据 / 真实规模可溯源，四项同时成立才 PASS |

模型准入规则：只有 Q3 返回的无证据路径声明，或 Q2 收敛源命中的声明会被拒绝；`score` 不参与放行判定。环境变量 `TRACELENS_LLM_ENDPOINT`、`TRACELENS_LLM_MODEL` 可替换推理服务；失败即报错，无预置回答兜底。

## 七、确定性与边界

- 阳性对照是确定性 fixture（`fixtures/demo-trace.json`），`build` 每次从代码重新生成；真实运行数据在 `real-traces/`，两者不混用。
- `store/*.rl` 是生成物，字节不稳定，不作为数据字典的事实来源。
- `Source.score` 是过滤条件，真因由 Q2 收敛 motif 从图结构推导，不用分数直接挑来源。
- 真实 trace 的 judge 可能是 FAIL；这是有效结论，不通过改参数把它变成 PASS。
- 本字典只描述结构与字段，不声称任何语义正确性结论。
