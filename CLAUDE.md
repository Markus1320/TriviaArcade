# CLAUDE.md

This file guides Claude Code when working in this repository. Read it fully before starting any task.

## Project Overview

**TriviaArcade** is an open source trivia web game in the style of classic arcade cabinets. Topics are geography and history.

Core loop (version one):

1. The player presses START.
2. The backend picks a random path through a Wikidata based knowledge graph and asks an LLM to write a trivia question from those facts.
3. The player types an answer. A second, independent LLM call judges it as correct or incorrect.
4. Each correct answer increases the streak. The first wrong answer ends the run.
5. After game over, the player picks an existing handle or enters a new one, and the run is added to a top 10 leaderboard.

The project must stay maintainable and extendable. Prefer clear module boundaries and small, readable units over clever shortcuts.

## Tech Stack

| Layer | Technology |
|---|---|
| Entry point | Caddy (reverse proxy, the only service exposed to the network) |
| Frontend | React, TypeScript (strict), Vite |
| Backend | Python 3.12, FastAPI, Pydantic |
| Knowledge graph | Neo4j Community Edition, official Neo4j Python driver |
| Game and player data | PostgreSQL, SQLAlchemy, Alembic migrations |
| LLM | Ollama API (cloud, via API key) behind an internal abstraction |
| Local Python tooling | uv with a project venv |
| Orchestration | Docker Compose |
| CI | GitHub Actions |

## Architecture

```
Browser (any device on the home network)
        |
      Caddy  :8080 (published on all interfaces)
      /     \
static      /api -> backend (FastAPI)
frontend             |          |            |
(built into        Neo4j    PostgreSQL    Ollama API
 Caddy image)   (knowledge   (players, runs,
                  graph)     leaderboard, logs)
```

The frontend has no runtime container of its own. `frontend/Dockerfile` builds the static files with Node and copies them into a Caddy image; the root `Caddyfile` is mounted into it. Caddy proxies `/api/*` to the backend without stripping the prefix, so all FastAPI routes live under `/api`.

Key principles:

- **Neo4j holds rebuildable data only.** The knowledge graph can always be recreated by rerunning the import. Never store player or game data in Neo4j.
- **PostgreSQL holds irreplaceable data.** Players, runs, questions asked, verdicts and LLM call logs. Every schema change goes through an Alembic migration.
- **All game state lives on the server.** The frontend only receives a run ID, the question text and results. The expected answer is never sent to the browser before the answer has been judged.
- **The LLM is behind an interface.** Game logic depends on an `LLMClient` protocol, never on Ollama directly.

## Repository Layout

```
/
├── CLAUDE.md
├── README.md
├── LICENSE                     # MIT
├── THIRD_PARTY_NOTICES.md      # Wikidata (CC0), pixel font (OFL), others
├── .gitattributes              # LF line endings everywhere
├── .github/workflows/ci.yml    # lint, type check, test, compose validation
├── docker-compose.yml
├── compose.debug.yml           # optional: exposes PostgreSQL on 127.0.0.1
├── Caddyfile
├── .env.example                # placeholders only, never real values
├── data/raw/                   # gitignored cache of raw Wikidata responses
├── config/
│   └── import.yaml             # fame thresholds, relation allowlist, alias languages
├── backend/
│   ├── pyproject.toml
│   ├── uv.lock
│   ├── Dockerfile
│   ├── alembic.ini
│   ├── alembic/                # migrations; applied when the backend container starts
│   ├── prompts/                # system prompt, "=== USER ===" line, user template ($placeholders)
│   │   ├── generate_question.md
│   │   └── judge_answer.md
│   ├── app/
│   │   ├── main.py
│   │   ├── config.py           # settings from environment
│   │   ├── api/                # routers (health, runs, leaderboard), deps.py, errors.py
│   │   ├── game/               # rules.py (streak, game over), service.py (run lifecycle)
│   │   ├── graph/              # Neo4j driver, repository, random walk (walk.py)
│   │   ├── llm/                # LLMClient protocol, Ollama client, generator, judge,
│   │   │                       # facts formatting, call logging, factory
│   │   ├── leaderboard/        # handles.py, ranking.py, service.py (claim, top 10)
│   │   └── db/                 # SQLAlchemy engine, models, session handling
│   ├── importer/               # Wikidata import into Neo4j (python -m importer)
│   │   ├── config.py           # typed model of config/import.yaml
│   │   ├── sparql.py           # rate limited, cached SPARQL client
│   │   ├── queries.py          # SPARQL query builders
│   │   ├── build.py            # seeds -> relations -> labels -> facts
│   │   └── loader.py           # writes the graph into Neo4j
│   ├── scripts/                # manual tools: sample_questions.py (real LLM calls)
│   └── tests/
└── frontend/
    ├── package.json
    ├── Dockerfile              # builds static files into the Caddy image
    └── src/
        ├── App.tsx             # screen switching, resumes a run after reload
        ├── screens/            # title, question, game over, handle entry, leaderboard
        ├── components/
        ├── api/                # typed API client
        ├── audio/              # Web Audio sound effects
        ├── strings.ts          # all UI texts in one place
        └── styles/
```

