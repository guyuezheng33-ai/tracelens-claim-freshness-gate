"""G1 programmatic gate: every pack must return non-empty, G1-compliant rows.

Run: python -m pytest tests/ -v
This is the CI gate that a judge can re-run with one command.
"""

import inspect
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import relate

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tracelens.querypacks import QUERIES, run_all
from tracelens.schema import GraphMapper

ROOT = Path(__file__).resolve().parent.parent
STORE = ROOT / "store" / "demo-run.rl"
FIXTURE = ROOT / "fixtures" / "demo-trace.json"


def _db(read_only=True):
    return relate.Database(str(STORE), read_only=read_only)


def test_store_persisted_and_nonempty():
    assert STORE.exists() and STORE.stat().st_size > 0
    db = _db()
    assert db.node_count() > 0
    assert db.relationship_count() > 0
    assert "Span" in db.labels() and "Source" in db.labels()
    db.close()


def test_all_four_packs_nonempty_and_g1_compliant():
    db = _db()
    results = run_all(db)
    db.close()
    for key, rows in results.items():
        assert len(rows) >= 1, f"{key} returned empty rows"
        assert QUERIES[key]["assert"](rows), f"{key} failed its G1 assertion: {rows}"


def test_q1_path_ends_at_source_no_null():
    db = _db()
    rows = run_all(db)["Q1"]
    db.close()
    assert len(rows) >= 1
    for r in rows:
        assert all(x is not None for x in r["path"]), f"null in path: {r['path']}"
        assert r["labels"][-1] == "Source", f"path does not end at Source: {r['labels']}"


def test_q2_old_noop_is_indeed_empty():
    """Regression: the deprecated self-loop query must stay empty (proof it was a no-op)."""
    db = _db()
    rows = list(db.execute(
        "MATCH p=(s:Span)-[:PARENT_OF*2..10]->(s) RETURN length(p) AS n"
    ).data)
    db.close()
    assert rows == [], "A real call tree must not contain PARENT_OF cycles"


def test_q3_discriminates_bad_from_good():
    db = _db()
    rows = run_all(db)["Q3"]
    db.close()
    ids = {r["claim_id"] for r in rows}
    assert "ba-claim-bad" in ids and "ba-claim-ok" not in ids


