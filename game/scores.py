"""After game over: claiming a run under a handle, the leaderboard, the handles and the
question log.

The leaderboard shows each player once, with their best run: the highest score, and on
a tie the run that ended first. Players are ordered the same way.
"""

import json
import sqlite3

from game import pool, runs
from game.db import transaction
from game.rules import normalize_handle
from game.runs import GameError
from game.settings import Settings

LEADERBOARD_SIZE = 10
# The question log: questions per request, and the most it shows in total.
LOG_PAGE_SIZE = 10
LOG_SIZE = 50

# Each player's best claimed run, best players first. row_number() numbers the runs of
# each player (PARTITION BY) from best to worst; place 1 is the best one. The run id only
# decides between two runs that ended in the same instant. LIMIT -1 means no limit.
BEST_RUNS = """
WITH numbered AS (
    SELECT runs.id, players.handle, runs.score, runs.ended,
           row_number() OVER (
               PARTITION BY runs.player ORDER BY runs.score DESC, runs.ended, runs.id
           ) AS place
    FROM runs JOIN players ON players.id = runs.player
    WHERE runs.status = 'over'
)
SELECT id, handle, score, ended FROM numbered
WHERE place = 1
ORDER BY score DESC, ended, id
LIMIT ?
"""


def claim(db: sqlite3.Connection, run_id: str, raw_handle: str) -> dict:
    """Put a finished run on the leaderboard under a handle, once. A new handle creates
    the player. Returns the player's rank, which may be below the top 10."""
    handle = normalize_handle(raw_handle)
    if handle is None:
        raise GameError("invalid_handle")
    with transaction(db):
        run = runs.load_run(db, run_id)
        if run["status"] != "over":
            raise GameError("run_not_over")
        if run["claimed"] is not None:
            raise GameError("run_already_claimed")
        db.execute("INSERT INTO players (handle) VALUES (?) ON CONFLICT DO NOTHING", (handle,))
        player = db.execute("SELECT id FROM players WHERE handle = ?", (handle,)).fetchone()
        db.execute(
            "UPDATE runs SET player = ?, claimed = ? WHERE id = ?",
            (player["id"], runs.to_text(runs.now()), run_id),
        )
        ranked = db.execute(BEST_RUNS, (-1,)).fetchall()
    rank = next(place for place, row in enumerate(ranked, 1) if row["handle"] == handle)
    return {
        "handle": handle,
        "streak": run["score"],
        "rank": rank,
        # Whether this run is now the player's best, i.e. their leaderboard entry.
        "personal_best": ranked[rank - 1]["id"] == run_id,
    }


def leaderboard(db: sqlite3.Connection) -> list[dict]:
    rows = db.execute(BEST_RUNS, (LEADERBOARD_SIZE,)).fetchall()
    return [
        {
            "rank": place,
            "handle": row["handle"],
            "streak": row["score"],
            "finished_at": row["ended"],
        }
        for place, row in enumerate(rows, 1)
    ]


def handles(db: sqlite3.Connection) -> list[str]:
    """Existing handles for the handle picker, most recently used first."""
    rows = db.execute(
        "SELECT players.handle FROM players LEFT JOIN runs ON runs.player = players.id"
        " GROUP BY players.id ORDER BY max(runs.claimed) DESC, players.handle"
    )
    return [row["handle"] for row in rows]


def question_log(db: sqlite3.Connection, settings: Settings, offset: int) -> dict:
    """Questions of finished runs, newest run first and within a run the last question
    first. It says whether each answer was right, never what was answered or by whom."""
    limit = min(LOG_PAGE_SIZE, LOG_SIZE - offset)
    if limit <= 0:
        return {"questions": [], "has_more": False}
    # One more row than needed tells whether there is a next page.
    rows = db.execute(
        "SELECT questions.*, runs.ended, runs.language FROM questions"
        " JOIN runs ON runs.id = questions.run"
        " WHERE runs.status = 'over' AND questions.correct IS NOT NULL"
        " ORDER BY runs.ended DESC, runs.id, questions.number DESC"
        " LIMIT ? OFFSET ?",
        (limit + 1, offset),
    ).fetchall()
    logged = []
    for row in rows[:limit]:
        question = pool.find(settings.pool_dir, row["language"], row["pool_id"])
        if question is None:
            # Removed from the pool file since; nothing left to show.
            continue
        options = json.loads(row["options"])
        logged.append(
            {
                "id": row["id"],
                # Questions of one run share this and are shown as a group.
                "run_ended_at": row["ended"],
                "language": row["language"],
                "number": row["number"],
                "correct": bool(row["correct"]),
                "skipped": bool(row["skipped"]),
                "format": question.format,
                "question": question.text,
                "options": options,
                "correct_options": pool.correct_positions(question, options),
                "expected_answer": question.expected_answer,
                "accepted_answers": question.accepted_answers,
                "explanation": question.explanation or None,
                "notes": question.notes,
                "model": question.model,
                "prompt": question.prompt,
            }
        )
    has_more = len(rows) > limit and offset + limit < LOG_SIZE
    return {"questions": logged, "has_more": has_more}
