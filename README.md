# ShipSmart — Integration & Evaluation Harness (`test`)

[![Python](https://img.shields.io/badge/Python-3.13-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![uv](https://img.shields.io/badge/uv-0.6%2B-DE5FE9?logo=python&logoColor=white)](https://docs.astral.sh/uv/)
[![pytest](https://img.shields.io/badge/pytest-contract%20%2B%20evals%20%2B%20e2e-0A9EDC?logo=pytest&logoColor=white)](https://docs.pytest.org/)
[![Evals](https://img.shields.io/badge/evals-six--layer%20%2B%20Wilson%20gates-7B61FF)](#the-six-layer-eval-system)
[![Coverage gate](https://img.shields.io/badge/governance-coverage.yml%20build%20gate-FF8A5B)](#the-coverage-gate)
[![Tests](https://img.shields.io/badge/tests-133%20keyless-3FB950?logo=pytest&logoColor=white)](#running-the-suites)
[![License](https://img.shields.io/badge/License-See%20LICENSE-blue)](./LICENSE)

> The **referee** of the ShipSmart platform: an executable **contract registry**
> (10 suites) whose CI checks out all six sibling repos and fails when any two
> drift; a **six-layer evaluation system** that measures AI behavior with
> Wilson-interval statistical gates, dev/holdout datasets, and a pinned,
> failover-capable LLM judge (never in CI, never on safety); and a **keyless
> skip-if-down e2e harness** that boots the whole mesh, then tears it down.
> It ships no features — it proves the other six repos agree.

**Stack:** Python 3.13 · uv · pytest (+ pytest-asyncio) · httpx · PyJWT · ruff

---

## Table of contents

- [The ShipSmart ecosystem](#the-shipsmart-ecosystem)
- [What this repo verifies](#what-this-repo-verifies)
- [The contract suites](#the-contract-suites)
- [The six-layer eval system](#the-six-layer-eval-system)
- [The coverage gate](#the-coverage-gate)
- [The LLM judge](#the-llm-judge)
- [Live e2e: the self-contained stack](#live-e2e-the-self-contained-stack)
- [Running the suites](#running-the-suites)
- [Layout](#layout)
- [License](#license)

---

## The ShipSmart ecosystem

This repo is the cross-repo harness for the platform. Clone all six under one
parent directory so the contract suite can resolve each sibling by relative
path (see `sibling.py`):

```
<any parent directory>/
├── ShipSmart-Web/   ShipSmart-API/   ShipSmart-MCP/
├── ShipSmart-Orchestrator/   ShipSmart-Infra/
└── ShipSmart-Test/   ← you are here
```

All six are also mirrored together in
**[ShipSmart](https://github.com/nia194/ShipSmart)** — the umbrella repository
that snapshots each component at a pinned commit (see its `COMPONENTS.yml`).

| Repo | What this harness checks |
|------|--------------------------|
| [ShipSmart-Web](https://github.com/nia194/ShipSmart-Web) | `typed-outputs.ts` ⇄ API Pydantic parity; wire shapes |
| [ShipSmart-Orchestrator](https://github.com/nia194/ShipSmart-Orchestrator) | §5.6 trust boundary intact; DTO shapes; live JWT-scoped e2e |
| [ShipSmart-API](https://github.com/nia194/ShipSmart-API) | decision tags ∈ registry; typed outputs; tool policy; AI-event trace; live advisor/RAG/concierge/workflow |
| [ShipSmart-MCP](https://github.com/nia194/ShipSmart-MCP) | tool `input_schema` ⇄ API policy; live API→MCP hop |
| [ShipSmart-Infra](https://github.com/nia194/ShipSmart-Infra) | `match_rag_chunks_lexical` SQL signature ⇄ API; corpus refs |

---

## What this repo verifies

Three complementary layers:

- **Contract** (`contract/`, 47 tests, **no services required**) — parses the
  sibling repos' *actual sources* and asserts the shared shapes line up across
  language boundaries. CI checks out all six repos on every push.
- **Evals** (`evals/`, 61 versioned cases + 54 infra self-tests) — grades AI
  *behavior* as a distribution: repetition, Wilson intervals, flake quarantine,
  safety-critical aggregation, and a governance coverage gate.
- **Live e2e** (`e2e/`, 32 tests, **skip-if-down**) — boots the real mesh
  keylessly and walks user journeys across the language boundary.

## The contract suites

Ten executable suites: `test_typed_outputs` (Pydantic ⇄ TypeScript,
field-for-field) · `test_decision_tags` (every emitted tag ∈
`tag_vocabulary.yml`, validated at `namespace:base` with dynamic suffixes) ·
`test_ai_trust_boundary` (§5.6 on both the Python and Java sides) ·
`test_tool_policy_contract` (API ⇄ MCP registry) ·
`test_coverage_completeness` (the governance gate, below) ·
`test_ai_event_trace` · `test_config_flags` · `test_feedback_contract` ·
`test_rag_corpus_refs` · `test_contracts` (core wire shapes).

> The contract is *code that runs on every push*, not a wiki page that rots.
> Rename a field in one repo and forget the other — this tier goes red before
> merge.

## The six-layer eval system

| Layer | Grades | Grader |
|---|---|---|
| 1 Contract | schema conformance | rule-based |
| 2 RAG | grounding, citations, poisoned-doc resistance | rule + semantic |
| 3 Agent/tool | tool selection & argument correctness | rule-based |
| 4 Safety | injection / misuse / forged-state refusal | rule-based — **never LLM-judged** |
| 5 Product | explanation & journey quality | LLM judge |
| 6 Governance | control coverage | `coverage.yml` join |

- **Datasets:** `evals/datasets/{agent,product,rag,safety,smoke}/*.v1.jsonl` —
  **61 cases** (33 adversarial red-team), `MANIFEST.yml`-governed, with
  **dev/holdout splits** so nothing tunes against the release set.
- **Lanes (`LANE_CONFIG`):** `ci` — 1 repetition, dev split, no model graders,
  **blocking** · `nightly` — 3 reps + judge, observational · `release` —
  **5 reps, dev + holdout, judge on, blocking**.
- **Statistics (`rigor.py`):** Wilson intervals (z = 1.96);
  `aggregate_verdict` is stricter for safety-critical cases (one bad rep fails
  the case); `is_flaky` quarantines noise; results append to `history.jsonl`
  and regenerate `trend.md` — a regression is a *significant* drop, not a vibe.

## The coverage gate

`evals/coverage.yml` joins each guardrail **control** → its spec reference →
the **tag** that proves it → the **eval case-IDs** that exercise it.
`test_coverage_completeness.py` **fails the build** when a `behavioral` control
has fewer non-flaky cases than its `min_cases` (injection: 8; misuse: 6) or
references a retired case — and asserts `structural` controls' named code tests
still exist. *"Is this safety control actually tested?"* is a failing check,
not a meeting.

## The LLM judge

`evals/config/judge.yml`: **gpt-4o at temperature 0, seed 7**, JSON-only
scoring with **one corrective retry → `judge_error`** (never a silent pass);
request-time failover (claude-sonnet-4-5 → gpt-4o-mini); **four versioned
rubrics** (faithfulness, answer relevance, refusal quality, explanation
quality) — every score records `judge_version`, so a rubric edit can never
silently rewrite a trend. The judge **never runs in CI and never grades
Layer-4 safety**. Calibration is first-class: `calibration.py` +
`docs/judge-calibration.md` + `docs/annotation-guide.md`.

## Live e2e: the self-contained stack

```bash
scripts/run-stack.sh up      # pgvector (Docker) → MCP :8001 → API :8000 → Java :8080
uv run pytest e2e/           # 32 tests: api · concierge · java · mcp · scope · workflow
scripts/run-stack.sh down
```

Entirely **keyless**: MCP uses the mock provider, the API uses EchoClient + the
in-memory vector store, Java gets a test HS256 JWT. The API boot waits on MCP's
health (it hydrates its tool registry at startup). Java is **optional** — if it
doesn't come up, the Java e2e tests **skip** and the rest still verify. Logs in
`.stack/*.log`, PIDs tracked.

## Running the suites

```bash
uv sync
uv run pytest contract/                    # 47 tests — no services, no keys
uv run pytest evals/                       # 54 eval-infra self-tests
uv run python -m evals.runners.run_lane ci # the blocking CI eval lane
uv run pytest e2e/                         # live (skips when stack is down)
uv run ruff check .
```

## Layout

```
contract/   10 cross-repo suites + sibling.py
evals/      datasets/ graders/ runners/ reports/ docs/
            coverage.yml · tag_vocabulary.yml · config/judge.yml ·
            rigor.py · alerts.py · calibration.py · promotion.py ·
            telemetry.py · trace.py
e2e/        6 live suites (skip-if-down)
scripts/    run-stack.sh
```

## License

See [LICENSE](./LICENSE).
