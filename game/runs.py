"""Playing a run: start, next question, start the clock, answer, skip, time out.

All game state lives in the database. The browser only gets the run ID, the question and
the verdicts; the correct answer leaves the server only together with a verdict.

Each function that changes a run works inside one transaction (see db.transaction), so a
double click cannot create two questions or judge one answer twice.

The functions return plain dicts, which the routes in main.py send to the browser as JSON.
"""

import json
import random
import sqlite3
from datetime import UTC, datetime
from uuid import uuid4

from game import pool
from game.db import transaction
from game.matcher import match_answer
from game.pool import PoolQuestion
from game.rules import (
    Progress,
    answer_in_time,
    apply_skip,
    apply_verdict,
    choice_correct,
    clean_answer,
    order_correct,
    seconds_left,
)
from game.settings import Settings

# Every error the player can see: code -> (HTTP status, message). The frontend shows the
# message, or its own German text for the code.
ERRORS = {
    "run_not_found": (404, "This run does not exist."),
    "run_over": (409, "This run is already over."),
    "no_open_question": (409, "There is no question to answer."),
    "invalid_answer": (422, "Please give an answer."),
    "no_life_left": (409, "You have no 1UP to skip with."),
    "question_unavailable": (503, "There is no question left for this run."),
    "no_questions_in_language": (
        503,
        "There are no questions in this language yet. Please play in another language.",
    ),
    "run_not_over": (409, "Only finished runs can be added to the leaderboard."),
    "run_already_claimed": (409, "This run is already on the leaderboard."),
    "invalid_handle": (422, "A handle has 3 to 8 characters: letters A-Z and digits 0-9."),
}


class GameError(Exception):
    """A request the game refuses, with one of the codes in ERRORS."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code
        self.status, self.detail = ERRORS[code]


# Picks questions and shuffles options.
rng = random.Random()


def now() -> datetime:
    """The current time. Tests replace this function to move the clock."""
    return datetime.now(UTC)


def to_text(moment: datetime) -> str:
    """A time as stored in the database, see schema.sql."""
    return moment.isoformat(timespec="microseconds")


def start_run(db: sqlite3.Connection, settings: Settings, language: str) -> str:
    """Start a run; its questions are in the given language until it ends."""
    run_id = str(uuid4())
    with transaction(db):
        db.execute(
            "INSERT INTO runs (id, language, status, lives, started) VALUES (?, ?, 'active', ?, ?)",
            (run_id, language, settings.start_lives, to_text(now())),
        )
    return run_id


def get_run(db: sqlite3.Connection, settings: Settings, run_id: str) -> dict:
    """The state of a run, so the browser can continue after a reload. Once the run is
    over it includes the last question's answer, for the game over screen."""
    run = load_run(db, run_id)
    state = {
        "run_id": run_id,
        "over": run["status"] == "over",
        "streak": run["score"],
        "lives": run["lives"],
        "combo": run["combo"],
        "open_question": None,
        "last_expected_answer": None,
        "last_explanation": None,
        "last_format": None,
        "last_options": None,
        "last_correct_options": None,
        "last_selected_options": None,
        "claimed_by": None,
    }
    if run["status"] == "active":
        row = open_question(db, run_id)
        if row is not None:
            state["open_question"] = question_view(settings, run, row)
        return state

    last = db.execute(
        "SELECT * FROM questions WHERE run = ? ORDER BY number DESC LIMIT 1", (run_id,)
    ).fetchone()
    if last is not None:
        question = pool_question(settings, run, last)
        state["last_expected_answer"] = question.expected_answer
        state["last_explanation"] = question.explanation or None
        if question.format != "free":
            options = json.loads(last["options"])
            state["last_format"] = question.format
            state["last_options"] = options
            state["last_correct_options"] = pool.correct_positions(question, options)
            state["last_selected_options"] = json.loads(last["selected"] or "[]")
    player = db.execute("SELECT handle FROM players WHERE id = ?", (run["player"],)).fetchone()
    if player is not None:
        state["claimed_by"] = player["handle"]
    return state


def next_question(db: sqlite3.Connection, settings: Settings, run_id: str) -> dict:
    """The open question, or a new one. Asking again before answering gives the same
    question, so reloading the page cannot skip a question."""
    with transaction(db):
        run = load_run(db, run_id)
        if run["status"] == "over":
            raise GameError("run_over")
        row = open_question(db, run_id)
        if row is None:
            row = ask_new_question(db, settings, run)
        return question_view(settings, run, row)


