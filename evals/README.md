# ShipSmart evals

The cross-repo evaluation home. Six layers run in three lanes over versioned
JSONL datasets, graded deterministically (+ semantic/judge in model lanes), gated
by honest statistics, and appended to a flat history with a regenerated trend.

**Philosophy:** deterministic contracts first; grade decisions and behavior, not
vibes; rule-based graders before judges; CI stays hermetic and keyless; every
gate has an owner and a number.

## Layers → lanes
| L | Layer | Question it answers |
|---|---|---|
| 1 | Contract & schema | Do the repos still agree on every cross-boundary shape? |
| 2 | RAG quality | Does retrieval fetch the right evidence, and do answers stay inside it? |
| 3 | Agent & tool-use | Does the agent choose the right tool, with the right args, and stop? |
| 4 | Safety & guardrail | Do injection, misuse, leakage, forged-state attacks fail? |
| 5 | Product-behavior | Do typed actions, drafts, quotes, refusals work end-to-end? |
| 6 | Online & review loop | Is production quality holding, and do real failures improve the suite? |

| Lane | Runs | Providers | Gate |
|---|---|---|---|
| **ci** (every PR) | 1 | scripted/echo, memory store — keyless, hermetic | zero failures; < 5 min |
| **nightly** | 3 | real embeddings + pinned judge (keys) | alert on trend deltas; no merge block |
| **release** | 5 (dev+holdout) | real providers, pinned versions | layer gates; zero critical; human sign-off |

## Run
```bash
uv run python -m evals.runners.run_lane ci        # keyless, exits non-zero on failure
uv run python -m evals.runners.run_lane nightly    # + semantic/judge on cases that declare them
uv run python -m evals.runners.run_lane release
uv run pytest evals/                               # the harness self-tests (F0)
```

## Layout
```
evals/
  case_model.py · trace.py · tags.py · rigor.py · manifest.py · protocol.py
  graders/  rule_based.py · semantic.py · llm_judge.py
  runners/  run_suite.py · run_lane.py · merge_reports.py
  datasets/ MANIFEST.yml · {smoke,contract,rag,agent,safety,product}/*.vN.jsonl
  reports/  history.jsonl · trend.md · traces/   (generated, gitignored)
  config/   judge.yml
  coverage.yml        # guardrail control → tag → case-ids (§13)
  tag_vocabulary.yml  # canonical decision tags (contract + coverage key)
  docs/     annotation-guide.md · judge-calibration.md · ai-governance-scope.md
```

## Status
**F0 (Foundation)** ships the mechanics: case model, manifest, rigor gate math,
graders, lane runners, history/trend, the tag vocabulary, `judge.yml`, and a
deterministic `smoke/foundation` self-test suite. Product datasets and real
systems-under-test are added per phase (F1–F10) — see the implementation plan.
