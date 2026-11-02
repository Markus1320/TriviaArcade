"""Compare the code matcher with real LLM judge verdicts, for tuning app/game/matcher.py.

Never part of CI. The input is exported from the questions table (free questions with a
typed answer and a verdict), one JSON object per line with question, expected, accepted,
answer and correct. It holds player answers, so it stays in the gitignored data/ folder.

    uv run python -m scripts.evaluate_matcher ../data/judge-eval.jsonl
"""

import argparse
import json
import sys
from pathlib import Path

from app.game.matcher import AnswerKey, match_answer


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m scripts.evaluate_matcher")
    parser.add_argument("file", type=Path)
    args = parser.parse_args(argv)

    rows = [json.loads(line) for line in args.file.read_text(encoding="utf-8").splitlines()]
    agree = 0
    too_strict: list[str] = []
    too_lenient: list[str] = []
    for row in rows:
        key = AnswerKey.of(row["question"], [row["expected"]], row["accepted"])
        verdict = match_answer(key, row["answer"])
        line = (
            f"{row['question']}\n    expected {row['expected']!r} also {row['accepted']}\n"
            f"    player {row['answer']!r}"
        )
        if verdict == row["correct"]:
            agree += 1
        elif row["correct"]:
            too_strict.append(line)
        else:
            too_lenient.append(line)
    correct = sum(1 for row in rows if row["correct"])
    print(f"{len(rows)} verdicts, matcher agrees on {agree} ({agree / len(rows):.1%})")
    print(f"Judge accepted {correct}: matcher rejected {len(too_strict)} of them")
    print(f"Judge rejected {len(rows) - correct}: matcher accepted {len(too_lenient)} of them")
    print("\n== Matcher accepts, judge rejected ==")
    print("\n".join(too_lenient))
    print("\n== Matcher rejects, judge accepted ==")
    print("\n".join(too_strict))
    return 0


if __name__ == "__main__":
    sys.exit(main())
