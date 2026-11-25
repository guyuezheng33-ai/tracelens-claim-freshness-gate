"""单文件交互看板的离线测试：全部使用内存中的最小 fake 数据。

不访问网络，不读取/写入 fixtures/ 或 real-traces/，不需要真实 relate store。
"""

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tracelens.dashboard import EMPTY_PATH_TEXT, render_dashboard

RESULTS = {
    "Q1": [{
        "path": ["ba-root", "ba-retriever", "src:stale-policy-v2.pdf"],
        "labels": ["Span", "Span", "Source"],
        "bad_source": "stale-policy-v2.pdf",
        "score": 0.12,
        "hops": 2,
    }],
    "Q2": [{
        "doc": "stale-policy-v2.pdf",
        "branch_a": "branch-a",
        "branch_b": "branch-b",
        "convergence_path": ["branch-a", "ba-root", "branch-b"],
    }],
    "Q3": [{
        "claim_id": "ba-claim-bad",
        "text": "fake bad claim",
        "answer_id": "ba-ans",
        "run_id": "ba-run",
    }],
    "Q4": [{
        "root_span": "ba-root",
        "spans": 3,
        "total_cost": 0.0123,
        "output_tokens": 42,
        "slowest_ms": 7,
    }],
}

VERDICT = {
    "verdict": "PASS",
    "metric": "fake structure-derived localization metric",
    "checks": {
        "baseline_misidentifies": True,
        "graph_localizes_true_cause": True,
        "graph_zero_false_positive_on_clean": True,
        "has_signal": True,
    },
    "baseline_global_lowest_score_picks": "stale-policy-v2.pdf",
    "convergence_causes": ["stale-policy-v2.pdf"],
    "answers_with_signal": {"ba-ans": ["stale-policy-v2.pdf"]},
}

ANSWER_BEFORE = [
    {
        "claim_id": "ba-claim-bad",
        "source": "stale-policy-v2.pdf",
        "score": 0.12,
        "text": "UNIQUE_BEFORE_CLAIM_marker deadline is March 1",
    },
]
ANSWER_AFTER = [
    {
        "claim_id": "ba-claim-ok",
        "source": "current-policy-v9.pdf",
        "score": 0.94,
        "text": "UNIQUE_AFTER_CLAIM_marker policy v9 current",
    },
]
TOOL_CALLS = [
    {"tool": "tracelens_graph_info", "result": {"node_count": 21}},
    {"tool": "tracelens_judge", "result": "PASS"},
    {
        "tool": "tracelens_query_pack",
        "pack": "Q3",
        "rows": 1,
        "claim_ids": ["ba-claim-bad"],
    },
]


def _render(tmp_path, **overrides):
    kwargs = {
        "answer_before": ANSWER_BEFORE,
        "answer_after": ANSWER_AFTER,
        "tool_calls": TOOL_CALLS,
    }
    kwargs.update(overrides)
    return render_dashboard(tmp_path / "demo.rl", RESULTS, VERDICT, **kwargs)


def test_output_is_complete_self_contained_html(tmp_path):
    out = _render(tmp_path)
    assert out.lstrip().startswith("<!DOCTYPE html>")
    assert "</html>" in out
    assert "<style>" in out and "<script>" in out

    # 无外部资源引用：src=/href= 只能指向 # 锚点（这里完全没有）。
    external = re.findall(r"""(?:src|href)\s*=\s*["']([^"']*)["']""", out, re.IGNORECASE)
    assert all(v.startswith("#") for v in external), external
    assert "<link" not in out.lower()
    assert "<img" not in out.lower()
    assert "@import" not in out.lower()


def test_contains_four_packs_claims_and_tool_names(tmp_path):
    out = _render(tmp_path)
    for key in ("Q1", "Q2", "Q3", "Q4"):
        assert key in out
    assert "UNIQUE_BEFORE_CLAIM_marker" in out
    assert "UNIQUE_AFTER_CLAIM_marker" in out
    for tool in ("tracelens_graph_info", "tracelens_judge", "tracelens_query_pack"):
        assert tool in out


def test_summary_shows_verdict_and_baseline_contrast(tmp_path):
    out = _render(tmp_path)
    assert "PASS" in out
    assert "baseline_global_lowest_score_picks" not in out or "stale-policy-v2.pdf" in out
    assert "全局最低分基线" in out
    assert "图路径定位真因" in out


def test_script_json_has_no_unescaped_close_tag(tmp_path):
    out = _render(tmp_path)
    scripts = re.findall(r"<script[^>]*>(.*?)</script>", out, flags=re.DOTALL | re.IGNORECASE)
    assert len(scripts) >= 2
    for script in scripts:
        assert "</script" not in script.lower()
    # 嵌入数据里有中文与 </script 风格文本时也必须被安全序列化。
    hostile = _render(
        tmp_path,
        answer_before=[{
            "claim_id": "evil",
            "source": "x.pdf",
            "text": "</script><img src=x>",
        }],
    )
    hostile_scripts = re.findall(r"<script[^>]*>(.*?)</script>", hostile, flags=re.DOTALL | re.IGNORECASE)
    assert all("</script" not in s.lower() for s in hostile_scripts)
    assert "&lt;img src=x&gt;" in hostile


def test_dropped_claim_highlighted_with_reason_from_tool_call(tmp_path):
    out = _render(tmp_path)
    assert "Q3: no SUPPORTED_BY evidence path" in out
    assert "删除：" in out
    assert "一眼看清" in out


def test_unmatched_claim_shows_explicit_empty_path_message(tmp_path):
    out = _render(tmp_path)
    # ba-claim-ok / current-policy-v9.pdf 在 fake Q1/Q3 里都没有路径。
    assert EMPTY_PATH_TEXT in out


def test_render_without_self_check_still_complete(tmp_path):
    out = render_dashboard(tmp_path / "demo.rl", RESULTS, VERDICT)
    assert out.lstrip().startswith("<!DOCTYPE html>")
    assert "未提供自查记录" in out
    assert all(k in out for k in ("Q1", "Q2", "Q3", "Q4"))
