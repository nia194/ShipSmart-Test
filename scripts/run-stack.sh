#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# Host the self-contained ShipSmart stack for live e2e tests.
#
#   up   → pgvector (Java DB) + MCP(:8001) + API(:8000) + Java(:8080)
#   down → stop services, remove the container, clean state
#
# Self-contained: no real Supabase / LLM keys. MCP uses the mock provider, the
# API uses the in-memory vector store + EchoClient, Java uses a test HS256 JWT
# secret + Hibernate create-drop (Flyway pointed at an empty location so the
# FlywayValidationRunner bean still wires but runs no migrations).
#
# Services log to .stack/*.log; PIDs in .stack/*.pid. Java is OPTIONAL — if it
# doesn't come up, the Java e2e tests skip and MCP+API still run.
# ─────────────────────────────────────────────────────────────────────────────
set -uo pipefail
HERE="$(cd "$(dirname "$0")/.." && pwd)"   # ShipSmart-Test
ROOT="$(cd "$HERE/.." && pwd)"             # repos parent
STATE="$HERE/.stack"
export PATH="$HOME/.local/bin:$PATH"

# Shared, NON-secret test JWT secret (>=32 bytes for HS256). Mirrored in e2e/conftest.py.
export SHIPSMART_E2E_JWT_SECRET="e2e-test-secret-please-change-32chars-minimum"
# NON-secret admin token so the /admin/ai-controls e2e can exercise the kill-switch
# surface (fail-closed: unset would 404 it). Mirrored in e2e/conftest.py.
export SHIPSMART_E2E_ADMIN_TOKEN="e2e-admin-token-nonsecret"

wait_http() {  # url name [max-seconds]
  local url="$1" name="$2" max="${3:-60}"
  if curl -fsS --retry "$max" --retry-connrefused --retry-delay 1 --max-time "$((max + 10))" "$url" >/dev/null 2>&1; then
    echo "  ✓ $name ready ($url)"; return 0
  fi
  echo "  ✗ $name NOT ready ($url)"; return 1
}

up() {
  mkdir -p "$STATE"
  echo "▶ Postgres + pgvector (:5433)…"
  docker rm -f ss_e2e_pg >/dev/null 2>&1 || true
  docker run -d --name ss_e2e_pg -p 5433:5432 \
    -e POSTGRES_PASSWORD=postgres -e POSTGRES_DB=postgres \
    pgvector/pgvector:pg15 >/dev/null

  echo "▶ MCP (:8001)…"
  ( cd "$ROOT/ShipSmart-MCP" && MCP_API_KEY= SHIPPING_PROVIDER=mock APP_ENV=development \
      nohup uv run uvicorn app.main:app --host 127.0.0.1 --port 8001 >"$STATE/mcp.log" 2>&1 &
    echo $! >"$STATE/mcp.pid" )
  # API hydrates its MCP tool registry at boot — wait for MCP first.
  wait_http http://127.0.0.1:8001/health MCP 60

  echo "▶ API (:8000)…"
  ( cd "$ROOT/ShipSmart-API" && \
      APP_ENV=development VECTOR_STORE_TYPE=memory EMBEDDING_PROVIDER= \
      LLM_PROVIDER= LLM_PROVIDER_REASONING= LLM_PROVIDER_SYNTHESIS= OPENAI_API_KEY= \
      SHIPSMART_MCP_URL=http://127.0.0.1:8001 SHIPSMART_MCP_API_KEY= \
      INTERNAL_JAVA_API_URL=http://127.0.0.1:8080 RAG_AUTO_INGEST=true DATABASE_URL= \
      GUARDRAILS_ENABLED=true GUARDRAILS_BLOCK_ON_INJECTION=true \
      WORKFLOW_ENABLED=true CONCIERGE_ENABLED=true CONVERSATION_STORE=memory \
      ASSISTANT_CONTRACT_V1=true ADMIN_API_TOKEN="$SHIPSMART_E2E_ADMIN_TOKEN" \
      SHIPPING_SCOPE="${SHIPPING_SCOPE:-worldwide}" \
      COMPLIANCE_EXPLICIT_ENABLED="${COMPLIANCE_EXPLICIT_ENABLED:-true}" \
      nohup uv run uvicorn app.main:app --host 127.0.0.1 --port 8000 >"$STATE/api.log" 2>&1 &
    echo $! >"$STATE/api.pid" )

  echo "▶ Java (:8080) — building bootJar (optional)…"
  ( cd "$ROOT/ShipSmart-Orchestrator"
    if ./gradlew bootJar -q >"$STATE/java_build.log" 2>&1; then
      JAR="$(ls build/libs/*.jar 2>/dev/null | grep -v plain | head -1)"
      SERVER_PORT=8080 SPRING_PROFILES_ACTIVE=local \
        DATABASE_URL=jdbc:postgresql://127.0.0.1:5433/postgres \
        DATABASE_USERNAME=postgres DATABASE_PASSWORD=postgres \
        SUPABASE_JWT_SECRET="$SHIPSMART_E2E_JWT_SECRET" REQUIRE_JWT_SECRET=true \
        SPRING_JPA_HIBERNATE_DDL_AUTO=create-drop \
        SPRING_FLYWAY_LOCATIONS=classpath:db/e2e-none \
        SPRING_FLYWAY_FAIL_ON_MISSING_LOCATIONS=false \
        SHIPSMART_RATE_LIMIT_ENABLED=false \
        MANAGEMENT_TRACING_SAMPLING_PROBABILITY=0.0 \
        MANAGEMENT_OTLP_TRACING_ENDPOINT=http://localhost:4318/v1/traces \
        nohup java -jar "$JAR" >"$STATE/java.log" 2>&1 &
      echo $! >"$STATE/java.pid"
    else
      echo "  (Java bootJar build failed — skipping Java; see .stack/java_build.log)"
    fi )

  echo "⏳ waiting for health…"
  wait_http http://127.0.0.1:8000/health API 60
  wait_http http://127.0.0.1:8080/api/v1/health Java 120 || echo "    (Java optional — its e2e tests will skip)"
  echo "stack: up"
}

down() {
  echo "▶ stopping services…"
  for s in api mcp java; do
    [ -f "$STATE/$s.pid" ] && kill "$(cat "$STATE/$s.pid")" 2>/dev/null || true
  done
  pkill -f "uvicorn app.main:app --host 127.0.0.1 --port 8001" 2>/dev/null || true
  pkill -f "uvicorn app.main:app --host 127.0.0.1 --port 8000" 2>/dev/null || true
  pkill -f "java -jar .*ShipSmart-Orchestrator" 2>/dev/null || true
  docker rm -f ss_e2e_pg >/dev/null 2>&1 || true
  rm -rf "$STATE"
  echo "stack: down"
}

case "${1:-}" in
  up) up ;;
  down) down ;;
  *) echo "usage: $0 up|down" ; exit 1 ;;
esac
