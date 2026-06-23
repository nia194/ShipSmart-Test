# ShipSmart — Integration Tests (`test`)

[![Python](https://img.shields.io/badge/Python-3.13-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![uv](https://img.shields.io/badge/uv-0.6%2B-DE5FE9?logo=python&logoColor=white)](https://docs.astral.sh/uv/)
[![pytest](https://img.shields.io/badge/pytest-contract%20%2B%20e2e-0A9EDC?logo=pytest&logoColor=white)](https://docs.pytest.org/)
[![Ruff](https://img.shields.io/badge/lint-ruff-D7FF64?logo=ruff&logoColor=black)](https://docs.astral.sh/ruff/)
[![License](https://img.shields.io/badge/License-See%20LICENSE-blue)](./LICENSE)

Cross-repo **contract** + live **e2e** integration tests for the ShipSmart
platform — the single place that proves the five services agree on their wire
shapes and actually work together end to end.

**Stack:** Python 3.13 · uv · pytest (+ pytest-asyncio) · httpx · PyJWT · ruff

---

## Table of contents

- [The ShipSmart ecosystem](#the-shipsmart-ecosystem)
- [What this repo verifies](#what-this-repo-verifies)
- [Layout](#layout)
- [Running the suites](#running-the-suites)
- [The self-contained stack](#the-self-contained-stack)
- [Planned: Hybrid Form ⇄ Chat Sync coverage](#planned-hybrid-form--chat-sync-coverage)
- [License](#license)

---

## The ShipSmart ecosystem

This repo is the cross-repo **test harness** for the five ShipSmart services.
Clone them all under one parent directory so the contract suite can resolve each
sibling by relative path (see `sibling.py`):

```
shipHub Details/
├── ShipSmart-Web/   ShipSmart-API/   ShipSmart-MCP/
├── ShipSmart-Orchestrator/   ShipSmart-Infra/
└── ShipSmart-Test/   ← you are here
```

| Repo | Role | What this suite checks |
|------|------|------------------------|
| [ShipSmart-Web](https://github.com/nia194/ShipSmart-Web) | React SPA — user-facing UI | TS types ↔ API / Java / MCP wire shapes |
| [ShipSmart-Orchestrator](https://github.com/nia194/ShipSmart-Orchestrator) | Java transactional API — single Postgres writer | `ShipmentSummaryDto` ↔ Web; live `/shipments` JWT-scoping + ownership |
| [ShipSmart-API](https://github.com/nia194/ShipSmart-API) | Python AI/orchestration — RAG, advisors, recommendations, compliance (UC2), multi-agent workflow (UC3/UC4) | schemas ↔ Web; live advisor / RAG / compliance / workflow |
| [ShipSmart-MCP](https://github.com/nia194/ShipSmart-MCP) | MCP tool server | tool `input_schema` ↔ API test double ↔ Web context; live API→MCP hop |
| [ShipSmart-Infra](https://github.com/nia194/ShipSmart-Infra) | Supabase migrations + env + docs | `match_rag_chunks_lexical` SQL signature ↔ API |

---

## What this repo verifies

Two complementary layers — one static, one live:

- **Contract** (`contract/`, **no services required**) — parses the sibling
  repos' *source as text* (`sibling.py`) and asserts the wire shapes line up, so
  a field rename in one repo can't silently break a consumer in another. Fast and
  hermetic; runs anywhere (**17 tests**):
  - ShipSmart-API advisor response models ↔ ShipSmart-Web TS types (incl.
    `decision_path` / `source` tags),
  - ShipSmart-API compliance + workflow schemas (`WorkflowResponse`,
    `ComplianceSummary`, the HS/duty/carrier/doc domain models, the
    `cleared|blocked` determination literal) ↔ ShipSmart-Web `workflow-api.ts`,
  - ShipSmart-Orchestrator `ShipmentSummaryDto` ↔ ShipSmart-Web `ShipmentSummary`,
  - ShipSmart-MCP tool `input_schema` ↔ the API's test double ↔ Web context keys,
  - ShipSmart-Web `compare.types.ts` ↔ ShipSmart-API `compare.py`,
  - ShipSmart-Infra `match_rag_chunks_lexical` signature ↔ the API's SQL.
- **e2e** (`e2e/`, **live stack**) — HTTP tests against a running self-contained
  stack: MCP tools, API `/ready` chain report, the **API → MCP** tool hop, RAG
  grounding, guardrail injection block, the **compliance check** + the full
  **workflow lifecycle** (process → durable `GET` → human review → resume, plus
  `404`/`409` edges), and (optional) Java `/shipments` JWT-scoping + ownership.
  Each suite **skips** (never fails) when its service is down.

---

## Layout

- `contract/` — static cross-repo shape checks (no services).
- `e2e/` — live cross-service HTTP tests (`pytest.mark.e2e`).
- `sibling.py` — text-parsing helpers (`ts_interface_fields`, `py_model_fields`,
  `py_class_fields`, `java_record_components`, `json_schema_required`).
- `scripts/run-stack.sh` — host the self-contained stack (pgvector + MCP + API +
  Java; sets `WORKFLOW_ENABLED=true` so the workflow e2e exercises UC3/UC4).
- `docker-compose.yml` — just the pgvector database.

---

## Running the suites

```bash
uv run ruff check .              # lint
uv run pytest contract/         # fast; nothing to host (17 tests)
scripts/run-stack.sh up         # host the stack (Docker required)
uv run pytest e2e/              # live cross-service tests
scripts/run-stack.sh down       # tear everything down
```

`uv run pytest` alone runs both suites; e2e tests **skip** (never fail) when a
service is down, so `contract/` always passes even with nothing hosted.

---

## The self-contained stack — no real Supabase / LLM keys

- **MCP** uses its mock provider.
- **API** uses the in-memory vector store + `EchoClient`, is pointed at the local
  MCP for tool calls, and runs with `WORKFLOW_ENABLED=true` (compliance is on by
  default) so the UC2/UC3/UC4 e2e paths are exercised.
- **Java** uses Hibernate `create-drop` (Flyway pointed at an empty location so
  the `FlywayValidationRunner` bean still wires but runs no migrations), the
  tracing exporter disabled, and a **test** HS256 JWT secret; e2e tokens are
  minted in `e2e/conftest.py`. The full context boots (the `QuoteCache`
  two-constructor wiring is fixed in ShipSmart-Orchestrator), so the Java e2e
  tests **run** — create → read → list → cross-user ownership (404) against real
  Postgres. They still skip gracefully if Java is intentionally left down.

Override endpoints/secret via `SHIPSMART_E2E_{MCP,API,JAVA}_URL` and
`SHIPSMART_E2E_JWT_SECRET`.

---

## Planned: Hybrid Form ⇄ Chat Sync coverage

> **Status: planned — not yet implemented.** Records upcoming cross-repo test coverage
> for the hybrid form ⇄ chat sync feature ahead of the code. The suites below don't
> exist yet.

When the shared-shipment-draft feature lands across ShipSmart-Web (a shared
`ShipmentDraft` store) and ShipSmart-API (the concierge consuming form-provided slots),
this harness will gain:

- **Contract** — assert the Web `ShipmentDraft` → concierge-state adapters line up with
  the API's `ConversationState.slots` / advisor-context fields (the shared
  shipment-context superset both surfaces populate).
- **e2e** — an additive live-stack flow proving the round trip: provide a route in chat
  → assert the form fields populate → provide weight in the form → assert the concierge
  **does not re-ask** for it → run a quote. Skips gracefully when the stack is down, like
  the other e2e suites.

Depends on the (also-planned) Conversational Concierge chat endpoint
(`/api/v1/concierge/chat`) in ShipSmart-API. **No Orchestrator / MCP / Infra change** is
involved — the draft is client-owned.

---

## License

See [LICENSE](./LICENSE) for the full text.
