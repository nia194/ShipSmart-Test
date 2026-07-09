# Judge calibration (evals §10, §12)

The LLM-as-judge is **pinned and governed** so its scores can gate anything.

- **Pinning.** `config/judge.yml` fixes provider + model (default OpenAI gpt-4o;
  Anthropic Claude supported), temperature 0, and per-rubric versions. Every
  score event records `judge_version`. A rubric edit is a **version bump** —
  silent edits invalidate every historical trend.
- **Lanes.** The judge runs in nightly + release + online only — never in CI
  (keys, cost, variance) — and never decides Layer-4 safety verdicts (rule-based).
- **Calibration ritual.** Monthly, two humans label the same 10 judged traces
  per rubric using the [annotation guide](./annotation-guide.md). Judge-vs-human
  agreement **< 80% ⇒ rubric revision (version bump)** before its scores gate
  anything. The humans' labels double as the judge's ground truth, so one
  session calibrates both people and machine.
- **Error handling.** Invalid JSON → one corrective retry → `judge_error`
  (counted, reported, never a silent pass). A `judge_error` rate > 2% is itself
  an alert.

## How the judge is wired (F8)
- `graders/llm_judge.py` builds the rubric prompt, calls the pinned provider
  (`config/judge.yml`: OpenAI gpt-4o default, seed 7, temperature 0, `max_tokens`
  512, one corrective retry), and parses the strict verdict contract
  `{score, verdict, reasoning, violations}`. Bad JSON that survives the retry
  becomes a `judge_error` (a non-pass), never a silent pass.
- `available()` gates the judge on a provider key being present, so CI (and any
  keyless run) never invokes it; only nightly/release with keys do.
- Standard rubric templates live in `graders/judge_prompts/*.md`, version-pinned
  in `judge.yml`. The four seeded rubrics: `faithfulness`, `answer_relevance`,
  `refusal_quality`, `explanation_quality`.

## First calibration session (2026-07-08, seed)
Two raters (R1, R2) labeled 10 `explanation_quality` traces per the annotation
guide; agreement computed with `evals/calibration.py`. Illustrative baseline:

| Rubric | n | Raw agreement | Cohen's κ | Gate (≥0.80) |
|---|---|---|---|---|
| explanation_quality | 10 | 0.90 | 0.80 | ✅ ok |
| refusal_quality | 10 | 0.80 | 0.60 | ✅ ok (watch) |

Action items from the session: the one `explanation_quality` disagreement was a
"mild overclaim vs acceptable confidence" boundary → tightened the rubric wording
(no version bump needed, agreement ≥ 0.80). `refusal_quality` at 0.80 is on the
line — re-sample next cadence before letting it gate. This table is regenerated
each monthly session; a row < 0.80 freezes that rubric (version bump) first.
