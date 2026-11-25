# TraceLens — Claim Freshness Gate

> **The lockfile is clean. The sentence is not.**

## Tagline

A coding agent's dependency advice was correct when it was written and stale when you read it. TraceLens walks a Relate graph from the claim to the fact's own clock and blocks the sentence before it becomes a lockfile change.

## What it does

TraceLens is a pre-merge **claim-freshness gate** for coding agents. Before an agent's answer is trusted, TraceLens walks a connected graph

`Span → Span → Source → PkgVersion ← Advisory → Alias → Ref`

from what the agent *said*, through where it *read* that version, to when the vulnerability *actually became public*. If the advice was already stale at the moment it was written, the merge is blocked with the public advisory URL and the version to pin instead.

The fully measured instance is **born-stale dependency versions** — the same failure mode the PinTrace measurement study (arXiv 2605.06279) found in 36.70%–55.70% of LLM-generated task solutions.

**The exact failure it catches:** a project's lockfile pins `requests==2.3.0`, so `pip-audit` / Dependabot / OSV-Scanner all report **clean**. The agent's PR comment still says `requests 2.2.0 is safe to use` — a version that entered a real OSV advisory range in 2014. Everymanifest-only scanner is blind to that sentence; the next agent that reads the PR is not.

## How it is built on Relate

- **One persisted graph, four stores.** Single scenario (19 nodes / 19 relationships), batch audit (162 / 175), cross-answer convergence (269 / 296), and the full real OSV graph (11,023 / 50,952 / 873 vulnerabilities). The audit graph shares Alias/Ref identity keys with the OSV graph.
- **Q6 provenance path** is variable-length and data-driven: **111 real paths over 8 declarations, 4–6 hops**, continued through `Advisory → Alias → Ref`. Not a fixed template.
- **Q7 hop-level time audit** carries a real clock per hop; the first stale hop is 4,421.06 days after publication, while the source document itself predates the advisory by 365 days.
- **Q8 declaration drift** joins the cited version, the lockfile pin and the advisory timeline, and resolves CVE/PYSEC aliases in the same query.
- **Q9/Q10** are graph-native aggregates on 22 merged answers from 10 models: cross-model convergence (three models independently cite the same born-stale `requests==2.2.0`) and advisory blast radius (one pillow advisory turns 5 answers from 5 models stale at once).
- **Q11 fixpoint rule reasoning.** Four Datalog-style rules (source predates advisory → retrieval after publication → recursive propagation up the span tree → answer born-stale, guarded by the exact cited version) iterate to a **fixpoint: 40 derived facts, 2 iterations**, every fact carrying rule + premises. The derived set is cross-checked against the independent Cypher Q8 computation. Then **R5 solves a minimum set cover** over producer→stale-source paths and **R6 verifies the plan blocks every derived answer**: 8 independent review chains need 8 cuts, but a **shared collector needs one cut to cover all 8 answers**. A per-answer boolean cannot express "fix the collection layer once" — this is constrained optimisation on the graph.

## Real data, not a toy

- 8 real OSV advisories → 8 real model-output declarations → **8 `BLOCK_MERGE_TEXT`**, with the SCA control clean on all 8 pins.
- 9 real model outputs (6 packages) and 5 real public Stack Overflow cases also blocked.
- **A real public catch, packaged verbatim:** PinTrace `direct_dependencies.jsonl` line 146 (`BigCodeBench/81`, `MiniMax-M2.5`, `from flask import Flask  # VERSION=2.3.0`) is blocked against `GHSA-4grg-w6v8-c28g` with its `CVE-2025-47278` alias chain, reproducible offline in `trace-lens/public-catches/catch-001-minimax-flask-230/`.
- Falsifiable, not constant-true: holding the advisory and version fixed and only moving the answer clock flips the verdict — a 2013 answer is clean, a 2026 answer is born-stale.
- **137 regression tests**, 18 evidence checks PASS, four graph exports PASS, all offline after `pip install`.

## Honest boundaries

- The cases are captured real model outputs, not paying customers; the lockfile pins are scenario configuration (set to each advisory's fixed version). This is stated in the evidence pack rather than papered over.
- Award readiness requires real calibration against the same cohort; that is not claimed until the official results are published.

## What's next

- Wire the gate into a PR-review bot so a real repository gets a real pre-merge block, producing the first customer-side evidence.
- Extend the freshness clock from dependency versions to other agent-claimed facts (API contracts, config defaults) on the same graph machinery.

## AI use disclosure

Required by Official Rules Sections 3 and 4. Stated plainly so judges can verify it.

- **AI coding tools** were used substantially for implementation, tests, documentation and submission copy. The human author reviewed, ran and corrected every committed command and result; all reported numbers were produced by executing the committed code, not generated by a model.
- **The model outputs analysed by TraceLens are research data, not generated submission content.** They are captured verbatim from public sources (PinTrace `direct_dependencies.jsonl` and Stack Overflow) and are the *input* the tool audits. Each is attributed to its source package/model in `trace-lens/real-cases/` and `trace-lens/public-catches/`.
- **Licensing.** Third-party data: OSV advisories and PinTrace outputs are used under their public availability; the full list of upstream URLs is in each case's `source.json`. Relate and its platform package are Apache-2.0. No paid image, video or music assets are used.
- **No runtime AI call.** TraceLens runs offline after install: the scan, graph queries and explorer need no API key and make no model call. AI appears only as the source of the claims being checked.
- **Demo video** is authored and narrated by the entrant; no cloned voice or third-party media is used.

## Links

- Repo: https://github.com/guyuezheng33-ai/tracelens-claim-freshness-gate (public, tagged `relate`)
- Demo video: `<1–2 minute walkthrough — fill after recording>`
- Graph explorer: `trace-lens/docs/graph-explorer.html` (double-click to open, offline)
