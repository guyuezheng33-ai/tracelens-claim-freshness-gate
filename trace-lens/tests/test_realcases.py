"""Real cases must be complete, non-customer, and graph-referencing."""

from __future__ import annotations

import copy

from tracelens.realcases import DEFAULT_CASES, load, markdown, validate


def test_committed_cases_pass_validation():
    doc = load(DEFAULT_CASES)
    check = validate(doc)
    assert check["ok"] is True, check["errors"]
    assert check["case_count"] >= 3
    assert check["nature"] in {"real-development-failures", "real-user", "real-agent-text"}
    assert all(c["customer"] is False for c in doc["cases"])


def test_markdown_contains_every_case_and_reproduce_command():
    doc = load(DEFAULT_CASES)
    text = markdown(doc)
    for case in doc["cases"]:
        assert case["case_id"] in text
        assert case["symptom"] in text
        assert case["graph_evidence"] in text
        assert case["reproduce"] in text


def test_validation_rejects_missing_fields():
    doc = copy.deepcopy(load(DEFAULT_CASES))
    doc["cases"][0].pop("after")
    check = validate(doc)
    assert check["ok"] is False
    assert any("after missing" in e for e in check["errors"])


def test_validation_rejects_customer_claim():
    doc = copy.deepcopy(load(DEFAULT_CASES))
    doc["cases"][0]["customer"] = True
    check = validate(doc)
    assert check["ok"] is False
    assert any("customer must be false" in e for e in check["errors"])


def test_validation_rejects_too_few_cases():
    doc = copy.deepcopy(load(DEFAULT_CASES))
    doc["cases"] = doc["cases"][:2]
    check = validate(doc)
    assert check["ok"] is False
    assert any("at least 3" in e for e in check["errors"])


def test_validation_rejects_duplicate_ids():
    doc = copy.deepcopy(load(DEFAULT_CASES))
    doc["cases"][1]["case_id"] = doc["cases"][0]["case_id"]
    check = validate(doc)
    assert check["ok"] is False
    assert any("duplicate case_id" in e for e in check["errors"])
