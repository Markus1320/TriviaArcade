# Simplification plan

Status: agreed, 2026-11-04. Steps 1 to 4 are done on the branch `simple` (see "Progress"
at the end).

## Goal

A version of TriviaArcade you can understand, change and test yourself, without a coding
agent. The game plays exactly as it does now, but only with questions from the pool.
Making questions is a separate offline step, which runs when an LLM is available.

Guiding rules for the new code:

- Few files. A file is read from top to bottom and does one job.
- Plain functions and plain data. A class only where it really holds state.
- No layer "for later". An abstraction is added when a second user needs it, not before.
- A test breaks only when the behaviour really changed.
- Every file is named in `docs/how-it-works.md`.

The current version is kept on the branch `classic` (see "Steps").

## The two parts

```
 OFFLINE (your PC, when an LLM is available)          ONLINE (home server, always)

 Wikidata ──► importer ──► Neo4j ──► poolgen ──► pool/en.jsonl ──► game ──► browser
                          (Browser                 (in git)       (FastAPI +
                           on :7474)                               SQLite)
```

The only link between the two parts is the pool file in git. The server never needs Neo4j
or an LLM.

### Online: the game

One container: FastAPI serves the API and the built frontend. No Caddy, no PostgreSQL, no
Neo4j.

| File | Job | About |
|---|---|---|
| `game/main.py` | all HTTP routes, start of the app | 200 lines |
| `game/rules.py` | score, 1UPs, combo, time limit, checking choice answers | 100 |
| `game/runs.py` | start a run, next question, answer, skip, timeout | 400 |
| `game/scores.py` | after game over: claim, leaderboard, handles, question log | 140 |
| `game/pool.py` | read the pool file, pick a question | 100 |
| `game/matcher.py` | check a typed answer (carried over) | 190 |
| `game/db.py` | open SQLite, small helper functions for queries | 80 |
| `game/schema.sql` | the tables | 50 |
| `game/settings.py` | values from the environment | 30 |

In total about 1,000 lines instead of about 4,600 in `backend/app`.

**Database: SQLite.** One file, `data/game.db` (`DATABASE`), mounted into the container. A backup is a
copy of that file. Tables:

- `players`: id, handle
- `runs`: id, language, status, score, lives, combo, started, ended, player, claimed
- `questions`: id, run, pool question id, options in the shown order, the player's
  answer, correct or not, skipped, timed out, shown at

A question row no longer copies the question text, answers and explanation: they are read
from the pool file by the pool question id. That removes most columns of today's table.

SQL is written by hand in a few small functions (`sqlite3` from Python's standard
library), so every query can be read and tried in an SQLite tool. No SQLAlchemy, no
Alembic. When a table changes later, a numbered `.sql` file is added and applied on start
(a few lines in `db.py`).

**What the player keeps:** both languages, all four answer formats, the 30 second timer
(checked on the server), 1UPs and skip, explanations, game over with the correct answer,
handles, the top 10 leaderboard, the question log, sound, the arcade look, resuming after
a reload, phone layout. The answers still never reach the browser before the verdict.

**What goes away** (only needed for live LLM questions):

- live and hybrid mode, `QUESTION_SOURCE`
- the LLM judge, "judge unavailable, run paused", and its retry
- generator retries and the `llm_calls` table in the game database
- prefetching the next question (a pool question is ready at once)
- the random walk at play time and the "recent starts" rule (the pool picks by type and
  by what was asked longest ago)
- row locks (SQLite allows one writer at a time anyway)
- Caddy as a separate container

### Offline: making questions

Everything runs in Docker with the profile `offline`, so the game alone starts without it.

| File | Job |
|---|---|
| `offline/importer/` | Wikidata into Neo4j, as today (config in `config/import.yaml`) |
| `offline/walk.py` | random walk in Neo4j, gives a few connected facts, and those as text |
| `offline/llm.py` | one function: send a chat to Ollama, get JSON back, with one retry |
| `offline/prompts/` | writer, critic and solver prompts (carried over, they are tuned) |
| `offline/questions.py` | what a question is, and the code checks on the writer's reply |
| `offline/poolgen.py` | the pipeline: write → check → critic → blind solve → append to the pool |
| `offline/report.py` | summary and review of a pool |

- Neo4j stays, with its Browser on `127.0.0.1:7474`, only in the offline part.
- poolgen writes straight to `pool/<language>.jsonl` in the repository. When you are happy
  with the new questions: commit, deploy.
- The critic rounds are already stored in each pool record, so the offline part needs no
  database for logging.
- Ollama's address and key come from `.env`, so a local Ollama on your GPU machine works
  the same way as the cloud.
- The importer is the biggest piece (1,300 lines) and changes rarely. It is carried over
  with small clean-ups, not rewritten.

### One compose file

```bash
docker compose up -d                                   # the game
docker compose --profile offline up -d neo4j           # the graph, with its Browser
docker compose --profile offline run --rm importer     # rebuild the graph
docker compose --profile offline run --rm poolgen --language en --walks 100
```

