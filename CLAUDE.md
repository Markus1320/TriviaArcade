# CLAUDE.md

Rules for working on TriviaArcade. Read this first, then
[docs/how-it-works.md](docs/how-it-works.md) for how the parts fit together.

## The project

An open source trivia game in the style of classic arcade cabinets, played in the browser
on the home network. Questions come from a pool written ahead of time (`pool/`); typed
answers are checked by code. A run ends at the first wrong answer unless a 1UP saves it.

Two parts, linked only by the pool file:

- **`game/`** (online, home server): FastAPI + SQLite in one container, serving the API
  and the built `frontend/` (React, TypeScript, Vite).
- **`offline/`** (your PC): importer (Wikidata → Neo4j), walk, LLM, poolgen (writes
  `pool/<language>.jsonl`), report. Only runs when an LLM is available. The Ollama cloud
  free plan ends on 2026-11-09; after that a local Ollama is the way to make questions.

## Keep it simple

The owner maintains this code without a coding agent. That decides most choices:

- Few files. A file is read from top to bottom and does one job.
- Plain functions and plain data. A class only where it really holds state.
- No layer "for later". An abstraction is added when a second user needs it.
- Plain SQL in a few functions; no ORM, no migration framework.
- Prefer obvious code over clever code. Explain a new concept in a short comment.
- A test breaks only when behaviour changes. Rule and matcher tests are tables: a new
  case is a new line.
- Every file is named in `docs/how-it-works.md`. Update it when files come or go.

Why the prompts, the walk and the matcher are the way they are (with measurements) is in
[docs/history.md](docs/history.md). Read it before changing one of them.

## Commands

```bash
docker compose up -d --build                                   # the game on :8080
docker compose --profile offline up -d neo4j                   # the graph (Browser :7474)
docker compose --profile offline run --rm importer             # rebuild the graph
docker compose --profile offline run --rm poolgen --language en --walks 100
uv run python -m offline.report --language en --summary
```

Checks (the same as CI):

```bash
uv run ruff check . && uv run ruff format --check . && uv run pytest
cd frontend && npm run lint && npm run format:check && npm run build
```

More recipes: [docs/how-to.md](docs/how-to.md).

- Python 3.12 through uv only: `uv run ...`, `uv add ...`. Never plain `pip`.
- The game alone needs no settings; the offline part reads Neo4j and Ollama values from
  `.env` (compose passes them; on the host use `uv run --env-file .env ...`).
- Check which model tags the Ollama account (or local Ollama) really has before setting
  `LLM_GENERATOR_MODEL` or `LLM_CRITIC_MODEL`. Do not guess tags.

## Rules that must hold

- **The answer never reaches the browser before the verdict.** A question view has no
  answer, accepted answers, correct options or explanation.
- **All game state is on the server.** The browser keeps only the run ID.
- **The time limit is checked on the server** (`answer_in_time` in `game/rules.py`).
- **No test calls an LLM or Neo4j.** poolgen is tested with canned replies.
- **Ports:** only the game is published on all interfaces (`GAME_PORT`, default 8080).
  Neo4j is bound to `127.0.0.1` only, never to all interfaces.
- **Secrets** live in `.env` (gitignored). `.env.example` lists every variable with
  placeholders. Never commit, print or hardcode keys.
- **Data:** `pool/` is committed. `data/` (the database `game.db`, the Wikidata cache) and
  player data are never committed.
- **Frontend:** all assets original (no characters, sprites, logos or sounds from real
  games); sound muted by default; every text in `src/strings.ts` in English and German;
  the layout works on phones; the answer input is never focused automatically (the phone
  keyboard would hide the question).

## Git

- Commit to `main`. Until the switch to this version (step 7 of
  [docs/simplification-plan.md](docs/simplification-plan.md)), work happens on the branch
  `simple` instead and `main` stays the classic version.
- Small, focused commits with the prefixes `feat:`, `fix:`, `docs:`, `refactor:`,
  `test:`, `chore:`, only when the checks pass.
- Never force push, never rewrite history. Tag playable milestones (`v0.6.0`).
- The classic version (live LLM questions, PostgreSQL, Neo4j at play time) is kept on
  the branch `classic` and the tag `v0.5.0`.

## Deployment

The game runs on a Debian laptop, `ssh markus@arcade.local`, checkout at
`/home/markus/TriviaArcade`, tracking `origin/main`. "Deploy" always means
`bash scripts/deploy.sh`: push `main`, wait for green CI (**never deploy while CI is
red**), pull and rebuild on the server, check `/api/health`.

On the server:

- Never read, copy, print or change the server's `.env` (no `cat .env`, no
  `docker compose config`, which prints resolved values).
- `data/` belongs to uid 999 (the container user). Never change its ownership or
  permissions.
- No manual edits in the server checkout; changes go through GitHub and a deploy.

## Definition of done

1. The checks above pass.
2. `docker compose up` still starts the game cleanly.
3. New settings are in `.env.example` (or `config/import.yaml`).
4. `docs/how-it-works.md`, `docs/how-to.md`, README and this file are updated when files,
   commands or rules changed.
5. The work is committed as above.

## When unsure

If a requirement is unclear or two rules conflict, stop and ask instead of guessing.
Propose options with a recommendation.
