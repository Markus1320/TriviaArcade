"""Empty the leaderboard, e.g. after the rules or the question pool changed.

    docker compose exec backend python -m scripts.reset_leaderboard --yes

Runs and their questions are kept for review and handles stay available; only the link
between runs and players is removed, so everybody starts from zero.
"""

import argparse
import sys

from app.db.engine import get_session_factory
from app.leaderboard.service import LeaderboardService


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m scripts.reset_leaderboard")
    parser.add_argument(
        "--yes", action="store_true", help="really reset; without it nothing happens"
    )
    args = parser.parse_args(argv)
    if not args.yes:
        print("Nothing done. Pass --yes to empty the leaderboard.", file=sys.stderr)
        return 2
    with get_session_factory()() as session:
        removed = LeaderboardService(session).reset()
    print(f"Leaderboard reset: {removed} runs removed from it.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
