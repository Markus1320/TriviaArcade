import uuid
from datetime import UTC, datetime, timedelta

from app.leaderboard.ranking import FinishedRun, rank_runs

T0 = datetime(2026, 9, 24, 12, 0, tzinfo=UTC)


def run(handle: str, streak: int, minutes: int) -> FinishedRun:
    return FinishedRun(
        run_id=uuid.uuid4(),
        handle=handle,
        streak=streak,
        finished_at=T0 + timedelta(minutes=minutes),
    )


def test_highest_streak_first() -> None:
    entries = rank_runs([run("AAA", 3, 0), run("BBB", 7, 5), run("CCC", 5, 1)])
    assert [(e.rank, e.handle, e.streak) for e in entries] == [
        (1, "BBB", 7),
        (2, "CCC", 5),
        (3, "AAA", 3),
    ]


def test_ties_are_broken_by_earlier_finish() -> None:
    entries = rank_runs([run("LATE", 5, 30), run("EARLY", 5, 10), run("MID", 5, 20)])
    assert [e.handle for e in entries] == ["EARLY", "MID", "LATE"]


def test_player_can_appear_several_times() -> None:
    entries = rank_runs([run("ACE", 4, 0), run("ACE", 6, 1), run("BOB", 5, 2)])
    assert [(e.handle, e.streak) for e in entries] == [("ACE", 6), ("BOB", 5), ("ACE", 4)]


def test_only_top_ten() -> None:
    entries = rank_runs([run(f"P{i:02d}", i, i) for i in range(15)])
    assert len(entries) == 10
    assert [e.rank for e in entries] == list(range(1, 11))
    assert entries[0].streak == 14
    assert entries[-1].streak == 5


def test_same_finish_time_is_still_a_total_order() -> None:
    a, b = run("AAA", 5, 0), run("BBB", 5, 0)
    assert rank_runs([a, b]) == rank_runs([b, a])


def test_empty_leaderboard() -> None:
    assert rank_runs([]) == []