Adjust the layout when there is a good reason, and update this file when you do.

## Environment and Commands

### Python

- Install uv on the host (e.g. `winget install astral-sh.uv`). uv provides Python 3.12 for the venv; the system Python is not used.
- Always use the uv managed venv in `backend/`. Run Python and tools through `uv run`, e.g. `uv run pytest`.
- Never install packages globally or with plain `pip`. Add dependencies with `uv add` so `uv.lock` stays in sync.

### Docker Compose

- `docker compose up --build` starts the full stack.
- Only Caddy publishes a port to the network (default `8080`, configurable via `CADDY_PORT`, bound to all interfaces) so the game is reachable from other devices on the home network via the host's local IP.
- Neo4j (7474, 7687) and PostgreSQL (5432) must **never** be published on all interfaces. Either keep them internal to Compose or bind them to `127.0.0.1` for local debugging.
- Current setup: Neo4j is bound to `127.0.0.1` (needed for the Neo4j Browser). PostgreSQL is internal; `docker compose -f docker-compose.yml -f compose.debug.yml up` exposes it on `127.0.0.1:${POSTGRES_DEBUG_PORT:-5432}`.
- `GET /api/health` checks both databases and returns 503 if one is down. The backend's Compose healthcheck uses it.
- Data volumes for Neo4j and PostgreSQL are named volumes so they survive restarts.

### Secrets

- All secrets and model names come from `.env`, which is gitignored.
- `.env.example` lists every variable with placeholder values and a short comment.
- Never commit real keys, never print them in logs, never hardcode them.

Expected variables (extend as needed):

```
OLLAMA_API_KEY=
OLLAMA_BASE_URL=
LLM_GENERATOR_MODEL=      # a recent Gemma or Qwen model
LLM_JUDGE_MODEL=          # a smaller, cheaper model
POSTGRES_USER=
POSTGRES_PASSWORD=
POSTGRES_DB=
NEO4J_USER=               # always "neo4j" for Community Edition
NEO4J_PASSWORD=           # at least 8 characters
NEO4J_HEAP_MAX=           # optional, default 1G
NEO4J_PAGECACHE=          # optional, default 512M
CADDY_PORT=               # optional, default 8080
POSTGRES_DEBUG_PORT=      # optional, only for compose.debug.yml, default 5432
LLM_TIMEOUT_SECONDS=      # optional, default 120
```

LLM variables are optional in the backend settings so the stack starts without an API key; `app/llm/factory.py` checks them when the LLM is used.

Model tags seen in the public Ollama cloud catalog (2026-09-23): `qwen3.5:397b` and `gemma4:31b` are the Gemma/Qwen options. The current setup uses `gemma4:31b-cloud` for both generator and judge (chosen by the project owner, verified with real sample runs).

Before filling in model names, check which model tags are actually available for the configured Ollama account. Do not guess tags.

## Game Rules (Version One)

- Constant difficulty. No difficulty ramp.
- No timer.
- One wrong answer ends the run. No lives, no skips.
- The streak is the score.
- Within a run, the same starting node is never used twice.
- After game over, the correct answer to the last question may be shown.
- If the judge fails technically (see below), the run is paused with an error message. A technical failure must never end a run.

