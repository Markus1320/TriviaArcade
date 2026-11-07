# History

What was tried, measured and decided while TriviaArcade grew from version 1 (live LLM
questions) to version 5 (the question pool). The simple version (from 0.6) keeps only
the pool, but these notes explain why the prompts, the walk and the matcher are the way
they are. Read them before changing a prompt, the walk or the matcher.

The sections below are copied from CLAUDE.md of v0.5.0, unchanged. They describe the
classic version: file names such as `app/llm/generator.py` or `GameService` refer to
the code on the branch `classic` (tag `v0.5.0`). Where things live now:

| Then (classic) | Now (simple) |
|---|---|
| `app/llm/generator_prompt.py`, `critic_prompt.py`, `solver_prompt.py` | `offline/prompts/writer.py`, `critic.py`, `solver.py` |
| `app/llm/generator.py` (checks on the output) | `offline/questions.py` |
| `app/graph/walk.py`, `app/llm/facts.py` | `offline/walk.py` |
| `poolgen/` | `offline/poolgen.py`, `offline/report.py` |
| `importer/` | `offline/importer/` |
| `app/game/rules.py`, `app/game/matcher.py` | `game/rules.py`, `game/matcher.py` |
| `app/pool/store.py`, `GameService` | `game/pool.py`, `game/runs.py` |
| the judge (an LLM checking typed answers) | gone; `game/matcher.py` checks them |

## Game Rules (Version One)

- Constant difficulty. No difficulty ramp.
- 30 seconds per question (`ANSWER_TIME_SECONDS`), enforced server side and counted from
  when the question is shown. When the time is up, whatever the player typed is judged;
  with nothing typed the run ends. A late answer ends the run like a wrong one.
- One wrong answer ends the run, unless the player has a 1UP: a run starts with one
  (`START_LIVES`), every 3 correct answers in a row (the combo, `LIFE_COMBO`) earn one more,
  at most 3 in stock (`MAX_LIVES`). A wrong or late answer, or running out
  of time, then costs a 1UP and resets the combo, and the run goes on with the correct
  answer shown. A 1UP can also be spent to skip a question (SKIP button); a skip adds
  nothing to the score and keeps the combo. Rules in `app/game/rules.py` (`LifeRules`,
  `apply_verdict`, `apply_skip`); the values come from the environment, and every question
  sends `life_combo` and `max_lives` to the browser so the hearts match. Started with 5
  for a 1UP and none at the start; changed to 3 and one at the start after playing.
- A question is answered by typing (`free`) or by picking from options: exactly one
  (`single`) or every one that applies (`multiple`: all correct options and no wrong one).
  Sorting questions (`order`) are answered by tapping all three or four items in the
  correct order; only the exact order counts. When the time is up, picked options are
  judged like a typed answer (an incomplete order is wrong).
- The game is played in English or German. A run keeps the language it was started in;
  both languages share one leaderboard.
- The score is the number of correct answers in the run (stored as `runs.streak`, the
  name from version one; the UI says SCORE / PUNKTE).
- Within a run, the same starting node is never used twice, and neither is the start of any
  of the last `RECENT_STARTS_BLOCKED` (300) questions of all runs.
- After every answer the player sees a short explanation (one or two sentences with the
  answer and a fact worth knowing), so there is something to learn whether the answer was
  right or wrong. After game over the correct answer is shown with it.
- If the judge fails technically (see below), the run is paused with an error message. A technical failure must never end a run.

## Knowledge Graph

### Source

Data comes from **Wikidata** (CC0). The importer queries the Wikidata SPARQL endpoint, caches raw responses in a gitignored `data/raw/` folder, and loads the processed result into Neo4j. Respect Wikidata's rate limits and send a descriptive User-Agent.

### Content and Balance

Balance is controlled at import time through `config/import.yaml`:

