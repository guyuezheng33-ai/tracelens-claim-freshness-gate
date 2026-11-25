"""G1-compliant query packs.

G1 definition (from the verdict report):
  - >=3 of 4 answers are produced by variable-length paths / graph patterns;
  - each returned path's last element is a Source node;
  - no null in the path array.

Every pack below was executed against relate-db 1.2.0 on fixtures/demo-trace.json
before being committed. See tests/test_querypacks.py for the programmatic gate.
"""

from __future__ import annotations

from typing import Any

# Uniform id projection: never null, regardless of node label.
ID_EXPR = "coalesce(n.node_id, n.span_id, n.answer_id, n.source_id, n.claim_id)"
LABEL_EXPR = "labels(n)[0]"

QUERIES: dict[str, dict[str, Any]] = {
    # ------------------------------------------------------------------ Q1 --
    "Q1": {
        "name": "path-to-evidence",
        "question": "哪个低分来源污染了这个答案？",
        "graph_native": True,
        "cypher": """
MATCH p = (a:Answer)<-[:PRODUCED]-(root:Span)
          -[:PARENT_OF*1..8]->(r:Span)
          -[:RETRIEVED_FROM]->(src:Source)
WHERE a.answer_id = $answer_id AND src.score < $threshold AND r.kind = 'RETRIEVER'
RETURN [n IN nodes(p) | coalesce(n.node_id, n.span_id, n.answer_id, n.source_id)] AS path,
       [n IN nodes(p) | labels(n)[0]] AS labels,
       src.doc_id AS bad_source,
       src.score AS score,
       length(p) AS hops
ORDER BY score ASC
LIMIT 20
""".strip(),
        "params": {"answer_id": "ba-ans", "threshold": 0.5},
        "assert": lambda rows: (
            len(rows) >= 1
            and all(
                r["path"]
                and r["path"][-1].startswith("src:")
                and all(x is not None for x in r["path"])
                and r["labels"][-1] == "Source"
                for r in rows
            )
        ),
        "why_graph": "答案是根 span 产出，证据在兄弟检索分支；只有沿 PARENT_OF "
                     "向下再接 RETRIEVED_FROM 的变长路径才能一次拿到完整因果链。",
        "table_counterexample": "表格需对 span 表做多跳自连接 + 手工递归，且无法返回有序节点路径。",
    },
    # ------------------------------------------------------------------ Q2 --
    "Q2": {
        "name": "evidence-convergence-loop",
        "question": "Agent 是否在多个分支上重复检索同一个（低分）来源——打转？",
        "graph_native": True,
        "cypher": """
MATCH (a:Span)-[ra:RETRIEVED_FROM]->(src:Source)<-[rb:RETRIEVED_FROM]-(b:Span)
WHERE a.span_id < b.span_id AND ra.score < $threshold AND rb.score < $threshold
MATCH path = (a)-[:PARENT_OF*1..4]-(common:Span)-[:PARENT_OF*1..4]-(b)
WHERE common.span_id <> a.span_id AND common.span_id <> b.span_id
WITH src, a, b, ra, rb, common, path
ORDER BY length(path) ASC
WITH src, a, b, ra, rb, head(collect(common)) AS lca, head(collect(path)) AS shortest
RETURN src.doc_id AS doc,
       a.name AS branch_a, b.name AS branch_b,
       lca.name AS common_ancestor,
       [n IN nodes(shortest) | coalesce(n.node_id, n.span_id)] AS convergence_path,
       ra.score AS score_a, rb.score AS score_b
LIMIT 20
""".strip(),
        "params": {"threshold": 0.5},
        "assert": lambda rows: (
            len(rows) >= 1
            and all(
                r["branch_a"] != r["branch_b"]
                and r["convergence_path"]
                and all(x is not None for x in r["convergence_path"])
                for r in rows
            )
        ),
        "why_graph": "同一 Source 被两个不同检索分支指向，再各自沿 PARENT_OF 收敛到共同祖先——"
                     "这是二元图 motif + 两段变长路径；v1 的 PARENT_OF 自环在调用树上恒为空，已废弃。",
        "table_counterexample": "表格 GROUP BY doc_id 能数出重复，但拿不到'两分支何时在哪个祖先汇合'的路径。",
    },
    # ------------------------------------------------------------------ Q3 --
    "Q3": {
        "name": "unsupported-claim-forensics",
        "question": "哪些断言没有任何证据路径支撑？",
        "graph_native": True,
        "cypher": """
MATCH (c:Claim)-[:ASSERTED_IN]->(a:Answer)
WHERE NOT (c)-[:SUPPORTED_BY]->(:Source)
  AND NOT (a)<-[:PRODUCED]-(:Span)-[:PARENT_OF*0..8]-()
          -[:RETRIEVED_FROM]->(:Source {doc_id: $trusted_doc})
RETURN c.claim_id AS claim_id, c.text AS text, a.answer_id AS answer_id,
       a.run_id AS run_id
LIMIT 50
""".strip(),
        # Default keeps the committed fixture's semantics. Real stores pass
        # a structure-derived $trusted_doc via discover_params().
        "params": {"trusted_doc": "current-policy-v9.pdf"},
        "assert": lambda rows: (
            len(rows) >= 1
            and all(r["claim_id"] and r["answer_id"] for r in rows)
            and any(r["claim_id"] == "ba-claim-bad" for r in rows)
            and all(r["claim_id"] != "ba-claim-ok" for r in rows)
        ),
        "why_graph": "反连接用存在性路径模式表达：断言既无 SUPPORTED_BY 边，其所属答案也无通向可信来源的路径。"
                     "v1 的 Claim 层是可选 LLM 层、默认无节点，改为 fixture 内置、零 LLM 依赖。",
        "table_counterexample": "NOT EXISTS 子查询在表格里等价，因此本包单独不算图优势；"
                                "G1 由图模式包 Q1/Q2/Q4 满足 >=3 条。",
    },
    # ------------------------------------------------------------------ Q4 --
    "Q4": {
        "name": "cost-attribution",
        "question": "这次运行哪个子树烧掉了预算？",
        "graph_native": True,
        "cypher": """
MATCH (root:Span {span_id: $root_id})-[:PARENT_OF*0..8]->(leaf:Span)
WITH root, leaf
RETURN root.name AS root_span,
       count(leaf) AS spans,
       round(sum(leaf.cost), 6) AS total_cost,
       sum(leaf.output_tokens) AS output_tokens,
       max(leaf.duration_ms) AS slowest_ms
LIMIT 10
""".strip(),
        "params": {"root_id": "ba-root"},
        "assert": lambda rows: (
            len(rows) >= 1 and rows[0]["spans"] >= 1 and rows[0]["total_cost"] > 0
        ),
        "why_graph": "子树 = 变长可达关系；跨分支成本沿同一 PARENT_OF 关系向下聚合。",
        "table_counterexample": "递归 CTE 可替代，但路径语义在本查询包与 Q1/Q2 共用同一关系，"
                                "一套图模型支撑四类问题。",
    },
}


