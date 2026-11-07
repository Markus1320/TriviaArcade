-- The game's tables. Applied on every start; IF NOT EXISTS leaves existing tables alone.
-- Times are UTC text like 2026-11-04T18:30:00.000000+00:00, so sorting the text sorts by
-- time. True and false are stored as 1 and 0.

CREATE TABLE IF NOT EXISTS players (
    id INTEGER PRIMARY KEY,
    handle TEXT NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS runs (
    id TEXT PRIMARY KEY,                     -- a random UUID, the browser keeps it
    language TEXT NOT NULL,                  -- 'en' or 'de', the language of its questions
    status TEXT NOT NULL,                    -- 'active' or 'over'
    score INTEGER NOT NULL DEFAULT 0,        -- correct answers
    lives INTEGER NOT NULL,                  -- 1UPs in stock
    combo INTEGER NOT NULL DEFAULT 0,        -- correct answers in a row towards a 1UP
    started TEXT NOT NULL,
    ended TEXT,
    player INTEGER REFERENCES players (id),  -- set when the run is claimed
    claimed TEXT                             -- when it was claimed; a run is claimed once
);

-- One row per question asked in a run. The question itself (text, answers, explanation)
-- stays in the pool file and is found by pool_id.
CREATE TABLE IF NOT EXISTS questions (
    id INTEGER PRIMARY KEY,
    run TEXT NOT NULL REFERENCES runs (id),
    number INTEGER NOT NULL,                 -- 1 for the first question of the run
    pool_id TEXT NOT NULL,
    options TEXT NOT NULL,                   -- JSON list in the order shown; [] if typed
    asked TEXT NOT NULL,
    shown TEXT,                              -- the clock starts here
    answered TEXT,
    answer TEXT,                             -- what was typed, or the picked options
    selected TEXT,                           -- JSON list of picked positions
    correct INTEGER,                         -- NULL while the question is open
    skipped INTEGER NOT NULL DEFAULT 0,
    timed_out INTEGER NOT NULL DEFAULT 0,
    UNIQUE (run, number)
);

CREATE INDEX IF NOT EXISTS questions_pool_id ON questions (pool_id);
