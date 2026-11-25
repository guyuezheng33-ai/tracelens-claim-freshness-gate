# Windows-native one-command verification (no Git Bash / make needed).
# Mirrors scripts/award-verify.sh step for step and writes the same
# logs/award-verify-*.log that the evidence pack reads its test count from.
# After the one-time `pip install -e .[dev]`, every step runs offline from
# committed snapshots and raw OSV record captures (real-traces/osv/records/):
# no OSV network fetch, no API key, no author-written demo prose.
param([string]$TraceLensPython)
$ErrorActionPreference = "Stop"
$Root = Split-Path $PSScriptRoot -Parent
$TL = Join-Path $Root "trace-lens"

if ($TraceLensPython) { $PY = $TraceLensPython }
elseif (Test-Path "$TL\.venv\Scripts\python.exe") { $PY = "$TL\.venv\Scripts\python.exe" }
else {
    python -m venv "$TL\.venv"
    $PY = "$TL\.venv\Scripts\python.exe"
    & $PY -m pip install -q -e "$TL[dev]"
    if ($LASTEXITCODE -ne 0) { throw "pip install failed" }
}
$env:PYTHONPATH = ".;$TL"
Set-Location $TL

$logDir = "$TL\logs"
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$log = Join-Path $logDir ("award-verify-" + (Get-Date -Format "yyyyMMddTHHmmss") + ".log")

function Step([string]$Label, [string[]]$PyArgs) {
    Write-Output "=== $Label ==="
    & $PY @PyArgs
    if ($LASTEXITCODE -ne 0) { throw "step failed: $Label (exit $LASTEXITCODE)" }
}

