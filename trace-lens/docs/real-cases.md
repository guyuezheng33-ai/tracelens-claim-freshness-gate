# 真实失败案例集

> Nine captured model outputs from the public PinTrace evaluation dataset (BigCodeBench and Stack Overflow tasks; model names and task ids kept), covering 6 packages. These are non-customer, real agent text, not author-written demo prose. Lockfiles are safe fixtures; the declaration line is the model's actual output.

共 9 条。每条都按「症状 → 图证据 → 修复 → 修复后 → 复现命令」记录。

## AGENT-minimax-flask-233 MiniMax-M2.5 on BigCodeBench/401: flask==2.3.3

- **症状**：real model output line `from flask import Flask  # VERSION=2.3.3` declares flask==2.3.3
- **根因**：flask 2.3.3 is inside GHSA range (fixed 3.1.1); the model output was already stale when produced
- **图证据**：Q6 path ['span:scan-root-0', 'span:scan-ret-0', 'src:scan-doc-0', 'pv:flask:2.3.3']; Q7 hop audit 1; Q8 drift 1; scan verdict BLOCK_MERGE_TEXT
- **修复**：reject the model output and keep flask==3.1.1
- **修复后**：scan returns BLOCK_MERGE_TEXT with 1 merge action(s)
- **复现**：`cd trace-lens && python -m tracelens.scan --text real-cases/real-agent/minimax-flask-233/text.txt --lockfile real-cases/real-agent/minimax-flask-233/requirements.lock --passport real-traces/scan/osv-batch-passport.json --as-of 2026-11-24T00:00:00Z --store real-cases/real-agent/minimax-flask-233/scan.rl --out real-cases/real-agent/minimax-flask-233/scan-verdict.json`
- **来源**：https://github.com/dw763j/PinTrace/blob/main/outputs/evaluation/direct_dependencies.jsonl (task BigCodeBench/401, model MiniMax-M2.5); PinTrace public evaluation output

## AGENT-llama-flask-222 meta-llama/llama-4-scout on BigCodeBench/80: flask==2.2.2

- **症状**：real model output line `from flask import Flask, render_template, request  # VERSION=2.2.2` declares flask==2.2.2
- **根因**：flask 2.2.2 is inside GHSA range (fixed 3.1.1); the model output was already stale when produced
- **图证据**：Q6 path ['span:scan-root-0', 'span:scan-ret-0', 'src:scan-doc-0', 'pv:flask:2.2.2']; Q7 hop audit 1; Q8 drift 1; scan verdict BLOCK_MERGE_TEXT
- **修复**：reject the model output and keep flask==3.1.1
- **修复后**：scan returns BLOCK_MERGE_TEXT with 1 merge action(s)
- **复现**：`cd trace-lens && python -m tracelens.scan --text real-cases/real-agent/llama-flask-222/text.txt --lockfile real-cases/real-agent/llama-flask-222/requirements.lock --passport real-traces/scan/osv-batch-passport.json --as-of 2026-11-24T00:00:00Z --store real-cases/real-agent/llama-flask-222/scan.rl --out real-cases/real-agent/llama-flask-222/scan-verdict.json`
- **来源**：https://github.com/dw763j/PinTrace/blob/main/outputs/evaluation/direct_dependencies.jsonl (task BigCodeBench/80, model meta-llama/llama-4-scout); PinTrace public evaluation output

## AGENT-claude-pillow-1000 claude-sonnet-4-6 on BigCodeBench/406: pillow==10.0.0

- **症状**：real model output line `from PIL import Image  # VERSION=10.0.0` declares pillow==10.0.0
- **根因**：pillow 10.0.0 is inside GHSA range (fixed 13.0.0); the model output was already stale when produced
- **图证据**：Q6 path ['span:scan-root-0', 'span:scan-ret-0', 'src:scan-doc-0', 'pv:pillow:10.0.0']; Q7 hop audit 1; Q8 drift 1; scan verdict BLOCK_MERGE_TEXT
- **修复**：reject the model output and keep pillow==13.0.0
- **修复后**：scan returns BLOCK_MERGE_TEXT with 1 merge action(s)
- **复现**：`cd trace-lens && python -m tracelens.scan --text real-cases/real-agent/claude-pillow-1000/text.txt --lockfile real-cases/real-agent/claude-pillow-1000/requirements.lock --passport real-traces/scan/osv-batch-passport.json --as-of 2026-11-24T00:00:00Z --store real-cases/real-agent/claude-pillow-1000/scan.rl --out real-cases/real-agent/claude-pillow-1000/scan-verdict.json`
- **来源**：https://github.com/dw763j/PinTrace/blob/main/outputs/evaluation/direct_dependencies.jsonl (task BigCodeBench/406, model claude-sonnet-4-6); PinTrace public evaluation output

