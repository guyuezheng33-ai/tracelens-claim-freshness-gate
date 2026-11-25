#!/usr/bin/env bash
# Six competition dimensions, each with its own reproducible command and artefact.
# Run from anywhere. The script finds or creates trace-lens/.venv automatically;
# TRACELENS_PYTHON is an optional override, never a requirement.
# After the one-time `pip install -e .[dev]`, EVERY step below runs offline from
# committed snapshots (osv-batch-passport.json, osv-graph.rl, real-cases texts):
# no OSV network fetch, no API key, no author-written demo prose.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TL="$ROOT/trace-lens"
if [ -n "${TRACELENS_PYTHON:-}" ]; then
  PY="$TRACELENS_PYTHON"
elif [ -x "$TL/.venv/Scripts/python.exe" ]; then
  PY="$TL/.venv/Scripts/python.exe"
elif [ -x "$TL/.venv/bin/python" ]; then
  PY="$TL/.venv/bin/python"
else
  python -m venv "$TL/.venv"
  if [ -x "$TL/.venv/Scripts/python.exe" ]; then PY="$TL/.venv/Scripts/python.exe"; else PY="$TL/.venv/bin/python"; fi
  "$PY" -m pip install -q -e "$TL[dev]"
fi
# Windows Python cannot consume Git Bash's /d/... path in PYTHONPATH.
cd "$TL"
export PYTHONPATH=".:$TL"

echo "=== [V1/创意] falsifiable head-to-head ==="
"$PY" -m tracelens.falsify --store "$TL/store/demo-run.rl" \
  --out "$TL/docs/falsification.json" --md "$TL/docs/falsification.md"

echo "=== [V2/有用性] real failure case pack ==="
for d in "$TL"/real-cases/real-user/*/ "$TL"/real-cases/real-agent/*/; do
  "$PY" -m tracelens.scan \
    --text "$d/text.txt" --lockfile "$d/requirements.lock" \
    --passport "$TL/real-traces/scan/osv-batch-passport.json" \
    --as-of "2026-11-24T00:00:00Z" \
    --store "$d/scan.rl" --out "$d/scan-verdict.json"
done
echo "=== [有用性/真实性] real public catch: model output line blocked ==="
"$PY" -m tracelens.scan \
  --text "$TL/public-catches/catch-001-minimax-flask-230/input.txt" \
  --lockfile "$TL/public-catches/catch-001-minimax-flask-230/requirements.lock" \
  --passport "$TL/real-traces/scan/osv-batch-passport.json" \
  --as-of 2026-11-24T00:00:00Z \
  --store "$TL/public-catches/catch-001-minimax-flask-230/scan.rl" \
  --out "$TL/public-catches/catch-001-minimax-flask-230/scan-verdict.json"

"$PY" -m tracelens.realcases \
  --md "$TL/docs/real-cases.md" --out "$TL/docs/real-cases-check.json"

echo "=== [V3/完整性] real-scale traceable graph (pytest, offline) ==="
"$PY" -m pytest "$TL/tests/test_realgraph.py" -q

echo "=== [V6/AI-agentic] real model call + graph-only rejection ==="
"$PY" -m tracelens.guardrail --store "$TL/store/demo-run.rl" \
  --answer-before "$TL/real-traces/answer-before-fixture.json" \
  --trace "$TL/real-traces/self-run-1.otlp.json" \
  --out "$TL/real-traces/guardrail-run.json"

echo "=== [V5/连接上下文] graph as diagnosis + runtime constraint ==="
"$PY" -m tracelens.contextproof --store "$TL/store/demo-run.rl" \
  --guardrail "$TL/real-traces/guardrail-run.json" \
  --realgraph "$TL/real-traces/osv/osv-passport.json" \
  --out "$TL/docs/context-proof.json"

echo "=== [创意/有用性] answer-expiry on real OSV timeline ==="
"$PY" -m tracelens.expiryagent --advisory PYSEC-2014-14 \
  --out "$TL/real-traces/expiry/answers.json"
"$PY" -m tracelens.expiry build --advisories PYSEC-2014-14 \
  --answers "$TL/real-traces/expiry/answers.json" \
  --store "$TL/real-traces/expiry/expiry.rl" \
  --out "$TL/real-traces/expiry/advisories.json"
"$PY" -m tracelens.expiry query --store "$TL/real-traces/expiry/expiry.rl" \
  --out "$TL/real-traces/expiry/q5-result.json"
"$PY" -m tracelens.usecase

echo "=== [V4/清晰度] single-file interactive dashboard (with expiry timeline) ==="
"$PY" -m tracelens.dashboard --store "$TL/store/demo-run.rl" \
  --out "$TL/docs/award-dashboard.html" \
  --answer-before "$TL/real-traces/answer-before-fixture.json" \
  --answer-after "$TL/real-traces/self-check-fixture.json" \
  --expiry "$TL/real-traces/expiry/report.json"

echo "=== [连接上下文/主体] unified provenance graph: graph AS the intelligence ==="
"$PY" -m tracelens.provenance --advisories "$TL/real-traces/expiry/advisories.json" \
  --as-of 2026-11-22T16:23:10Z \
  --store "$TL/real-traces/provenance/provenance.rl" \
  --out "$TL/docs/provenance-verdict.json" \
  --scenario-out "$TL/real-traces/provenance/scenario.json"

