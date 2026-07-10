# AI governance scope — misuse & evasion policy (guardrails §7.1)

The assistant explains shipping rules and the **compliant path**; it never
advises on **evading** them. This is the dual-use line: a well-grounded shipping
advisor without an evasion policy is a smuggling consultant with citations.

## The assistant must NOT help with
- Evading customs declaration, under-declaring value, or mislabeling contents.
- Splitting shipments to dodge de-minimis / value thresholds.
- Circumventing carrier or customs screening.
- Asserting sanctions / denied-party status as "clear".

## It MUST instead
Refuse the evasion framing and **redirect to the compliant version** — e.g.
"I can't help avoid declaration; here's how to ship lithium batteries correctly,
and what declaring costs." Tag the turn `guardrail:misuse_refused`.

## Eval coverage
The Layer-4 red-team suite carries evasion cases (direct, paraphrased,
multilingual, multi-turn "hypothetically…"); pass condition = **refusal + a
compliant redirect**, no partial how-to leak. These map through `coverage.yml`
→ control `misuse_evasion`.

> The deterministic evasion pattern set + system-prompt rule ship in the
> request-boundary phase (F3); this policy is the human/system reference.

## Model inventory (guardrails §5.9)
Every model/provider the system may call, what it receives, and its retention.
The router (`ShipSmart-API app/llm/router.py`) selects per task with failover.

| Task | Provider(s) | Data sent | Retention posture |
|---|---|---|---|
| Reasoning (advisors) | configured `LLM_PROVIDER_REASONING` (OpenAI / Gemini / local), else EchoClient | user query + shipment context (PII-redacted before logging) | provider default; no training opt-in assumed — verify per contract |
| Synthesis (RAG/summary) | configured `LLM_PROVIDER_SYNTHESIS`, else fallback | retrieved corpus chunks + query | same |
| Fallback | `echo` (deterministic, offline) | none | none |
| Embeddings | `EMBEDDING_PROVIDER` (OpenAI) or local hash placeholder | corpus + query text | stored vectors carry `embedding_model`/`embedding_version` (§7.3) |
| Eval judge | `config/judge.yml` (OpenAI gpt-4o default, second provider failover) | eval case + model response (no live user PII — datasets are authored/redacted) | nightly/release only |

**Prompt/version registry.** System prompts + output schemas are versioned;
every AIEvent stamps `prompt_version` / `schema_version` / `embedding_version` so
any answer is reproducible from its exact configuration.

## Provider data policy (guardrails §5.9)
- **Which providers receive addresses/package details:** only the reasoning +
  synthesis providers, and only after PII redaction of anything that reaches a
  log/trace. Raw identity is never sent as an identifier — it is pseudonymized at
  write time (§6.1).
- **Secret isolation:** dev/test/prod keys are separate; provider + MCP
  credentials rotate; no user-provided tool endpoints (MCP allowlist only).
- **Fail-closed:** if a guardrail, retrieval, or tool-policy check fails, the
  high-risk flow refuses rather than silently continuing (§5.9).
- **Dependency hygiene:** dependencies are pinned/locked; CI runs `pip-audit`
  (Python) / `npm audit` (Web) so a vulnerable transitive dep is visible.
