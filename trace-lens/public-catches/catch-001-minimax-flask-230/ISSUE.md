# Public catch #1 — MiniMax-M2.5 emits `flask 2.3.0`, stale against GHSA-4grg-w6v8-c28g

A coding model's real output line, captured verbatim from the public PinTrace
evaluation file, is rejected by TraceLens before merge:

```python
from flask import Flask  # VERSION=2.3.0
```

## Where the input comes from (verifiable upstream)

- File: [`outputs/evaluation/direct_dependencies.jsonl`](https://github.com/dw763j/PinTrace/blob/main/outputs/evaluation/direct_dependencies.jsonl)
- Line: **146**
- Task: `BigCodeBench/81` · Model: `MiniMax-M2.5`
- Declaration form: `inline_annotation`, specified version `2.3.0`

## What TraceLens decided

`BLOCK_MERGE_TEXT`. The graph matched the real advisory
[GHSA-4grg-w6v8-c28g](https://github.com/pallets/flask/security/advisories/GHSA-4grg-w6v8-c28g)
(aliases `CVE-2025-47278`, `PYSEC-2026-1377`, fixed **3.1.1**, published
2025-05-13). The Q6 provenance path resolves the advisory's public identity,
not just its row id:

```
span:scan-root-0 → span:scan-ret-0 → src:scan-doc-0 → pv:flask:2.3.0
→ adv:GHSA-4grg-w6v8-c28g → alias:CVE-2025-47278
→ https://nvd.nist.gov/vuln/detail/CVE-2025-47278
```

## Reproduce offline (no network after `pip install`)

```powershell
cd trace-lens
python -m tracelens.scan `
  --text public-catches/catch-001-minimax-flask-230/input.txt `
  --lockfile public-catches/catch-001-minimax-flask-230/requirements.lock `
  --passport real-traces/scan/osv-batch-passport.json `
  --as-of 2026-11-24T00:00:00Z `
  --store public-catches/catch-001-minimax-flask-230/scan.rl `
  --out public-catches/catch-001-minimax-flask-230/scan-verdict.json
```

Expected: `verdict = BLOCK_MERGE_TEXT`, `declarations_found = 1`,
`Q8_declaration_drift = 1`.

## Why a manifest scanner misses it

`requirements.lock` pins `flask==3.1.1` — the already-fixed state. `pip-audit`
/ Dependabot / OSV-Scanner report **clean**. The stale advice lives in the
sentence, not in the manifest, and only a claim-level gate reads it.

## Honest boundaries

- This is **captured public model output**, not a paying customer.
- The upstream row is annotated with `CVE-2023-30861` and `CVE-2026-27205`.
  This gate matched `GHSA-4grg-w6v8-c28g` (`CVE-2025-47278`); the claim here is
  only the advisory the graph actually resolved.
- The lockfile pin is scenario configuration (the project's already-fixed state),
  stated as such rather than presented as a real project's file.
