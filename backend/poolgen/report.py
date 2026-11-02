"""Print a review of a question pool: numbers first, then every question and rejection.

python -m poolgen.report --language en [--last 30] [--dir ../pool]
"""

import argparse
import sys
from collections import Counter
from collections.abc import Sequence
from pathlib import Path
from typing import get_args

from app.languages import Language
from app.llm.generator import GeneratedQuestion
from app.pool.records import (
    DEFAULT_DIR,
    PoolQuestion,
    Rejection,
    Round,
    pool_path,
    read_records,
    rejected_path,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m poolgen.report")
    parser.add_argument("--language", choices=get_args(Language), required=True)
    parser.add_argument("--dir", type=Path, default=Path(DEFAULT_DIR))
    parser.add_argument("--last", type=int, help="only the latest N records of each file")
    parser.add_argument("--summary", action="store_true", help="numbers only")
    args = parser.parse_args(argv)

    accepted = list(read_records(pool_path(args.dir, args.language), PoolQuestion))
    rejected = list(read_records(rejected_path(args.dir, args.language), Rejection))
    if args.last:
        accepted, rejected = accepted[-args.last :], rejected[-args.last :]
    print_summary(accepted, rejected)
    if not args.summary:
        for number, question in enumerate(accepted, 1):
            print_question(number, question)
        for number, rejection in enumerate(rejected, 1):
            print_rejection(number, rejection)
    return 0


def print_summary(accepted: Sequence[PoolQuestion], rejected: Sequence[Rejection]) -> None:
    walks = len(accepted) + len(rejected)
    if not walks:
        print("The pool is empty.")
        return
    calls = sum(r.calls for r in accepted) + sum(r.calls for r in rejected)
    seconds = sum(r.seconds for r in accepted) + sum(r.seconds for r in rejected)
    print(f"Walks: {walks}, accepted {len(accepted)} ({len(accepted) / walks:.0%})")
    print(f"Calls: {calls}, {calls / walks:.1f} per walk", end="")
    print(f", {calls / len(accepted):.1f} per accepted question" if accepted else "")
    print(f"Time: {seconds / 60:.0f} min, {seconds / walks:.0f}s per walk", end="")
    print(f", {seconds / len(accepted):.0f}s per accepted question" if accepted else "")
    _counts("Formats", Counter(str(q.question.format) for q in accepted))
    _counts("Drafts per accepted question", Counter(len(q.rounds) for q in accepted))
    _counts("Start types (accepted)", Counter(q.start_type for q in accepted))
    _counts("Rejected by", Counter(_reason_kind(r.reason) for r in rejected))
    revised = sum(1 for q in accepted if len(q.rounds) > 1)
    print(f"Accepted after a revision: {revised}")


def _counts(title: str, counter: Counter[str] | Counter[int]) -> None:
    if counter:
        items = ", ".join(f"{key} {count}" for key, count in sorted(counter.items()))
        print(f"{title}: {items}")


def _reason_kind(reason: str) -> str:
    return reason.split(":")[0].removeprefix("not approved after ").strip()


def print_question(number: int, record: PoolQuestion) -> None:
    print(f"\n=== Accepted {number}: {record.id} ({record.start_type}) ===")
    print(record.facts)
    for draft_number, draft in enumerate(record.rounds, 1):
        _print_round(draft_number, draft, final=draft_number == len(record.rounds))
    print(f"Solver: {record.solver_answers}")
    if record.graph_aliases:
        print(f"Graph aliases: {record.graph_aliases}")


def print_rejection(number: int, record: Rejection) -> None:
    print(f"\n=== Rejected {number}: {record.start_entity} ({record.start_type}) ===")
    print(record.facts)
    for draft_number, draft in enumerate(record.rounds, 1):
        _print_round(draft_number, draft, final=False)
    print(f"Reason: {record.reason}")


def _print_round(number: int, draft: Round, *, final: bool) -> None:
    print(f"\n-- Draft {number}: {draft.verdict}")
    print_generated(draft.question, full=final)
    if draft.feedback:
        print(f"   Feedback: {draft.feedback}")


def print_generated(question: GeneratedQuestion, *, full: bool = True) -> None:
    print(f"Q ({question.format}): {question.question}")
    if question.format == "order":
        print(f"   order: {' < '.join(question.correct_options)}")
    elif question.is_choice:
        for option in question.options:
            print(f"   [{'x' if option in question.correct_options else ' '}] {option}")
    else:
        print(f"A: {question.expected_answer}")
        if question.accepted_answers:
            print(f"   also: {', '.join(question.accepted_answers)}")
    if full:
        print(f"E: {question.explanation or '(none)'}")
        print(f"   topic: {question.topic}")


if __name__ == "__main__":
    sys.exit(main())
