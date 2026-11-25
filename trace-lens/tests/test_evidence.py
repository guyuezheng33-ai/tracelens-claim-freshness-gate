"""Evidence-pack gate: numbers must be read, cross-checked and falsifiable."""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tracelens import evidence

ROOT = Path(__file__).resolve().parent.parent


def test_evidence_pack_passes_with_live_artefacts():
    doc = evidence.build()
    assert doc["verdict"] == "PASS", doc["checks"]
    assert all(doc["checks"].values()), doc["checks"]
    assert doc["measured"]["full_suite_tests_passed"] > 0


def test_measured_numbers_are_independently_recomputed():
    """Do not trust the pack's own numbers: re-read the source artefacts."""
    doc = evidence.build()
    scan = json.loads((ROOT / "docs/scan-verdict.json").read_text(encoding="utf-8"))
    prov = json.loads((ROOT / "docs/provenance-verdict.json").read_text(encoding="utf-8"))
    export = json.loads((ROOT / "docs/graph-scan.json").read_text(encoding="utf-8"))
    m = doc["measured"]
    assert m["text_declarations"] == scan["declarations_found"]
    assert m["q6_multihop_paths"] == scan["Q6_provenance_paths"]
    assert m["q8_drifts"] == scan["Q8_drifts"] == len(scan["Q8_declaration_drift"])
    assert m["merge_actions"] == len(scan["merge_actions"])
    assert m["single_scenario_graph"]["nodes"] == prov["graph"]["nodes"]
    assert m["batch_graph"]["nodes"] == export["counts"]["nodes"]
    assert m["batch_graph"]["relationships"] == export["counts"]["relationships"]


def test_markdown_and_json_render_from_one_object():
    doc = evidence.build()
    md = evidence.to_markdown(doc)
    assert str(doc["measured"]["real_advisories"]) in md
    assert doc["decision"]["graph_verdict"] in md
    assert doc["measured"]["verification_log"] in md
    for key in doc["checks"]:
        assert key in md


def test_pack_rejects_a_scan_that_stops_blocking_the_merge(tmp_path, monkeypatch):
    """Falsifiable by construction: flip the scan verdict and the pack FAILS."""
    scan = json.loads((ROOT / "docs/scan-verdict.json").read_text(encoding="utf-8"))
    scan["verdict"] = "PASS"
    fake = tmp_path / "scan.json"
    fake.write_text(json.dumps(scan, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setitem(evidence.FILES, "scan", fake)
    doc = evidence.build()
    assert doc["checks"]["graph_blocks_merge_text_where_sca_cannot"] is False
    assert doc["verdict"] == "FAIL"
