"""Tests for the reproducible non-functional probe and its data passport."""

from __future__ import annotations

import csv
import json

from tracelens.bench import (
    FIELDS,
    ROOT,
    build_scaled_fixture,
    percentile,
    run_benchmark,
    sha256_file,
    summarize,
    write_store,
)
from tracelens.querypacks import QUERIES, run_all


def test_scaled_fixture_is_deterministic_and_ids_are_unique():
    a = build_scaled_fixture(3)
    b = build_scaled_fixture(3)
    assert a == b
    assert len(a["runs"]) == 8  # 2 committed runs + 3 pairs of renamed copies
    ids = []
    for run in a["runs"]:
        ids.append(run["run_id"])
        ids.extend(s["span_id"] for s in run["spans"])
        ids.extend(x["answer_id"] for x in run.get("answers", []))
    assert len(ids) == len(set(ids))


def test_percentile_and_summary_are_monotone():
    assert percentile([1.0], 0.95) == 1.0
    assert percentile([1.0, 2.0, 3.0, 4.0], 0.5) == 2.5
    s = summarize([3.0, 1.0, 2.0])
    assert s["min_ms"] == 1.0 and s["max_ms"] == 3.0
    assert s["p50_ms"] <= s["p95_ms"]


def test_write_store_counts_real_nodes(tmp_path):
    counters = write_store(build_scaled_fixture(1), tmp_path / "one.rl")
    assert counters["nodes"] > 0
    assert counters["relationships"] > 0
    assert counters["store_bytes"] > 0


def test_all_query_assertions_hold_on_scaled_graph(tmp_path):
    """The tightened README definition promises 4 packs pass on 42 runs/381 nodes.

    Prove it on a real .rl store built from the same scaled fixture the
    benchmark uses -- not on the 2-run demo fixture.
    """
    import relate

    fixture = build_scaled_fixture(20)
    assert len(fixture["runs"]) == 42
    counters = write_store(fixture, tmp_path / "scaled.rl")
    assert counters["nodes"] == 381
    db = relate.Database(str(tmp_path / "scaled.rl"), read_only=True)
    try:
        results = run_all(db)
    finally:
        db.close()
    assert set(results) == set(QUERIES)
    for key, rows in results.items():
        assert QUERIES[key]["assert"](rows), "%s failed its own assertion" % key


def test_small_benchmark_produces_positive_measurements(tmp_path):
    out = tmp_path / "results.csv"
    summary = run_benchmark(1, 2, "1,2", out, "unit-test command")
    rows = list(csv.DictReader(out.open(encoding="utf-8", newline="")))
    assert summary["rows_written"] == len(rows) == 6
    assert all(float(r["p50_ms"]) >= 0 for r in rows)
    assert all(float(r["p95_ms"]) >= float(r["p50_ms"]) for r in rows)
    assert {r["scenario"] for r in rows} == {"single", "parallel"}


def test_committed_results_match_passport():
    csv_path = ROOT / "benchmarks" / "results.csv"
    meta_path = ROOT / "benchmarks" / "meta.json"
    assert csv_path.exists() and meta_path.exists()
    with csv_path.open(encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        assert reader.fieldnames == FIELDS
        rows = list(reader)
    assert len(rows) > 0
    assert all(float(r["p50_ms"]) > 0 for r in rows)
    assert {r["scenario"] for r in rows} == {"single", "parallel"}
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    assert meta["nature"] == "real"
    assert "合成" in meta["caveat"]
    assert meta["files"][0]["file"] == csv_path.name
    assert meta["files"][0]["sha256"] == sha256_file(csv_path)
