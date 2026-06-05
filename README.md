# ShipSmart-Test

Cross-repo **contract** + live **e2e** integration tests for the ShipSmart system.
Assumes the five service repos are siblings of this one:

```
shipHub Details/
├── ShipSmart-Web/  ShipSmart-API/  ShipSmart-MCP/
├── ShipSmart-Orchestrator/  ShipSmart-Infra/
└── ShipSmart-Test/   ← you are here
```

## Layout
- `contract/` — parse the sibling repos' source and assert the wire shapes line up
  so a rename in one repo can't silently break a consumer in another:
  - ShipSmart-API advisor response models ↔ ShipSmart-Web TS types (incl.
    `decision_path`/`source` tags),
  - ShipSmart-Orchestrator `ShipmentSummaryDto` ↔ ShipSmart-Web `ShipmentSummary`,
  - ShipSmart-MCP tool `input_schema` ↔ the API's test double ↔ Web context keys,
  - ShipSmart-Infra `match_rag_chunks_lexical` signature ↔ the API's SQL.
  **No services required** — runs anywhere, fast.
- `e2e/` — live HTTP tests against a running self-contained stack: MCP tools,
  API `/ready` chain report, the **API → MCP** tool hop, RAG grounding, guardrail
  injection block, and (optional) Java `/shipments` JWT-scoping + ownership.
- `scripts/run-stack.sh` — host the stack (pgvector + MCP + API + Java).
- `docker-compose.yml` — just the pgvector database.

## Run
```bash
uv run pytest contract/          # fast; nothing to host
scripts/run-stack.sh up          # host the stack (Docker required)
uv run pytest e2e/               # live cross-service tests
scripts/run-stack.sh down        # tear everything down
```
`uv run pytest` alone runs both suites; e2e tests **skip** (never fail) when a
service is down, so `contract/` always passes even with nothing hosted.

## Self-contained stack — no real Supabase / LLM keys
- **MCP** uses its mock provider.
- **API** uses the in-memory vector store + `EchoClient`, and is pointed at the
  local MCP for tool calls.
- **Java** uses Hibernate `create-drop` (Flyway pointed at an empty location so
  the `FlywayValidationRunner` bean still wires but runs no migrations) and a
  **test** HS256 JWT secret; e2e tokens are minted in `e2e/conftest.py`.
  Java is optional — if it doesn't boot, its e2e tests skip and MCP+API still run.

Override endpoints/secret via `SHIPSMART_E2E_{MCP,API,JAVA}_URL` and
`SHIPSMART_E2E_JWT_SECRET`.