def ask_new_question(db: sqlite3.Connection, settings: Settings, run: sqlite3.Row) -> sqlite3.Row:
    questions = pool.load(settings.pool_dir, run["language"])
    if not questions:
        raise GameError("no_questions_in_language")
    last_asked = {
        row["pool_id"]: row["last"]
        for row in db.execute("SELECT pool_id, max(id) AS last FROM questions GROUP BY pool_id")
    }
    in_this_run = {
        row["pool_id"]
        for row in db.execute("SELECT pool_id FROM questions WHERE run = ?", (run["id"],))
    }
    question = pool.pick(questions, last_asked, in_this_run, rng)
    if question is None:
        raise GameError("question_unavailable")
    number = len(in_this_run) + 1
    options = pool.shuffled_options(question, rng)
    cursor = db.execute(
        "INSERT INTO questions (run, number, pool_id, options, asked) VALUES (?, ?, ?, ?, ?)",
        (run["id"], number, question.id, json.dumps(options), to_text(now())),
    )
    return db.execute("SELECT * FROM questions WHERE id = ?", (cursor.lastrowid,)).fetchone()


def start_question(db: sqlite3.Connection, settings: Settings, run_id: str) -> dict:
    """Start the clock when the browser shows the question. Calling it again (after a
    reload) keeps the clock running instead of starting it again."""
    with transaction(db):
        run = load_run(db, run_id)
        row = open_question_or_error(db, run)
        if row["shown"] is None:
            db.execute("UPDATE questions SET shown = ? WHERE id = ?", (to_text(now()), row["id"]))
            row = db.execute("SELECT * FROM questions WHERE id = ?", (row["id"],)).fetchone()
        return question_view(settings, run, row)


def answer(
    db: sqlite3.Connection,
    settings: Settings,
    run_id: str,
    typed: str | None,
    selected: list[int] | None,
) -> dict:
    """Judge a typed answer (free questions) or the picked options (choice questions)."""
    with transaction(db):
        run = load_run(db, run_id)
        row = open_question_or_error(db, run)
        question = pool_question(settings, run, row)
        options = json.loads(row["options"])
        if question.format == "free":
            picked = None
            text = clean_answer(typed or "")
            if not text:
                raise GameError("invalid_answer")
        else:
            picked = valid_selection(question.format, options, selected)
            text = ", ".join(options[position] for position in picked)

        received = now()
        if not in_time(settings, row, received):
            correct, timed_out = False, True
        elif question.format == "free":
            answers = [question.expected_answer, *question.accepted_answers]
            correct, timed_out = match_answer(question.text, answers, text), False
        elif question.format == "order":
            correct = order_correct(picked or [], pool.correct_positions(question, options))
            timed_out = False
        else:
            correct = choice_correct(picked or [], pool.correct_positions(question, options))
            timed_out = False
        return finish(db, settings, run, row, question, text, picked, correct, timed_out)


def skip(db: sqlite3.Connection, settings: Settings, run_id: str) -> dict:
    """Skip the open question with a 1UP. The score and the combo stay as they are. A skip
    after the time limit counts as running out of time."""
    with transaction(db):
        run = load_run(db, run_id)
        row = open_question_or_error(db, run)
        if run["lives"] <= 0:
            raise GameError("no_life_left")
        question = pool_question(settings, run, row)
        received = now()
        if not in_time(settings, row, received):
            return finish(db, settings, run, row, question, None, None, False, True)
        progress = apply_skip(progress_of(run))
        db.execute(
            "UPDATE questions SET shown = coalesce(shown, ?), answered = ?, correct = 0,"
            " skipped = 1 WHERE id = ?",
            (to_text(received), to_text(received), row["id"]),
        )
        db.execute("UPDATE runs SET lives = ? WHERE id = ?", (progress.lives, run_id))
        return verdict(question, row, progress, correct=False, timed_out=False, skipped=True)


def time_out(db: sqlite3.Connection, settings: Settings, run_id: str) -> dict:
    """The browser's countdown ran out with nothing typed or picked: like a wrong answer.
    It only ever ends the caller's own run, so the deadline is not checked here."""
    with transaction(db):
        run = load_run(db, run_id)
        row = open_question_or_error(db, run)
        question = pool_question(settings, run, row)
        return finish(db, settings, run, row, question, None, None, False, True)