- **Fame filter:** each entity's Wikidata sitelinks count is its fame score. Only entities above `fame_threshold` are imported. Obscure entities must simply not exist in the graph. This is the only fame filter: the random walk uses every imported entity.
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
- Kinds of people cannot be selected by class, because every person is just "human" on Wikidata. A type can therefore set `select_by: P39` (position held: exact lists such as US presidents) or `select_by: P106` (occupation: loose, every occupation a person ever had counts). The first matching type wins, so positions come before occupations, and a per-type `exclude` list removes people whose listed occupation is not what they are known for (they stay available for later types). People not claimed by any type still enter as `person` when a relation reaches them.
- `include_subclasses: true` also accepts entities of subclasses (the planets are filed as "inner planet" etc.). It is slower and can pull in junk, so check the result with `--names`.
- `include` adds hand picked entities to a type that its selection misses (the horse is a subspecies on Wikidata, the potato only a plant species); they still need the type's fame threshold and an earlier type still wins.
- Plants and animals: queries over the taxon tree ("everything below Mammalia") time out on the public endpoint, so the nature types use handles that do work. `plant` is selected by fruit type (`select_by: P4000`, only plants carry it), `animal` by the class "organism known by a particular common name" (dog, cat, elephant), `species` by IUCN conservation status (`select_by: P141`), `animal_group` by taxon rank order or family (`select_by: P105`), `prehistoric_animal` by "fossil taxon". Food plants come first as `fruit_and_vegetable`. Many taxa have Latin English labels (Strigiformes); the aliases hold the common names. Everyday things (organs, diseases, instruments, food) are filed under newer "type of ..." classes on Wikidata.
- A relation can set `max_targets`: a subject with a longer list keeps none of it (the forty countries a wolf lives in make no question, kangaroo → Australia does). Used for the range and the food of animals.
- Birthplaces and places of death are not imported (they made boring, obscure questions).
- Small or obscure types are kept tight with a high `fame_threshold` and `max_entities`; since every type is an equal slice of the question starts, a type should only contain entities a casual player may know.
- Targets of some relations get their type from `fallback_target_type` (positions, awards, game platforms, sports); overly generic targets ("professor", "mobile phone") are in `exclude_entities`.
- Each import replaces the whole graph and writes an `ImportMeta` node with the import time and counts.
- Run it with `docker compose run --rm importer` (or `uv run python -m importer` on the host). `--dry-run` prints stats without touching Neo4j, `--names` also lists the entities of every type (use it to review a config change before importing), `--refresh` ignores the cache.
- `uv run python -m importer.explore QID...` previews candidate types before they go into `config/import.yaml`: entity counts per fame threshold, the most famous names and the properties those entities carry. `--by P106` or `--by P39` selects people by occupation or position held instead of "instance of", `--subclasses` includes subclasses. It only reads from Wikidata (cached like the importer).

### Question Seeds (Random Walk)

1. Pick a random eligible starting node (not used earlier in the current run).
2. Walk 1 to 3 random hops along allowed relations.
3. Return the resulting small subgraph of facts.

All randomness comes from code. The graph access lives behind a clear interface in `app/graph/`.

Current implementation (`app/graph/walk.py`): the start is chosen by picking an entity type uniformly, then a random entity of that type. Every type is one equal slice of the question starts, however many entities it has; within a type every entity is equally likely. There are no weights per type: how the types are cut in `config/import.yaml` decides the mix. Every imported entity can take part, for the start and for every step. The import thresholds in `config/import.yaml` are the only fame filter (an earlier second filter, `WALK_TOP_SHARE`, was removed); to make a type less obscure, raise its threshold and re-import. The walk takes `WALK_MIN_HOPS` to `WALK_MAX_HOPS` hops (default 1 to 2), the natural base for a later difficulty ramp.

The walker does not label how famous an entity is; the generator judges that itself. (Labels relative to the type, "world famous" / "well known" / "known to fans", were removed: on the same 30 walks they changed little, questions without them were slightly easier, and they did not cause or prevent repetition.) Starts without neighbors are skipped. Each hop goes to a neighbor (either direction) not visited yet, picked with weight 1 / degree ^ `WALK_HUB_PENALTY` (default 0.5); every neighboring entity counts once, however many relations lead to it. Without the penalty, walks drifted to a few hubs (the United States was in 9% of 2,000 simulated walks, 20 entities in 28%) and the generator then asked about the hub; with 0.5 it is 4% and 18%, and 30 sample questions named a top hub 12 instead of 16 times. A penalty of 1 gained little more and favoured odd leaf entities. A dead end ends the walk early. `RandomWalker` takes a `random.Random`, so walks are reproducible with a seed.

## LLM Integration

### Abstraction

- `app/llm/` defines an `LLMClient` protocol and an Ollama implementation.
- Generator and judge use separately configured models.
- Prompts live as Python modules: `app/llm/generator_prompt.py` and `app/llm/judge_prompt.py`.
  Each holds the system prompt, a `string.Template` user template and a `PROMPT` object.
  Do not reintroduce separate prompt template files.