## AGENT-minimax-pillow-950 MiniMax-M2.5 on BigCodeBench/406: pillow==9.5.0

- **症状**：real model output line `from PIL import Image  # VERSION=9.5.0` declares pillow==9.5.0
- **根因**：pillow 9.5.0 is inside GHSA range (fixed 13.0.0); the model output was already stale when produced
- **图证据**：Q6 path ['span:scan-root-0', 'span:scan-ret-0', 'src:scan-doc-0', 'pv:pillow:9.5.0']; Q7 hop audit 1; Q8 drift 1; scan verdict BLOCK_MERGE_TEXT
- **修复**：reject the model output and keep pillow==13.0.0
- **修复后**：scan returns BLOCK_MERGE_TEXT with 1 merge action(s)
- **复现**：`cd trace-lens && python -m tracelens.scan --text real-cases/real-agent/minimax-pillow-950/text.txt --lockfile real-cases/real-agent/minimax-pillow-950/requirements.lock --passport real-traces/scan/osv-batch-passport.json --as-of 2026-11-24T00:00:00Z --store real-cases/real-agent/minimax-pillow-950/scan.rl --out real-cases/real-agent/minimax-pillow-950/scan-verdict.json`
- **来源**：https://github.com/dw763j/PinTrace/blob/main/outputs/evaluation/direct_dependencies.jsonl (task BigCodeBench/406, model MiniMax-M2.5); PinTrace public evaluation output

## AGENT-kimi-pillow-1001 kimi-k2.5 on BigCodeBench/1019: pillow==10.0.1

- **症状**：real model output line `from PIL import Image  # VERSION=10.0.1` declares pillow==10.0.1
- **根因**：pillow 10.0.1 is inside GHSA range (fixed 13.0.0); the model output was already stale when produced
- **图证据**：Q6 path ['span:scan-root-0', 'span:scan-ret-0', 'src:scan-doc-0', 'pv:pillow:10.0.1']; Q7 hop audit 1; Q8 drift 1; scan verdict BLOCK_MERGE_TEXT
- **修复**：reject the model output and keep pillow==13.0.0
- **修复后**：scan returns BLOCK_MERGE_TEXT with 1 merge action(s)
- **复现**：`cd trace-lens && python -m tracelens.scan --text real-cases/real-agent/kimi-pillow-1001/text.txt --lockfile real-cases/real-agent/kimi-pillow-1001/requirements.lock --passport real-traces/scan/osv-batch-passport.json --as-of 2026-11-24T00:00:00Z --store real-cases/real-agent/kimi-pillow-1001/scan.rl --out real-cases/real-agent/kimi-pillow-1001/scan-verdict.json`
- **来源**：https://github.com/dw763j/PinTrace/blob/main/outputs/evaluation/direct_dependencies.jsonl (task BigCodeBench/1019, model kimi-k2.5); PinTrace public evaluation output

## AGENT-minimax-requests-2310 MiniMax-M2.5 on BigCodeBench/32: requests==2.31.0

- **症状**：real model output line `import requests  # VERSION=2.31.0` declares requests==2.31.0
- **根因**：requests 2.31.0 is inside GHSA-9hjg-9r4m-mvj7 range (fixed 2.32.4); the model output was already stale when produced
- **图证据**：Q6 path ['span:scan-root-0', 'span:scan-ret-0', 'src:scan-doc-0', 'pv:requests:2.31.0']; Q7 hop audit 1; Q8 drift 1; scan verdict BLOCK_MERGE_TEXT
- **修复**：reject the model output and keep requests==2.32.4
- **修复后**：scan returns BLOCK_MERGE_TEXT with 1 merge action(s)
- **复现**：`cd trace-lens && python -m tracelens.scan --text real-cases/real-agent/minimax-requests-2310/text.txt --lockfile real-cases/real-agent/minimax-requests-2310/requirements.lock --passport real-traces/scan/osv-batch-passport.json --as-of 2026-11-24T00:00:00Z --store real-cases/real-agent/minimax-requests-2310/scan.rl --out real-cases/real-agent/minimax-requests-2310/scan-verdict.json`
- **来源**：https://github.com/dw763j/PinTrace/blob/main/outputs/evaluation/direct_dependencies.jsonl (task BigCodeBench/32, model MiniMax-M2.5); PinTrace public evaluation output

