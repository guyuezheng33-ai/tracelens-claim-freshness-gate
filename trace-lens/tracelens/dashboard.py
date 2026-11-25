"""单文件交互看板：60 秒内从错误答案点到污染来源路径。

本模块是黑客松「清晰度」维度的证据：把四个查询包的结构诊断、G2 判定以及
agent 自查时间旅行（before -> 图诊断 -> after）渲染成一个零外部资源的 HTML
文件。评委离线双击即可打开，点击任意区块/声明即可展开其证据链。

设计约束：
  * 单一 HTML 文件，CSS/JS/数据全部内联，不引用任何 CDN / 字体 / 图片；
  * 所有进入 HTML 的值都经过 html.escape；
  * 嵌入 <script> 的 JSON 使用安全序列化（转义 < > & 与行分隔符）。

CLI:
  python -m tracelens.dashboard --store <rl> --out <html> \
      [--answer-before <json>] [--answer-after <json>] [--trace <json>]
"""
from __future__ import annotations

import argparse
import html
import json
from collections import defaultdict
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

from .querypacks import QUERIES

PACK_ORDER = ("Q1", "Q2", "Q3", "Q4")
EMPTY_PATH_TEXT = "该 store 无对应图路径"
_Q3_UNSUPPORTED = "Q3: no SUPPORTED_BY evidence path"

_STYLE = """
:root { color-scheme: light; --ink:#1d2330; --muted:#5b6475; --line:#e2e6ee;
        --bg:#f7f8fa; --blue:#1a5fb4; --green:#17693a; --red:#a32d2d; }
* { box-sizing: border-box; }
body { font-family: system-ui, -apple-system, "Segoe UI", sans-serif; margin:0;
       padding:28px 32px 56px; background:var(--bg); color:var(--ink); line-height:1.5; }
h1 { font-size:23px; font-weight:650; margin:0 0 6px; }
h2 { font-size:16px; font-weight:650; margin:0 0 12px; }
.sub { color:var(--muted); font-size:13px; margin:4px 0 0; }
.card { background:#fff; border:1px solid var(--line); border-radius:10px;
        padding:16px 20px; margin-bottom:16px; }
section { margin-bottom:26px; }
code { font-family:ui-monospace, SFMono-Regular, Consolas, monospace; font-size:12px;
       background:#f1f3f7; border-radius:4px; padding:1px 5px; }
table { border-collapse:collapse; width:100%; font-size:13px; }
th,td { text-align:left; padding:7px 10px; border-bottom:1px solid #edf0f5;
        vertical-align:top; }
th { color:var(--muted); font-weight:600; }
.badge { display:inline-block; font-size:12px; font-weight:650; padding:2px 9px;
         border-radius:999px; }
.pass { background:#e6f4ea; color:var(--green); }
.fail { background:#fce8e6; color:var(--red); }
.unknown { background:#eef0f4; color:var(--muted); }
.tag { display:inline-block; background:#eef3fb; border:1px solid #cbdcf5;
       color:var(--blue); border-radius:5px; padding:1px 7px; font-size:11px;
       margin-right:6px; font-weight:600; }
.tag.tool { background:#f3effb; border-color:#d9cbf5; color:#6d3fb5; }
.tag.pack { background:#e6f4ea; border-color:#bfe3cb; color:var(--green); }
.tag.drop { background:#fce8e6; border-color:#f3c6c2; color:var(--red); }
details { border:1px solid var(--line); border-radius:8px; background:#fff;
          margin:8px 0; overflow:hidden; }
details > summary { cursor:pointer; padding:11px 14px; font-size:13px;
                    list-style:none; display:flex; align-items:center; gap:6px;
                    flex-wrap:wrap; }
details > summary::-webkit-details-marker { display:none; }
details > summary::before { content:"\\25B8"; color:#8a93a5; font-size:11px; }
details[open] > summary::before { content:"\\25BE"; }
details > summary:hover { background:#fafbfd; }
.detail-body { padding:4px 16px 14px; border-top:1px solid #edf0f5; }
.muted { color:var(--muted); font-size:12px; }
.chain { display:inline-block; background:#eef3fb; border:1px solid #cbdcf5;
         border-radius:5px; padding:2px 7px; font-family:ui-monospace, monospace;
         font-size:12px; }
.arrow { color:#8a93a5; margin:0 4px; }
.controls { display:flex; gap:8px; margin-bottom:10px; }
button { font:inherit; font-size:12px; padding:5px 11px; border:1px solid var(--line);
         background:#fff; border-radius:6px; cursor:pointer; color:var(--ink); }
button:hover { background:#f1f3f7; }
button.active { background:#eef3fb; border-color:#cbdcf5; color:var(--blue); }
pre { white-space:pre-wrap; word-break:break-word; font-size:12px; background:#fafbfd;
      border:1px solid var(--line); border-radius:6px; padding:10px 12px; margin:8px 0; }
.callout { border-left:4px solid var(--blue); background:#f4f8ff; border-radius:6px;
           padding:10px 14px; font-size:13px; margin:10px 0; }
.callout.dropped-callout { border-left-color:var(--red); background:#fff5f4; }
.claim.dropped > summary { background:#fff5f4; }
.stage { font-size:11px; color:var(--muted); text-transform:uppercase;
         letter-spacing:.04em; margin:14px 0 2px; font-weight:650; }
[hidden] { display:none !important; }
"""


