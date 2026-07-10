# The online eval loop (evals §14 / guardrails §6.4 — Layer 6)

Production behavior feeding the eval suite, with a human gate in the middle.
Live as of F10: the intake endpoint ships in ShipSmart-API, the client in
ShipSmart-Web, and the sampler/queue here.

## The path

1. **Intake.** `POST /api/v1/feedback` (ShipSmart-API) records a thumbs-up/down +
   optional category/comment as an AIEvent — identity pseudonymized, comment
   PII-redacted at build time. The Web client (`src/lib/feedback-api.ts`) is
   fire-and-forget: feedback never breaks the surface that asked for it.
2. **Shadow sampling.** `evals/promotion.py::build_review_queue` samples the
   event stream **deterministically** (hash-based, auditable — no seed drift).
   The §9.2 priority signals are always sampled — a `feedback:down` complaint or
   any `guardrail:*` firing in the decision path (a block/refusal/structured-output
   retry) — plus `DEFAULT_SAMPLE_RATE` (5%) of the remaining traffic. Candidates
   append to `reports/review_queue.jsonl` (gitignored).
3. **Weekly review.** A human works the queue with the
   [annotation guide](./annotation-guide.md): label the failure category +
   severity, decide `promoted` or `dismissed`.
4. **Promotion — a reviewed diff, never an append.** For a promoted item,
   `to_candidate_case` emits a dataset-ready dict with
   `provenance: "online_promoted"` (validated through the real Case model;
   promoted cases enter the `dev` split — holdout stays authored-only). The
   reviewer pastes it into the target `*.vN.jsonl`, bumps the dataset version,
   re-records the manifest sha256, and — if it carries a `guardrail:*` tag —
   adds the case id to `coverage.yml`. CI enforces all three.

## Invariants

- **Nothing promotes itself.** The pipeline writes candidates; only a human
  moves a case into a dataset (the manifest sha256 makes silent appends fail).
- **PII never enters a dataset.** Redaction happened at AIEvent build time,
  upstream of the sampler; the reviewer is the second pair of eyes.
- **Incidents skip the queue.** A production incident becomes a case directly
  with `provenance: "incident"` (see [incident-response](./incident-response.md)).
- **Drift watch.** The nightly lane replays promoted cases like any other; the
  §11 trend alerts catch a promoted-case cluster regressing.

This is cross-doc reconciliation #3: the evals promotion pipeline and the
guardrails feedback-triage queue are one path, not two.
