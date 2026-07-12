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

> **Metric convention:** counts and lane/judge configs are facts (133 tests,
> 61 cases, lanes ci×1/nightly×3/release×5, judge temp 0 seed 7); the trend
> chart below is **(illustrative)**.

---

## Table of contents

- [The ShipSmart ecosystem](#the-shipsmart-ecosystem)
- [Architecture (HLD)](#architecture-hld)
- [The contract mesh](#the-contract-mesh)
- [The six-layer eval system](#the-six-layer-eval-system)
- [Lanes & statistical gating](#lanes--statistical-gating)
- [The LLM judge](#the-llm-judge)
- [The coverage gate](#the-coverage-gate)
- [Live e2e: the self-contained stack](#live-e2e-the-self-contained-stack)
- [Test pyramid & threat model](#test-pyramid--threat-model)
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

---

## Architecture (HLD)

**Figure 1 — three pillars + the six-repo CI checkout.**

```mermaid
flowchart TB
    subgraph CI["GitHub Actions (keyless)"]
        CO["checkout ×6 sibling repos"]
        LINT["ruff"]
    end
    subgraph P1["contract/ (47 tests)"]
        SIB["sibling.py repo locator"]
        S10["10 suites: typed_outputs · decision_tags · ai_trust_boundary · tool_policy · coverage_completeness · ai_event_trace · config_flags · feedback · rag_corpus_refs · contracts"]
    end
    subgraph P2["evals/"]
        DS["datasets {agent, product, rag, safety, smoke} + MANIFEST"]
        GR["graders: rule_based · semantic · llm_judge"]
        RN["runners: run_suite · run_lane · merge_reports"]
        RG["rigor: wilson_interval · aggregate_verdict · is_flaky · gate"]
        CV["coverage.yml + tag_vocabulary.yml + judge.yml"]
        REP["reports: history.jsonl -> trend.md"]
    end
    subgraph P3["e2e/ (32 tests)"]
        RS["scripts/run-stack.sh"]
        E6["6 suites: api · concierge · java · mcp · scope · workflow"]
    end
    CI --> P1
    CI --> P2
    DEV[Developer] --> P3
```

---

## The contract mesh

**Figure 2 — which suite binds which repos.** Every edge is *executable*: a
rename or removal on either end reddens the build before merge. The contract is
code that runs on every push, not a wiki page that rots.

```mermaid
flowchart LR
    API[ShipSmart-API]
    WEB[ShipSmart-Web]
    MCP[ShipSmart-MCP]
    JAVA[ShipSmart-Orchestrator]
    INFRA[ShipSmart-Infra]
    VOC["tag_vocabulary.yml + coverage.yml (in this repo)"]
    API ---|"typed_outputs: Pydantic == typed-outputs.ts"| WEB
    API ---|"tool_policy: policy == registry"| MCP
    API ---|"ai_trust_boundary: 5.6 intact both sides"| JAVA
    API ---|"rag_corpus_refs: corpus == migrations"| INFRA
    API ---|"decision_tags: emitted tags in registry"| VOC
    API ---|"coverage_completeness: controls have cases"| VOC
```

---

## The six-layer eval system

**Figure 3 — layers, graders, datasets.** Layer-4 safety is graded by rules
**only** — never by a model.

```mermaid
flowchart TB
    L1["L1 Contract — schema conformance — rule_based"]
    L2["L2 RAG — grounding, citations, poisoned docs — rule + semantic — rag/policy, rag/international"]
    L3["L3 Agent/tool — tool + args correctness — rule_based — agent/tool_use"]
    L4["L4 Safety — injection / misuse / forged state — rule_based ONLY — safety/redteam ×33"]
    L5["L5 Product — explanation + journey quality — LLM judge — product/journeys"]
    L6["L6 Governance — coverage.yml join — completeness check"]
    L1 --> L2 --> L3 --> L4 --> L5 --> L6
```

Datasets: `*.v1.jsonl` + `MANIFEST.yml` — **61 cases** (33 adversarial
red-team) with **dev/holdout splits** so nothing tunes against the release set.

---

## Lanes & statistical gating

**Figure 4 — lanes as policy (exact `LANE_CONFIG` facts).**

```mermaid
flowchart LR
    subgraph CI_LANE["ci — every push"]
        A["repetition 1 · dev split · model graders OFF · BLOCKING"]
    end
    subgraph NIGHTLY["nightly"]
        B["repetition 3 · dev split · judge ON (if key) · observational"]
    end
    subgraph RELEASE["release"]
        C["repetition 5 · dev + holdout · judge ON · BLOCKING"]
    end
    CI_LANE --> NIGHTLY --> RELEASE
```

**Figure 5 — from verdicts to a gate.** A regression is a *significant*
interval drop, not one flaky rep.

```mermaid
flowchart LR
    RUNS["N repetitions per case"] --> AGG["aggregate_verdict (safety-critical: one bad rep fails the case)"]
    AGG --> FLK{"is_flaky?"}
    FLK -->|yes| QUAR["quarantined — reported, not gating"]
    FLK -->|no| W["wilson_interval(pass, n, z=1.96)"]
    W --> GATE{"lane threshold vs interval"}
    GATE -->|holds| GREEN[lane passes]
    GATE -->|fails| RED["non-zero exit (blocking lanes)"]
    GREEN --> H["append history.jsonl -> regenerate trend.md"]
    RED --> H
```

**Figure 6 — (illustrative) pass-rate trend with a Wilson lower bound.**

```mermaid
xychart-beta
    title "Safety pass-rate trend, % (illustrative)"
    x-axis ["run-1", "run-2", "run-3", "run-4", "run-5"]
    y-axis "pass %" 80 --> 100
    line [93, 94, 95, 91, 95]
    line [88, 90, 91, 86, 91]
```

---

## The LLM judge

**Figure 7 — pinned, failover-capable, kept in its lane.** Never in CI, never
on Layer-4 safety; rubric edits are version bumps, so history is never silently
rewritten.

```mermaid
sequenceDiagram
    participant R as run_suite (nightly/release)
    participant J as llm_judge
    participant P as gpt-4o (temp 0, seed 7)
    participant F1 as claude-sonnet-4-5
    participant F2 as gpt-4o-mini
    R->>J: grade(case, rubric vN)
    J->>P: scoring prompt (JSON only)
    alt provider fails
        J->>F1: failover
        F1--xJ: fails too
        J->>F2: second failover
    end
    P-->>J: JSON score
    alt invalid JSON
        J->>P: ONE corrective retry
        P--xJ: still invalid
        J-->>R: judge_error (never a silent pass)
    else valid
        J-->>R: score + judge_version recorded
    end
```

Four versioned rubrics: faithfulness · answer relevance · refusal quality ·
explanation quality. Calibration is first-class: `calibration.py` +
`docs/judge-calibration.md` + `docs/annotation-guide.md` (human inter-rater
loop).

---

## The coverage gate

**Figure 8 — control → tag → cases → build gate (the §13 join).** *"Is this
safety control actually tested?"* is a failing check, not a meeting.

```mermaid
flowchart LR
    CTRL["control: injection (guardrails_ref 5.2/5.3)"] --> TAG["tag: guardrail:injection (must exist in tag_vocabulary.yml)"]
    TAG --> CASES["case_ids: rt-inj-0001..0008 (min_cases 8)"]
    CASES --> CHK["test_coverage_completeness.py: count NON-FLAKY cases carrying the tag"]
    CHK -->|"count < min OR case retired"| FAIL["BUILD FAILS"]
    CHK -->|ok| PASS[green]
    STRUCT["kind: structural -> named code test must exist + module still emits tag"] --> CHK
```

`kind: behavioral` controls are proven by adversarial cases (injection: min 8;
misuse: min 6); `kind: structural` ones by named code tests (e.g. the
embedding-compat startup check).

---

## Live e2e: the self-contained stack

**Figure 9 — boot order, keyless env, graceful skip.** No Supabase, no LLM
keys, no carrier credentials — the full mesh runs hermetically.

```mermaid
sequenceDiagram
    participant D as Developer
    participant RS as run-stack.sh
    participant PG as pgvector (Docker)
    participant M as MCP :8001
    participant A as API :8000
    participant J as Java :8080 (optional)
    D->>RS: up
    RS->>PG: start container
    RS->>M: start (SHIPPING_PROVIDER=mock, no key)
    RS->>RS: wait_http /health (API hydrates its tool registry from MCP at boot)
    RS->>A: start (EchoClient, in-memory store, RAG_AUTO_INGEST=true)
    RS->>J: build bootJar + start (test HS256 JWT)
    alt Java fails to build/start
        RS-->>D: java e2e will SKIP — MCP+API journeys still verify
    end
    D->>D: pytest e2e/ (32 tests: api · concierge · java · mcp · scope · workflow)
    D->>RS: down (PIDs + logs under .stack/)
```

---

## Test pyramid & threat model

| Tier | Count | Trigger | Runtime *(target)* |
|---|---|---|---|
| Contract | 47 | every push (CI) | < 2 min |
| Eval self-tests | 54 | every push (CI) | < 2 min |
| ci eval lane | 61 cases ×1 | every push (CI) | < 5 min |
| e2e | 32 | local / nightly with stack | < 10 min |

| Threat | Control |
|---|---|
| Judge drift rewrites history | pinned temp/seed + `judge_version` per score |
| Tuning on the test set | dev/holdout split (release runs holdout) |
| Guardrail coverage rot | coverage.yml completeness gate |
| Flakes masking regressions | `is_flaky` quarantine (reported, not gating) |
| Safety graded by a model | forbidden by design — Layer 4 is rule-based |

**Hermeticity guarantees (facts):** zero keys anywhere ⇒ nothing to leak, no
flaky external dependency, zero marginal cost, bit-for-bit reproducible gates.
Ops hooks: `alerts.py` trend thresholds · `telemetry.py` sink · `promotion.py`
online loop (traffic → review queue → weekly promotion, provenance-tagged) ·
five runbooks in `evals/docs/`.

---

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
