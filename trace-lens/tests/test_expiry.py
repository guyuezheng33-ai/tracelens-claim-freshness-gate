"""Answer-expiry tests: real advisory times, real answer times, no baked labels."""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest
from tracelens.expiry import advisory_view, build_store, iso_to_ns, parse_version, run_q5, version_affected
from tracelens.usecase import USER, markdown, render_report

REAL_ADVISORY = {
    "id": "PYSEC-2014-14",
    "published": "2014-10-15T14:55:00Z",
    "modified": "2024-10-21T22:22:54Z",
    "aliases": ["CVE-2014-1830"],
    "affected": [{
        "package": {"name": "requests", "ecosystem": "PyPI"},
        "ranges": [{"type": "ECOSYSTEM", "events": [
            {"introduced": "0"}, {"fixed": "2.3.0"}]}],
    }],
    "references": [{"type": "WEB", "url": "https://example.test/advisory"}],
    "summary": "test advisory",
}


def test_advisory_view_keeps_time_and_version_separate():
    v = advisory_view(REAL_ADVISORY)
    assert v["fixed"] == "2.3.0"
    # OSV `modified` is kept under an honest name; it is NOT a fix time.
    assert v["osv_modified_ns"] == iso_to_ns("2024-10-21T22:22:54Z")
    assert "fixed_ns" not in v
    # No real fix_available field in this record -> explicit unknown sentinel.
    assert v["fix_available_ns"] == -1
    assert v["published_ns"] < v["osv_modified_ns"]
    assert v["url"].startswith("https://")


def test_fix_available_comes_from_data_not_modified():
    """A real fix_available timestamp is used; modified never substitutes for it."""
    rec = copy.deepcopy(REAL_ADVISORY)
    rec["fix_available"] = "2014-11-01T00:00:00Z"
    v = advisory_view(rec)
    assert v["fix_available_ns"] == iso_to_ns("2014-11-01T00:00:00Z")
    assert v["fix_available_ns"] != v["osv_modified_ns"]


def test_version_range_uses_real_fixed_boundary():
    v = advisory_view(REAL_ADVISORY)
    assert version_affected(v, "2.2.0") is True
    assert version_affected(v, "2.3.0") is False
    assert parse_version("2.10.0") > parse_version("2.3.0")


def test_build_q5_distinguishes_stale_from_clean(tmp_path):
    v = advisory_view(REAL_ADVISORY)
    answers = [{
        "answer_id": "a1", "question": "q", "created_ns": iso_to_ns("2026-01-01T00:00:00Z"),
        "claims": [
            {"claim_id": "stale", "text": "old", "package": "requests", "version": "2.2.0"},
            {"claim_id": "clean", "text": "new", "package": "requests", "version": "2.3.0"},
        ],
    }]
    store = tmp_path / "expiry.rl"
    build_store(store, [v], answers)
    result = run_q5(store)
    assert result["verdict"] == "PASS"
    assert result["stale_count"] == 1
    assert result["clean_count"] == 1
    assert result["stale"][0]["claim_id"] == "stale"
    assert result["stale"][0]["advisory_url"].startswith("https://")


def test_advisory_does_not_affect_its_own_fixed_version(tmp_path):
    """Regression: an earlier build marked the fixed version as vulnerable."""
    v = advisory_view(REAL_ADVISORY)
    answers = [{
        "answer_id": "a1", "created_ns": iso_to_ns("2026-01-01T00:00:00Z"),
        "claims": [{"claim_id": "clean", "text": "fixed", "package": "requests",
                    "version": v["fixed"]}],
    }]
    store = tmp_path / "expiry.rl"
    build_store(store, [v], answers)
    result = run_q5(store)
    assert result["stale_count"] == 0
    assert result["clean_count"] == 1


def test_committed_answers_pipeline_is_consistent():
    root = Path(__file__).resolve().parent.parent
    base = root / "real-traces" / "expiry"
    if not (base / "q5-result.json").exists():
        pytest.skip("expiry run not produced yet")
    q5 = json.loads((base / "q5-result.json").read_text(encoding="utf-8"))
    ans = json.loads((base / "answers.json").read_text(encoding="utf-8"))
    adv = json.loads((base / "advisories.json").read_text(encoding="utf-8"))
    assert q5["verdict"] == "PASS"
    assert q5["stale_count"] == 1 and q5["clean_count"] == 1
    assert adv["advisories"][0]["published"].startswith("2014-")
    assert all(a["created_ns"] > adv["advisories"][0]["published_ns"]
               for a in ans["answers"])
    report = render_report(q5, ans, adv)
    assert report["summary"]["verdict"] == "PASS"
    assert report["stale_findings"][0]["public_evidence_url"].startswith("https://")
    assert "pin" in report["stale_findings"][0]["action"]


