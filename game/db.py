"""Opening the SQLite database, and transactions.

sqlite3 is part of Python. A query is plain SQL with ? placeholders for the values:

    db.execute("SELECT score FROM runs WHERE id = ?", (run_id,)).fetchone()

Rows come back as sqlite3.Row, which can be read like a dict: row["score"].
"""

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

SCHEMA = Path(__file__).with_name("schema.sql")


def connect(path: str) -> sqlite3.Connection:
    # isolation_level=None: sqlite3 starts no transactions on its own; transaction()
    # below starts them. timeout: how long to wait while another request is writing.
    db = sqlite3.connect(path, isolation_level=None, timeout=10, check_same_thread=False)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys = ON")
    return db


def create_tables(path: str) -> None:
    """Create the database file and its tables if they do not exist yet.

    When a table changes later, add the change as a numbered SQL file and apply it here
    once, remembering the applied number in PRAGMA user_version.
    """
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    db = connect(path)
    try:
        # WAL lets the game read while another request writes. It is stored in the file.
        db.execute("PRAGMA journal_mode = WAL")
        db.executescript(SCHEMA.read_text(encoding="utf-8"))
    finally:
        db.close()


@contextmanager
def transaction(db: sqlite3.Connection) -> Iterator[None]:
    """Everything inside the with block is saved together, or not at all on an error.

    BEGIN IMMEDIATE takes SQLite's write lock at the start, so two requests for the same
    run (a double click) run one after the other: the second one sees what the first
    one wrote and cannot, for example, create a second open question.
    """
    db.execute("BEGIN IMMEDIATE")
    try:
        yield
    except BaseException:
        db.execute("ROLLBACK")
        raise
    db.execute("COMMIT")
