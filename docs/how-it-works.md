# How it works

TriviaArcade has two parts. They share one thing: the pool file.

```
 OFFLINE (your PC, when an LLM is available)          ONLINE (home server, always)

 Wikidata ──► importer ──► Neo4j ──► poolgen ──► pool/en.jsonl ──► game ──► browser
                          (Browser                 (in git)       (FastAPI +
                           on :7474)                               SQLite)
```

- **Online, the game:** one container. FastAPI serves the API under `/api` and the built
  frontend. Players, runs and answers are kept in SQLite (`data/game.db`). Questions are
  read from `pool/<language>.jsonl`. No LLM and no Neo4j are needed.
- **Offline, making questions:** the importer builds a knowledge graph from Wikidata in
  Neo4j. poolgen walks through it and lets an LLM write, review and test questions, which
  it appends to the pool file. You commit the new questions and deploy.

This page follows one question through the game, then shows how a question is made.
Every file of the project is named somewhere on this page.

## 1. The game starts

`docker compose up -d --build` reads [docker-compose.yml](../docker-compose.yml) and
builds the image from the [Dockerfile](../Dockerfile):

1. A Node stage runs `npm run build` in `frontend/` and keeps only the result, `dist/`.
2. A Python stage installs the dependencies listed in [pyproject.toml](../pyproject.toml)
   (exact versions in `uv.lock`, Python version in `.python-version`) and copies
   `game/`, `offline/` and the built frontend. `.dockerignore` keeps the rest out.

The container starts `uvicorn game.main:create_app --factory`.
[game/main.py](../game/main.py) `create_app()` reads the settings with
[game/settings.py](../game/settings.py) (environment variables with defaults), creates the
tables with [game/db.py](../game/db.py) and [game/schema.sql](../game/schema.sql) if they
do not exist yet, and registers the routes. Compose mounts `pool/` (read only) and
`data/` into the container.

## 2. The browser loads the page

The browser gets `frontend/index.html` (built into `dist/`) and the script it loads,
which starts at [frontend/src/main.tsx](../frontend/src/main.tsx):

