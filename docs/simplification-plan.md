# Simplification plan

Status: agreed, 2026-11-04. Nothing here is built yet.

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
| `game/runs.py` | start a run, next question, answer, skip, timeout, claim | 250 |
| `game/pool.py` | read the pool file, pick a question | 100 |
| `game/matcher.py` | check a typed answer (carried over) | 190 |
| `game/db.py` | open SQLite, small helper functions for queries | 80 |
| `game/schema.sql` | the tables | 50 |
| `game/settings.py` | values from the environment | 30 |

In total about 1,000 lines instead of about 4,600 in `backend/app`.

**Database: SQLite.** One file, `data/game.db`, mounted into the container. A backup is a
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
| `offline/walk.py` | random walk in Neo4j, gives a few connected facts |
| `offline/llm.py` | one function: send a chat to Ollama, get JSON back, with one retry |
| `offline/prompts/` | writer, critic and solver prompts (carried over, they are tuned) |
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
