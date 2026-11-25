"""Out-of-sample fixture: same graph shape, completely different ids/names.

Used only to prove judge.py derives the verdict from structure rather than
memorizing the committed demo fixture's literals.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from tracelens.schema import GraphMapper

BAD_DOC = "obsolete-regulations-2019.pdf"   # true cause, low score, two retrievers
NOISE_DOC = "telemetry-scratch.tmp"          # global lowest score, monitor branch
CLEAN_DOC = "current-regulations-2026.pdf"   # high score, control run

FIXTURE = {
    "schema_version": "1.0",
    "story": "out-of-sample: different ids and doc names, same causal structure",
    "runs": [
        {
            "run_id": "invoice-parsing-run-77", "model": "probe-agent-7",
            "outcome": "wrong", "root_spans": ["x-root"],
            "spans": [
                {"span_id": "x-root", "parent_span_id": None, "kind": "AGENT",
                 "name": "invoice-parse", "start": 0.0, "end": 2.0, "duration_ms": 2000,
                 "input_tokens": 100, "output_tokens": 30, "cost": 0.001},
                {"span_id": "x-r1", "parent_span_id": "x-root", "kind": "RETRIEVER",
                 "name": "hybrid-search", "start": 0.1, "end": 0.6, "duration_ms": 500,
                 "input_tokens": 20, "output_tokens": 0, "cost": 0.0001,
                 "tool_calls": [{"call_id": "x-t1", "tool_name": "hybrid_search",
                                 "arguments_hash": "hx1", "ok": True}],
                 "retrieved_from": [{"doc_id": BAD_DOC, "uri": "fixtures://" + BAD_DOC,
                                     "snippet_hash": "hx-bad", "score": 0.18, "rank": 1}]},
                {"span_id": "x-r2", "parent_span_id": "x-root", "kind": "RETRIEVER",
                 "name": "bm25-search", "start": 0.15, "end": 0.65, "duration_ms": 500,
                 "input_tokens": 20, "output_tokens": 0, "cost": 0.0001,
                 "tool_calls": [{"call_id": "x-t2", "tool_name": "bm25_search",
                                 "arguments_hash": "hx2", "ok": True}],
                 "retrieved_from": [{"doc_id": BAD_DOC, "uri": "fixtures://" + BAD_DOC,
                                     "snippet_hash": "hx-bad", "score": 0.18, "rank": 2}]},
                {"span_id": "x-mon", "parent_span_id": "x-root", "kind": "MONITOR",
                 "name": "cache-flush", "start": 0.2, "end": 0.3, "duration_ms": 100,
                 "input_tokens": 0, "output_tokens": 0, "cost": 0.0,
                 "retrieved_from": [{"doc_id": NOISE_DOC, "uri": "fixtures://" + NOISE_DOC,
                                     "snippet_hash": "hx-noise", "score": 0.02, "rank": 1}]},
                {"span_id": "x-llm", "parent_span_id": "x-root", "kind": "LLM",
                 "name": "answer-gen", "start": 0.8, "end": 1.9, "duration_ms": 1100,
                 "input_tokens": 2000, "output_tokens": 300, "cost": 0.009},
            ],
            "answers": [{"answer_id": "x-ans", "produced_by_span_id": "x-root",
                         "text_hash": "hx-answer",
                         "claims": [{"claim_id": "x-c1", "text": "deadline changed",
                                     "supported_by_docs": []}]}],
        },
        {
            "run_id": "invoice-parsing-run-78", "model": "probe-agent-7",
            "outcome": "correct", "root_spans": ["y-root"],
            "spans": [
                {"span_id": "y-root", "parent_span_id": None, "kind": "AGENT",
                 "name": "invoice-parse", "start": 0.0, "end": 1.2, "duration_ms": 1200,
                 "input_tokens": 90, "output_tokens": 28, "cost": 0.0009},
                {"span_id": "y-r", "parent_span_id": "y-root", "kind": "RETRIEVER",
                 "name": "hybrid-search", "start": 0.05, "end": 0.4, "duration_ms": 350,
                 "input_tokens": 18, "output_tokens": 0, "cost": 0.0001,
                 "tool_calls": [{"call_id": "y-t1", "tool_name": "hybrid_search",
                                 "arguments_hash": "hy1", "ok": True}],
                 "retrieved_from": [{"doc_id": CLEAN_DOC, "uri": "fixtures://" + CLEAN_DOC,
                                     "snippet_hash": "hy-clean", "score": 0.95, "rank": 1}]},
                {"span_id": "y-llm", "parent_span_id": "y-root", "kind": "LLM",
                 "name": "answer-gen", "start": 0.5, "end": 1.1, "duration_ms": 600,
                 "input_tokens": 1200, "output_tokens": 200, "cost": 0.006},
            ],
            "answers": [{"answer_id": "y-ans", "produced_by_span_id": "y-root",
                         "text_hash": "hy-answer",
                         "claims": [{"claim_id": "y-c1", "text": "policy current",
                                     "supported_by_docs": [CLEAN_DOC]}]}],
        },
    ],
}


def main():
    root = Path(__file__).resolve().parent
    fx = root / "fixtures" / "out-of-sample.json"
    fx.parent.mkdir(parents=True, exist_ok=True)
    fx.write_text(json.dumps(FIXTURE, ensure_ascii=False, indent=2), encoding="utf-8")
    store = root / "store" / "out-of-sample.rl"
    store.unlink(missing_ok=True)
    import relate
    db = relate.Database(str(store), read_only=False)
    GraphMapper(db).ingest_run(FIXTURE["runs"][0])
    GraphMapper(db).ingest_run(FIXTURE["runs"][1])
    db.close()
    print(json.dumps({"fixture": str(fx), "store": str(store)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
