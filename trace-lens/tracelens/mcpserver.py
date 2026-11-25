"""Read-only MCP stdio server for TraceLens.

Model Context Protocol over stdio is newline-delimited JSON-RPC 2.0. No third
party package is required: this module implements the three methods an MCP
client needs (initialize / tools/list / tools/call) with the standard library,
so any MCP-capable agent can inspect a TraceLens store without write access.

Safety contract (R4): every tool is a read. ``tracelens_readonly_cypher``
rejects any statement whose vocabulary contains a write verb, and opens the
store with ``read_only=True`` as a second line of defence. A rejected query
returns isError=true and never reaches the database.

stdout carries protocol messages only. Diagnostics go to stderr / auditlog.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

import relate

from .auditlog import log_event
from .judge import judge
from .querypacks import QUERIES, run_pack
from .schema import GraphMapper  # noqa: F401 - keeps the import surface explicit

PROTOCOL_VERSION = "2024-11-05"
SERVER_NAME = "tracelens-readonly"

# Write verbs are rejected even inside a comment-like string: the tool is a
# read interface, not a sanitizer. False positives are acceptable here.
WRITE_RX = re.compile(
    r"\b(CREATE|MERGE|SET|DELETE|REMOVE|DROP|DETACH|CALL|LOAD\s+CSV|FOREACH|"
    r"INSERT|UPDATE|UPSERT|TRUNCATE|GRANT|REVOKE)\b",
    re.IGNORECASE,
)
READ_START_RX = re.compile(r"^\s*(MATCH|OPTIONAL\s+MATCH|WITH|UNWIND|RETURN)\b", re.IGNORECASE)


def is_readonly(cypher: str) -> tuple[bool, str]:
    """Return (allowed, reason). Two independent gates: prefix and write verbs."""
    text = (cypher or "").strip()
    if not text:
        return False, "empty query"
    if not READ_START_RX.match(text):
        return False, "query must start with MATCH/OPTIONAL MATCH/WITH/UNWIND/RETURN"
    hit = WRITE_RX.search(text)
    if hit:
        return False, "write verb rejected: %s" % hit.group(0).upper()
    if ";" in text.rstrip(";"):
        return False, "multiple statements rejected"
    return True, ""


def tool_specs() -> list[dict]:
    return [
        {
            "name": "tracelens_query_pack",
            "description": (
                "Run one of the four graph-native diagnostic packs (Q1 path to "
                "evidence, Q2 convergence motif, Q3 unsupported claim, Q4 cost "
                "subtree) on the read-only TraceLens store. Returns JSON rows."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "pack": {"type": "string", "enum": ["Q1", "Q2", "Q3", "Q4"]},
                    "params": {"type": "object", "additionalProperties": True},
                },
                "required": ["pack"],
            },
        },
        {
            "name": "tracelens_judge",
            "description": (
                "Structure-derived verdict: does the graph localize the true "
                "cause while a global-lowest-score baseline misidentifies it? "
                "Returns checks, baseline pick, convergence causes, verdict."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {"threshold": {"type": "number"}},
                "required": [],
            },
        },
        {
            "name": "tracelens_graph_info",
            "description": "Node count, relationship count, labels and relationship types.",
            "inputSchema": {"type": "object", "properties": {}, "required": []},
        },
        {
            "name": "tracelens_readonly_cypher",
            "description": (
                "Run an arbitrary READ-ONLY Cypher query against the store. "
                "Write verbs and multi-statement input are rejected before execution."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {"cypher": {"type": "string"}},
                "required": ["cypher"],
            },
        },
    ]


class Session:
    def __init__(self, store: str | Path):
        self.store = str(store)

    def _db(self):
        return relate.Database(self.store, read_only=True)

    def call(self, name: str, args: dict) -> dict:
        if name == "tracelens_query_pack":
            pack = str(args.get("pack", ""))
            if pack not in QUERIES:
                return self._error("unknown pack %r" % pack)
            db = self._db()
            try:
                # Pass None when the caller gave no params: run_pack then
                # discovers parameters from graph structure. Passing {} here
                # used to suppress discovery and leave fixture-only defaults,
                # making Q1/Q3/Q4 return zero rows on a real store.
                explicit = args.get("params")
                rows = run_pack(db, pack, explicit if explicit else None)
            finally:
                db.close()
            log_event("mcp_tool", tool=name, pack=pack, rows=len(rows))
            return self._text(json.dumps(rows, ensure_ascii=False, default=str))

        if name == "tracelens_judge":
            threshold = float(args.get("threshold", 0.5))
            verdict = judge(self.store, threshold=threshold)
            log_event("mcp_tool", tool=name, verdict=verdict["verdict"])
            return self._text(json.dumps(verdict, ensure_ascii=False))

        if name == "tracelens_graph_info":
            db = self._db()
            try:
                info = {
                    "node_count": db.node_count(),
                    "relationship_count": db.relationship_count(),
                    "labels": db.labels(),
                    "relationship_types": db.relationship_types(),
                }
            finally:
                db.close()
            log_event("mcp_tool", tool=name)
            return self._text(json.dumps(info, ensure_ascii=False, default=str))

        if name == "tracelens_readonly_cypher":
            cypher = str(args.get("cypher", ""))
            ok, reason = is_readonly(cypher)
            if not ok:
                log_event("mcp_rejected", tool=name, reason=reason)
                return self._error(reason)
            db = self._db()
            try:
                rows = list(db.execute(cypher, {}).data)
            finally:
                db.close()
            log_event("mcp_tool", tool=name, rows=len(rows))
            return self._text(json.dumps(rows, ensure_ascii=False, default=str))

        return self._error("unknown tool %r" % name)

    @staticmethod
    def _text(payload: str) -> dict:
        return {"content": [{"type": "text", "text": payload}], "isError": False}

    @staticmethod
    def _error(message: str) -> dict:
        return {"content": [{"type": "text", "text": message}], "isError": True}


def handle(msg: dict, session: Session) -> dict | None:
    """Handle one JSON-RPC message. Returns None for notifications."""
    method = msg.get("method")
    rid = msg.get("id")
    if method == "initialize":
        return {
            "jsonrpc": "2.0", "id": rid,
            "result": {
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities": {"tools": {}},
                "serverInfo": {"name": SERVER_NAME, "version": "1.0.0"},
            },
        }
    if method == "ping":
        return {"jsonrpc": "2.0", "id": rid, "result": {}}
    if method in ("notifications/initialized", "initialized"):
        return None
    if method == "tools/list":
        return {"jsonrpc": "2.0", "id": rid, "result": {"tools": tool_specs()}}
    if method == "tools/call":
        params = msg.get("params") or {}
        name = str(params.get("name", ""))
        args = params.get("arguments") or {}
        try:
            result = session.call(name, args)
        except Exception as exc:  # noqa: BLE001 - MCP must convert any tool error into a JSON-RPC error result
            result = Session._error("%s: %s" % (type(exc).__name__, exc))
        return {"jsonrpc": "2.0", "id": rid, "result": result}
    if rid is None:
        return None
    return {
        "jsonrpc": "2.0", "id": rid,
        "error": {"code": -32601, "message": "method not found: %s" % method},
    }


def serve(store: str | Path) -> None:
    session = Session(store)
    log_event("mcp_server_start", store=str(store))
    for raw in sys.stdin:
        line = raw.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            out = {"jsonrpc": "2.0", "id": None,
                   "error": {"code": -32700, "message": "parse error"}}
        else:
            out = handle(msg, session)
        if out is not None:
            sys.stdout.write(json.dumps(out, ensure_ascii=False) + "\n")
            sys.stdout.flush()


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(prog="python -m tracelens.mcpserver")
    p.add_argument("--store", required=True, help="read-only .rl store to expose")
    args = p.parse_args(argv)
    serve(args.store)


if __name__ == "__main__":
    main()
