# Windows-native one command: rebuild all graph exports and open the explorer.
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
function Step([string[]]$PyArgs) {
    & $PY @PyArgs
    if ($LASTEXITCODE -ne 0) { throw "graph step failed (exit $LASTEXITCODE)" }
}
Step @("-m","tracelens.graphexport","--store","real-traces/provenance/provenance.rl","--verdict","docs/provenance-verdict.json","--out","docs/graph-provenance.json","--title","单场景 · 溯源图")
Step @("-m","tracelens.graphexport","--store","real-traces/scan/scan.rl","--verdict","docs/scan-verdict.json","--out","docs/graph-scan.json","--title","批量 8 包 · scan 图（真实模型输出）")
Step @("-m","tracelens.graphexport","--store","real-traces/convergence/convergence.rl","--verdict","docs/convergence-verdict.json","--out","docs/graph-convergence.json","--title","跨答案 · Q9/Q10 收敛图")
Step @("-m","tracelens.graphexport","--store","real-traces/osv/osv-graph.rl","--out","docs/graph-osv.json","--title","OSV 全量 · 真实漏洞图（交互探索）")
Step @("-m","tracelens.graphexplorer","--graph","docs/graph-provenance.json","--graph","docs/graph-scan.json","--graph","docs/graph-convergence.json","--graph","docs/graph-osv.json","--out","docs/graph-explorer.html")
$p = (Resolve-Path "docs/graph-explorer.html").Path
Write-Output $p
Start-Process $p