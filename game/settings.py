"""Values from the environment, with the defaults the game is played with."""

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    # The SQLite file with players, runs and questions. A backup is a copy of this file.
    database: str = "data/game.db"
    # The folder with the question pool, one <language>.jsonl file per language.
    pool_dir: str = "pool"
    # Seconds per question, counted from when it is shown. 0 turns the time limit off.
    answer_time_seconds: int = 30
    # Correct answers in a row that earn a 1UP.
    life_combo: int = 3
    # The most 1UPs a player can hold.
    max_lives: int = 3
    # 1UPs a new run starts with.
    start_lives: int = 1


def load_settings() -> Settings:
    """Read the settings from environment variables; unset ones keep their default."""
    default = Settings()
    settings = Settings(
        database=os.environ.get("DATABASE", default.database),
        pool_dir=os.environ.get("POOL_DIR", default.pool_dir),
        answer_time_seconds=int(os.environ.get("ANSWER_TIME_SECONDS", default.answer_time_seconds)),
        life_combo=int(os.environ.get("LIFE_COMBO", default.life_combo)),
        max_lives=int(os.environ.get("MAX_LIVES", default.max_lives)),
        start_lives=int(os.environ.get("START_LIVES", default.start_lives)),
    )
    if settings.life_combo < 1:
        raise ValueError("LIFE_COMBO must be at least 1")
    if not 0 <= settings.start_lives <= settings.max_lives:
        raise ValueError("START_LIVES must be between 0 and MAX_LIVES")
    if settings.answer_time_seconds < 0:
        raise ValueError("ANSWER_TIME_SECONDS must not be negative")
    return settings
