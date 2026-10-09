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

Widget and demo web client:

```bash
cd widget && npm install
cd client/web && npm install
```