def test_report_rejects_hackathon_entrant_as_persona():
    assert "hackathon entrant" in USER["not_a_persona"]
    assert "developer" in USER["persona"]
    q5 = json.loads((Path(__file__).resolve().parent.parent /
                     "real-traces" / "expiry" / "q5-result.json").read_text(encoding="utf-8"))
    base = Path(__file__).resolve().parent.parent / "real-traces" / "expiry"
    report = render_report(q5, json.loads((base / "answers.json").read_text(encoding="utf-8")),
                           json.loads((base / "advisories.json").read_text(encoding="utf-8")))
    text = markdown(report)
    assert "developer or student" in text
    assert "参赛者" not in text


def test_public_advisory_with_late_fix_is_not_born_stale(tmp_path):
    """published < answer but fix shipped AFTER answer -> clean, not stale.

    This is the core counterfactual: a fix that did not exist at answer time
    cannot make that answer born-stale. Rejects the old 'published alone' rule.
    """
    rec = copy.deepcopy(REAL_ADVISORY)
    rec["fix_available"] = "2027-01-01T00:00:00Z"  # fix far after the answer
    v = advisory_view(rec)
    answers = [{
        "answer_id": "a-late-fix", "created_ns": iso_to_ns("2026-01-01T00:00:00Z"),
        "claims": [{"claim_id": "c", "text": "2.2.0", "package": "requests",
                    "version": "2.2.0"}],
    }]
    store = tmp_path / "expiry.rl"
    build_store(store, [v], answers)
    result = run_q5(store)
    assert result["stale_count"] == 0, "a not-yet-available fix must not mark answer stale"
    assert result["clean_count"] == 1


def test_answer_before_publication_is_not_born_stale(tmp_path):
    """answer predating the advisory is clean (counterfactual time control)."""
    v = advisory_view(REAL_ADVISORY)
    answers = [{
        "answer_id": "a-early", "created_ns": iso_to_ns("2013-01-01T00:00:00Z"),
        "claims": [{"claim_id": "c", "text": "2.2.0", "package": "requests",
                    "version": "2.2.0"}],
    }]
    store = tmp_path / "expiry.rl"
    build_store(store, [v], answers)
    result = run_q5(store)
    assert result["stale_count"] == 0
    assert result["clean_count"] == 1


def test_clean_version_is_checked_against_range_not_self_labelled():
    """The default run validates clean version is outside the advisory range."""
    v = advisory_view(REAL_ADVISORY)
    assert version_affected(v, "2.2.0") is True
    assert version_affected(v, v["fixed"]) is False


def test_external_answers_are_loaded_without_generation(tmp_path):
    """Independent answers bypass version/timestamp generation entirely."""
    from tracelens.expiryagent import load_external_answers
    doc = {"answers": [{
        "answer_id": "ext-1", "created_ns": 1700000000000000000,
        "claims": [{"claim_id": "e", "text": "x", "package": "requests", "version": "2.2.0"}],
    }]}
    p = tmp_path / "ext.json"
    p.write_text(json.dumps(doc), encoding="utf-8")
    answers, meta = load_external_answers(str(p))
    assert answers[0]["answer_id"] == "ext-1"
    assert meta["clock_source"] == "external"
    assert meta["clean_version_check"] == "not-generated-by-this-tool"


def test_report_without_stale_or_clean_fails(monkeypatch):
    base = Path(__file__).resolve().parent.parent / "real-traces" / "expiry"
    ans = json.loads((base / "answers.json").read_text(encoding="utf-8"))
    adv = json.loads((base / "advisories.json").read_text(encoding="utf-8"))
    empty = {"stale": [], "clean": [], "stale_count": 0, "clean_count": 0, "verdict": "FAIL"}
    report = render_report(empty, ans, adv)
    assert report["summary"]["verdict"] == "FAIL"
