"""Reproducible non-functional probe for TraceLens.

It builds a scaled graph from the committed deterministic fixture, times the
four query packs on a real persistent store, and probes parallel read handles.
Every number written to benchmarks/results.csv comes from this module's own
clock; nothing is copied from a document or an earlier run.

The workload is generated, not business data. The *timings* are real machine
measurements and are labelled as such in benchmarks/meta.json's caveat.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import tempfile
import time
from collections.abc import Sequence
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from pathlib import Path
from typing import Any

import relate

from .fixture import build_fixture
from .querypacks import QUERIES, run_pack
from .schema import GraphMapper

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUT = ROOT / "benchmarks" / "results.csv"

FIELDS = [
    "scenario", "query", "workers", "iterations",
    "store_bytes", "nodes", "relationships",
    "rows", "p50_ms", "p95_ms", "min_ms", "max_ms",
]


# ---------------------------------------------------------------------------
# workload construction
# ---------------------------------------------------------------------------
def build_scaled_fixture(extra_runs: int = 0) -> dict[str, Any]:
    """Return the two committed runs plus N renamed copies.

    Copies keep the same graph shape but carry distinct ids, so a query must
    walk the actual graph instead of hitting one hard-coded run. The original
    runs are always present: the judge and the query assertions stay valid.
    """
    base = build_fixture()
    if extra_runs < 0:
        raise ValueError("extra_runs must be >= 0")
    for i in range(extra_runs):
        prefix = f"s{i:03d}-"
        for template in base["runs"][:2]:
            run = deepcopy(template)
            old = run["run_id"]
            run["run_id"] = prefix + old
            run["root_spans"] = [prefix + s for s in run.get("root_spans", [])]
            for span in run["spans"]:
                span["span_id"] = prefix + span["span_id"]
                if span.get("parent_span_id"):
                    span["parent_span_id"] = prefix + span["parent_span_id"]
            for answer in run.get("answers", []):
                answer["answer_id"] = prefix + answer["answer_id"]
                answer["produced_by_span_id"] = prefix + answer["produced_by_span_id"]
                for claim in answer.get("claims", []):
                    claim["claim_id"] = prefix + claim["claim_id"]
            base["runs"].append(run)
    return base


def write_store(fixture: dict[str, Any], path: Path) -> dict[str, Any]:
    """Ingest the fixture into a real .rl store and return its size counters."""
    path.parent.mkdir(parents=True, exist_ok=True)
    db = relate.Database(str(path))
    try:
        mapper = GraphMapper(db)
        for run in fixture["runs"]:
            mapper.ingest_run(run)
        db.flush()
        return {
            "store_bytes": path.stat().st_size,
            "nodes": db.node_count(),
            "relationships": db.relationship_count(),
        }
    finally:
        db.close()


# ---------------------------------------------------------------------------
# timing helpers (no third-party statistics import: keeps the math axis honest)
# ---------------------------------------------------------------------------
def elapsed_ms(t0: float, t1: float) -> float:
    return round((t1 - t0) * 1000.0, 4)


def percentile(sorted_values: Sequence[float], fraction: float) -> float:
    """Linear-interpolated quantile on an already sorted, non-empty sequence."""
    if not sorted_values:
        raise ValueError("empty sample")
    if len(sorted_values) == 1:
        return round(float(sorted_values[0]), 4)
    pos = (len(sorted_values) - 1) * fraction
    low = int(pos)
    high = min(low + 1, len(sorted_values) - 1)
    value = sorted_values[low] + (sorted_values[high] - sorted_values[low]) * (pos - low)
    return round(float(value), 4)


def summarize(samples: Sequence[float]) -> dict[str, float]:
    s = sorted(float(x) for x in samples)
    return {
        "p50_ms": percentile(s, 0.50),
        "p95_ms": percentile(s, 0.95),
        "min_ms": round(s[0], 4),
        "max_ms": round(s[-1], 4),
    }


def _params_for(query: str, run_prefix: str) -> dict[str, Any]:
    p = dict(QUERIES[query]["params"])
    if query == "Q1":
        p["answer_id"] = run_prefix + "ba-ans"
    elif query == "Q4":
        p["root_id"] = run_prefix + "ba-root"
    return p


def time_query_pack(store: Path, query: str, iterations: int,
                    run_prefix: str = "") -> dict[str, Any]:
    """Time one pack on a fresh read-only handle; return rows + distribution."""
    if query not in QUERIES:
        raise KeyError(query)
    if iterations < 1:
        raise ValueError("iterations must be >= 1")
    db = relate.Database(str(store), read_only=True)
    samples: list[float] = []
    rows = 0
    try:
        for _ in range(iterations):
            t0 = time.perf_counter()
            result = run_pack(db, query, _params_for(query, run_prefix))
            t1 = time.perf_counter()
            samples.append(elapsed_ms(t0, t1))
            rows = len(result)
    finally:
        db.close()
    return {"rows": rows, "iterations": iterations, **summarize(samples)}


def time_parallel(store: Path, workers: int, iterations: int,
                  run_prefix: str) -> dict[str, Any]:
    """Run independent read handles at the same time; measure wall time."""
    def one_job(_: int) -> float:
        db = relate.Database(str(store), read_only=True)
        try:
            t0 = time.perf_counter()
            run_pack(db, "Q1", _params_for("Q1", run_prefix))
            return elapsed_ms(t0, time.perf_counter())
        finally:
            db.close()

    tasks = workers * iterations
    t0 = time.perf_counter()
    with ThreadPoolExecutor(max_workers=workers) as pool:
        samples = list(pool.map(one_job, range(tasks)))
    wall = elapsed_ms(t0, time.perf_counter())
    return {
        "rows": workers * iterations,
        "iterations": iterations,
        **summarize(samples),
        "wall_ms": wall,
        "queries_per_second": round(tasks / (wall / 1000.0), 2) if wall > 0 else 0.0,
    }


# ---------------------------------------------------------------------------
# committed artifact + passport
# ---------------------------------------------------------------------------
def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def write_results(rows: list[dict[str, Any]], out: Path) -> Path:
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=FIELDS)
        writer.writeheader()
        for row in rows:
            writer.writerow({k: row[k] for k in FIELDS})
    return out


def write_passport(csv_path: Path, command: str) -> Path:
    meta = {
        "schema": "tracelens/benchmark-measurement@1",
        "nature": "real",
        "source": command,
        "caveat": (
            "工作负载由 build_scaled_fixture 合成为压测图，只用于压测，不是业务事实；"
            "本表记录的是本机每次查询/并发的真实计时，换机器需重跑。"
        ),
        "files": [{
            "file": csv_path.name,
            "nature": "real",
            "sha256": sha256_file(csv_path),
            "source": command,
            "caveat": "计时实测；生成负载非事实数据，不得进入对外业务结论。",
        }],
    }
    path = csv_path.with_name("meta.json")
    path.write_text(json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def run_benchmark(extra_runs: int, iterations: int, worker_text: str,
                  out: Path, command: str) -> dict[str, Any]:
    workers = [int(x.strip()) for x in worker_text.split(",") if x.strip()]
    if not workers or any(w < 1 for w in workers):
        raise ValueError("workers must be a comma list of positive integers")
    fixture = build_scaled_fixture(extra_runs)
    with tempfile.TemporaryDirectory(prefix="tracelens-bench-") as tmp:
        store = Path(tmp) / "bench.rl"
        counters = write_store(fixture, store)
        prefix = f"s{extra_runs - 1:03d}-" if extra_runs else ""
        rows: list[dict[str, Any]] = []
        for query in QUERIES:
            m = time_query_pack(store, query, iterations, prefix)
            rows.append({
                "scenario": "single", "query": query, "workers": 1,
                "iterations": iterations, **counters,
                "rows": m["rows"], "p50_ms": m["p50_ms"], "p95_ms": m["p95_ms"],
                "min_ms": m["min_ms"], "max_ms": m["max_ms"],
            })
        for w in workers:
            m = time_parallel(store, w, 1, prefix)
            rows.append({
                "scenario": "parallel", "query": "Q1", "workers": w,
                "iterations": 1, **counters,
                "rows": m["rows"], "p50_ms": m["p50_ms"], "p95_ms": m["p95_ms"],
                "min_ms": m["min_ms"], "max_ms": m["max_ms"],
            })
    csv_path = write_results(rows, Path(out))
    meta_path = write_passport(csv_path, command)
    return {
        "out": str(csv_path),
        "passport": str(meta_path),
        "rows_written": len(rows),
        "extra_runs": extra_runs,
        "iterations": iterations,
        "workers": workers,
        "store_bytes": counters["store_bytes"],
        "nodes": counters["nodes"],
        "relationships": counters["relationships"],
    }


def main(argv: Sequence[str] | None = None) -> None:
    p = argparse.ArgumentParser(prog="python -m tracelens.bench")
    p.add_argument("--extra-runs", type=int, default=20,
                   help="number of renamed run pairs added to the two base runs")
    p.add_argument("--iterations", type=int, default=15,
                   help="timed executions per query pack")
    p.add_argument("--workers", default="1,4,8",
                   help="comma separated parallel read-handle counts")
    p.add_argument("--out", default=str(DEFAULT_OUT))
    args = p.parse_args(argv)
    command = (
        "python -m tracelens.bench --extra-runs %d --iterations %d --workers %s"
        % (args.extra_runs, args.iterations, args.workers)
    )
    print(json.dumps(run_benchmark(
        args.extra_runs, args.iterations, args.workers, Path(args.out), command
    ), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
