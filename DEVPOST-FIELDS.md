# Devpost 提交字段（可直接复制粘贴）

> 用法：打开提交页后，把下面每个字段的正文原样粘到对应输入框。`<...>` 占位符在拿到实际链接/视频后替换。
> 仓库已建好并公开：https://github.com/guyuezheng33-ai/tracelens-claim-freshness-gate （topic `relate` 已加）。下面所有 `<REPO_URL>` 用这个地址替换。

## Title

TraceLens — Claim Freshness Gate

## Tagline / short description

The lockfile is clean. The sentence is not. TraceLens walks a Relate graph to block coding-agent advice that was already stale when it was written.

## Description / About the project

（粘贴 SUBMISSION.md 的 `## What it does` + `## How it is built on Relate` + `## Real data, not a toy` 三段全文；不要删数字。）

## How it uses Relate

（粘贴 SUBMISSION.md 的 `## How it is built on Relate` 全文——这段直接回答官方 README 模板的 "how are you using Relate, and why"。）

## Setup and run（贴在 Description 末尾或 "Try it out" 说明里）

```bash
git clone https://github.com/guyuezheng33-ai/tracelens-claim-freshness-gate.git
cd "Relate by Neo4j Hackathon/trace-lens"
python -m pip install -e .
python -m tracelens.scan --text real-traces/scan/pr-answer.txt --lockfile real-traces/scan/requirements.lock --passport real-traces/scan/osv-batch-passport.json --store real-traces/scan/scan.rl --out docs/scan-verdict.json
```

Then double-click `trace-lens/docs/graph-explorer.html` — it opens offline with four persisted stores (single-file mode). No server, no API key, no signup.

## Demo video

`<1–2 分钟视频链接>`

（录好视频后粘贴公开链接；同时把链接写回 SUBMISSION.md 和 owner_work.json 的 demo_video.evidence。）

## GitHub URL

https://github.com/guyuezheng33-ai/tracelens-claim-freshness-gate

## Built With

Python, Relate (embedded single-file store), Cypher, MCP, Datalog-style rule reasoning, pytest, Ruff

## AI and third-party disclosure

（粘贴 SUBMISSION.md 的 `## AI use disclosure` 全文——官方规则 §3/§4 要求申报，这段已经写好。）

## Screenshots

- `trace-lens/docs/scan.svg`（8 包批量 scan：声明→路径→拦截）
- `trace-lens/docs/graph-explorer.html` 截图（节点属性 + Q6/Q7 路径高亮）

## 提交前自检（官方 Requirements 逐条）

- [ ] 项目描述写了 use case 和"什么连接什么"
- [x] Public GitHub repo + README（已建并推送）
- [x] topic `relate`（已加，`relate-neo4j-hackathon` 被 GitHub topic 目录拒绝，官方仅建议非必需）
- [ ] 持久化 Relate store 在仓库里（`trace-lens/real-traces/**/*.rl`，已入仓）
- [ ] 可运行代码，Relate 真的在跑（137 测试 + scan CLI，已备）
- [ ] 1–2 分钟演示视频（待你录制上传）
- [ ] AI 使用申报（已写好，待粘贴）
