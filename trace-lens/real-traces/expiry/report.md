# 依赖保质期体检报告

**使用者**：developer or student accepting code from a coding agent　**时机**：before merging the agent's suggestion

**要回答的问题**：was the cited version already known-vulnerable when the agent answered?

检查 2 条答案：1 条出生即过期，1 条干净。判定：**PASS**

## 需要拒绝的声明

- 声明：`requests 2.2.0 is safe to use`（expiry-claim-stale）
- 引用版本：**requests 2.2.0**；漏洞自 **2014-10-15T14:55:00Z** 起公开，答案生成于 2026-11-24T03:09:45.901568+00:00，滞后 **4422.51 天**
- 公开证据：https://github.com/kennethreitz/requests/issues/1885
- 动作：reject 2.2.0; pin requests 2.3.0 or later

## 通过的声明

- `expiry-claim-clean` → requests 2.3.0（no advisory covers this version）

数据来源：https://api.osv.dev/v1/vulns/。答案为自运行产物（self-run，无付费客户）。