# --------------------------------------------------------------------------- #
# 安全序列化 / 小工具
# --------------------------------------------------------------------------- #
def _esc(value: Any) -> str:
    return html.escape(str(value), quote=True)


def _json_for_script(data: Any) -> str:
    """JSON 文本，保证不能提前闭合 <script> 标签。"""
    text = json.dumps(data, ensure_ascii=False, default=str)
    return (
        text.replace("&", "\\u0026")
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
        .replace("\u2028", "\\u2028")
        .replace("\u2029", "\\u2029")
    )


def _pretty(value: Any) -> str:
    try:
        return _esc(json.dumps(value, ensure_ascii=False, indent=2, default=str))
    except Exception:  # noqa: BLE001 - rendering fallback: any unserialisable value renders as text
        return _esc(value)


def _as_list(value: Any) -> list:
    if isinstance(value, list):
        return value
    if value is None:
        return []
    return [value]


def _pack_passed(key: str, rows: list[dict]) -> bool | None:
    fn = QUERIES.get(key, {}).get("assert")
    if not callable(fn):
        return None
    try:
        return bool(fn(rows))
    except Exception:  # noqa: BLE001 - a broken check assert must render as "unknown", never crash the board
        return False


def _passed_badge(passed: bool | None) -> str:
    if passed is None:
        return '<span class="badge unknown">未知</span>'
    cls = "pass" if passed else "fail"
    return '<span class="badge %s">%s</span>' % (cls, "PASS" if passed else "FAIL")


# --------------------------------------------------------------------------- #
# 路径 / 声明匹配
# --------------------------------------------------------------------------- #
def _build_path_index(results: Mapping[str, list[dict]]) -> tuple[dict, dict]:
    """按 claim_id / source 建立 Q1/Q3 证据路径索引。"""
    by_claim: dict[str, list[dict]] = defaultdict(list)
    by_source: dict[str, list[dict]] = defaultdict(list)

    for key in ("Q1", "Q3"):
        for row in results.get(key, []) or []:
            if not isinstance(row, dict):
                continue
            cid = row.get("claim_id")
            path = list(_as_list(row.get("path") or row.get("convergence_path")))
            labels = list(_as_list(row.get("labels")))
            if key == "Q3" and cid and not path:
                # Q3 的结构证据是 Claim -> Answer（且无 SUPPORTED_BY 边）。
                path = ["claim:%s" % cid, "answer:%s" % row.get("answer_id", "?")]
                labels = ["Claim", "Answer"]
            if not path:
                continue
            entry = {
                "pack": key,
                "path": path,
                "labels": labels,
                "source": row.get("bad_source") or row.get("doc") or row.get("source"),
                "score": row.get("score"),
                "hops": row.get("hops"),
                "row": row,
            }
            if cid:
                by_claim[str(cid)].append(entry)
            source = row.get("bad_source") or row.get("source") or row.get("doc")
            if source:
                by_source[str(source)].append(entry)
            tail = str(path[-1])
            if tail.startswith("src:"):
                by_source[tail[4:]].append(entry)
    return by_claim, by_source