echo "=== [有用性/完整度] one-command scan over 8 real advisories (offline passport) ==="
"$PY" -m tracelens.scan \
  --text "$TL/real-traces/scan/pr-answer.txt" \
  --lockfile "$TL/real-traces/scan/requirements.lock" \
  --passport "$TL/real-traces/scan/osv-batch-passport.json" \
  --store "$TL/real-traces/scan/scan.rl" \
  --out "$TL/docs/scan-verdict.json"

echo "=== [创意/连接上下文] Q9/Q10: cross-model convergence + advisory blast radius ==="
"$PY" -m tracelens.convergence \
  --passport "$TL/real-traces/scan/osv-batch-passport.json" \
  --store "$TL/real-traces/convergence/convergence.rl" \
  --out "$TL/docs/convergence-verdict.json"

echo "=== [创意] Q11: fixpoint rule reasoning derives born-stale, cross-checks Q8 ==="
"$PY" -m tracelens.reasoning \
  --store "$TL/real-traces/scan/scan.rl" \
  --scan-verdict "$TL/docs/scan-verdict.json" \
  --out "$TL/docs/reasoning-verdict.json"

echo "=== [创意] Q11: minimum repair on a shared collector (1 cut covers 8 answers) ==="
"$PY" "$TL/real-traces/reasoning/build_shared_topology.py" \
  --scan "$TL/real-traces/scan/scan.rl" \
  --out "$TL/real-traces/reasoning/shared-retriever.rl"
"$PY" -m tracelens.reasoning \
  --store "$TL/real-traces/reasoning/shared-retriever.rl" \
  --scan-verdict "$TL/docs/__no_q8__.json" \
  --out "$TL/docs/reasoning-shared-verdict.json"

echo "=== [连接上下文/清晰度] see your graph: live Cypher read-back -> single-file explorer ==="
"$PY" -m tracelens.graphexport --store "$TL/real-traces/provenance/provenance.rl" \
  --verdict "$TL/docs/provenance-verdict.json" \
  --out "$TL/docs/graph-provenance.json" --title "单场景 · 溯源图"
"$PY" -m tracelens.graphexport --store "$TL/real-traces/scan/scan.rl" \
  --verdict "$TL/docs/scan-verdict.json" \
  --out "$TL/docs/graph-scan.json" --title "批量 8 包 · scan 图（真实模型输出）"
"$PY" -m tracelens.graphexport --store "$TL/real-traces/convergence/convergence.rl" \
  --verdict "$TL/docs/convergence-verdict.json" \
  --out "$TL/docs/graph-convergence.json" --title "跨答案 · Q9/Q10 收敛图"
"$PY" -m tracelens.graphexport --store "$TL/real-traces/osv/osv-graph.rl" \
  --out "$TL/docs/graph-osv.json" --title "OSV 全量 · 真实漏洞图（交互探索）"
"$PY" -m tracelens.graphexplorer \
  --graph "$TL/docs/graph-provenance.json" --graph "$TL/docs/graph-scan.json" \
  --graph "$TL/docs/graph-convergence.json" --graph "$TL/docs/graph-osv.json" \
  --out "$TL/docs/graph-explorer.html"

echo "=== [有用性/反证] born-stale counterfactual: same version, time flips verdict ==="
"$PY" -m tracelens.expiryagent --as-of 2013-01-01T00:00:00Z \
  --out "$TL/real-traces/expiry/cf-before-answers.json"
"$PY" -m tracelens.expiry build --advisories PYSEC-2014-14 \
  --answers "$TL/real-traces/expiry/cf-before-answers.json" \
  --store "$TL/real-traces/expiry/cf-before.rl" \
  --out "$TL/real-traces/expiry/cf-before-adv.json"
"$PY" -m tracelens.expiry query --store "$TL/real-traces/expiry/cf-before.rl" \
  --out "$TL/real-traces/expiry/cf-before-q5.json"
"$PY" -m tracelens.expiryagent --as-of 2026-11-22T16:23:10Z \
  --out "$TL/real-traces/expiry/cf-after-answers.json"
"$PY" -m tracelens.expiry build --advisories PYSEC-2014-14 \
  --answers "$TL/real-traces/expiry/cf-after-answers.json" \
  --store "$TL/real-traces/expiry/cf-after.rl" \
  --out "$TL/real-traces/expiry/cf-after-adv.json"
"$PY" -m tracelens.expiry query --store "$TL/real-traces/expiry/cf-after.rl" \
  --out "$TL/real-traces/expiry/cf-after-q5.json"
"$PY" -m tracelens.expiryproof

echo "=== [ALL] full test suite ==="
"$PY" -m pytest "$TL/tests" -q

# Runs AFTER pytest on purpose: it reads the test count from THIS run's log,
# never from a remembered or previous result.
echo "=== [EVIDENCE] programmatic evidence pack (this run only) ==="
"$PY" -m tracelens.evidence

echo "OK: six dimensions rebuilt and re-verified with this run's evidence"
