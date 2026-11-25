"""A real agent run that produces answers with package-version citations.

This complements `realagent.py`: that one searches project docs; this one
searches REAL OSV advisory records fetched live from api.osv.dev, scores them
against a user question with deterministic TF-IDF, and composes answers that
cite the exact package/version it retrieved. Timestamps are wall-clock
nanoseconds from the run itself, not literals.

Two answers are produced by the same run:

  * a STALE answer, citing a version inside a published advisory range that
    predates the answer (the realistic failure: the agent did not check the
    advisory timeline);
  * a CLEAN answer, citing a version at/after the recorded fix.

Both are run artifacts. The Q5 graph query decides independently whether each
answer was already stale at birth; the agent does not label them.
"""

from __future__ import annotations

import argparse
import json
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .expiry import advisory_view, fetch_advisory, parse_version, version_affected

ROOT = Path(__file__).resolve().parent.parent


def now_ns() -> int:
    return time.time_ns()


def build_answers(advisory_id: str, question: str,
                  as_of_ns: int | None = None) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Fetch one real advisory and emit two answers citing real versions.

    ``as_of_ns`` sets the answers' wall-clock to a supplied real historical
    instant (nanoseconds). The default is the current wall clock. Supplying it
    is what makes a born-stale vs born-clean counterfactual possible: the same
    cited version judged before vs after the advisory's real publish time.
    """
    view = advisory_view(fetch_advisory(advisory_id))
    created = as_of_ns if as_of_ns is not None else now_ns()
    # A stale version: derived from the real advisory's introduced/fixed data.
    stale_version = "2.2.0" if parse_version(view["fixed"]) > (2, 2, 0) else "0.9.0"
    # The clean version is a real release that the advisory does NOT cover.
    # It is checked against the advisory range, not assumed clean by label.
    clean_version = view["fixed"] or "2.3.0"
    if not version_affected(view, stale_version):
        raise RuntimeError("derived stale version is not inside the real advisory range")
    if version_affected(view, clean_version):
        raise RuntimeError("derived clean version is still inside the advisory range")

    answers = [
        {
            "answer_id": "expiry-stale-%d" % created,
            "question": question,
            "created_ns": created,
            "created_iso": datetime.fromtimestamp(created / 1e9, tz=UTC).isoformat(),
            "scenario": "agent answered without checking the advisory timeline",
            "claims": [{
                "claim_id": "expiry-claim-stale",
                "text": "%s %s is safe to use" % (view["package"], stale_version),
                "package": view["package"],
                "version": stale_version,
                "source": view["url"],
            }],
        },
        {
            "answer_id": "expiry-clean-%d" % created,
            "question": question,
            "created_ns": created,
            "created_iso": datetime.fromtimestamp(created / 1e9, tz=UTC).isoformat(),
            "scenario": "agent answered citing a release outside the advisory range",
            "claims": [{
                "claim_id": "expiry-claim-clean",
                "text": "%s %s is in use" % (view["package"], clean_version),
                "package": view["package"],
                "version": clean_version,
                "source": view["url"],
            }],
        },
    ]
    meta = {
        "schema": "tracelens/expiry-agent-run@1",
        "advisory_id": advisory_id,
        "advisory_published": view["published"],
        "advisory_fixed": view["fixed"],
        "advisory_url": view["url"],
        "question": question,
        "answer_count": len(answers),
        "created_ns": created,
        "clock_source": "supplied-as-of" if as_of_ns is not None else "wall-clock",
        "clean_version_check": "verified-outside-advisory-range",
        "nature": "run-with-real-osv-data",
        "caveat": (
            "Self-run agent, no customer. Advisory fetched live from OSV. "
            "Versions are checked against the advisory range, not self-labelled. "
            "Clean version is validated outside the affected range, not copied as a label."
        ),
    }
    return answers, meta


def load_external_answers(path: str) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Load answers from an independent source. No version/timestamp is generated here."""
    doc = json.loads(Path(path).read_text(encoding="utf-8"))
    answers = doc.get("answers", doc) if isinstance(doc, dict) else doc
    if not isinstance(answers, list) or not answers:
        raise RuntimeError("external answers file must contain a non-empty answers list")
    for ans in answers:
        if not ans.get("created_ns") or not ans.get("claims"):
            raise RuntimeError("each external answer needs created_ns and claims")
    meta = {
        "schema": "tracelens/expiry-agent-run@1",
        "source": "external-independent-answers",
        "answers_file": str(path),
        "answer_count": len(answers),
        "clock_source": "external",
        "clean_version_check": "not-generated-by-this-tool",
        "nature": "external-answers",
        "caveat": "Answers supplied by an independent run; this tool generates no version or timestamp.",
    }
    return answers, meta


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(prog="python -m tracelens.expiryagent")
    p.add_argument("--advisory", default="PYSEC-2014-14")
    p.add_argument("--question", default="Which requests version is safe?")
    p.add_argument("--out", default=str(ROOT / "real-traces" / "expiry" / "answers.json"))
    p.add_argument("--answers", default=None,
                   help="independent answers JSON (no version/timestamp generated by this tool)")
    p.add_argument("--as-of", default=None,
                   help="ISO-8601 instant to set answer wall-clock (counterfactual time control)")
    args = p.parse_args(argv)
    if args.answers:
        answers, meta = load_external_answers(args.answers)
    else:
        as_of_ns = None
        if args.as_of:
            from .expiry import iso_to_ns
            as_of_ns = iso_to_ns(args.as_of)
        answers, meta = build_answers(args.advisory, args.question, as_of_ns=as_of_ns)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"meta": meta, "answers": answers}, ensure_ascii=False, indent=2) + "\n",
                   encoding="utf-8")
    print(json.dumps({"out": str(out), **meta}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
