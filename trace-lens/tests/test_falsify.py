"""Falsifiable comparison must produce a real head-to-head, not a narration."""

from __future__ import annotations

import json
from pathlib import Path

from tracelens.falsify import compare, report_markdown

ROOT = Path(__file__).resolve().parent.parent
STORE = ROOT / "store" / "demo-run.rl"


def test_compare_runs_both_detectors_on_the_same_store():
    if not STORE.exists():
        import pytest
        pytest.skip("demo store not built yet")
    record = compare(STORE)
    assert record["verdict"] in {"PASS", "FAIL"}
    assert record["judge"]["verdict"] in {"PASS", "FAIL"}
    assert record["baseline"]["pick"]
    assert record["graph"]["answers"] >= 2
    assert len(record["per_answer"]) == record["graph"]["answers"]
    for row in record["per_answer"]:
        assert row["baseline_pick"] == record["baseline"]["pick"]
        assert isinstance(row["graph_picks"], list)
        assert row["graph_path_count"] >= len(row["graph_picks"])


def test_falsifiable_checks_are_independently_computable():
    if not STORE.exists():
        import pytest
        pytest.skip("demo store not built yet")
    record = compare(STORE)
    checks = record["falsifiable_checks"]
    assert checks["baseline_is_answer_blind"] is True
    assert checks["baseline_wrong_on_at_least_one_answer"] is True
    # The graph must not simply repeat the baseline for every answer.
    assert checks["graph_distinguishes_answers"] is True
    assert record["judge"]["passed"] is True
    assert record["passed"] is True


def test_markdown_is_generated_from_the_same_record():
    if not STORE.exists():
        import pytest
        pytest.skip("demo store not built yet")
    record = compare(STORE)
    text = report_markdown(record)
    assert "全局最低分基线" in text
    assert "可证伪判据" in text
    for row in record["per_answer"]:
        assert row["answer_id"] in text
    assert record["baseline"]["pick"] in text
    # Report must contain no hardcoded verdict that contradicts the data.
    assert ("判定：**%s**" % record["verdict"]) in text


def test_compare_output_is_json_serialisable():
    if not STORE.exists():
        import pytest
        pytest.skip("demo store not built yet")
    record = compare(STORE)
    assert json.loads(json.dumps(record, ensure_ascii=False))["verdict"] == record["verdict"]