- Both calls send an Ollama structured output schema (the question object for the generator, `{"type": "boolean"}` for the judge), but the Ollama cloud API does not reliably enforce it: `gemma4:31b-cloud` wrapped its JSON in Markdown code fences. Therefore the generator prompt spells out the exact JSON shape with examples and asks for no code fences, and the generator parser also tolerates a code fence or text around the JSON object (the raw output is logged unchanged). The judge stays strict: only `true` or `false` is accepted.
- The generator also retries once on invalid output (bad JSON, schema mismatch) and then raises `QuestionGenerationError`. The judge raises `JudgeUnavailableError` after its retry; the game must pause the run on it.

### Call One: Generate Question

- Input: the subgraph facts from the random walk.
- The LLM has creative freedom in how it builds the question, including questions that connect several hops.
- Target audience in the prompt: a casual quiz player born in the 1990s or later, with school knowledge and the pop culture of roughly the last thirty years; older things only when still widely known. (It said "experienced quiz player" before; on 40 sample walks the casual wording made questions easier, mostly through more true or false: 8 to 14 of 40, free 19 to 14, some of them trivial. The true or false hint is in every request and may prime that type.) The request itself asks for an easy question for a casual player (see the format mix below for why). One clear answer. No obscure numbers. Only the facts needed to point to the answer are used, no side details. The prompt contains good examples and real too-hard examples for calibration.
- The generator chooses one of four answer formats. The prompt lists them in order of
  difficulty (free, multiple, order, single) and tells the model to choose by two factors
  that weigh the same: difficulty (the less famous the fact, the further down the list)
  and fun (a surprising true or false claim, a close comparison or a sorting is often more
  entertaining than one more typed answer). Easy points are not fun: claims anyone sees
  through, comparisons with an obvious winner and options with only one plausible answer
  stay free or ask something else.
  - `free`: the player types. For answers a casual player can recall. Question types:
    direct, record or rank ("the first country to...", "the second largest..."), open
    ("Name a country that borders Germany"), name several, rough time (century), analogy
    and completion.
  - `multiple`: "select all that apply" (or "that do not apply"), four to six options, at
    least two correct and one wrong. The second choice, when the answer is too hard to
    recall.
  - `single`: options with exactly one correct. The last choice, for the hardest facts and
    everything that offers alternatives: true or false, comparisons (the two things are
    the options), "which of these" with three or four options, odd one out.
  - `order`: the only format for sorting questions ("oldest first").
    Three or four items as options; `correct_options` lists every option in the correct
    order. The code checks that, and shuffles until the shown order is not already sorted.
  Comparisons of size or location pair two entities of the same kind, neither part of the
  other, with a clear but not absurdly obvious answer. Comparisons in time may cross
  domains ("Which was released first: the Disney film Cinderella or the programming
  language Java?").
- The facts are the inspiration and the starting point; the model may add its own
  knowledge (context, famous records, the second option of a comparison, wrong options) as
  long as it is certainly true.
- `FREE_EXAMPLES` and `CHOICE_EXAMPLES` hold hand written examples, the same number in each
  group (a test checks it). A request normally gets one of each, in random order, in the
  user message (`pick_examples` builds the whole example block, per language). They
  inspire format and style only; the prompt says the topic must come from
  the facts. `format_example` renders them as JSON; a test checks that every example is
  valid generator output with an explanation. Long lines are fine there (E501 is ignored
  for `generator_prompt.py`).
- Language: the system prompt, the examples and the facts are always English. The user
  message exists per language (`localized_user_templates` in the prompt, German in
  `USER_TEMPLATE_DE`) and asks for the language explicitly; the system prompt explains
  the mismatch and asks for the names usual in that language, with the English name as an
  accepted answer. Whether German names need to come from the graph instead is decided on
  real questions.
- The facts carry no fame labels; the prompt tells the model to judge itself how well
  known each entity is and to build the question around entities a casual player knows.
  Sorting questions need three or four items; with two they are just "pick one" and
  belong in a comparison.
- Sorting share: with sorting as its own format, one sorting example among the choice
  examples and no push, a batch of 40 had no sorting question, and only 1 of 120
  candidate drafts was a sorting question (with two items). A hint per request was
  offered and declined for now.
- Fun as a format factor, measured on the same 40 walks (seed 41): with the formats only
  in order of difficulty 38 to 40 were free. Fun as an equal factor gave 15 free, 1
  multiple, 24 single, with 12 true or false questions, many trivially false ("Handel was
  a French composer"). Adding "easy points are not fun" (current) gave 19 free, 1
  multiple, 20 single, with better comparisons ("Snow White or Java?") but still some
  options that make a famous fact easy. Adding entertainment as a general content rule
  (audience, topic, review) changed nothing measurable and was dropped.
- Repetition: the start entity is blocked within a run and for the last 300 questions of
  all runs (`GameService._recent_starts`); hops avoid hubs (see the random walk). Different walks reach the
  same entities, and the model then tends to ask the same famous fact (twice "Earth is to
  the Moon as Neptune is to ...?" in one batch of 30). Passing the run's earlier topics to
  the generator would be the direct fix; not built yet.
- Code checks on the output (`generator.py`), each counting as invalid output with a retry:
  a free question must not contain its expected or an accepted answer (word for word,
  answers under three characters are not checked); a single choice question must not name
  only its correct option; no option may combine or exclude the others ("All of the
  above", "Both A and B"); option counts and correct options must fit the format. The
  retry request names the reason for the rejection (`RETRY_NOTE`).
- Format mix, measured on batches of 40 real questions:
  - The request wording decides it. "One easy trivia question for a casual quiz player"
    gives about two thirds free input and options for the harder answers. "Experienced
    quiz player" flipped it to two thirds single choice with more failures, so the request
    stays "easy" and "casual" although the audience section speaks of an experienced
    player.
  - Left alone, the model almost never writes multiple choice, sorting, analogies or
    completions, whatever the prompt says about them.
  - An example alone is not a lever: with a single example and "follow it if it fits" the
    model followed the type in 6 of 34 questions. Naming the type in the request works
    (about 30 of 33), but forced sorting, analogy, comparison and odd one out questions
    were weak.
  - Suggesting multiple choice in 15% of the requests was tried and removed again: the
    share was right, but too many of the forced questions were weak. No type is suggested
    now; every request shows one free and one choice example.
  - With the formats listed in order of priority (free, multiple, single), a batch of 40
    gave 35 free, 2 multiple and 3 single. Two of the three single questions still had
    giveaway options from other continents or fields, despite the prompt rule.
- The options are shuffled by code, because models tend to put the correct one first.
  True/False (and Yes/No, Wahr/Falsch) keep their order.
- Left alone, the model writes mostly true claims for true or false questions. So the code
  decides per request whether a true or false claim must be false (`FALSE_CLAIM_SHARE`,
  default 0.7) or true, and adds that hint to the user message.
- Notes before the question: the reply starts with four note fields, written in this order
  (`NOTE_FIELDS` in `generator.py`):
  - `topic`: which widely known entity and which fact to ask about.
  - `candidates`: three draft questions about that topic, each of a different type and
    none of them a plain direct question or a completion (a completion is a direct
    question in other words).
  - `choice`: the best candidate, or "none" when all are weak, forced or unfair; then the
    model writes a plain direct question or a completion instead. The prompt calls "none"
    a normal outcome for about half of the questions.
  - `review`: a strict check of the chosen question, ending in "Keep." or in what changes.
  They give the model room to work things out inside the one JSON object. They are logged
  with the call (`llm_calls.parsed`), never stored with the question or shown to the
  player, and optional when parsing.
- How the note fields were found, each measured on the same 30 walks (1 to 4 hops, about
  1.3 to 1.6 seconds per question in every variant):
  - No notes: 1 broken question, 3 rule breaks or giveaways.
  - One free `reasoning` field: those were gone, but more trivial questions.
  - `topic`, `format_choice`, `draft`, `review`: 4 drafts corrected by the review, 21 free
    and 9 single, mostly direct questions with some comparisons and true or false.
  - Candidates with a direct question allowed: the model picked the direct one 24 times.
  - Candidates that must not be direct: 19 completions, mostly direct questions reworded.
  - Candidates that are neither direct nor completions, with "none" allowed (current):
    12 plain questions, 7 open, 4 analogies, 2 comparisons, 2 multiple choice, 1 other
    single. Three open questions had only one answer, so the prompt now requires at least
    three correct answers for an open question.
  - The same without `topic`: the candidates spread over weak corners of the facts, the
    model fell back to a plain question 21 times and picked the most famous entity
    ("What is the capital city of Russia?"). The topic step stays.
  - The model's own thinking (`ChatRequest.think`, sent to Ollama as `think`) gave the
    best questions but took about 8 seconds each, so the generator does not use it.
- Output is enforced as JSON via Ollama's structured output and validated with Pydantic:

```json
{
  "format": "free",
  "question": "string",
  "expected_answer": "string",
  "accepted_answers": ["string"],
  "explanation": "string"
}
```

```json
{
  "format": "single",
  "question": "string",
  "options": ["string"],
  "correct_options": ["string"],
  "explanation": "string"
}
```

Both shapes start with the four note fields (`topic`, `candidates`, `choice`, `review`),
left out here. For choice questions `expected_answer` is derived: the correct options, joined.

`explanation` is what the player reads after answering: one or two short sentences that state the answer and add a fact worth knowing ("False: Ankara is the capital of Turkey. Istanbul is its largest city."). It is optional when parsing: a question without one is still used, and nothing is shown. It is only sent to the browser together with a verdict, because it names the answer.

The expected answer, accepted answers, options, correct options and explanation are stored server side with the run.

### Call Two: Judge Answer

- Only for free questions; choice questions are checked by code (`choice_correct` in
  `rules.py`) and never reach the judge.
- Independent from call one. Input: question, expected answer, accepted answers, player answer.
- Output: exactly `true` or `false`, nothing else.
- Leniency policy (part of the judge prompt):
  - Typos are accepted.
  - Answers in any language are accepted if correct.
  - Surnames alone are accepted for well known people (e.g. "Napoleon").
  - Vague answers are rejected (e.g. "in Europe" for a country).
  - Years must be exact unless the question asks for a decade or century.
  - "Name three" questions need at least that many distinct, correct items.
  - If a question allows several correct answers, any answer that is certainly correct for the question as asked is accepted, even if not listed. Ambiguous questions are therefore acceptable.
- **Prompt injection defense:** the player answer is wrapped in clear delimiters and the prompt states that it is untrusted data, never instructions.
- **Strict parsing:** any output other than `true` or `false` triggers one retry. If the retry fails too, the run is paused with an error, not ended.
- Limit player answer length (e.g. 200 characters) before it reaches the LLM.

### Logging

Every generator and judge call is logged in PostgreSQL (inputs, raw output, parsed result, model, latency), so questionable verdicts and question quality can be reviewed later.

The table is `llm_calls` (one row per attempt, so retries are visible). A failure to write the log is reported but never breaks the game. Each row has an optional `run_id`, so all calls of a run can be reviewed together.

## Question Pool (Version 5)

The Ollama cloud free plan ends on 2026-11-09 and paid LLM use is not an option, so
questions are written ahead of time into a pool. Without the latency limit of live play,
the pool pipeline can use thinking and a review loop. `QUESTION_SOURCE` chooses where the
game takes its questions (see "Serving pool questions" below): `live`, `hybrid` (unasked
pool questions first, then live) or `pool` (pool only, typed answers judged by code).

Pipeline (`backend/poolgen/`, one walk at a time):

1. The writer is the game's generator (`QuestionGenerator` with `think=True`). Its request
   also lists the pool's questions about the walk's entities ("do not ask these again").
2. Code check: the same typed answer may be in the pool at most `--answer-cap` (2) times;
   otherwise the draft goes back to the writer with a note.
3. The critic (`app/llm/critic.py`, `critic_prompt.py`, `LLM_CRITIC_MODEL`, thinking
   "high") answers approve, revise (with feedback, back to the writer) or reject. At most
   `--max-rounds` (3) drafts.
4. The blind solver (`app/llm/solver.py`, `solver_prompt.py`, the critic model) answers
   the question without its answer. For free questions it lists English and German forms
   whatever the language of the pool, since German players type German names in English
   runs (the first 100 English questions had English forms only; their free questions
   were deleted). Choice questions must get exactly the correct options;
   free questions must have the expected or an accepted answer among the solver's
   answers. The solver lists every form a typed answer may take; the pool keeps them (and
   the graph aliases of the answer entity) for judging without an LLM.

- gpt-oss thinks only briefly with `think: true`; `ChatRequest.think` also takes "low",
  "medium" or "high". With "high" the critic and solver take about 2 seconds a call.
- Every start entity is walked once per pool. Rejected walks are recorded too, so their
  starts are not retried; technical failures (`technical: true`) leave the start free.
- Files: `<dir>/<language>.jsonl` (accepted) and `<dir>/<language>.rejected.jsonl`, one
  JSON object per line, appended at once so a run can stop any time. The generator writes
  to `data/pool/` (gitignored; on the server owned by the container user like the rest of
  `data/`; the whole `data/` is mounted, because a missing bind mount folder is created
  by Docker as root and the container cannot write to it). Snapshots are copied off the
  server with `scp` into the repository's `pool/` and committed (never committed on the
  server); the game itself only reads `data/pool/`.
- One pool per language, chosen with `--language`; no translation.
- HTTP 429 from Ollama (`LLMRateLimitError`) drops the walk in progress and waits
  `--wait-hours` (5); so do five technical failures in a row.
- Run: `docker compose run --rm poolgen python -m poolgen --language en --walks N
  [--dir /data/pool/<name>] [--seed S]`, review with `python -m poolgen.report --language en
  [--dir ...] [--summary]`. Calls are logged to `llm_calls` with the purposes `critic` and
  `solve`.
- The long run on the server is a detached container with a fixed name, restarted by
  removing it (`docker rm -f poolgen-en`) and starting it again; the new run continues
  where the pool stands: `docker compose run -d --name poolgen-en poolgen python -m poolgen
  --language en --walks 4000`. Follow it with `docker logs -f poolgen-en`.
- Long run (started 2026-11-02, after both trials): first snapshot on 2026-11-04 with 792
  accepted of 839 walks (94%), 3.7 calls and 33 seconds per accepted question, formats
  single 520, free 192, multiple 48, order 32; 156 accepted after a revision. The Ollama
  monthly limit stopped it for about a day in between.
- First trial (30 walks, seed 41, before critic tuning): 28 accepted, 3.7 calls and 28
  seconds per accepted question, formats free 6, single 19, multiple 1, order 2. The
  critic fixed real problems (Malta has two official languages, a trivial true or false)
  but let giveaway options pass (Biryani among Sushi, Paella, Risotto) and a disputed
  fact (Elbrus as Europe's highest mountain with Mont Blanc as an option).
- Second trial (same walks) after adding a giveaway test with those real examples, a
  point on facts that depend on a definition, and a light format point (recallable
  answers are better typed; suggest a more interesting type only when the facts clearly
  offer one): 29 accepted, 8 after a revision, formats free 8, single 17, multiple 3,
  order 1, with four analogies. The critic now catches obvious outliers (Biryani became
  a choice among Indian dishes, Titan became Rhea) but still approved the Elbrus question.

### Serving pool questions

- `app/pool/store.py` reads `<POOL_DIR>/<language>.jsonl` (the backend mounts `data/`
  read only, `POOL_DIR=/data/pool`) and reads it again when the file changes, since
  poolgen may still be appending; a half written last line is skipped. The record model is
  `app/pool/records.py`, shared with poolgen.
- `questions.pool_question_id` (migration 0010) links a question to its pool record. A
  pool question counts as asked once any run had it, prefetched or not.
- `GameService._new_question`: in `hybrid` and `pool`, a pool question in the run's
  language that no run has had, picked like a walk start (entity type uniformly, then a
  question of that type), not from a start entity used in this run or in the last
  `RECENT_STARTS_BLOCKED` questions. Then, in `hybrid`, a live question; if that fails, and
  always in `pool`, one of the 50 pool questions asked longest ago (never one of this
  run; the recent starts are given up when nothing else is left).
- Pool questions are stored with `accepted_answers` = the writer's accepted answers plus
  the blind solver's answers (never the graph aliases) and their options shuffled anew.
- In `pool` mode there is no generator and the judge is `MatcherJudge`, so no LLM settings
  are needed. A language without pool questions gets 503 `no_questions_in_language`; the
  question screen then shows the message with only a BACK button (no TRY AGAIN). Only an
  English pool exists so far.

### Answer Matcher (pool only mode)

`app/game/matcher.py` judges typed answers by code (`AnswerKey.of(question, *answer
lists)`, `match_answer`); `MatcherJudge` puts it behind the judge interface.

- Normalization: case, accents, punctuation, spacing, leading articles and a leading "in"
  / "in the" / "im" do not matter. "19th century" may be answered "19" (and "19.
  Jahrhundert").
- Typos: up to six letters a changed letter is never accepted (Rhine and Rhone, Iran and
  Iraq, AS and AC Roma), only one missing or extra letter (five or more letters) or two
  swapped neighbours; 7 to 8 letters one edit, 9 or more two (Slovakia and Slovenia are
  two apart). Digits must match exactly.
- "Name three ..." (also German "Nenne drei") needs that many distinct matching items,
  split at commas, "and", "und", "&", "/".
- Measured with `scripts/evaluate_matcher.py` against 741 real judge verdicts of live
  questions (exported to the gitignored `data/judge-eval.jsonl`; it holds player answers),
  using only the generator's answer lists: 94.6% agreement, no answer the judge rejected
  is accepted. Of the 40 answers the judge accepted and the matcher did not, about 13 are
  German names in English runs (Themse, Florenz), 13 open questions with incomplete lists
  (Israel for "borders Syria"), 8 short forms (Fischer, Russia for Russian Empire) and 6
  bad typos.
- Graph aliases are not used for matching: Wikidata aliases include wrong friends (Zeus
  has "Jupiter" and "Jove", rabies "extreme salivation").

## Players and Leaderboard

- Handles: 3 to 8 characters, uppercase letters and digits only (`^[A-Z0-9]{3,8}$`). Normalize input to uppercase.
- After game over the player picks an existing handle or creates a new one.
- No passwords or accounts in version one. Anyone can post under any handle. This is accepted for a home network setup.
- A run can be claimed exactly once, and only after it has ended.
- The leaderboard shows the top 10 players, each with their best run (highest streak; on a tie, the earlier finish). Players are ordered by that streak, ties broken by the earlier finish time. Every run can still be claimed; a run below the player's best is stored but does not change the leaderboard.

## Game Loop (Current Implementation)

- PostgreSQL tables: `players` (unique handle), `runs` (UUID, status `active` or `over`, streak, start and end time, claiming player), `questions` (one row per question with the walk facts, the `format`, expected and accepted answers, for choice questions `options` in the shown order with `correct_options` and `selected_options` as positions in it, the explanation, the generator model, prompt and notes for the question log, `asked_at` (generated), `shown_at` (clock started), player answer, verdict and `timed_out`). `llm_calls.run_id` links calls to runs.
- `app/game/rules.py` and `app/leaderboard/{handles,ranking}.py` hold the rules as pure functions; `app/game/service.py` and `app/leaderboard/service.py` apply them in transactions.
- Every run changing request locks the run row (`SELECT ... FOR NO KEY UPDATE`, so call log inserts referencing the run are not blocked). Parallel requests cannot create two questions or judge twice.
- Asking for the next question while one is open returns the open question, so reloading cannot skip a question. The browser keeps only the run ID (in `sessionStorage`) and resumes after a reload.
- 1UPs: `runs.lives` and `runs.combo`; `questions.skipped` marks a question skipped with
  a 1UP (stored with `correct = false`). `POST /runs/{id}/skip` spends a 1UP (409
  `no_life_left` without one); a skip after the deadline counts as running out of time.
  Verdicts carry `lives`, `combo`, `life_earned`, `saved` (a 1UP took the hit) and
  `skipped`, and the correct answer whenever the answer was not correct. A technical judge
  failure never costs a 1UP.
- A judge failure (`JudgeUnavailableError`) writes no verdict and returns 503 `judge_unavailable`; the question stays open and gets a fresh time limit. A generation failure returns 503 `question_unavailable`; the run continues.
- Only claimed runs count for the leaderboard, one entry per player (`best_per_player` in `ranking.py`, a `row_number()` window query in `service.py`). Claiming returns the player's rank (may be below 10) and `personal_best`, whether this run became the player's entry.
- After a correct answer the frontend immediately requests the next question in the background (prefetch), so NEXT QUESTION usually shows it without waiting. The server keeps it as the open question, so reloads stay safe.
- Time limit: generating (or prefetching) a question does not start the clock. When the browser shows a question it calls `POST /runs/{id}/question/start`, which sets `shown_at` once; calling it again (after a reload) returns the seconds left without restarting the clock. `POST /answer` checks the deadline when the answer arrives, before judging, with `ANSWER_GRACE_SECONDS` (3) for the auto-submit's network delay (`rules.py`); a late answer is stored with `timed_out` and the judge is not called. When the countdown ends with nothing typed, the browser calls `POST /runs/{id}/timeout`, which ends the run (it only ever ends the caller's own run, so no deadline check).
- `runs.language` holds the language of the run, set by `POST /runs` (`{"language": "de"}`,
  default `en`) and passed to the generator for every question.
- `POST /answer` takes `{"answer": "..."}` for free questions and `{"selected": [positions]}`
  for choice questions; the wrong kind for the open question is a 422 and the question
  stays open. For order questions `selected` is the tapped order and `correct_options` the
  correct order (`order_correct` in `rules.py`). Choice verdicts carry `correct_options`;
  once the run is over, `GET /runs/{id}` returns `last_format`, `last_options`,
  `last_correct_options` and `last_selected_options` so the game over screen survives a
  reload.
- Every verdict (`POST /answer`, `POST /timeout`) carries the question's `explanation`; `GET /runs/{id}` returns `last_explanation` once the run is over. The frontend shows it in the question box after a correct answer and under the answer on the game over screen.
- `python -m scripts.reset_leaderboard --yes` (inside the backend container) empties the leaderboard: runs are detached from their players but kept with their questions, handles stay (`--remove-handles` deletes them too; done when 1UPs were introduced). A claim checks `claimed_at`, so detached runs cannot be claimed again. Use it when rules or the question pool change so much that old scores are not comparable.
- Question log: `GET /api/question-log?offset=N` lists the questions of finished runs,
  newest run first and within a run the last question first, 10 per request and at most
  the last 50 (`app/questionlog/service.py`). It shows whether each answer was right and
  every field of the question: format, options, answers, explanation, the generator's
  notes, the model and the user message sent to the generator (`questions.generator_model`,
  `prompt`, `notes`; the system prompt is the same for all and left out). Never the
  player's answer, the handle or the run ID. Runs are grouped by their end time. Questions
  from before the log (no `prompt`) are left out. The title screen links to it.
- Domain errors map to HTTP responses in `app/api/errors.py` as `{"code", "detail"}`; the frontend shows `detail`.

## Frontend and Styling

- Classic arcade look: black background, neon colors, the "Press Start 2P" pixel font (bundled locally, not loaded from Google), subtle CRT scanline overlay.
- Screens: title with blinking PRESS START, question screen with score, 1UPs and combo, game over, handle entry, leaderboard, question log.
- All assets are original. Do not use characters, sprites, logos or sounds from real arcade games.
- Sound effects for correct, wrong and game over are generated with the Web Audio API (no audio files). Sound is **muted by default** with a visible toggle.
- UI languages are English and German, switched with a button next to the sound toggle.
  All UI texts live in `src/strings.ts`, once per language. Arcade phrases (PRESS START,
  GAME OVER, HIGH SCORES, ENTER) and the name of the game are the same in both.
- The layout must work on phones, since the game is played across the home network.

Current implementation:

- The font comes from the npm package `@fontsource/press-start-2p` (OFL, Latin and Latin Extended subsets imported in `main.tsx`); Vite bundles the woff2 files.
- `src/styles/global.css` holds the design tokens (colours on `:root`), the scanline and vignette overlay (`body::before` / `body::after`, `pointer-events: none`) and all screen styles. `prefers-reduced-motion` disables blinking, flicker and other animations. Inputs use at least 16px font size so phones do not zoom. The answer input is never focused automatically, because the phone keyboard would cover the question.
- Sounds: `src/audio/sfx.ts` synthesizes start, correct, wrong, game over and the countdown tick with oscillators; `SoundProvider` keeps the on/off state (default off, remembered in `localStorage`) and only creates the `AudioContext` after the player turns sound on. `useSound()` lives in `audio/soundState.ts`.
- `components/SoundToggle.tsx` and `components/LanguageToggle.tsx` sit in the fixed
  `.toggles` bar at the bottom of every screen (one per corner on phones, both left on
  wider screens).
- Language: `LanguageProvider` keeps the choice (remembered in `localStorage`; without one a
  German browser starts in German) and components read texts with `useStrings()`. Errors
  are kept as thrown and turned into text when rendered (`errors.ts`), so they follow the
  language; German translates the backend's error codes, English shows its `detail`.
- `components/OptionList.tsx` shows the options of a choice question: buttons while asking
  (digits pick, arrow keys move, Enter confirms; the keyboard handling is in
  `QuestionScreen.tsx`), and after the verdict a list marked right, missing (a correct option not picked, red like a wrong pick) or wrong, on the
  question screen and on the game over screen. For order questions a tap gives the next
  place (shown as a badge; tapping a numbered item takes it back and the later ones move
  up), ENTER needs every item, and the reveal lists the items in the correct order with
  "YOU: n" where the player put one elsewhere.
- The answer input ignores paste and drop, and the open question text cannot be selected.
  This only slows down looking answers up; the time limit is the real defence.
- `components/LifeMeter.tsx` shows the 1UPs as hearts in the HUD between question number and score; the next empty heart fills from the bottom with the combo (a CSS gradient on the glyph, `--fill`). The numbers (`life_combo`, `max_lives`) come with each question. After a correct answer that completes the combo "1UP!" flashes with its own sound (`oneUp` in `sfx.ts`); a saved or skipped question shows the answer and the explanation in a yellow box with SAVED BY 1UP / SKIPPED, then NEXT QUESTION.
- `components/TimeBar.tsx` is the shrinking time bar (red in the last 5 seconds, which also tick); `useCountdown.ts` drives it from the server's `seconds_left`. The width is set from JavaScript, not a CSS transition, because `prefers-reduced-motion` turns transitions off.
