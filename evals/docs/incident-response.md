# AI incident response (Governance & Guardrails §12)

What to do when a guardrail metric pages. The detection side is
`ai_guardrail_daily` (Infra view) + `guardrail_metrics.check_thresholds`
(ShipSmart-API) + the eval trend alerts (`evals/alerts.py` → `trend.md`); this
doc is the human side: severity, first response, and which switch to pull.

## Severity ladder

| Severity | Definition | Examples | Response clock |
|---|---|---|---|
| **SEV-1** | Money/legal/safety exposure is live | AI-confirmed booking without a stored quote; PII in an outbound reply; compliance "cleared" asserted by the model | Kill the feature first, ask questions second |
| **SEV-2** | A control is degrading but the trust boundary held | Injection-block spike; structured_output_invalid > 2%; judge_error > 2%; state-signature failures climbing | Same day: diagnose, tighten, add the incident case |
| **SEV-3** | Quality drift, no control breached | Pass-rate warn in trend.md; explanation-quality slump; latency creep | Next working session; track in trend |

## Runbooks (per control)

| Paging signal | Likely cause | First response | Kill-switch |
|---|---|---|---|
| `injection_blocks` spike | Attack wave / new jailbreak pattern | Sample blocked inputs from the audit log; add the pattern as a redteam case (provenance `incident`) | `concierge` (chat surface) |
| `structured_output_invalid` > 2% | Provider/model drift, prompt regression | Pin/roll back model version; check prompt_version diff in AIEvents | `agent` if the loop misbehaves |
| `state_integrity_failures` climbing | Client bug or forged-state probing | Correlate session hashes; if probing, treat as SEV-2 attack | none (verification must stay on) |
| `tool_denials` spike | Planner drift or misuse probing | Inspect denied (tool, route) pairs in the tool audit | `agent` |
| `quarantined_chunks` on ingest | Poisoned/compromised source document | Quarantine stays; verify the source against its registry hash; re-ingest clean | `rag` if poison reached the store |
| judge_error > 2% (trend warn) | Judge provider outage or contract drift | Fail over judge provider in `config/judge.yml`; nightly scores are suspect until green | n/a (judge never gates safety) |
| Layer-4 gate FAIL (trend page) | A safety control regressed | Block release; bisect the offending commit; the failing case pins the regression | feature under test |

## Kill-switch inventory

* **Runtime (minutes):** `POST /api/v1/admin/ai-controls` on ShipSmart-API —
  token-gated (`ADMIN_API_TOKEN`; unset = endpoint does not exist), flips
  `agent | concierge | workflow | compliance | rag`, every flip audited as an
  AIEvent (`guardrail:killswitch:{feature}:{on|off}`). Guardrails/security
  modules are deliberately NOT killable.
* **Deploy-time (baseline):** the `*_enabled` env flags on API Settings.
* **Data plane:** RAG auto-ingest off via `RAG_AUTO_INGEST=false`; embedding
  compat check fails closed on its own (§7.3).

## After the incident

1. Write the postmortem note in the audit trail (the WORM log is the timeline).
2. **Every incident becomes an eval case** — add it to the relevant dataset with
   `provenance: "incident"` and a `guardrail:*` tag, so `coverage.yml` counts it
   and the regression can never return silently.
3. If a rubric/judge misjudged during the incident, run an off-cycle calibration
   session (see [judge-calibration](./judge-calibration.md)).