One Python project (`pyproject.toml`) and one image for both parts; only the command
differs. The frontend is built in a first stage of the same Dockerfile.

## Frontend

React, TypeScript and Vite stay. The screens and the look stay. Changes:

- `QuestionScreen.tsx` (485 lines) loses prefetching and the "judge paused" state and is
  split into a few small components (question, answer input, verdict).
- `api/client.ts` loses the types of removed fields.
- ESLint uses the recommended rules instead of "strict type checked". Prettier stays.
- `docs/react-for-angular-devs.md`: one page mapping what you know from Angular to React
  (component, template → JSX, service → plain module, `ngOnInit` → `useEffect`).

## Tests

About 600 lines instead of 3,500.

- `test_matcher.py`: one table of answers and whether they count ("Berln" for Berlin: yes,
  "Iraq" for Iran: no). Adding a case is adding a line.
- `test_rules.py`: a table for 1UPs, combo and choice answers.
- `test_game.py`: 5 to 10 whole runs through the API with a tiny pool file and a temporary
  SQLite file: a correct answer, a wrong one saved by a 1UP, game over, skip, timeout,
  claiming, a language without questions.
- `test_poolgen.py`: the pipeline with canned LLM replies (a list of strings), no other
  fakes.

No test calls an LLM. `uv run pytest` runs all of them in a few seconds.

## Tools

- Python: `ruff` (finds mistakes, formats the code) and `pytest`. mypy is dropped: it
  needs many type annotations, and the tests catch what matters here. It can come back
  later.
- Frontend: TypeScript, ESLint (recommended rules), Prettier.
- CI: the same checks on every push, as today.

## Documentation

- `docs/how-it-works.md`: follows one question from the pool file to the screen and back,
  naming each file on the way. Then the same for making a question offline.
- `docs/how-to.md`: short recipes. Add a topic, change a rule (e.g. 1UPs), add a UI text,
  make more questions, deploy, back up the database.
- `docs/history.md`: what was tried and measured (today most of CLAUDE.md), so nothing is
  lost.
- `CLAUDE.md`: short, the rules for working on the project, including the rule to keep it
  simple.
- `README.md`: what the game is, how to start it.

## Steps

Each step ends in something that runs. Work happens on a branch `simple`; `main` keeps
the current version until the switch, so the running pool generation and deploys are not
disturbed.

1. **Keep the original.** Push the tag `v0.5.0`, create the branch `classic` from it,
   create the branch `simple`.
2. **Game backend.** `game/` with SQLite, the routes the frontend already calls, rules and
   matcher carried over, the tests above. Played locally against `pool/en.jsonl`.
3. **Frontend and container.** Remove the live-only states, split the question screen,
   one Dockerfile, the new compose file. `docker compose up` gives the whole game on
   `localhost:8080`.
4. **Offline part.** `offline/` with Neo4j, importer, walk, LLM, poolgen and report. A
   trial with a few walks shows it writes the same kind of records.
5. **Tools and CI.** Milder lint settings, CI for the new layout.
6. **Documentation.** The documents above.
7. **Switch, after 2026-11-09** (when the pool run on the server has ended):
   - take the last pool snapshot from the server and commit it
   - merge `simple` into `main`, deploy with a simpler `scripts/deploy.sh`
   - keep the old PostgreSQL and Neo4j volumes on the server for a while, remove them
     once everything works

Steps 2 to 6 are each a review point for you.

## Decisions (2026-11-04)

1. **Leaderboard and history:** start fresh. No data is carried over from PostgreSQL.
2. **Question log:** the generator's notes stay (read from the pool record).
3. **Folders:** `game/` and `offline/` at the top, replacing `backend/app/`,
   `backend/poolgen/` and `backend/importer/`.
4. **Branch:** the rebuild happens on `simple`, an exception to "commit directly to
   `main`" until the switch.

## Progress

### Step 1 (2026-11-04)

The tag `v0.5.0` points at the commit before this plan. `classic` was created from it
and pushed; `simple` was created from `main`.

### Step 2 (2026-11-04)

Built as planned, with these differences:

- **`game/scores.py`** is one more file: claiming a run, the leaderboard, the handle list
  and the question log. `runs.py` is then only about playing a run, and both stay
  readable top to bottom.
- **No "recent starts" rule at all.** Every start entity is walked once per pool, so two
  pool questions never share a start. A run never gets a question twice, and questions
  nobody has had come first.
- **Concurrency:** each changing request runs in `BEGIN IMMEDIATE`, which takes SQLite's
  write lock at once, so a double click cannot create two questions or judge twice.
- **Errors:** one `GameError` with a code; the table `ERRORS` in `runs.py` holds every
  code with its HTTP status and message (same codes as before, minus `judge_unavailable`).
- **The project file** `pyproject.toml` (and `uv.lock`) is at the top of the repository,
  tests are in `tests/`. The old `backend/` keeps its own until step 4 removes it.