- It loads the pixel font and [styles/global.css](../frontend/src/styles/global.css)
  (colours, scanlines, every screen's layout).
- It wraps the app in [LanguageProvider.tsx](../frontend/src/language/LanguageProvider.tsx)
  (English or German, remembered in the browser) and
  [SoundProvider.tsx](../frontend/src/audio/SoundProvider.tsx) (sound on or off, off by
  default). Components read them with `useStrings()` from
  [languageState.ts](../frontend/src/language/languageState.ts) and `useSound()` from
  [soundState.ts](../frontend/src/audio/soundState.ts).
- It shows the two buttons in the corners,
  [LanguageToggle.tsx](../frontend/src/components/LanguageToggle.tsx) and
  [SoundToggle.tsx](../frontend/src/components/SoundToggle.tsx).
- It renders [App.tsx](../frontend/src/App.tsx), which decides which screen is shown.

Every text on screen comes from [strings.ts](../frontend/src/strings.ts), once per
language. The tab icon is `frontend/public/favicon.svg`.

## 3. PRESS START

[TitleScreen.tsx](../frontend/src/screens/TitleScreen.tsx) calls `api.startRun()` in
[api/client.ts](../frontend/src/api/client.ts), the only file that talks to the server.
It sends `POST /api/runs` with the language.

On the server, the route `start_run` in `main.py` calls `start_run()` in
[game/runs.py](../game/runs.py). It inserts a row into the table `runs` (score 0, one
1UP) and returns a new random run ID. The browser keeps only this ID, in
[runStorage.ts](../frontend/src/runStorage.ts), so a reload can continue the run.
`App.tsx` switches to the question screen.

## 4. A question is picked

[QuestionScreen.tsx](../frontend/src/screens/QuestionScreen.tsx) asks for a question with
`POST /api/runs/{id}/question`. `next_question()` in `runs.py`:

1. Returns the open question if there is one, so reloading cannot skip a question.
2. Otherwise reads the pool with `load()` in [game/pool.py](../game/pool.py). It reads
   `pool/en.jsonl` once and again only when the file changes.
3. `pick()` chooses a question no run has had yet: first an entity type, every type
   equally likely, then a question of that type. When every question has been asked, it
   takes one of those asked longest ago, never one this run already had.
4. `shuffled_options()` puts the options in a new order (True/False stays as it is).
5. A row goes into the table `questions`: the run, the pool question's ID and the
   options in the order shown. The question text and its answers stay in the pool file.
6. `question_view()` sends the question to the browser: text, format, options, score,
   1UPs, the time limit. **Never the answer.**

Then the browser calls `POST /api/runs/{id}/question/start`. That stores `shown`, and
the 30 seconds count from then.

## 5. The player answers

[AnswerForm.tsx](../frontend/src/components/AnswerForm.tsx) shows the question:

- [Hud.tsx](../frontend/src/components/Hud.tsx) at the top: question number, 1UPs as
  hearts ([LifeMeter.tsx](../frontend/src/components/LifeMeter.tsx)) and score.
- [TimeBar.tsx](../frontend/src/components/TimeBar.tsx), driven by
  [useCountdown.ts](../frontend/src/useCountdown.ts).
- An input for typed answers, or the options as buttons in
  [OptionList.tsx](../frontend/src/components/OptionList.tsx).

ENTER sends `POST /api/runs/{id}/answer` with `{"answer": "..."}` or
`{"selected": [0, 2]}`. SKIP sends `/skip`; a countdown that runs out with nothing typed
sends `/timeout`.

`answer()` in `runs.py` checks the answer:

- Too late (more than 30 + 3 seconds after `shown`, see `answer_in_time()` in
  [game/rules.py](../game/rules.py)): wrong.
- A typed answer: `match_answer()` in [game/matcher.py](../game/matcher.py) compares it
  with the expected answer and every accepted form from the pool record. Case, accents
  and small typos do not matter.
- Picked options: `choice_correct()` or `order_correct()` in `rules.py`.

`finish()` stores the verdict in the question row and applies `apply_verdict()` from
`rules.py`: a correct answer adds to the score and the combo (3 in a row earn a 1UP); a
wrong one costs a 1UP or ends the run. The browser now gets the verdict, the correct
answer and the explanation.

## 6. The verdict

`QuestionScreen.tsx` plays a sound from [audio/sfx.ts](../frontend/src/audio/sfx.ts)
(made with the Web Audio API, no sound files) and shows
[Verdict.tsx](../frontend/src/components/Verdict.tsx): the explanation, the options
marked right, missed or wrong, and NEXT QUESTION, which starts again at step 4.

Errors come back as `{"code": "...", "detail": "..."}`. The codes are the table `ERRORS`
in `runs.py`. [errors.ts](../frontend/src/errors.ts) turns them into text: German from
`strings.ts`, English from the server's `detail`.

## 7. Game over and the leaderboard

When the run ends, `App.tsx` shows
[GameOverScreen.tsx](../frontend/src/screens/GameOverScreen.tsx) with the correct answer.
SAVE SCORE leads to [HandleScreen.tsx](../frontend/src/screens/HandleScreen.tsx), which
sends `POST /api/runs/{id}/claim` with a handle. `claim()` in
[game/scores.py](../game/scores.py) checks the handle (`normalize_handle()` in
`rules.py`), creates the player if needed, attaches the run, and computes the rank with
the SQL query `BEST_RUNS` (each player's best run, highest score first).

[LeaderboardScreen.tsx](../frontend/src/screens/LeaderboardScreen.tsx) shows
`GET /api/leaderboard`, the top 10. On the title screen, QUESTION LOG opens
[QuestionLogScreen.tsx](../frontend/src/screens/QuestionLogScreen.tsx), which shows
`GET /api/question-log`: `question_log()` in `scores.py`, the questions of finished
runs, with everything from the pool record, but never what a player answered.

**After a reload**, `App.tsx` reads the run ID from `runStorage.ts` and asks
`GET /api/runs/{id}` (`get_run()` in `runs.py`): an open question continues where it
was, with the clock still running; a finished run shows its game over screen again.

## The database

[game/schema.sql](../game/schema.sql) is the whole database, in three tables:

| Table | One row per | Holds |
|---|---|---|
| `players` | handle | the handle |
| `runs` | game | language, active or over, score, 1UPs, combo, times, the player once claimed |
| `questions` | question asked in a game | the pool question's ID, the options as shown, the answer, right or wrong, skipped, timed out, times |

All queries are plain SQL in `runs.py` and `scores.py`. Every request that changes a run
runs inside `transaction()` from `db.py`, so a double click is handled one after the
other.

## How a question is made (offline)

### The knowledge graph

[config/import.yaml](../config/import.yaml) says what goes into the graph: entity types
(countries, rivers, films, painters, ...) with fame thresholds, the relations between
them, and numbers and years. `docker compose --profile offline run --rm importer` runs
[offline/importer/](../offline/importer/):

| File | Job |
|---|---|
| `__main__.py` | the command: read the config, build the graph, load it into Neo4j (`__init__.py` only marks the folder as a package) |
| `settings.py` | where the config and the cache are, and the Neo4j login from the environment |
| `config.py` | the typed model of `config/import.yaml` (checked with Pydantic) |
| `queries.py` | the SPARQL queries sent to Wikidata |
| `sparql.py` | sends them, slowly enough for Wikidata, and caches every answer in `data/raw/` |
| `parsing.py` | turns Wikidata's values into plain Python values |
| `build.py` | seeds, then relations, labels and facts: the whole graph in memory |
| `model.py` | that graph: nodes and relations |
| `loader.py` | replaces the graph in Neo4j |
| `explore.py` | a separate command to look at new entity types on Wikidata first |

Neo4j runs with `docker compose --profile offline up -d neo4j`; its Browser is on
<http://localhost:7474>.

### From a walk to a pool line

`docker compose --profile offline run --rm poolgen --language en --walks 100` runs
`main()` in [offline/poolgen.py](../offline/poolgen.py). For every walk:

1. `random_walk()` in [offline/walk.py](../offline/walk.py) picks a start entity (an
   entity type first, then an entity, skipping starts the pool already has) and walks one
   or two hops through Neo4j. `facts_text()` writes those facts as text.
2. `write()` sends the facts to the writer model with the prompt in
   [offline/prompts/writer.py](../offline/prompts/writer.py), plus the pool's questions
   about the same entities. `check_question()` in
   [offline/questions.py](../offline/questions.py) checks the reply (options, no answer
   in the question, ...). A broken reply is sent back once with the reason.
3. The same typed answer may be in the pool at most twice.
4. `review()` asks the critic model ([offline/prompts/critic.py](../offline/prompts/critic.py)):
   approve, revise (back to 2 with its feedback) or reject. At most three drafts.
5. `solve()` asks the blind solver ([offline/prompts/solver.py](../offline/prompts/solver.py))
   to answer the question without its answer. It must find the right one. For typed
   answers its list of forms is kept, so the game's matcher knows them.
6. `make_question()` returns the record, and `append_record()` writes it as one line to
   `pool/en.jsonl`, or to `pool/en.rejected.jsonl` with the reason.

Every call to the model goes through `ask()` in [offline/llm.py](../offline/llm.py),
which sends the chat to Ollama, reads the JSON reply and tries once more if it is not
usable.

[offline/report.py](../offline/report.py) prints numbers and every question of a pool, to
review new questions before committing them.

## Everything else

| File | Job |
|---|---|
| `tests/test_rules.py`, `tests/test_matcher.py` | tables of cases for the rules and the matcher |
| `tests/test_game.py` | whole runs through the API, with a tiny pool and a temporary database |
| `tests/test_poolgen.py` | poolgen with canned LLM replies, and the checks on the writer's reply |
| `tests/test_importer_*.py` | the importer: building, config, explore, parsing, SPARQL client |
| `.github/workflows/ci.yml` | runs ruff, pytest, ESLint, Prettier, the frontend build and the image build on every push |
| `scripts/deploy.sh` | deploys `main` to the home server (see [how-to.md](how-to.md)) |
| `.env.example` | every setting, with placeholders; copy it to `.env` |
| `.env`, `CLAUDE.local.md` | yours, never committed: settings and secrets; notes for Claude Code about your own machines |
| `frontend/package.json`, `package-lock.json` | frontend dependencies and the `npm run` commands |
| `frontend/vite.config.ts` | the dev server, which passes `/api` on to the game on port 8080 |
| `frontend/tsconfig*.json` | TypeScript settings (strict) |
| `frontend/eslint.config.js`, `.prettierrc.json`, `.prettierignore` | lint and format rules |
| `.gitattributes`, `.gitignore` | line endings (LF), and what git ignores (`.env`, `data/`, ...) |
| `pool/` | the question pools, committed |
| `data/` | not committed: `game.db`, the Wikidata cache `raw/` |
| `docs/` | this page, [how-to.md](how-to.md), [history.md](history.md), [react-for-angular-devs.md](react-for-angular-devs.md), [simplification-plan.md](simplification-plan.md) |
| `README.md`, `CLAUDE.md` | what the game is and how to start it; the rules for working on the code |
| `LICENSE`, `THIRD_PARTY_NOTICES.md` | MIT; Wikidata (CC0) and the pixel font (OFL) |
