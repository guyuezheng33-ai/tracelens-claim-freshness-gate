#!/usr/bin/env bash
# One command: rebuild all graph exports and open the offline explorer.
# Finds or creates trace-lens/.venv automatically; no manual setup.
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
cd "$TL"
export PYTHONPATH=".:$TL"

"$PY" -m tracelens.graphexport --store real-traces/provenance/provenance.rl \
  --verdict docs/provenance-verdict.json \
  --out docs/graph-provenance.json --title "单场景 · 溯源图"
"$PY" -m tracelens.graphexport --store real-traces/scan/scan.rl \
  --verdict docs/scan-verdict.json \
  --out docs/graph-scan.json --title "批量 8 包 · scan 图（真实模型输出）"
"$PY" -m tracelens.graphexport --store real-traces/convergence/convergence.rl \
  --verdict docs/convergence-verdict.json \
  --out docs/graph-convergence.json --title "跨答案 · Q9/Q10 收敛图"
"$PY" -m tracelens.graphexport --store real-traces/osv/osv-graph.rl \
  --out docs/graph-osv.json --title "OSV 全量 · 真实漏洞图（交互探索）"
"$PY" -m tracelens.graphexplorer \
  --graph docs/graph-provenance.json --graph docs/graph-scan.json \
  --graph docs/graph-convergence.json --graph docs/graph-osv.json \
  --out docs/graph-explorer.html

"$PY" -c "import pathlib, webbrowser; p=pathlib.Path('docs/graph-explorer.html').resolve(); print(p); webbrowser.open(p.as_uri())"