- **Settings:** `DATABASE` (default `data/game.db`), `POOL_DIR` (default `pool`, the
  committed snapshots), `ANSWER_TIME_SECONDS`, `LIFE_COMBO`, `MAX_LIVES`, `START_LIVES`.
- **Clock in tests:** `runs.now()` is replaced by a fake clock, the only fake in the
  game tests.
- The backend does not serve the frontend yet; that comes with the Dockerfile in step 3.
- A question whose pool record disappears from the pool file is left out of the
  question log; during a run it gives `question_unavailable`.

### Step 3 (2026-11-04)

- **Question screen** split into `QuestionScreen.tsx` (loading, talking to the server,
  214 lines), `components/Hud.tsx` (number, 1UPs, score), `components/AnswerForm.tsx`
  (time bar, question, input or options, keyboard, ENTER and SKIP) and
  `components/Verdict.tsx` (explanation, marked options, NEXT QUESTION). Prefetching and
  the "judge paused" state are gone; when a request fails after the time is up, the
  error screen offers TRY AGAIN.
- **One `Dockerfile`** at the top: Node builds the frontend, the Python image runs
  uvicorn and serves the API and the built files (`FRONTEND_DIR`). It runs as the system
  user `app`, uid 999, the owner of `data/` on the server. `Caddyfile`,
  `compose.debug.yml` and `frontend/Dockerfile` are removed.
- **`docker-compose.yml`:** the service `game` on `${GAME_PORT:-8080}`, with `pool/`
  mounted read only (new questions are picked up without a restart, so the pool is not
  copied into the image) and `data/` mounted for `game.db`. Under the profile `offline`:
  `neo4j` (Browser on `127.0.0.1:7474`, same volume as before, so the graph is kept) and
  `importer` (still built from `backend/` until step 4). The old `poolgen` service is
  left out until step 4, because it needs PostgreSQL for its call log.
- **`.env.example`** lists only what the game and the offline part read.
- **For the switch (step 7):** `CADDY_PORT` is now `GAME_PORT`. If the server's `.env`
  sets `CADDY_PORT`, the owner renames it. The old containers (caddy, backend, postgres)
  show up as "orphans" of the project until they are removed.
- ESLint keeps the strict rules until step 5; the new code passes them.
- Played in the container on `localhost:8080`: order and single choice questions, the
  keyboard, a reload during a question (same question, clock kept running), a wrong
  answer saved by a 1UP, a timeout ending the run, claiming a handle, the leaderboard,
  the question log, and German without questions (message and BACK only).

### Step 4 (2026-11-04)

- **`offline/`** as planned, plus `offline/questions.py` (the question's JSON shape and
  the checks on the writer's reply: options, giveaways, "all of the above"), taken out
  of the old generator so `poolgen.py` stays readable. `poolgen.py` is 530 lines: the
  pool files and index, the three roles (writer, critic, solver), one walk from start to
  end, and the command line, in that order.
- **`llm.ask(chat, ..., check=...)`** is the one function. `chat` sends one request body
  and returns the reply text; in use it is `Ollama(...).chat`, in the tests a function
  returning canned replies. A retry after a reply that failed its check tells the model
  why (as the writer did before; the critic and the solver now get the note too).
- **Pool records** are plain dicts with exactly the old keys, so the existing
  `pool/en.jsonl` and new lines look the same; `python -m offline.report` reads the
  whole pool (839 walks, 792 accepted). Pydantic stays only where it checks data from
  outside: the writer's reply (`questions.Question`) and `config/import.yaml`.
- **No database:** the call log (`llm_calls`) is gone; the critic rounds are in each
  record.
- **The importer** moved unchanged except for its Neo4j settings (plain environment
  variables instead of pydantic-settings). **Its five test files moved with it**
  (680 lines): the importer is carried over, not rewritten, and those tests protect it.
  So the tests are about 1,500 lines instead of the planned 600.
- **`offline/walk.py` has no unit test**: it is mostly Neo4j queries; it was checked
  against the real graph (three walks, same facts text as in the pool records).
- **Commands** (on the host the values of `.env` are passed with `--env-file`):

  ```bash
  docker compose --profile offline run --rm importer --dry-run --names
  docker compose --profile offline run --rm poolgen --language en --walks 100
  uv run python -m offline.report --language en --summary
  uv run --env-file .env python -m offline.importer.explore Q11424
  ```

- **Removed with `backend/`:** the old app, Alembic, the judge and live generator,
  `scripts/sample_questions.py` (live questions), `scripts/reset_leaderboard.py`
  (becomes one SQL line in `docs/how-to.md`) and `scripts/evaluate_matcher.py` (it
  compared the matcher with judge verdicts, which no longer exist; its result is kept in
  CLAUDE.md for `docs/history.md`).
- **Not yet checked:** a trial with real LLM calls. Ollama runs only in the cloud here,
  and the account is shared with the pool run on the server until 2026-11-09.
- CI still points at `backend/` and fails until step 5.