def finish(
    db: sqlite3.Connection,
    settings: Settings,
    run: sqlite3.Row,
    row: sqlite3.Row,
    question: PoolQuestion,
    text: str | None,
    picked: list[int] | None,
    correct: bool,
    timed_out: bool,
) -> dict:
    """Store the verdict of the open question and apply the rules to the run."""
    before = progress_of(run)
    after = apply_verdict(before, correct, settings)
    moment = to_text(now())
    db.execute(
        "UPDATE questions SET shown = coalesce(shown, ?), answered = ?, answer = ?,"
        " selected = ?, correct = ?, timed_out = ? WHERE id = ?",
        (
            moment,
            moment,
            text,
            None if picked is None else json.dumps(picked),
            correct,
            timed_out,
            row["id"],
        ),
    )
    db.execute(
        "UPDATE runs SET score = ?, lives = ?, combo = ?, status = ?, ended = ? WHERE id = ?",
        (
            after.score,
            after.lives,
            after.combo,
            "over" if after.over else "active",
            moment if after.over else None,
            run["id"],
        ),
    )
    earned = correct and after.lives > before.lives
    return verdict(question, row, after, correct, timed_out, life_earned=earned)


def verdict(
    question: PoolQuestion,
    row: sqlite3.Row,
    progress: Progress,
    correct: bool,
    timed_out: bool,
    life_earned: bool = False,
    skipped: bool = False,
) -> dict:
    """What the browser shows after an answer, a skip or a timeout."""
    options = json.loads(row["options"])
    return {
        "correct": correct,
        "streak": progress.score,
        "game_over": progress.over,
        "timed_out": timed_out,
        "lives": progress.lives,
        "combo": progress.combo,
        # A correct answer completed the combo and earned a 1UP.
        "life_earned": life_earned,
        # A wrong or late answer cost a 1UP instead of ending the run.
        "saved": not correct and not progress.over and not skipped,
        "skipped": skipped,
        "expected_answer": None if correct else question.expected_answer,
        "explanation": question.explanation or None,
        "correct_options": None
        if question.format == "free"
        else pool.correct_positions(question, options),
    }


def question_view(settings: Settings, run: sqlite3.Row, row: sqlite3.Row) -> dict:
    """The open question as the browser sees it: without any answer."""
    question = pool_question(settings, run, row)
    limit = settings.answer_time_seconds or None
    left = None
    if limit is not None and row["shown"] is not None:
        left = seconds_left(datetime.fromisoformat(row["shown"]), now(), limit)
    return {
        "question_id": row["id"],
        "number": row["number"],
        "text": question.text,
        "format": question.format,
        "options": json.loads(row["options"]),
        "streak": run["score"],
        "lives": run["lives"],
        "combo": run["combo"],
        "life_combo": settings.life_combo,
        "max_lives": settings.max_lives,
        # None when the time limit is off.
        "time_limit_seconds": limit,
        # None until the question has been shown.
        "seconds_left": left,
    }


def in_time(settings: Settings, row: sqlite3.Row, received: datetime) -> bool:
    if not settings.answer_time_seconds or row["shown"] is None:
        return True
    shown = datetime.fromisoformat(row["shown"])
    return answer_in_time(shown, received, settings.answer_time_seconds)


def valid_selection(
    question_format: str, options: list[str], selected: list[int] | None
) -> list[int]:
    """The picked positions, checked. Order questions keep the tapped order (it may be
    incomplete when the time ran out); for the others only the set counts."""
    picked = list(selected or [])
    if not picked or len(set(picked)) != len(picked):
        raise GameError("invalid_answer")
    if min(picked) < 0 or max(picked) >= len(options):
        raise GameError("invalid_answer")
    if question_format == "single" and len(picked) != 1:
        raise GameError("invalid_answer")
    return picked if question_format == "order" else sorted(picked)


def progress_of(run: sqlite3.Row) -> Progress:
    return Progress(score=run["score"], lives=run["lives"], combo=run["combo"])


def load_run(db: sqlite3.Connection, run_id: str) -> sqlite3.Row:
    run = db.execute("SELECT * FROM runs WHERE id = ?", (run_id,)).fetchone()
    if run is None:
        raise GameError("run_not_found")
    return run


def open_question(db: sqlite3.Connection, run_id: str) -> sqlite3.Row | None:
    """The run's question without a verdict yet, if there is one."""
    return db.execute(
        "SELECT * FROM questions WHERE run = ? AND correct IS NULL", (run_id,)
    ).fetchone()


def open_question_or_error(db: sqlite3.Connection, run: sqlite3.Row) -> sqlite3.Row:
    if run["status"] == "over":
        raise GameError("run_over")
    row = open_question(db, run["id"])
    if row is None:
        raise GameError("no_open_question")
    return row


def pool_question(settings: Settings, run: sqlite3.Row, row: sqlite3.Row) -> PoolQuestion:
    """The pool question of a question row."""
    question = pool.find(settings.pool_dir, run["language"], row["pool_id"])
    if question is None:
        # Only when a question was removed from the pool file during a run.
        raise GameError("question_unavailable")
    return question