## Knowledge Graph

### Source

Data comes from **Wikidata** (CC0). The importer queries the Wikidata SPARQL endpoint, caches raw responses in a gitignored `data/raw/` folder, and loads the processed result into Neo4j. Respect Wikidata's rate limits and send a descriptive User-Agent.

### Content and Balance

Balance is controlled at import time through `config/import.yaml`:

- **Fame filter:** each entity's Wikidata sitelinks count is its fame score. Only entities above `fame_threshold` are imported. Obscure entities must simply not exist in the graph.
- **Relation allowlist:** only trivia shaped relations are imported, e.g. capital, shares border with, continent, located in, flows through, official language, currency, head of state or ruler, participant in, founded by, point in time for major events.
- **Numeric facts** (population, share of world population, area, well known years) are allowed only for entities above the much higher `numeric_fame_threshold` (continents, the largest countries, the longest rivers). Store the reference year with time dependent values.
- **Aliases:** import labels and alternative labels in several languages (at least English and German, configurable) so answers in any language can be recognized.

Everything in the config must be tunable without code changes.

### Model

- Nodes carry at least: Wikidata ID, English label, aliases, sitelinks count, entity type.
- Relationships use the Wikidata property as type or attribute.
- Create indexes and constraints needed for fast random selection and lookups.

Current implementation:

- Every node has the label `Entity` plus a type label (`Country`, `HistoricalState`, ...). Properties: `wikidata_id`, `label` (English), `aliases` (other labels and alternative labels in all configured languages), `description` (English), `sitelinks`, `entity_type`, `seq`, and optional years and numeric facts named as in `config/import.yaml`.
- `seq` is a dense number `0..n-1` with a unique constraint, so the random walk can pick a random number in code instead of `ORDER BY rand()`.
- Relationship types are the allowlist names (`CAPITAL`, `SHARES_BORDER_WITH`, ...). Each relationship stores the Wikidata `property` and, from statement qualifiers, `start_year`, `end_year` or `year` where known. Historical values (e.g. former heads of state) are included; deprecated statements are not.
- Years use historical numbering: negative years are BCE, there is no year 0. Only values with at least year precision are stored.
- Seed entities come from the configured classes and fame thresholds. Relation targets outside the seeds (people, languages, currencies, obscure capitals) are added if they pass the target threshold and can be classified into a configured type. Direct queries for all famous humans time out on the public endpoint, so people only enter the graph through relations. `exclude_entities` removes ambiguous items (e.g. Afro-Eurasia); the order of `entity_types` decides the type of entities matching several types, and an entity cut by one type's `max_entities` is not picked up by a later type.
- Each import replaces the whole graph and writes an `ImportMeta` node with the import time and counts.
- Run it with `docker compose run --rm importer` (or `uv run python -m importer` on the host). `--dry-run` prints stats without touching Neo4j, `--refresh` ignores the cache.

### Question Seeds (Random Walk)

1. Pick a random eligible starting node (not used earlier in the current run).
2. Walk 1 to 3 random hops along allowed relations.
3. Return the resulting small subgraph of facts.

All randomness comes from code. The graph access lives behind a clear interface in `app/graph/`.

Current implementation (`app/graph/walk.py`): the start is chosen by picking an entity type uniformly, then a random entity of that type, so large types do not dominate. Starts without neighbors are skipped. Each hop goes to a random neighbor (either direction) not visited yet; a dead end ends the walk early. `RandomWalker` takes a `random.Random`, so walks are reproducible with a seed.

## LLM Integration

### Abstraction

- `app/llm/` defines an `LLMClient` protocol and an Ollama implementation.
- Generator and judge use separately configured models.
- Prompts live as template files in `backend/prompts/`, never as long strings inside Python code.
- Both calls send an Ollama structured output schema (the question object for the generator, `{"type": "boolean"}` for the judge), but the Ollama cloud API does not reliably enforce it: `gemma4:31b-cloud` wrapped its JSON in Markdown code fences. Therefore the generator prompt spells out the exact JSON shape with examples and asks for no code fences, and the generator parser also tolerates a code fence or text around the JSON object (the raw output is logged unchanged). The judge stays strict: only `true` or `false` is accepted.
- The generator also retries once on invalid output (bad JSON, schema mismatch, answer given away in the question) and then raises `QuestionGenerationError`. The judge raises `JudgeUnavailableError` after its retry; the game must pause the run on it.