## AGENT-claudesonnet-django-427 claude-sonnet-4-6 on BigCodeBench/181: django==4.2.7

- **症状**：real model output line `from django.http import HttpResponse` declares django==4.2.7
- **根因**：django 4.2.7 is inside GHSA-2mcm-79hx-8fxw range (fixed 6.0.2); the model output was already stale when produced
- **图证据**：Q6 path ['span:scan-root-0', 'span:scan-ret-0', 'src:scan-doc-0', 'pv:django:4.2.7']; Q7 hop audit 1; Q8 drift 1; scan verdict BLOCK_MERGE_TEXT
- **修复**：reject the model output and keep django==6.0.2
- **修复后**：scan returns BLOCK_MERGE_TEXT with 1 merge action(s)
- **复现**：`cd trace-lens && python -m tracelens.scan --text real-cases/real-agent/claudesonnet-django-427/text.txt --lockfile real-cases/real-agent/claudesonnet-django-427/requirements.lock --passport real-traces/scan/osv-batch-passport.json --as-of 2026-11-24T00:00:00Z --store real-cases/real-agent/claudesonnet-django-427/scan.rl --out real-cases/real-agent/claudesonnet-django-427/scan-verdict.json`
- **来源**：https://github.com/dw763j/PinTrace/blob/main/outputs/evaluation/direct_dependencies.jsonl (task BigCodeBench/181, model claude-sonnet-4-6); PinTrace public evaluation output

## AGENT-minimax-numpy-1210 MiniMax-M2.5 on BigCodeBench/10: numpy==1.21.0

- **症状**：real model output line `import numpy as np  # VERSION=1.21.0` declares numpy==1.21.0
- **根因**：numpy 1.21.0 is inside GHSA-fpfv-jqm9-f5jm range (fixed 1.22); the model output was already stale when produced
- **图证据**：Q6 path ['span:scan-root-0', 'span:scan-ret-0', 'src:scan-doc-0', 'pv:numpy:1.21.0']; Q7 hop audit 1; Q8 drift 1; scan verdict BLOCK_MERGE_TEXT
- **修复**：reject the model output and keep numpy==1.22
- **修复后**：scan returns BLOCK_MERGE_TEXT with 1 merge action(s)
- **复现**：`cd trace-lens && python -m tracelens.scan --text real-cases/real-agent/minimax-numpy-1210/text.txt --lockfile real-cases/real-agent/minimax-numpy-1210/requirements.lock --passport real-traces/scan/osv-batch-passport.json --as-of 2026-11-24T00:00:00Z --store real-cases/real-agent/minimax-numpy-1210/scan.rl --out real-cases/real-agent/minimax-numpy-1210/scan-verdict.json`
- **来源**：https://github.com/dw763j/PinTrace/blob/main/outputs/evaluation/direct_dependencies.jsonl (task BigCodeBench/10, model MiniMax-M2.5); PinTrace public evaluation output

## AGENT-deepseek-jinja2-312 DeepSeek-V3.2 on stackexchange-63901755: jinja2==3.1.2

- **症状**：real model output line `from jinja2 import Environment, PackageLoader, select_autoescape  # VERSION=3.1.2` declares jinja2==3.1.2
- **根因**：jinja2 3.1.2 is inside GHSA-cpwx-vrp4-4pq7 range (fixed 3.1.6); the model output was already stale when produced
- **图证据**：Q6 path ['span:scan-root-0', 'span:scan-ret-0', 'src:scan-doc-0', 'pv:jinja2:3.1.2']; Q7 hop audit 1; Q8 drift 1; scan verdict BLOCK_MERGE_TEXT
- **修复**：reject the model output and keep jinja2==3.1.6
- **修复后**：scan returns BLOCK_MERGE_TEXT with 1 merge action(s)
- **复现**：`cd trace-lens && python -m tracelens.scan --text real-cases/real-agent/deepseek-jinja2-312/text.txt --lockfile real-cases/real-agent/deepseek-jinja2-312/requirements.lock --passport real-traces/scan/osv-batch-passport.json --as-of 2026-11-24T00:00:00Z --store real-cases/real-agent/deepseek-jinja2-312/scan.rl --out real-cases/real-agent/deepseek-jinja2-312/scan-verdict.json`
- **来源**：https://github.com/dw763j/PinTrace/blob/main/outputs/evaluation/direct_dependencies.jsonl (task stackexchange-63901755, model DeepSeek-V3.2); PinTrace public evaluation output