def _matching_entries(claim: Mapping[str, Any], by_claim: dict, by_source: dict) -> list[dict]:
    keys = [str(claim.get("claim_id") or ""), str(claim.get("source") or "")]
    found: list[dict] = []
    seen: set = set()
    for key in keys:
        if not key:
            continue
        for entry in by_claim.get(key, []) + by_source.get(key, []):
            marker = (entry["pack"], tuple(str(x) for x in entry["path"]))
            if marker not in seen:
                seen.add(marker)
                found.append(entry)
    return found


def _path_entry_html(entry: dict) -> str:
    nodes = []
    for i, node in enumerate(entry["path"]):
        label = entry["labels"][i] if i < len(entry["labels"]) else ""
        nodes.append('<span class="chain">%s%s</span>' % (
            ("%s: " % _esc(label)) if label else "", _esc(node)
        ))
    chain = '<span class="arrow">&rarr;</span>'.join(nodes)
    meta = []
    if entry.get("source"):
        meta.append("污染来源 <code>%s</code>" % _esc(entry["source"]))
    if entry.get("score") is not None:
        meta.append("分数 %s" % _esc(entry["score"]))
    if entry.get("hops") is not None:
        meta.append("%s 跳" % _esc(entry["hops"]))
    return (
        '<div class="callout"><span class="tag pack">%s</span>%s'
        '<div class="muted">%s</div></div>'
    ) % (_esc(entry["pack"]), chain, " &middot; ".join(meta) if meta else "结构路径证据")


def _claim_html(claim: Mapping[str, Any], by_claim: dict, by_source: dict,
                drop_reason: str | None = None) -> str:
    cid = str(claim.get("claim_id") or "")
    source = str(claim.get("source") or "")
    text = claim.get("text") or cid or source or "(无文本)"
    entries = _matching_entries(claim, by_claim, by_source)
    cls = "claim dropped" if drop_reason else "claim"
    head = '<span class="tag">声明</span>%s' % _esc(text)
    if cid:
        head += ' <code>%s</code>' % _esc(cid)
    if source:
        head += ' <span class="muted">来源 %s</span>' % _esc(source)
    if drop_reason:
        head += ' <span class="tag drop">删除：%s</span>' % _esc(drop_reason)
    body = "".join(_path_entry_html(e) for e in entries) if entries else (
        '<p class="muted">%s</p>' % EMPTY_PATH_TEXT
    )
    return '<details class="%s"><summary>%s</summary><div class="detail-body">%s</div></details>' % (
        cls, head, body
    )


# --------------------------------------------------------------------------- #
# 时间旅行：从 tool_calls 提取 drop_reason
# --------------------------------------------------------------------------- #
def _collect_drop_reasons(tool_calls: Iterable[Mapping[str, Any]] | None) -> dict[str, str]:
    reasons: dict[str, str] = {}
    for call in tool_calls or []:
        if not isinstance(call, dict):
            continue
        mapping = call.get("drop_reasons")
        if isinstance(mapping, dict):
            for cid, reason in mapping.items():
                reasons[str(cid)] = str(reason)
        single = call.get("drop_reason")
        if single:
            ids = list(_as_list(call.get("claim_ids")))
            if call.get("claim_id"):
                ids.append(call["claim_id"])
            for cid in ids:
                reasons[str(cid)] = str(single)
        tool = str(call.get("tool") or "")
        if tool == "tracelens_query_pack" and str(call.get("pack") or "") == "Q3":
            for cid in _as_list(call.get("claim_ids")):
                reasons.setdefault(str(cid), _Q3_UNSUPPORTED)
        result = call.get("result")
        if isinstance(result, dict):
            nested = result.get("drop_reasons")
            if isinstance(nested, dict):
                for cid, reason in nested.items():
                    reasons.setdefault(str(cid), str(reason))
            for key in ("claim_ids", "unsupported_claims_from_q3"):
                for cid in _as_list(result.get(key)):
                    reasons.setdefault(str(cid), _Q3_UNSUPPORTED)
    return reasons