### Call One: Generate Question

- Input: the subgraph facts from the random walk.
- The LLM has creative freedom in how it builds the question, including questions that connect several hops.
- Target audience in the prompt: answerable by a well read trivia fan. One clear answer. No obscure numbers.
- Numeric questions must be phrased as approximations and include an accepted range.
- Output is enforced as JSON via Ollama's structured output and validated with Pydantic:

```json
{
  "question": "string",
  "expected_answer": "string",
  "accepted_answers": ["string"],
  "numeric_range": { "min": 0, "max": 0, "unit": "string" }
}
```

`numeric_range` is null for non numeric questions. The expected answer and accepted answers are stored server side with the run.

### Call Two: Judge Answer

- Independent from call one. Input: question, expected answer, accepted answers, numeric range, player answer.
- Output: exactly `true` or `false`, nothing else.
- Leniency policy (part of the judge prompt):
  - Typos are accepted.
  - Answers in any language are accepted if correct.
  - Surnames alone are accepted for well known people (e.g. "Napoleon").
  - Vague answers are rejected (e.g. "in Europe" for a country).
  - Years must be exact unless the question asks for a decade or century.
  - Numeric answers are accepted within the given range.
- **Prompt injection defense:** the player answer is wrapped in clear delimiters and the prompt states that it is untrusted data, never instructions.
- **Strict parsing:** any output other than `true` or `false` triggers one retry. If the retry fails too, the run is paused with an error, not ended.
- Limit player answer length (e.g. 200 characters) before it reaches the LLM.

### Logging

Every generator and judge call is logged in PostgreSQL (inputs, raw output, parsed result, model, latency), so questionable verdicts and question quality can be reviewed later.

The table is `llm_calls` (one row per attempt, so retries are visible). A failure to write the log is reported but never breaks the game. Each row has an optional `run_id`, so all calls of a run can be reviewed together.

## Players and Leaderboard

- Handles: 3 to 8 characters, uppercase letters and digits only (`^[A-Z0-9]{3,8}$`). Normalize input to uppercase.
- After game over the player picks an existing handle or creates a new one.
- No passwords or accounts in version one. Anyone can post under any handle. This is accepted for a home network setup.
- A run can be claimed exactly once, and only after it has ended.
- The leaderboard shows the top 10 runs by streak. A player can appear multiple times. Ties are broken by the earlier finish time.

## Game Loop (Current Implementation)

- PostgreSQL tables: `players` (unique handle), `runs` (UUID, status `active` or `over`, streak, start and end time, claiming player), `questions` (one row per question with the walk facts, expected and accepted answers, numeric range, player answer and verdict). `llm_calls.run_id` links calls to runs.
- `app/game/rules.py` and `app/leaderboard/{handles,ranking}.py` hold the rules as pure functions; `app/game/service.py` and `app/leaderboard/service.py` apply them in transactions.
- Every run changing request locks the run row (`SELECT ... FOR NO KEY UPDATE`, so call log inserts referencing the run are not blocked). Parallel requests cannot create two questions or judge twice.
- Asking for the next question while one is open returns the open question, so reloading cannot skip a question. The browser keeps only the run ID (in `sessionStorage`) and resumes after a reload.
- A judge failure (`JudgeUnavailableError`) writes nothing and returns 503 `judge_unavailable`; the question stays open. A generation failure returns 503 `question_unavailable`; the run continues.
- Only claimed runs appear on the leaderboard. Claiming returns the run's rank, which may be below 10.
- Domain errors map to HTTP responses in `app/api/errors.py` as `{"code", "detail"}`; the frontend shows `detail`.

## Frontend and Styling