def test_g2_metric_is_measured_not_hardcoded():
    db = _db()
    out = {
        # Scope marker: these counts are for the Q1-Q4 diagnostic demo store,
        # NOT the born-stale graphs (19/19 and 162/175). Without this a reader
        # sees 21/22 and assumes an old number leaked back into the pack.
        "store": "store/demo-run.rl",
        "scope": "Q1-Q4 diagnostic demo graph only; not the born-stale claim graph",
        "nodes": db.node_count(),
        "relationships": db.relationship_count(),
        "labels": db.labels(),
        "relationship_types": db.relationship_types(),
    }
    db.close()
    (ROOT / "docs" / "measured-metrics.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    assert out["nodes"] > 0 and out["relationships"] > 0


def test_cli_one_command_repro():
    """Judge-facing: python -m tracelens.cli build && query all."""
    env = dict(os.environ)
    env["PYTHONPATH"] = str(ROOT)
    r = subprocess.run(
        [sys.executable, "-m", "tracelens.cli", "query", "--pack", "all"],
        cwd=str(ROOT), env=env, capture_output=True, text=True, check=False,
    )
    assert r.returncode == 0, r.stderr
    data = json.loads(r.stdout)
    assert all(v["passed"] for v in data.values()), data


def test_g2_graph_beats_global_lowest_score_baseline():
    """G2 effect size: without the graph, the lowest score misidentifies the cause."""
    db = _db()
    baseline = list(db.execute(
        "MATCH (s:Source) WHERE s.node_id CONTAINS 'bad-answer' "
        "RETURN s.doc_id AS doc ORDER BY s.score ASC LIMIT 1"
    ).data)
    graph_rows = run_all(db)["Q1"]
    db.close()
    assert baseline and baseline[0]["doc"] == "cache-tmp.bin", baseline
    assert graph_rows and all(
        r["bad_source"] == "stale-policy-v2.pdf" for r in graph_rows
    ), graph_rows
    (ROOT / "docs" / "g2-effect.json").write_text(
        json.dumps({
            "metric": "root-cause localization on the bad-answer run",
            "baseline_global_lowest_score_picks": baseline[0]["doc"],
            "baseline_correct": False,
            "tracelens_answer_path_picks": graph_rows[0]["bad_source"],
            "tracelens_correct": True,
        }, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def test_g2_strict_judge_localizes_and_no_false_positive():
    """Stricter G2: correct root cause on bad run + zero false positives on clean run."""
    from tracelens.judge import judge
    v = judge(STORE)
    assert v["checks"]["baseline_misidentifies"] is True, v
    assert v["checks"]["graph_localizes_true_cause"] is True, v
    assert v["checks"]["graph_zero_false_positive_on_clean"] is True, v
    assert v["verdict"] == "PASS", v


def test_judge_cli_emits_structured_verdict():
    env = dict(os.environ)
    env["PYTHONPATH"] = str(ROOT)
    r = subprocess.run(
        [sys.executable, "-m", "tracelens.cli", "judge"],
        cwd=str(ROOT), env=env, capture_output=True, text=True, check=False,
    )
    assert r.returncode == 0, r.stderr
    data = json.loads(r.stdout)
    assert data["verdict"] == "PASS" and data["passed"] is True, data
    assert set(data["checks"]) == {
        "baseline_misidentifies", "graph_localizes_true_cause",
        "graph_zero_false_positive_on_clean", "has_signal",
    }, data



def test_judge_is_structural_no_hardcoded_literals():
    """Judge must derive the verdict, not memorize committed doc names."""
    from tracelens import judge as jmod
    src = inspect.getsource(jmod)
    for literal in ["stale-policy-v2.pdf", "cache-tmp.bin", "ba-ans", "cl-ans", "bad-answer"]:
        assert literal not in src, "judge hardcoded %s" % literal
    assert "MATCH (a:Answer)" in src and "MATCH (s:Source)" in src


def _build_oos_store(dest):
    """Build an out-of-sample store (different ids/doc names, same shape)."""
    import relate
    from tracelens.oos_fixture import FIXTURE
    from tracelens.schema import GraphMapper
    db = relate.Database(str(dest), read_only=False)
    for run in FIXTURE["runs"]:
        GraphMapper(db).ingest_run(run)
    db.close()
    return dest


def test_judge_on_out_of_sample_store():
    """Same structure, different ids/doc names -> judge still PASS."""
    import tempfile

    from tracelens.judge import judge
    with tempfile.TemporaryDirectory() as d:
        s = _build_oos_store(Path(d) / "oos.rl")
        v = judge(s)
    assert v["verdict"] == "PASS", v
    assert v["convergence_causes"] == ["obsolete-regulations-2019.pdf"], v
    assert v["baseline_global_lowest_score_picks"] == "telemetry-scratch.tmp", v
    assert set(v["answers_with_signal"]) == {"x-ans"} and v["answers_clean"] == ["y-ans"], v


def test_judge_rejects_degenerate_store_no_control():
    """Falsifiability: without a clean control the judge must not pass."""
    import tempfile

    import relate
    from tracelens.judge import judge
    from tracelens.oos_fixture import FIXTURE
    from tracelens.schema import GraphMapper
    with tempfile.TemporaryDirectory() as d:
        s = Path(d) / "degenerate.rl"
        db = relate.Database(str(s), read_only=False)
        GraphMapper(db).ingest_run(FIXTURE["runs"][0])  # only the bad run
        db.close()
        v = judge(s)
    assert v["verdict"] == "FAIL" and v["checks"]["has_signal"] is False, v


def test_render_html_and_markdown_share_the_same_verdict():
    """Presentation layer: both views are built from one in-memory result."""
    import relate
    from tracelens.judge import judge
    from tracelens.render import render_dashboard_html, render_report_markdown

    with tempfile.TemporaryDirectory() as d:
        s = Path(d) / "view.rl"
        db = relate.Database(str(s), read_only=False)
        for run in json.loads((ROOT / "fixtures" / "demo-trace.json").read_text(encoding="utf-8"))["runs"]:
            GraphMapper(db).ingest_run(run)
        db.close()
        db = relate.Database(str(s), read_only=True)
        try:
            results = run_all(db)
        finally:
            db.close()
        v = judge(s)

    page = render_dashboard_html(results, v, str(s))
    md = render_report_markdown(results, v, str(s))
    assert "<html" in page and "dashboard" in page.lower()
    assert "ans:ba-ans" in page and "stale-policy-v2.pdf" in page
    assert "cache-tmp.bin" in page and "PASS" in page
    for key, val in v["checks"].items():
        assert key in page and key in md
        assert ("通过" if val else "未通过") in page
    assert "stale-policy-v2.pdf" in md and "cache-tmp.bin" in md
    assert "| Q1 |" in md


def test_report_cli_writes_both_formats():
    env = dict(os.environ)
    env["PYTHONPATH"] = str(ROOT)
    for fmt, name in (("html", "dashboard.html"), ("md", "report.md")):
        with tempfile.TemporaryDirectory() as d:
            out = Path(d) / name
            r = subprocess.run(
                [sys.executable, "-m", "tracelens.cli", "report",
                 "--format", fmt, "--out", str(out)],
                cwd=str(ROOT), env=env, capture_output=True, text=True, check=False,
            )
            assert r.returncode == 0, r.stderr
            data = json.loads(r.stdout)
            assert data["verdict"] == "PASS" and data["format"] == fmt, data
            assert out.exists() and out.stat().st_size > 400
            body = out.read_text(encoding="utf-8")
            assert "stale-policy-v2.pdf" in body and "PASS" in body, body[:200]



def test_data_dictionary_fields_match_schema_source():
    """Data dictionary must index fields that actually exist in the mapper."""
    from tracelens import schema
    dd = (ROOT / "docs" / "DATA_DICTIONARY.md").read_text(encoding="utf-8")
    src = inspect.getsource(schema)
    for field in ["node_id", "span_id", "run_id", "kind", "duration_ms",
                  "input_tokens", "output_tokens", "cost", "status", "call_id",
                  "tool_name", "arguments_hash", "doc_id", "uri", "snippet_hash",
                  "score", "rank", "answer_id", "text_hash", "claim_id"]:
        assert field in dd, "dictionary missing field %s" % field
        assert field in src, "schema missing field %s" % field


def test_cli_writes_audit_log_without_polluting_stdout():
    """A CLI run leaves structured log lines; stdout stays parseable JSON."""
    from tracelens.auditlog import read_events
    env = dict(os.environ)
    env["PYTHONPATH"] = str(ROOT)
    r = subprocess.run(
        [sys.executable, "-m", "tracelens.cli", "judge"],
        cwd=str(ROOT), env=env, capture_output=True, text=True, check=False,
    )
    assert r.returncode == 0, r.stderr
    verdict = json.loads(r.stdout)  # would fail if logging leaked into stdout
    assert verdict["verdict"] == "PASS", verdict
    tail = read_events()[-2:]
    assert [e["event"] for e in tail] == ["cli_start", "cli_done"], tail
    assert all(e["cmd"] == "judge" for e in tail), tail