def _tool_call_html(call: Mapping[str, Any], by_claim: dict, by_source: dict) -> str:
    tool = str(call.get("tool") or "unknown-tool")
    head = '<span class="tag tool">%s</span>' % _esc(tool)
    if call.get("pack"):
        head += '<span class="tag pack">%s</span>' % _esc(call["pack"])
    if call.get("rows") is not None:
        head += '<span class="muted">%s 行</span>' % _esc(call["rows"])
    ids = list(_as_list(call.get("claim_ids")))
    if ids:
        head += '<span class="muted">标记 %s</span>' % _esc(", ".join(str(i) for i in ids))

    body = ""
    q3_rows = []
    for cid in ids:
        q3_rows.extend(_matching_entries({"claim_id": cid}, by_claim, by_source))
    if q3_rows:
        body += '<div class="stage">Q3 路径证据</div>'
        body += "".join(_path_entry_html(e) for e in q3_rows)
    elif str(call.get("pack") or "") == "Q3" or tool == "tracelens_query_pack":
        body += '<p class="muted">%s</p>' % EMPTY_PATH_TEXT
    body += '<div class="stage">工具返回（原始 JSON）</div><pre>%s</pre>' % _pretty(call)
    return '<details class="toolcall"><summary>%s</summary><div class="detail-body">%s</div></details>' % (
        head, body
    )


# --------------------------------------------------------------------------- #
# 各区块
# --------------------------------------------------------------------------- #
def _summary_html(results: Mapping[str, list[dict]], verdict: Mapping[str, Any]) -> str:
    ok = verdict.get("verdict") == "PASS"
    badge = '<span class="badge %s" style="font-size:14px">%s</span>' % (
        "pass" if ok else "fail", _esc(verdict.get("verdict") or "UNKNOWN")
    )
    metric = verdict.get("metric") or ""
    checks = verdict.get("checks") or {}
    check_rows = "".join(
        "<tr><td><code>%s</code></td><td>%s</td></tr>" % (
            _esc(k), _passed_badge(bool(v))
        )
        for k, v in checks.items() if isinstance(checks, Mapping)
    ) or '<tr><td colspan="2" class="muted">无判定检查项</td></tr>'

    keys = list(results.keys())
    ordered = [k for k in PACK_ORDER if k in keys] + [k for k in keys if k not in PACK_ORDER]
    pack_rows = "".join(
        "<tr><td><strong>%s</strong></td><td>%s</td><td>%d</td><td>%s</td></tr>" % (
            _esc(k), _esc(QUERIES.get(k, {}).get("name", "")),
            len(results.get(k, []) or []), _passed_badge(_pack_passed(k, results.get(k, []) or [])),
        )
        for k in ordered
    )

    baseline = verdict.get("baseline_global_lowest_score_picks")
    causes = list(_as_list(verdict.get("convergence_causes")))
    cause_text = ", ".join("<code>%s</code>" % _esc(c) for c in causes) or "—"
    compare = (
        '<table><thead><tr><th>方式</th><th>结论</th><th>解读</th></tr></thead><tbody>'
        '<tr><td>全局最低分基线</td><td><code>%s</code></td>'
        '<td>对每条答案都一样，无法定位被污染的那一条（误判）</td></tr>'
        '<tr><td>图路径定位真因</td><td>%s</td>'
        '<td>由 Q2 收敛 motif 与 Q1 证据路径结构推导</td></tr>'
        '</tbody></table>'
    ) % (_esc(baseline if baseline is not None else "—"), cause_text)

    return (
        '<section class="card"><h2>① 摘要：判定 / 查询包 / 真因对照</h2>'
        '<div>%s</div><p class="sub">%s</p>'
        '<div class="stage">判定检查</div><table><thead><tr><th>检查项</th><th>结果</th></tr></thead>'
        '<tbody>%s</tbody></table>'
        '<div class="stage">查询包行数（共 %d 包）</div>'
        '<table><thead><tr><th>包</th><th>名称</th><th>行数</th><th>断言</th></tr></thead>'
        '<tbody>%s</tbody></table>'
        '<div class="stage">基线 vs 图定位真因</div>%s'
        '</section>'
    ) % (badge, _esc(metric), check_rows, len(ordered), pack_rows, compare)