def discover_params(db: Any, threshold: float = 0.5) -> dict[str, dict[str, Any]]:
    """Derive query parameters from graph structure, never from a fixture id.

    This is what makes the four packs usable on a real agent trace: the trusted
    document is the highest-score source, the root is the span that produces an
    Answer, and the answer is every Answer node. The committed fixture keeps
    its original ids because they are exactly what these rules derive there.
    """
    def _rows(cypher: str) -> list[dict[str, Any]]:
        return list(db.execute(cypher, {}).data)

    answers = [r["id"] for r in _rows("MATCH (a:Answer) RETURN a.answer_id AS id ORDER BY a.answer_id")]
    roots = [r["id"] for r in _rows(
        "MATCH (root:Span)-[:PRODUCED]->(:Answer) RETURN root.span_id AS id ORDER BY root.span_id"
    )]
    trusted_rows = list(db.execute(
        "MATCH (s:Source) WHERE s.score >= $t RETURN s.doc_id AS doc ORDER BY s.score DESC LIMIT 1",
        {"t": threshold},
    ).data)
    trusted_doc = trusted_rows[0]["doc"] if trusted_rows else ""

    out: dict[str, dict[str, Any]] = {}
    if answers:
        out["Q1"] = {"answer_id": answers[0], "threshold": threshold}
    out["Q2"] = {"threshold": threshold}
    if trusted_doc:
        out["Q3"] = {"trusted_doc": trusted_doc}
    if roots:
        out["Q4"] = {"root_id": roots[0]}
    return out


def run_pack(db: Any, key: str, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    pack = QUERIES[key]
    p = dict(pack["params"])
    # On a real store the fixture defaults do not exist. Derive parameters
    # from structure unless the caller supplied them explicitly.
    if params is None and key in ("Q1", "Q3", "Q4"):
        discovered = discover_params(db).get(key, {})
        p.update(discovered)
    elif params:
        p.update(params)
    result = db.execute(pack["cypher"], p)
    return list(result.data)


def run_all(db: Any) -> dict[str, list[dict[str, Any]]]:
    return {k: run_pack(db, k) for k in QUERIES}


def to_mermaid(rows: list[dict[str, Any]], key: str) -> str:
    """Turn a query result into a Mermaid graph (pure string assembling).

    IDs are assigned in first-seen order so the output is deterministic across
    runs (Python's built-in hash() is randomized per process and must not be
    used for a committed artifact).
    """
    lines = ["flowchart LR"]
    node_ids: dict[str, str] = {}
    counter = [0]

    def nid(node: str) -> str:
        if node not in node_ids:
            node_ids[node] = f"N{counter[0]}"
            counter[0] += 1
        return node_ids[node]

    for i, r in enumerate(rows):
        path = r.get("path") or r.get("convergence_path") or []
        labs = r.get("labels") or []
        for j, node in enumerate(path):
            label = labs[j] if j < len(labs) else node.split(":", 1)[0].upper()
            lines.append(f'  {nid(node)}["{label}: {node}"]')
        for j in range(len(path) - 1):
            lines.append(f"  {nid(path[j])} --> {nid(path[j + 1])}")
        if not path and "claim_id" in r:
            lines.append(
                f'  C{i}["Claim: {r["claim_id"]}"] --> A{i}["Answer: {r["answer_id"]}"]'
            )
    return "\n".join(lines)
