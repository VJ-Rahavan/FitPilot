# FitGen for Alexa+: Progress

Status of the build against the implementation plan. Last updated 2026-10-12.

**Summary:** Phases 0–4 of 11 are done on `feature/alexa-mcp-server` and verified end to
end: all 152 tests pass against a real Postgres, and every tool call takes 6–36 ms.

## Phase status

| Phase | Scope | Status |
|---|---|---|
| 0 | Repo setup | ✅ Done |
| 1 | MCP server skeleton | ✅ Done, verified end to end |
| 2 | Data layer | ✅ Done, verified against Postgres |
| 3 | Catalog, presenters, MVP tools | ✅ Done, verified end to end |
| 4 | Guided session | ✅ Done, verified end to end |
| 5 | Widget (MCP Apps) | ⏳ Not started |
| 6 | Background AI jobs | ⏳ Not started |
| 7 | Stretch utilities | ⏳ Not started |
| 8 | Demo client | ⏳ Not started |
| 9 | Deployment and docs | ⏳ Not started |
| 10 | OAuth (only if Alexa requires it) | ⏸ Needs go-ahead |

## What each phase delivered

### Phase 0: Repo setup

- Repo layout per the plan, MIT `LICENSE`, empty `FRICTION_LOG.md` and `FEEDBACK.md`.
- Python tooling: uv, ruff, pytest (`pyproject.toml`).
- Node scaffolds (Vite + React + TypeScript) in `widget/` and `client/web/`.
- `infra/docker-compose.yml`: Postgres 16 on host port **5434** (5432/5433 are used by other
  projects on the dev machine).
- Import commit `aa19c70` "Import component catalog and renderer from FitGen
  (pre-hackathon)": the 14-component catalog and React renderer copied unchanged.
  Everything after it is hackathon work.

### Phase 1: MCP server skeleton

- `server/app.py`: FastAPI app with the MCP server mounted at `/mcp` (Streamable HTTP).
- `server/mcp_server.py`: the official MCP Python SDK server. `initialize` negotiates
  protocol **2025-11-25**. A middleware logs every tool call as
  `tool=<name> status=<ok|error> duration_ms=<n>`.
- `server/auth.py`: `get_current_user()` returns the demo user. `AUTH_MODE=api_key`
  checks `x-api-key` with a constant-time comparison and returns 401 otherwise.
  `AUTH_MODE=oauth` raises `NotImplementedError`.
- `server/config.py`: settings from env / `.env`.
- `ping` tool.

### Phase 2: Data layer

- `server/db/models.py`: users, user_profiles, exercises, exercise_aliases, plans,
  plan_days, plan_exercises, sessions, logged_sets, body_metrics, insights, jobs.
  - Weights stored in kg (`Numeric(8,3)`); every user-owned table has an indexed `user_id`.
  - The database enforces one active plan and one active session per user.
- `server/db/init_db.py`: creates tables from the models (no Alembic, see decisions).
- `server/db/repository.py`: queries; each user-owned query requires `user_id`.
- `server/services/units.py`: lb/kg conversion, unit parsing ("lbs", "kilos"),
  spoken formatting ("225 pounds").
- `server/services/exercise_resolver.py`: spoken name → exercise. Handles aliases
  ("bench", "rdl"), plurals ("squats"), missing spaces ("benchpress") and typos
  ("squatz"). Vague names ("press") return suggestions. Runs in memory.
- `server/db/seed.py` + `seed_data.py`: demo user (lb, strength goal, 4 days/week),
  28 exercises with aliases and 3 form cues each, a 4-day upper/lower plan, and 8 weeks
  of deterministic history (gradual progression, ~7% missed sets, 4 skipped sessions,
  twice-weekly weigh-ins).

### Phase 3: Catalog, presenters, MVP tools

- **Catalog** (`server/catalog/`): imports adapted; 16 components (the original 14 plus
  `session_card` and `plate_diagram`). Unknown keys are rejected. A validation failure
  is logged and raised as a server bug, never retried.
- **Every tool result has three parts:** spoken text, `structuredContent`
  (`{"components": [...], "display": "fragment" | "full"}`), and `_meta.ui.resourceUri`
  on the tool definition. The widget resource is a placeholder
  (`ui://fitgen/widget.html`, `text/html;profile=mcp-app`, empty CSP) until Phase 5.
