---
name: verify-db
description: Get Postgres running for FitGen, seed it, and run the database-backed tests (the ones that skip without a DB), including troubleshooting Docker and port problems. Use when DB tests are skipped, after a schema change, or when asked to verify a phase end to end.
---

# Verifying FitGen against Postgres

The DB tests (`tests/test_db.py`, `tests/test_tools_db.py`) skip silently when Postgres is
unreachable. A run with those skips is **not** full verification; say so explicitly.

## Connection settings

| Setting | Default | Used by |
|---|---|---|
| `DATABASE_URL` | `postgresql+asyncpg://fitgen:fitgen@localhost:5433/fitgen` | server, seed |
| `TEST_DATABASE_URL` | `postgresql+asyncpg://fitgen:fitgen@localhost:5433/fitgen_test` | tests (wiped each run) |

Compose maps container 5432 to host **5433** (`POSTGRES_PORT` overrides it), because
something else already listens on 5432 on the dev machine.

## Steps

1. Check Docker answers, with a timeout (a hung Docker Desktop blocks forever):
   `timeout 5 docker version --format '{{.Server.Version}}'`
2. Start Postgres: `docker compose -f infra/docker-compose.yml up -d`, then wait for
   `docker compose -f infra/docker-compose.yml ps` to show it healthy.
   `infra/postgres-init/01-create-test-db.sql` creates `fitgen_test`, but only when the
   volume is first created. If the volume already existed, create it by hand:
   `docker compose -f infra/docker-compose.yml exec postgres createdb -U fitgen fitgen_test`
3. Seed the dev database: `uv run python -m server.db.seed --reset` (wipes all data).
4. Run everything: `uv run pytest -q`. Expect zero skips. The test fixtures reseed
   `fitgen_test` themselves.
5. Optional manual check: `uv run uvicorn server.app:app --port 8000`, then MCP Inspector
   (`npx @modelcontextprotocol/inspector`, Streamable HTTP, `http://localhost:8000/mcp`).

## Troubleshooting

- **Docker hangs** (`docker version` never returns, socket ping times out): Docker
  Desktop is stuck. Ask the user to quit and reopen it. Don't kill processes yourself.
- **Use an existing local Postgres instead:** if something on port 5432 is a Postgres the
  user controls, it can host the `fitgen` role and both databases. Ask before creating
  anything on it, then set both URLs in `.env` to port 5432.
- **`password authentication failed` / `database does not exist`:** the volume was created
  with different settings, or step 2's test DB wasn't created. Removing the volume
  (`docker compose -f infra/docker-compose.yml down -v`) deletes all local data, so ask
  the user first.
- **Tests fail after a model change:** reseed with `--reset`; there's no Alembic.
- **Run in a sandbox:** if the shell sandbox blocks the Docker socket, retrying the same
  command outside the sandbox tells a sandbox block apart from a stuck Docker.

## Report

State the Postgres source (compose on 5433, or local on 5432), seed result, and the
pytest line with pass/fail/skip counts. Any remaining skip means not fully verified.