def _rows_table(rows: list[dict]) -> str:
    if not rows:
        return '<p class="muted">该查询包在此 store 返回 0 行。</p>'
    columns: list[str] = []
    for row in rows:
        if isinstance(row, dict):
            for key in row:
                if key not in columns:
                    columns.append(key)
    if not columns:
        return '<p class="muted">无字段</p>'
    head = "".join("<th>%s</th>" % _esc(c) for c in columns)
    body = []
    for row in rows:
        cells = []
        for col in columns:
            value = row.get(col) if isinstance(row, dict) else row
            if isinstance(value, (list, tuple)):
                chain = '<span class="arrow">&rarr;</span>'.join(
                    '<span class="chain">%s</span>' % _esc(x) for x in value
                )
                cells.append('<td>%s</td>' % chain)
            elif value is None:
                cells.append('<td class="muted">—</td>')
            elif isinstance(value, dict):
                cells.append('<td><code>%s</code></td>' % _esc(json.dumps(value, ensure_ascii=False, default=str)))
            else:
                cells.append('<td>%s</td>' % _esc(value))
        body.append("<tr>%s</tr>" % "".join(cells))
    return (
        '<table class="table-view"><thead><tr>%s</tr></thead><tbody>%s</tbody></table>'
    ) % (head, "".join(body))


def _packs_html(results: Mapping[str, list[dict]]) -> str:
    keys = list(results.keys())
    ordered = [k for k in PACK_ORDER if k in keys] + [k for k in keys if k not in PACK_ORDER]
    blocks = []
    for key in ordered:
        rows = results.get(key, []) or []
        meta = QUERIES.get(key, {})
        passed = _pack_passed(key, rows)
        head = (
            '<span class="tag pack">%s</span><strong>%s</strong>'
            '<span class="muted">%s</span><span class="muted">%d 行</span>%s'
        ) % (
            _esc(key), _esc(meta.get("name", "")), _esc(meta.get("question", "")),
            len(rows), _passed_badge(passed),
        )
        body = (
            '<div class="controls">'
            '<button type="button" class="view-btn active" data-view="table">表格视图</button>'
            '<button type="button" class="view-btn" data-view="json">JSON 视图</button>'
            '</div>'
            '<div class="table-view-wrap">%s</div>'
            '<div class="json-view" hidden><pre>%s</pre></div>'
        ) % (_rows_table(rows), _pretty(rows))
        blocks.append('<details class="pack" open><summary>%s</summary><div class="detail-body">%s</div></details>' % (
            head, body
        ))
    return (
        '<section><h2>② 四个查询包（点击标题展开 / 折叠，可切换 JSON 视图）</h2>'
        '<div class="controls">'
        '<button type="button" id="expand-all">全部展开</button>'
        '<button type="button" id="collapse-all">全部折叠</button>'
        '</div>%s</section>'
    ) % "".join(blocks)


