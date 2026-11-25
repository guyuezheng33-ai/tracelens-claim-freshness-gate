# 图定位 vs 全局最低分基线：同 store 反证

- 判定：**PASS**
- 答案数：2；阈值：0.5
- 基线（对每个答案都一样）：`cache-tmp.bin`

| 答案 | 基线指向 | 基线命中 | 图路径指向 | 路径条数 |
|---|---|---|---|---|
| ba-ans | cache-tmp.bin | 否 | stale-policy-v2.pdf | 2 |
| cl-ans | cache-tmp.bin | 否 | （无污染路径） | 0 |

## 可证伪判据

- baseline_is_answer_blind: **PASS**
- graph_distinguishes_answers: **PASS**
- baseline_wrong_on_at_least_one_answer: **PASS**

基线的失败不是随机的：它对每条答案都给出同一个全局最低分，
因此无法识别「哪条答案被污染」；图路径在有污染的答案上返回路径，
在干净答案上返回空集。这一差异由 `per_answer` 逐行给出，可现场复算。
