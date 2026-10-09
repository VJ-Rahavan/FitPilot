# FitGen for Alexa+

Voice-first AI strength coach, delivered as a self-hosted MCP server
(MCP spec 2025-11-25, Streamable HTTP) with an MCP Apps widget.

Work in progress. Full docs land in Phase 9.

## Local dev

```bash
cp .env.example .env
docker compose -f infra/docker-compose.yml up -d   # Postgres 16 on localhost:5433
uv sync
uv run ruff check .
uv run pytest
```

Run the MCP server (Streamable HTTP at `http://localhost:8000/mcp`):

```bash
uv run uvicorn server.app:app --port 8000
```

Connect with MCP Inspector:

```bash
npx @modelcontextprotocol/inspector
```

In the Inspector UI choose transport **Streamable HTTP**, URL `http://localhost:8000/mcp`,
then Connect → Tools → `ping`. With `AUTH_MODE=api_key`, add an `x-api-key` header.

Widget and demo web client:

```bash
cd widget && npm install
cd client/web && npm install
```
# FitPilot
