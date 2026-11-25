"""Real model calls over an OpenAI-compatible HTTP endpoint, standard library only.

No SDK and no API key are assumed. The default endpoint is a public inference
service; both endpoint and model are configurable through environment
variables so a private endpoint can replace it without code changes.

Every call returns a receipt (endpoint, model, hashes, latency, usage) so a
reviewer can tell a real model response from a canned string. Network or HTTP
failures raise; there is no silent mock fallback.
"""

from __future__ import annotations

import hashlib
import json
import os
import time
import urllib.error
import urllib.request
from typing import Any

DEFAULT_ENDPOINT = "https://text.pollinations.ai/openai"
DEFAULT_MODEL = "gpt-oss-20b"
ENDPOINT_ENV = "TRACELENS_LLM_ENDPOINT"
MODEL_ENV = "TRACELENS_LLM_MODEL"
TIMEOUT_SECONDS = 40


def _digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def endpoint() -> str:
    return os.environ.get(ENDPOINT_ENV, DEFAULT_ENDPOINT)


def model_name() -> str:
    return os.environ.get(MODEL_ENV, DEFAULT_MODEL)


def chat(messages: list[dict[str, str]], max_tokens: int = 180,
         temperature: float = 0.0) -> dict[str, Any]:
    """Call the configured model and return both content and a receipt.

    Raises RuntimeError on transport/HTTP/JSON failure; no fabricated content.
    """
    url = endpoint()
    model = model_name()
    payload = {
        "model": model,
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": temperature,
    }
    raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        url, data=raw,
        headers={"Content-Type": "application/json", "Accept": "application/json"},
        method="POST",
    )
    started = time.perf_counter()
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
            body = response.read().decode("utf-8", errors="replace")
            status = int(response.status)
    except (urllib.error.URLError, OSError) as exc:
        raise RuntimeError("LLM transport failure: %s" % exc) from exc
    elapsed_ms = round((time.perf_counter() - started) * 1000, 3)
    if status < 200 or status >= 300:
        raise RuntimeError("LLM HTTP %d: %s" % (status, body[:400]))
    try:
        data = json.loads(body)
    except json.JSONDecodeError as exc:
        raise RuntimeError("LLM returned non-JSON: %s" % body[:200]) from exc
    try:
        content = data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise RuntimeError("LLM response has no message content: %s" % body[:300]) from exc
    if not isinstance(content, str) or not content.strip():
        raise RuntimeError("LLM message content is empty")
    return {
        "content": content.strip(),
        "receipt": {
            "endpoint": url,
            "model_requested": model,
            "model_returned": data.get("model"),
            "response_id": data.get("id"),
            "status": status,
            "latency_ms": elapsed_ms,
            "request_sha256": _digest(raw.decode("utf-8")),
            "response_sha256": _digest(body),
            "prompt_messages": [
                {"role": m.get("role"), "sha256": _digest(str(m.get("content", "")))}
                for m in messages
            ],
            "usage": data.get("usage"),
        },
    }


def explanation_prompt(claim: dict[str, Any], graph_reason: str,
                       graph_evidence: list[dict[str, Any]]) -> list[dict[str, str]]:
    """Build a grounded prompt: the graph has already decided; explain that."""
    evidence = json.dumps(graph_evidence[:6], ensure_ascii=False, default=str)
    return [
        {
            "role": "system",
            "content": (
                "You are an audit assistant for TraceLens. The graph diagnosis has "
                "already made the decision. Do not override it. In at most two short "
                "sentences, explain the decision using only the supplied evidence. "
                "Never invent a document, score, or path that is not supplied."
            ),
        },
        {
            "role": "user",
            "content": (
                "Claim: %s\nSource: %s\nGraph decision: %s\nGraph evidence: %s\n"
                "Explain why this decision follows from the evidence."
                % (
                    str(claim.get("text", ""))[:400],
                    str(claim.get("source", ""))[:200],
                    graph_reason,
                    evidence[:1600],
                )
            ),
        },
    ]