def _timetravel_html(answer_before: list[dict] | None,
                     answer_after: list[dict] | None,
                     tool_calls: list[dict] | None,
                     by_claim: dict, by_source: dict) -> str:
    before = [c for c in (answer_before or []) if isinstance(c, dict)]
    after = [c for c in (answer_after or []) if isinstance(c, dict)]
    calls = [c for c in (tool_calls or []) if isinstance(c, dict)]
    if not (before or after or calls):
        return (
            '<section class="card"><h2>③ 答案自查时间旅行</h2>'
            '<p class="muted">未提供自查记录。命令行传入 --answer-before / --answer-after '
            '（可指向 self-check JSON）后，此处逐条展示 before claim、图诊断工具动作与 after claim。</p>'
            '</section>'
        )

    reasons = _collect_drop_reasons(calls)
    after_ids = {str(c.get("claim_id")) for c in after if c.get("claim_id")}
    dropped = [c for c in before if str(c.get("claim_id")) not in after_ids]

    before_html = "".join(
        _claim_html(c, by_claim, by_source, reasons.get(str(c.get("claim_id"))))
        for c in before
    ) or '<p class="muted">无 before claim</p>'

    diag_html = "".join(_tool_call_html(c, by_claim, by_source) for c in calls) or (
        '<p class="muted">无工具调用记录</p>'
    )
    after_html = "".join(_claim_html(c, by_claim, by_source) for c in after) or (
        '<p class="muted">无 after claim（全部被图证据删除）</p>'
    )

    drop_lines = "".join(
        '<li>%s &larr; <strong>%s</strong></li>' % (
            _esc(c.get("text") or c.get("claim_id") or "(无文本)"),
            _esc(reasons.get(str(c.get("claim_id")), "图证据标记删除")),
        )
        for c in dropped
    )
    callout = ""
    if drop_lines:
        callout = (
            '<div class="callout dropped-callout"><strong>一眼看清：</strong>'
            '被删除的 claim 与图给出的删除理由'
            '<ul>%s</ul>点击每条 claim 可展开其 Q1/Q3 路径直达污染来源。</div>'
        ) % drop_lines

    return (
        '<section class="card"><h2>③ 答案自查时间旅行：before &rarr; 图诊断 &rarr; after</h2>'
        '%s'
        '<div class="stage">BEFORE：自查前答案（%d 条，红框为被删 claim）</div>%s'
        '<div class="stage">DIAGNOSE：MCP 工具诊断动作（点击展开工具名与 Q3 路径证据）</div>%s'
        '<div class="stage">AFTER：自查后答案（%d 条）</div>%s'
        '</section>'
    ) % (callout, len(before), before_html, diag_html, len(after), after_html)


def _expiry_html(expiry: Mapping[str, Any] | None) -> str:
    """答案保质期时间轴：advisory 发布时刻 vs 答案墙钟，逐条 stale/clean。"""
    if not expiry:
        return ""
    summary = expiry.get("summary") or {}
    stale = [f for f in (expiry.get("stale_findings") or []) if isinstance(f, dict)]
    clean = [f for f in (expiry.get("clean_findings") or []) if isinstance(f, dict)]
    verdict = expiry.get("verdict") or summary.get("verdict") or ""
    badge = '<span class="badge %s">%s</span>' % (
        "pass" if verdict == "PASS" else "fail", _esc(verdict or "N/A")
    )

    def finding_row(f: Mapping[str, Any], stale_row: bool) -> str:
        cited = f.get("cited") or "%s %s" % (f.get("package", ""), f.get("version", ""))
        if stale_row:
            detail = (
                "漏洞自 <code>%s</code> 公开 · 答案生成于 %s · 滞后 <strong>%s 天</strong>" % (
                    _esc(f.get("known_vulnerable_since", "?")),
                    _esc(f.get("answer_created", "?")),
                    _esc(f.get("advisory_aged_days_at_answer", "?")),
                )
            )
            url = str(f.get("public_evidence_url", ""))
            if url:
                # Shown as text, never as a live <a href>: the dashboard stays
                # fully offline with zero outbound requests of any kind.
                detail += " · 公开证据 <code>%s</code>" % _esc(url)
            detail += " · 动作：<strong>%s</strong>" % _esc(f.get("action", "?"))
            tag = '<span class="tag drop">出生即过期</span>'
        else:
            detail = "无 advisory 覆盖此版本 · %s" % _esc(f.get("status", "clean"))
            tag = '<span class="tag pack">干净</span>'
        return "<li>%s <code>%s</code><div class=\"muted\">%s</div></li>" % (
            tag, _esc(cited), detail
        )

    stale_html = "".join(finding_row(f, True) for f in stale) or '<li class="muted">无过期声明</li>'
    clean_html = "".join(finding_row(f, False) for f in clean) or '<li class="muted">无干净声明</li>'
    user = expiry.get("user") or {}
    question = user.get("question", "答案出生时引用的版本是否已过期？")
    return (
        '<section class="card"><h2>⓪ 答案保质期：合并前的一条 Cypher 判定</h2>'
        '<p class="sub">要回答的问题：%s · 判定 %s</p>'
        '<div class="stage">需要拒绝（出生即过期）</div><ul>%s</ul>'
        '<div class="stage">通过（干净）</div><ul>%s</ul>'
        '<p class="muted">advisory 与答案时间来自真实 OSV 记录与运行墙钟；'
        '时间反事实对照见 docs/expiry-counterfactual.json（同一版本、答案时间前移则判定翻转）。</p>'
        '</section>'
    ) % (_esc(question), badge, stale_html, clean_html)


