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

> Wired to a live judge client in the judge phase (F8); seeded here in F0.