- **Tools:**

  | Tool | Inputs | Display |
  |---|---|---|
  | `log_workout` | exercise, sets, reps, weight?, unit? | fragment |
  | `log_body_metric` | bodyweight, unit? | fragment |
  | `undo_last_log` | (none) | fragment |
  | `get_todays_workout` | (none) | full |
  | `get_weekly_summary` | weeks_ago? | full |
  | `get_exercise_progress` | exercise, weeks? | full |

- **Services** (`server/services/`): progressive overload, PR detection (heaviest
  weight, or most reps at a weight), dedupe of identical logs within 60 s, batch undo,
  weekly stats, deterministic fallback coaching line.
- **Presenters** (`server/presenters/`): short spoken text with rounded numbers and
  units in full; helpful voice errors ("Did you mean bench press or overhead press?").
- No LLM calls on the request path.

### Phase 4: Guided session

- **Tools:**

  | Tool | Inputs | Display |
  |---|---|---|
  | `start_session` | (none) | full |
  | `complete_set` | reps?, weight?, unit? | fragment |
  | `skip_exercise` | (none) | fragment |
  | `end_session` | (none) | full |

- **Server-owned position:** `sessions.current_position` / `current_set`; no IDs from the
  client. Targets are snapshotted into a new `session_exercises` table at start, so
  defaults stay fixed for the whole workout. A weight the user changes carries to the
  remaining sets of that exercise.
