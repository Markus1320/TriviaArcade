# How to

Short recipes. Commands run from the repository root unless they say `cd frontend`. For
how the parts fit together, see [how-it-works.md](how-it-works.md).

## Play locally

```bash
docker compose up -d --build
```

Open <http://localhost:8080>. From a phone on the same Wi-Fi: `http://<your PC's IP>:8080`
(`ipconfig` shows it; allow the port in the Windows firewall if it does not load). Stop it
with `docker compose down`.

## Work on the code without Docker

Two terminals:

```bash
uv run uvicorn game.main:create_app --factory --reload --port 8080
```

```bash
cd frontend
npm install
npm run dev
```

Open the address Vite prints (<http://localhost:5173>). It passes `/api` on to port
8080, and both reload when you save a file.

## Check everything before a commit

The same checks as CI:

```bash
uv run ruff check .
uv run ruff format .
uv run pytest
```

```bash
cd frontend
npm run lint
npm run format
npm run build
```

`ruff format` and `npm run format` fix the formatting themselves; the others report
problems.

## Change a rule

- **Numbers** (seconds per question, 1UPs): set them in `.env` and restart with
  `docker compose up -d`.

  | Setting | Default | Meaning |
  |---|---|---|
  | `ANSWER_TIME_SECONDS` | 30 | seconds per question, 0 = no timer |
  | `LIFE_COMBO` | 3 | correct answers in a row for a 1UP |
  | `MAX_LIVES` | 3 | the most 1UPs a player can hold |
  | `START_LIVES` | 1 | 1UPs a new run starts with |

- **How a rule works**: change the function in [game/rules.py](../game/rules.py) and add
  a line for the new case to the table in [tests/test_rules.py](../tests/test_rules.py).
  The same for typed answers: [game/matcher.py](../game/matcher.py) and
  [tests/test_matcher.py](../tests/test_matcher.py).

Old scores are then hard to compare; consider resetting the leaderboard (below).

## Add or change a UI text

All texts are in [frontend/src/strings.ts](../frontend/src/strings.ts), once in English
(`en`) and once in German (`de`). Add the key to both; TypeScript reports a key missing in
one of them. Use it in a component with `const strings = useStrings();` and
`{strings.yourKey}`.

## Add a topic

1. Find the Wikidata class: open the Wikidata page of a typical example and read its
   "instance of". Look at what Wikidata has for it:

   ```bash
   uv run python -m offline.importer.explore Q11424
   ```

2. Add an entity type to [config/import.yaml](../config/import.yaml) (copy a similar one;
   the comments there explain every field). Keep the fame threshold high enough that a
   casual player knows the entities.
3. Check the result without touching Neo4j:

   ```bash
   docker compose --profile offline up -d neo4j
   docker compose --profile offline run --rm importer --dry-run --names
   ```

4. Import, then make questions from the new type only:

   ```bash
   docker compose --profile offline run --rm importer
   docker compose --profile offline run --rm poolgen --language en --walks 20 --types your_type
   ```

## Make more questions

Needs an LLM: `OLLAMA_BASE_URL`, `OLLAMA_API_KEY` (empty for a local Ollama),
`LLM_GENERATOR_MODEL` and `LLM_CRITIC_MODEL` in `.env`. For an Ollama on this PC use
`OLLAMA_BASE_URL=http://host.docker.internal:11434`.

```bash
docker compose --profile offline up -d neo4j
docker compose --profile offline run --rm poolgen --language en --walks 100
uv run python -m offline.report --language en --last 100
```

New questions are appended to `pool/en.jsonl`; walks that gave no question go to
`pool/en.rejected.jsonl`. Stop any time with Ctrl+C: the next run continues where the
pool stands. A running game picks up new questions without a restart. Read the report,
then commit both files and deploy.

`--language de` makes a German pool (`pool/de.jsonl`); until it exists, the game says
there are no German questions.

## Look into the database

`data/game.db` is a normal SQLite file. Open it with any SQLite tool (for example "DB
Browser for SQLite"), or from the command line:

```bash
uv run python -c "import sqlite3; db = sqlite3.connect('data/game.db'); print(db.execute('SELECT handle FROM players').fetchall())"
```

The tables are described in [game/schema.sql](../game/schema.sql).

## Back up the database

On the server, while the game runs (SQLite's backup copies a consistent state). Replace
`<server>` and `<dir>` with your `DEPLOY_SERVER` and `DEPLOY_DIR`:

```bash
ssh <server> "cd <dir> && docker compose exec -T game python -c \"import sqlite3; sqlite3.connect('/data/game.db').backup(sqlite3.connect('/data/backup.db'))\""
scp <server>:<dir>/data/backup.db game-backup.db
```

To restore: stop the game (`docker compose stop game`), replace `data/game.db` with the
backup, start it again.

## Reset the leaderboard

Runs are kept but no longer belong to anybody, so everybody starts from zero. They cannot
be claimed again. Handles stay available.

```bash
docker compose exec -T game python -c "import sqlite3; db = sqlite3.connect('/data/game.db'); db.execute('UPDATE runs SET player = NULL'); db.commit()"
```

Add `db.execute('DELETE FROM players');` before `db.commit()` to remove the handles too.

## Change a table

Add the change as a numbered SQL file and apply it once on start, remembering the number
in SQLite's `PRAGMA user_version` (see the note in `create_tables()` in
[game/db.py](../game/db.py)). Adjust [game/schema.sql](../game/schema.sql) as well, so a
new database gets the table right away. Never edit an existing table by hand on the
server.

## Add a dependency

- Python: `uv add <package>` (or `uv add --dev <package>` for tools). Never plain `pip`.
- Frontend: `cd frontend` and `npm install <package>`.

Commit `uv.lock` or `package-lock.json` with it.

## Deploy

```bash
bash scripts/deploy.sh
```

It deploys to `DEPLOY_SERVER` (the ssh login) into `DEPLOY_DIR` (the checkout there),
both set in your `.env`. The server needs Docker, a clone of this repository and ssh
access with a key. It pushes `main`, waits for CI to be green, pulls and rebuilds the game on the home
server and checks `/api/health`. The server needs neither Neo4j nor an LLM: new questions
arrive with the pool file in git. Never deploy while CI is red. The server's `.env` and
`data/` are managed there; never change them by hand.

On the server the deploy also removes containers that are not part of the game: those of
services no longer in `docker-compose.yml`, and those of the `offline` profile. Their
volumes are kept.