- Classic arcade look: black background, neon colors, the "Press Start 2P" pixel font (bundled locally, not loaded from Google), subtle CRT scanline overlay.
- Screens: title with blinking PRESS START, question screen with streak counter, game over, handle entry, leaderboard.
- All assets are original. Do not use characters, sprites, logos or sounds from real arcade games.
- Sound effects for correct, wrong and game over are generated with the Web Audio API (no audio files). Sound is **muted by default** with a visible toggle.
- UI language is English. All UI texts live in `src/strings.ts` so a translation can be added later.
- The layout must work on phones, since the game is played across the home network.

## Code Quality and Testing

This project uses a deliberately light testing setup for version one.

### Always required

- Backend: `ruff` for linting and formatting, `mypy` for type checking.
- Frontend: ESLint (flat config with `typescript-eslint` strict type checked rules), Prettier, TypeScript strict mode. The current Vite template ships oxlint; this project uses ESLint instead.
- Backend tests with `pytest` for the critical logic:
  - parsing and validation of the generator JSON
  - strict true or false parsing of the judge, including retry and error behavior
  - streak and game over rules
  - handle validation
  - leaderboard ranking and tie breaking
- LLM calls are **always mocked** in tests. No test may call the real Ollama API.

- The game flow is tested through the HTTP API (`tests/test_game_api.py`) on in-memory SQLite with fake walk, generator and judge. JSON columns use JSONB on PostgreSQL and JSON on SQLite; row locks are no-ops there.

### Postponed (note for later)

- Frontend unit tests.
- Database integration tests with test containers (PostgreSQL specifics such as row locks are not covered by the SQLite tests).

### Manual quality check

`backend/scripts/` contains a script that runs real LLM calls to print a batch of sample questions, so question quality can be reviewed by a human. It is never part of CI.

### CI

GitHub Actions runs linters, type checks and tests on every push.

## Git Workflow

- Commit directly to `main`.
- Small, focused commits, one logical change each.
- Commit message prefixes: `feat:`, `fix:`, `docs:`, `refactor:`, `test:`, `chore:`.
- Commit only when linters, type checks and tests pass locally.
- Never force push and never rewrite history.
- Never commit `.env`, keys, raw data caches or database volumes.
- Tag playable milestones (e.g. `v0.1.0`).

## Definition of Done

A task is only finished when:

1. Linters, type checks and tests pass.
2. The Docker Compose stack still starts cleanly.
3. New configuration is reflected in `.env.example` or `config/import.yaml`.
4. README and this file are updated if setup, commands or architecture changed.
5. The work is committed following the rules above.

## Milestones

Work through these in order. **Stop after each milestone** and report: what was built, how to test it manually, and any open decisions. Do not start the next milestone until told to.

1. **Skeleton:** Docker Compose with Caddy, frontend, backend, Neo4j and PostgreSQL talking to each other; uv venv; linters; CI; MIT license; README with setup steps. Result: a placeholder page reachable from a phone on the home network, and a backend health endpoint that checks both databases.
2. **Knowledge graph:** Wikidata importer with fame filter, relation allowlist, numeric tier, aliases and `config/import.yaml`. Result: a browsable graph in the Neo4j browser with balanced content.
3. **LLM core:** random walk, question generator, judge, prompt files, structured output, call logging, and the sample question script. Alembic is introduced here, with the LLM call log table as the first migration. Result: printed sample questions that can be reviewed for quality.
4. **Game loop and leaderboard:** server side runs, PostgreSQL schema for players and runs (further Alembic migrations), API endpoints, handle entry, top 10 leaderboard. Result: the full game playable in a plain, unstyled UI.
5. **Arcade look:** pixel font, neon styling, scanlines, all classic screens, Web Audio sound effects. Result: tagged as `v0.1.0`.

## Out of Scope for Version One

These are planned for later. Keep the design open for them, but do not build them yet:

- Difficulty ramp based on streak (via fame score and hop count)
- Timer per question, enforced server side
- Lives or skips
- Player accounts and handle protection
- Deterministic or fuzzy answer matching before the LLM judge
- Hallucination checks against the graph
- German UI translation
- Per category leaderboards, stats, achievements
- Production hosting outside the home network

## When Unsure

If a requirement is unclear or two rules in this file conflict, stop and ask instead of guessing. Propose options with a recommendation.