- **Flow:**
  - `start_session` starts today's plan day, or resumes today's active workout.
  - On a rest day it starts the next scheduled day and says so.
  - An active workout from an earlier day is closed first (deleted if it has no sets).
  - After the last set the workout stays open until `end_session` ("Say end workout to
    wrap up").
  - `end_session` with no sets cancels the workout.
- **Short replies between sets:** `complete_set` says "Set 2 of 4 done." and adds reps or
  weight only when they differ from the target, plus records and the next exercise.
  `session_card`, a rest `timer` (120 s barbell, 90 s other) and control buttons are
  returned for the widget.
- **Undo:** `undo_last_log` on a guided set moves the workout back to that set. Guided sets
  record `logged_sets.session_exercise_id`, so free-form `log_workout` sets never rewind
  the workout.
- **Retries:** a repeated `complete_set` within 8 s is treated as a retried request and not
  logged twice.
- **Background job hook:** `end_session` queues a `regenerate_weekly_insight` row in `jobs`
  (one queued per user) for the Phase 6 worker.
- `get_todays_workout` now includes a "Start workout" button.

## Decisions and deviations from the plan

| Decision | Reason |
|---|---|
| `MCPServer` instead of `FastMCP` | mcp 2.x renamed FastMCP to MCPServer; same official SDK |
| No Alembic | No real data to preserve; `seed --reset` rebuilds the schema. Add Alembic before real users |
| Overload step +2.5 lb / +1.25 kg for dumbbells | A flat +5 lb is a ~20% jump on a 25 lb dumbbell; barbell, machine and cable lifts keep +5 lb / +2.5 kg |
| Undo removes the whole last log | "Undo" after "3 sets of bench" should remove all 3 sets (`logged_sets.batch_id`) |
| `exercises.equipment` field | Bodyweight moves log no weight; plate calculator needs to know barbell lifts |
| `user_profiles.timezone` (demo: `Asia/Kolkata`) | "Today" and "this week" depend on the user's local date |
| `plan_days.weekday` | Lets "today's workout" come from the schedule in the database |
| Spoken weights round to 0.5 lb / 0.25 kg | So a 27.5 lb dumbbell isn't read out as "28 pounds" |
| Postgres on host port 5434 | Another project's container (`todo_postgres`) holds 5433 |
| `session_exercises` snapshot table | Default reps and weights stay fixed during a workout even if other sets are logged |
| Rest day starts the next scheduled day | Training on an off day is common; Alexa says which day it started |
| Workout stays open after the last set | Lets the user add a set before saying "end workout" |
| `complete_set` speaks details only when they differ | It's heard after every set; "Set 2 of 4 done." is enough |
| 8 s retry guard on `complete_set` | Voice requests get retried; a real set never follows the last one that fast |
| Demo user has fixed id 1 | Keeps `get_current_user()` free of DB lookups until OAuth |
| No tool `outputSchema` | The full catalog schema is large; tools validate against it before sending instead |

## Tests

152 tests, **all passing** against Postgres 16 (2026-10-12). Without a reachable database
the DB tests skip, which is not full verification.

Measured tool latency (server timing log, local Postgres): `get_todays_workout` 32 ms,
`log_workout` 25 ms, `get_weekly_summary` 14 ms, `log_body_metric` 8 ms,
`undo_last_log` 8 ms, `get_exercise_progress` 6 ms; `start_session` 36 ms, `end_session`
24 ms, `complete_set` 14 ms, `skip_exercise` 6 ms. Budget: 500 ms.

| Area | File | Needs DB |
|---|---|---|
| Server, auth, handshake | `tests/test_server_skeleton.py` | No |
| Units | `tests/test_units.py` | No |
| Exercise resolver, voice errors | `tests/test_exercise_resolver.py` | No |
| Seed history simulation | `tests/test_seed_history.py` | No |
| Catalog validation | `tests/test_catalog.py` | No |
| Progression and PRs | `tests/test_progression.py` | No |
| Presenters (spoken text + components) | `tests/test_presenters.py` | No |
| Tool listing, schemas, widget resource | `tests/test_tools_listing.py` | No |
| Models, seed, repository, user scoping | `tests/test_db.py` | **Yes** |
| All six tools end to end + < 500 ms latency | `tests/test_tools_db.py` | **Yes** |
| Session position state machine | `tests/test_session_state.py` | No |
| Session presenters (spoken text + components) | `tests/test_session_presenters.py` | No |
| Guided session end to end: walk-through, skip, resume, undo, retries, stale, latency | `tests/test_sessions_db.py` | **Yes** |

## How to run

```bash
cp .env.example .env
docker compose -f infra/docker-compose.yml up -d    # Postgres 16 on localhost:5434
uv sync
uv run python -m server.db.seed --reset              # tables + demo data
uv run pytest
uv run uvicorn server.app:app --port 8000            # MCP at http://localhost:8000/mcp
npx @modelcontextprotocol/inspector                  # Streamable HTTP → that URL
```

After any model change, rerun `uv run python -m server.db.seed --reset` (wipes all data).

## Open items

1. **MCP Apps capability on 2025-11-25.** The SDK advertises extensions under
   `capabilities.extensions` only for protocol 2026-07-28, so a 2025-11-25 connection
   doesn't announce MCP Apps there. Tools still carry `_meta.ui.resourceUri`. Check the
   ext-apps spec in Phase 5.
2. **Deployment note for Phase 9.** The SDK's DNS-rebinding protection defaults to
   localhost hosts; allowed hosts must be configured behind the ALB.

## Next up: Phase 5, widget (MCP Apps)

React + Vite single-file widget using `@modelcontextprotocol/ext-apps` for the host
bridge, rendering the catalog components (including `session_card`, `timer` and the
control buttons, which call tools), light/dark theme from hostContext, served as a hashed
`ui://fitgen/widget-<hash>.html` resource. Resolve open item 1 (MCP Apps capability on
2025-11-25) first.

## Claude Code agents and skills

Project-level helpers in `.claude/`. No agent changes git state; only `implementer`
edits files.

| Type | Name | Use it for |
|---|---|---|
| Agent | `implementer` | Implement an approved plan step, tool or fix, with tests, in the repo's conventions |
| Agent | `sdk-researcher` | How an SDK really works (MCP, ext-apps, Bedrock, Groq…), from installed source or official docs |
| Agent | `test-runner` | Run ruff + pytest, report failures with likely causes and any skipped DB tests |
| Agent | `voice-reviewer` | Check spoken text and tool descriptions for voice quality |
| Agent | `rules-reviewer` | Check changes against the non-negotiable rules |
| Skill | `phase-workflow` | Run one plan phase: propose, wait, implement, verify, summarize, no commits |
| Skill | `add-mcp-tool` | Recipe for a new tool: service → presenter → `apps.tool` → tests |
| Skill | `verify-db` | Start Postgres, seed, run the DB tests, troubleshoot Docker and ports |

## Working agreements

- One phase at a time: propose a plan, wait for OK, implement, test, summarize.
- Claude does not commit or push; changes are left for the user to commit.
- Read SDK source or official docs before using an API; ask when unclear.
- Friction log entries only for genuine, verified tool or SDK problems.
