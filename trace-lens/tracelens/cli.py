"""TraceLens CLI: build a persistent store and run the four query packs."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import relate

from .auditlog import configure_log, log_event
from .fixture import write_fixture
from .querypacks import QUERIES, run_all, run_pack, to_mermaid
from .schema import GraphMapper

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_STORE = ROOT / "store" / "demo-run.rl"
DEFAULT_FIXTURE = ROOT / "fixtures" / "demo-trace.json"


def _open(path: Path, read_only: bool = False):
    return relate.Database(str(path), read_only=read_only)


def cmd_build(args):
    fixture = Path(args.fixture)
    # Always regenerate the deterministic fixture from source code so that a
    # stale on-disk JSON can never shadow a fixture.py change.
    fixture = write_fixture(fixture)
    data = json.loads(fixture.read_text(encoding="utf-8"))
    store = Path(args.store)
    store.parent.mkdir(parents=True, exist_ok=True)
    if store.exists():
        store.unlink()
    db = _open(store)
    mapper = GraphMapper(db)
    for run in data["runs"]:
        mapper.ingest_run(run)
    db.flush()
    # G2 metric: measured from the actual store, never hardcoded.
    nodes = db.node_count()
    edges = db.relationship_count()
    db.close()
    print(json.dumps({
        "store": str(store),
        "bytes": store.stat().st_size,
        "nodes": nodes,
        "relationships": edges,
        "runs": len(data["runs"]),
    }, ensure_ascii=False, indent=2))


def cmd_judge(args):
    from .judge import judge
    verdict = judge(Path(args.store))
    (ROOT / "docs" / "g2-effect.json").write_text(
        json.dumps(verdict, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(verdict, ensure_ascii=False, indent=2))


def cmd_import(args):
    """Import a standard OTLP/JSON trace export into a persistent .rl store."""
    from .otlp import import_otlp
    sources = [Path(p) for p in args.input]
    store = Path(args.store)
    store.parent.mkdir(parents=True, exist_ok=True)
    if args.fresh and store.exists():
        store.unlink()
    db = _open(store)
    mapper = GraphMapper(db)
    ingested: list[str] = []
    for source in sources:
        doc = json.loads(source.read_text(encoding="utf-8"))
        # One OTLP document may carry several traces; group by traceId so each
        # becomes its own run. GraphMapper MERGEs, so repeated imports are safe.
        grouped: dict[str, list[dict]] = {}
        for resource in doc.get("resourceSpans", []) or []:
            if not isinstance(resource, dict):
                continue
            for scope in resource.get("scopeSpans", []) or []:
                for span in (scope or {}).get("spans", []) or []:
                    if not isinstance(span, dict) or not span.get("spanId"):
                        continue
                    tid = str(span.get("traceId", "trace:unknown"))
                    grouped.setdefault(tid, []).append({
                        **resource,
                        "scopeSpans": [{**scope, "spans": [span]}],
                    })
        if grouped:
            for tid, resources in grouped.items():
                run = import_otlp(
                    {"resourceSpans": resources},
                    run_id=tid if len(grouped) > 1 else args.run_id,
                )
                mapper.ingest_run(run)
                ingested.append(run["run_id"])
        else:
            run = import_otlp(doc, run_id=args.run_id)
            mapper.ingest_run(run)
            ingested.append(run["run_id"])
    db.flush()
    nodes = db.node_count()
    edges = db.relationship_count()
    db.close()
    print(json.dumps({
        "store": str(store),
        "inputs": [str(p) for p in sources],
        "runs": ingested,
        "nodes": nodes,
        "relationships": edges,
    }, ensure_ascii=False, indent=2))


def cmd_query(args):
    db = _open(Path(args.store), read_only=True)
    try:
        if args.pack == "all":
            results = run_all(db)
        else:
            results = {args.pack: run_pack(db, args.pack)}
        out = {
            k: {
                "name": QUERIES[k]["name"],
                "question": QUERIES[k]["question"],
                "rows": rows,
                "passed": bool(QUERIES[k]["assert"](rows)),
            }
            for k, rows in results.items()
        }
        print(json.dumps(out, ensure_ascii=False, indent=2, default=str))
    finally:
        db.close()


def cmd_mermaid(args):
    db = _open(Path(args.store), read_only=True)
    try:
        rows = run_pack(db, args.pack)
        print(to_mermaid(rows, args.pack))
    finally:
        db.close()


def cmd_report(args):
    """Render the presentation layer: HTML dashboard or Markdown report."""
    from .judge import judge
    from .render import render_to_file

    store = Path(args.store)
    db = _open(store, read_only=True)
    try:
        results = run_all(db)
    finally:
        db.close()
    verdict = judge(store)
    default_name = "report.html" if args.format == "html" else "report.md"
    out = Path(args.out) if args.out else ROOT / "docs" / default_name
    written = render_to_file(args.format, out, results, verdict, str(store))
    print(json.dumps({
        "out": str(written),
        "bytes": written.stat().st_size,
        "format": args.format,
        "verdict": verdict["verdict"],
        "packs": {k: len(v) for k, v in results.items()},
    }, ensure_ascii=False, indent=2))


def cmd_realagent(args):
    from .realagent import run as run_real_agent

    doc = run_real_agent(
        args.question, args.docs, args.run_id,
        top_k=args.top_k, threshold=args.threshold,
    )
    meta = doc.pop("_run_meta")
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"out": str(out), **meta}, ensure_ascii=False, indent=2))


def cmd_realtrace(args):
    """Intake a real OTLP export: inspect structure and write a provenance passport."""
    from .realtrace import inspect, write_passport

    source = Path(args.input)
    doc = json.loads(source.read_text(encoding="utf-8"))
    report = inspect(doc)
    if not report["ok"] and not args.force:
        print(json.dumps({"ok": False, "reason": report["reason"], "checks": report["checks"]},
                         ensure_ascii=False, indent=2))
        raise SystemExit(3)
    passport = write_passport(
        source, doc, report, origin=args.origin, caveat=args.caveat, out=args.out,
    )
    print(json.dumps({"ok": report["ok"], "passport": str(passport),
                      "report": report}, ensure_ascii=False, indent=2))


def cmd_agentloop(args):
    from .agentloop import run_loop

    before = json.loads(Path(args.answer_before).read_text(encoding="utf-8"))
    record = run_loop(args.store, before, args.trace, args.threshold)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "out": str(out), "verdict": record["verdict"],
        "claims_before": len(record["answer_before"]),
        "claims_after": len(record["answer_after"]),
        "dropped": len(record["claims_dropped"]),
        "tool_calls": len(record["tool_calls"]),
    }, ensure_ascii=False, indent=2))


def cmd_info(args):
    db = _open(Path(args.store), read_only=True)
    try:
        print(json.dumps({
            "node_count": db.node_count(),
            "relationship_count": db.relationship_count(),
            "labels": db.labels(),
            "relationship_types": db.relationship_types(),
        }, ensure_ascii=False, indent=2, default=str))
    finally:
        db.close()


def main(argv=None):
    p = argparse.ArgumentParser(prog="tracelens")
    sub = p.add_subparsers(dest="cmd", required=True)

    b = sub.add_parser("build", help="生成 fixture 并写入持久化 .rl store")
    b.add_argument("--fixture", default=str(DEFAULT_FIXTURE))
    b.add_argument("--store", default=str(DEFAULT_STORE))
    b.set_defaults(func=cmd_build)

    im = sub.add_parser("import", help="从标准 OTLP/JSON trace 导入建图")
    im.add_argument("--input", required=True, nargs="+", help="一个或多个 OTLP/JSON 文件")
    im.add_argument("--store", default=str(DEFAULT_STORE))
    im.add_argument("--fresh", action="store_true", help="先清空目标 store 再导入")
    im.add_argument("--run-id", default=None, help="可选：覆盖 run_id")
    im.set_defaults(func=cmd_import)

    q = sub.add_parser("query", help="运行查询包（all 或 Q1/Q2/Q3/Q4）")
    q.add_argument("--store", default=str(DEFAULT_STORE))
    q.add_argument("--pack", default="all", choices=["all", "Q1", "Q2", "Q3", "Q4"])
    q.set_defaults(func=cmd_query)

    m = sub.add_parser("mermaid", help="把查询结果导出为 Mermaid 文本")
    m.add_argument("--store", default=str(DEFAULT_STORE))
    m.add_argument("--pack", default="Q1", choices=["Q1", "Q2", "Q3", "Q4"])
    m.set_defaults(func=cmd_mermaid)

    i = sub.add_parser("info", help="store 统计")
    i.add_argument("--store", default=str(DEFAULT_STORE))
    i.set_defaults(func=cmd_info)

    r = sub.add_parser("report", help="呈现层：导出 HTML 仪表盘或 Markdown 报告")
    r.add_argument("--store", default=str(DEFAULT_STORE))
    r.add_argument("--format", default="html", choices=["html", "md"])
    r.add_argument("--out", default=None)
    r.set_defaults(func=cmd_report)

    j = sub.add_parser("judge", help="G2 严格判定：图定位准确 + clean 零误报")
    j.add_argument("--store", default=str(DEFAULT_STORE))
    j.set_defaults(func=cmd_judge)

    ra = sub.add_parser("realagent", help="真实运行一个最小 agent，导出 OTLP trace")
    ra.add_argument("--question", required=True)
    ra.add_argument("--docs", default=str(ROOT.parent))
    ra.add_argument("--run-id", default="real-run-1")
    ra.add_argument("--out", required=True)
    ra.add_argument("--top-k", type=int, default=2)
    ra.add_argument("--threshold", type=float, default=0.5)
    ra.set_defaults(func=cmd_realagent)

    rt = sub.add_parser("realtrace", help="真实 trace 接入：结构检查 + 来源护照")
    rt.add_argument("--input", required=True)
    rt.add_argument("--origin", required=True, help="来源说明（含 self-run）")
    rt.add_argument("--caveat", required=True, help="必须含 self-run")
    rt.add_argument("--out", default=None)
    rt.add_argument("--force", action="store_true", help="结构不合格也写护照（标注失败）")
    rt.set_defaults(func=cmd_realtrace)

    al = sub.add_parser("agentloop", help="agent 自查闭环：调用只读 MCP 工具改答案")
    al.add_argument("--store", required=True)
    al.add_argument("--answer-before", required=True)
    al.add_argument("--trace", default=None)
    al.add_argument("--out", required=True)
    al.add_argument("--threshold", type=float, default=0.5)
    al.set_defaults(func=cmd_agentloop)

    args = p.parse_args(argv)
    configure_log()
    log_event("cli_start", cmd=args.cmd, store=getattr(args, "store", None))
    try:
        args.func(args)
    except Exception as exc:
        log_event("cli_error", cmd=args.cmd, error="%s: %s" % (type(exc).__name__, exc))
        raise
    log_event("cli_done", cmd=args.cmd)
    # No console handler: stdout is reserved for each command's JSON output.


if __name__ == "__main__":
    main()