_SCRIPT_JS = """
(function () {
  function setView(btn, showTable) {
    var box = btn.closest('.pack');
    if (!box) { return; }
    var table = box.querySelector('.table-view-wrap');
    var json = box.querySelector('.json-view');
    if (table) { table.hidden = !showTable; }
    if (json) { json.hidden = showTable; }
    var buttons = box.querySelectorAll('.view-btn');
    for (var i = 0; i < buttons.length; i++) {
      var active = (buttons[i].getAttribute('data-view') === 'table') === showTable;
      buttons[i].classList.toggle('active', active);
    }
  }
  var viewButtons = document.querySelectorAll('.view-btn');
  for (var i = 0; i < viewButtons.length; i++) {
    viewButtons[i].addEventListener('click', function () {
      setView(this, this.getAttribute('data-view') === 'table');
    });
  }
  var expand = document.getElementById('expand-all');
  var collapse = document.getElementById('collapse-all');
  if (expand) {
    expand.addEventListener('click', function () {
      var all = document.querySelectorAll('details');
      for (var j = 0; j < all.length; j++) { all[j].open = true; }
    });
  }
  if (collapse) {
    collapse.addEventListener('click', function () {
      var all = document.querySelectorAll('details');
      for (var j = 0; j < all.length; j++) { all[j].open = false; }
    });
  }
})();
"""


# --------------------------------------------------------------------------- #
# 核心渲染
# --------------------------------------------------------------------------- #
def render_dashboard(
    store: Path,
    results: dict[str, list[dict]],
    verdict: dict,
    answer_before: list[dict] | None = None,
    answer_after: list[dict] | None = None,
    tool_calls: list[dict] | None = None,
    expiry: Mapping[str, Any] | None = None,
) -> str:
    """返回完整、自包含、离线可打开的 HTML 看板字符串。"""
    results = dict(results or {})
    verdict = dict(verdict or {})
    by_claim, by_source = _build_path_index(results)

    embedded = {
        "schema": "tracelens/dashboard@1",
        "store": str(store),
        "verdict": verdict,
        "packs": {
            key: {
                "name": QUERIES.get(key, {}).get("name", ""),
                "question": QUERIES.get(key, {}).get("question", ""),
                "rows": results.get(key, []),
            }
            for key in results
        },
        "answer_before": answer_before,
        "answer_after": answer_after,
        "tool_calls": tool_calls,
        "drop_reasons": _collect_drop_reasons(tool_calls),
        "expiry": dict(expiry) if expiry else None,
    }

    return """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>TraceLens · 单文件交互看板</title>
<style>%s</style>
</head>
<body>
<h1>TraceLens · 单文件交互看板</h1>
<p class="sub">store: <code>%s</code> · 零外部资源，离线可打开 · 点击任意区块展开证据</p>
%s
%s
%s
%s
<script>window.__TRACELENS_DASHBOARD__ = %s;</script>
<script>%s</script>
<footer><p class="muted">由 tracelens.dashboard 从查询结果与结构判定同源生成 · 单文件 / 无网络依赖</p></footer>
</body>
</html>
""" % (
        _STYLE, _esc(store), _expiry_html(expiry),
        _summary_html(results, verdict), _packs_html(results),
        _timetravel_html(answer_before, answer_after, tool_calls, by_claim, by_source),
        _json_for_script(embedded), _SCRIPT_JS,
    )


