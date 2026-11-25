#!/usr/bin/env bash
# TraceLens one-command verification: from-scratch build, judge, report, tests.
set -euo pipefail

PY="${TRACELENS_PYTHON:-python}"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
APP="$ROOT/trace-lens"

export PYTHONPATH="$APP${PYTHONPATH:+:$PYTHONPATH}"
cd "$APP"

# Build from zero: a stale .rl store must never mask a fixture/code change.
rm -f store/demo-run.rl
"$PY" -m tracelens.cli build
"$PY" -m tracelens.cli judge
"$PY" -m tracelens.cli report --format html
"$PY" -m tracelens.cli report --format md
"$PY" -m pytest tests/ -q

# Real-pipeline gate: self-check loop must consume graph tool output.
"$PY" -m tracelens.cli agentloop \
  --store store/demo-run.rl \
  --answer-before real-traces/answer-before-fixture.json \
  --out real-traces/self-check-fixture.json

echo "OK: build -> judge -> report(html/md) -> pytest -> agentloop all passed"