& {
    Step "[V1/创意] falsifiable head-to-head" @("-m","tracelens.falsify","--store","$TL/store/demo-run.rl","--out","$TL/docs/falsification.json","--md","$TL/docs/falsification.md")

    Write-Output "=== [V2/有用性] real failure case pack ==="
    foreach ($sub in @("real-user","real-agent")) {
        Get-ChildItem "$TL/real-cases/$sub" -Directory | ForEach-Object {
            $d = $_.FullName
            Step "scan $($_.Name)" @("-m","tracelens.scan","--text","$d/text.txt","--lockfile","$d/requirements.lock","--passport","$TL/real-traces/scan/osv-batch-passport.json","--as-of","2026-11-24T00:00:00Z","--store","$d/scan.rl","--out","$d/scan-verdict.json")
        }
    }
    Write-Output "=== [有用性/真实性] real public catch: model output line blocked ==="
    Step "public catch scan" @("-m","tracelens.scan","--text","$TL/public-catches/catch-001-minimax-flask-230/input.txt","--lockfile","$TL/public-catches/catch-001-minimax-flask-230/requirements.lock","--passport","$TL/real-traces/scan/osv-batch-passport.json","--as-of","2026-11-24T00:00:00Z","--store","$TL/public-catches/catch-001-minimax-flask-230/scan.rl","--out","$TL/public-catches/catch-001-minimax-flask-230/scan-verdict.json")

    Step "realcases validate" @("-m","tracelens.realcases","--md","$TL/docs/real-cases.md","--out","$TL/docs/real-cases-check.json")

    Step "[V3/完整性] real-scale traceable graph (pytest, offline)" @("-m","pytest","$TL/tests/test_realgraph.py","-q")

    Step "[V6/AI-agentic] real model call + graph-only rejection" @("-m","tracelens.guardrail","--store","$TL/store/demo-run.rl","--answer-before","$TL/real-traces/answer-before-fixture.json","--trace","$TL/real-traces/self-run-1.otlp.json","--out","$TL/real-traces/guardrail-run.json")

    Step "[V5/连接上下文] graph as diagnosis + runtime constraint" @("-m","tracelens.contextproof","--store","$TL/store/demo-run.rl","--guardrail","$TL/real-traces/guardrail-run.json","--realgraph","$TL/real-traces/osv/osv-passport.json","--out","$TL/docs/context-proof.json")

    Write-Output "=== [创意/有用性] answer-expiry on real OSV timeline ==="
    Step "expiryagent" @("-m","tracelens.expiryagent","--advisory","PYSEC-2014-14","--out","$TL/real-traces/expiry/answers.json")
    Step "expiry build" @("-m","tracelens.expiry","build","--advisories","PYSEC-2014-14","--answers","$TL/real-traces/expiry/answers.json","--store","$TL/real-traces/expiry/expiry.rl","--out","$TL/real-traces/expiry/advisories.json")
    Step "expiry query" @("-m","tracelens.expiry","query","--store","$TL/real-traces/expiry/expiry.rl","--out","$TL/real-traces/expiry/q5-result.json")
    Step "usecase" @("-m","tracelens.usecase")

    Step "[V4/清晰度] single-file interactive dashboard" @("-m","tracelens.dashboard","--store","$TL/store/demo-run.rl","--out","$TL/docs/award-dashboard.html","--answer-before","$TL/real-traces/answer-before-fixture.json","--answer-after","$TL/real-traces/self-check-fixture.json","--expiry","$TL/real-traces/expiry/report.json")

    Step "[连接上下文/主体] unified provenance graph" @("-m","tracelens.provenance","--advisories","$TL/real-traces/expiry/advisories.json","--as-of","2026-11-22T16:23:10Z","--store","$TL/real-traces/provenance/provenance.rl","--out","$TL/docs/provenance-verdict.json","--scenario-out","$TL/real-traces/provenance/scenario.json")

    Step "[有用性/完整度] one-command scan over 8 real advisories" @("-m","tracelens.scan","--text","$TL/real-traces/scan/pr-answer.txt","--lockfile","$TL/real-traces/scan/requirements.lock","--passport","$TL/real-traces/scan/osv-batch-passport.json","--store","$TL/real-traces/scan/scan.rl","--out","$TL/docs/scan-verdict.json")

    Step "[创意/连接上下文] Q9/Q10 convergence + blast radius" @("-m","tracelens.convergence","--passport","$TL/real-traces/scan/osv-batch-passport.json","--store","$TL/real-traces/convergence/convergence.rl","--out","$TL/docs/convergence-verdict.json")

    Step "[创意] Q11 fixpoint rule reasoning (derives born-stale, cross-checks Q8)" @("-m","tracelens.reasoning","--store","$TL/real-traces/scan/scan.rl","--scan-verdict","$TL/docs/scan-verdict.json","--out","$TL/docs/reasoning-verdict.json")
    Step "Q11 shared-collector counterfactual" @("$TL/real-traces/reasoning/build_shared_topology.py","--scan","$TL/real-traces/scan/scan.rl","--out","$TL/real-traces/reasoning/shared-retriever.rl")
    Step "[创意] Q11 minimum-repair on shared collector (1 cut vs 8 answers)" @("-m","tracelens.reasoning","--store","$TL/real-traces/reasoning/shared-retriever.rl","--scan-verdict","$TL/docs/__no_q8__.json","--out","$TL/docs/reasoning-shared-verdict.json")

    Write-Output "=== [连接上下文/清晰度] see your graph ==="
    Step "export provenance" @("-m","tracelens.graphexport","--store","$TL/real-traces/provenance/provenance.rl","--verdict","$TL/docs/provenance-verdict.json","--out","$TL/docs/graph-provenance.json","--title","单场景 · 溯源图")
    Step "export scan" @("-m","tracelens.graphexport","--store","$TL/real-traces/scan/scan.rl","--verdict","$TL/docs/scan-verdict.json","--out","$TL/docs/graph-scan.json","--title","批量 8 包 · scan 图（真实模型输出）")
    Step "export convergence" @("-m","tracelens.graphexport","--store","$TL/real-traces/convergence/convergence.rl","--verdict","$TL/docs/convergence-verdict.json","--out","$TL/docs/graph-convergence.json","--title","跨答案 · Q9/Q10 收敛图")
    Step "export osv" @("-m","tracelens.graphexport","--store","$TL/real-traces/osv/osv-graph.rl","--out","$TL/docs/graph-osv.json","--title","OSV 全量 · 真实漏洞图（交互探索）")
    Step "explorer" @("-m","tracelens.graphexplorer","--graph","$TL/docs/graph-provenance.json","--graph","$TL/docs/graph-scan.json","--graph","$TL/docs/graph-convergence.json","--graph","$TL/docs/graph-osv.json","--out","$TL/docs/graph-explorer.html")

    Write-Output "=== [有用性/反证] born-stale counterfactual ==="
    Step "cf-before answers" @("-m","tracelens.expiryagent","--as-of","2013-01-01T00:00:00Z","--out","$TL/real-traces/expiry/cf-before-answers.json")
    Step "cf-before build" @("-m","tracelens.expiry","build","--advisories","PYSEC-2014-14","--answers","$TL/real-traces/expiry/cf-before-answers.json","--store","$TL/real-traces/expiry/cf-before.rl","--out","$TL/real-traces/expiry/cf-before-adv.json")
    Step "cf-before query" @("-m","tracelens.expiry","query","--store","$TL/real-traces/expiry/cf-before.rl","--out","$TL/real-traces/expiry/cf-before-q5.json")
    Step "cf-after answers" @("-m","tracelens.expiryagent","--as-of","2026-11-22T16:23:10Z","--out","$TL/real-traces/expiry/cf-after-answers.json")
    Step "cf-after build" @("-m","tracelens.expiry","build","--advisories","PYSEC-2014-14","--answers","$TL/real-traces/expiry/cf-after-answers.json","--store","$TL/real-traces/expiry/cf-after.rl","--out","$TL/real-traces/expiry/cf-after-adv.json")
    Step "cf-after query" @("-m","tracelens.expiry","query","--store","$TL/real-traces/expiry/cf-after.rl","--out","$TL/real-traces/expiry/cf-after-q5.json")
    Step "expiryproof" @("-m","tracelens.expiryproof")

    Step "[ALL] full test suite" @("-m","pytest","$TL/tests","-q")
    Step "[EVIDENCE] programmatic evidence pack (this run only)" @("-m","tracelens.evidence")

    Write-Output "OK: six dimensions rebuilt and re-verified with this run's evidence"
} 2>&1 | Tee-Object -FilePath $log
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
Write-Output "log: $log"