# --------------------------------------------------------------------------- #
# CLI 辅助：加载自查记录
# --------------------------------------------------------------------------- #
def _load_json(path: str) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _extract_claims(doc: Any, key: str) -> list[dict] | None:
    if isinstance(doc, dict):
        value = doc.get(key)
        return value if isinstance(value, list) else None
    if isinstance(doc, list):
        return doc
    return None


def _merge_self_check(doc: Any, state: dict) -> None:
    """从 self-check / agent-loop 记录中抽取 before/after/tool_calls。"""
    if isinstance(doc, dict):
        for key, target in (
            ("answer_before", "answer_before"),
            ("answer_after", "answer_after"),
            ("tool_calls", "tool_calls"),
        ):
            value = doc.get(key)
            if isinstance(value, list) and state.get(target) is None:
                state[target] = value
        reasons = doc.get("drop_reasons")
        if isinstance(reasons, dict):
            state.setdefault("drop_reasons", {}).update(reasons)


def _attach_drop_reasons(state: dict) -> None:
    """把自查记录顶层的 drop_reasons 挂进 tool_calls，便于从工具证据里读取。"""
    reasons = state.get("drop_reasons") or {}
    calls = state.get("tool_calls")
    if not reasons or not calls:
        return
    for call in calls:
        if call.get("pack") == "Q3" or "query_pack" in str(call.get("tool") or ""):
            call["drop_reasons"] = dict(reasons)
            return
    calls.append({
        "tool": "tracelens_query_pack",
        "pack": "Q3",
        "claim_ids": list(reasons.keys()),
        "drop_reasons": dict(reasons),
    })


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(prog="python -m tracelens.dashboard")
    p.add_argument("--store", required=True, help="持久化 .rl store 路径")
    p.add_argument("--out", required=True, help="输出单文件 HTML 路径")
    p.add_argument("--answer-before", default=None, help="before claim JSON（list 或自查记录）")
    p.add_argument("--answer-after", default=None, help="after claim JSON；self-check 记录会自动抽取")
    p.add_argument("--trace", default=None, help="可选自查记录 JSON，作为 before/after/tool_calls 的补充来源")
    p.add_argument("--expiry", default=None, help="可选答案保质期报告 JSON（report.json），渲染时间轴区块")
    args = p.parse_args(argv)

    import relate

    from .judge import judge
    from .querypacks import run_all

    store = Path(args.store)
    db = relate.Database(str(store), read_only=True)
    try:
        results = run_all(db)
    finally:
        db.close()
    verdict = judge(store)

    state: dict[str, Any] = {
        "answer_before": None,
        "answer_after": None,
        "tool_calls": None,
        "drop_reasons": {},
    }
    if args.answer_before:
        doc = _load_json(args.answer_before)
        state["answer_before"] = _extract_claims(doc, "answer_before")
        _merge_self_check(doc, state)
    if args.answer_after:
        doc = _load_json(args.answer_after)
        if isinstance(doc, dict):
            # self-check / agent-loop 记录：自动抽取 answer_after 与 tool_calls。
            _merge_self_check(doc, state)
            if state["answer_after"] is None:
                state["answer_after"] = _extract_claims(doc, "answer_after")
        else:
            state["answer_after"] = _extract_claims(doc, "answer_after")
    if args.trace:
        _merge_self_check(_load_json(args.trace), state)

    _attach_drop_reasons(state)
    expiry_doc = _load_json(args.expiry) if args.expiry else None
    html_text = render_dashboard(
        store, results, verdict,
        answer_before=state["answer_before"],
        answer_after=state["answer_after"],
        tool_calls=state["tool_calls"],
        expiry=expiry_doc,
    )
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html_text, encoding="utf-8")
    print(json.dumps({
        "out": str(out),
        "bytes": out.stat().st_size,
        "verdict": verdict.get("verdict"),
        "packs": {k: len(v or []) for k, v in results.items()},
        "claims_before": len(state["answer_before"] or []),
        "claims_after": len(state["answer_after"] or []),
        "tool_calls": len(state["tool_calls"] or []),
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
