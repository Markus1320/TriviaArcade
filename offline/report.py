"""Print a review of a question pool: numbers first, then every question and rejection.

uv run python -m offline.report --language en [--last 30] [--summary] [--dir pool]
"""

import argparse
import sys
from collections import Counter
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from offline.poolgen import LANGUAGE_NAMES, pool_file, read_records, rejected_file

# One line of a pool file.
Record = dict[str, Any]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m offline.report")
    parser.add_argument("--language", choices=sorted(LANGUAGE_NAMES), required=True)
    parser.add_argument("--dir", type=Path, default=Path("pool"), help="pool directory")
    parser.add_argument("--last", type=int, help="only the latest N records of each file")
    parser.add_argument("--summary", action="store_true", help="numbers only")
    args = parser.parse_args(argv)
    # Names like Kāne need UTF-8; the Windows console would use an older encoding.
    sys.stdout.reconfigure(encoding="utf-8")

    accepted = list(read_records(pool_file(args.dir, args.language)))
    rejected = list(read_records(rejected_file(args.dir, args.language)))
    if args.last:
        accepted, rejected = accepted[-args.last :], rejected[-args.last :]
    print_summary(accepted, rejected)
    if not args.summary:
        for number, record in enumerate(accepted, 1):
            print_question(number, record)
        for number, record in enumerate(rejected, 1):
            print_rejection(number, record)
    return 0


def print_summary(accepted: Sequence[Record], rejected: Sequence[Record]) -> None:
    walks = len(accepted) + len(rejected)
    if not walks:
        print("The pool is empty.")
        return
    records = [*accepted, *rejected]
    calls = sum(record["calls"] for record in records)
    seconds = sum(record["seconds"] for record in records)
    print(f"Walks: {walks}, accepted {len(accepted)} ({len(accepted) / walks:.0%})")
    print(f"Calls: {calls}, {calls / walks:.1f} per walk", end="")
    print(f", {calls / len(accepted):.1f} per accepted question" if accepted else "")
    print(f"Time: {seconds / 60:.0f} min, {seconds / walks:.0f}s per walk", end="")
    print(f", {seconds / len(accepted):.0f}s per accepted question" if accepted else "")
    print_counts("Formats", Counter(r["question"]["format"] for r in accepted))
    print_counts("Drafts per accepted question", Counter(len(r["rounds"]) for r in accepted))
    print_counts("Start types (accepted)", Counter(r["start_type"] for r in accepted))
    print_counts("Rejected by", Counter(reason_kind(r["reason"]) for r in rejected))
    revised = sum(1 for record in accepted if len(record["rounds"]) > 1)
    print(f"Accepted after a revision: {revised}")


def print_counts(title: str, counter: Counter) -> None:
    if counter:
        items = ", ".join(f"{key} {count}" for key, count in sorted(counter.items()))
        print(f"{title}: {items}")


def reason_kind(reason: str) -> str:
    """ "critic rejected: ..." -> "critic rejected", "not approved after 3 drafts" -> "3 drafts"."""
    return reason.split(":")[0].removeprefix("not approved after ").strip()


def print_question(number: int, record: Record) -> None:
    print(f"\n=== Accepted {number}: {record['id']} ({record['start_type']}) ===")
    print(record["facts"])
    rounds = record["rounds"]
    for draft_number, draft in enumerate(rounds, 1):
        print_round(draft_number, draft, final=draft_number == len(rounds))
    print(f"Solver: {record['solver_answers']}")
    if record["graph_aliases"]:
        print(f"Graph aliases: {record['graph_aliases']}")


def print_rejection(number: int, record: Record) -> None:
    print(f"\n=== Rejected {number}: {record['start_entity']} ({record['start_type']}) ===")
    print(record["facts"])
    for draft_number, draft in enumerate(record["rounds"], 1):
        print_round(draft_number, draft, final=False)
    print(f"Reason: {record['reason']}")


def print_round(number: int, draft: Record, *, final: bool) -> None:
    print(f"\n-- Draft {number}: {draft['verdict']}")
    print_draft(draft["question"], full=final)
    if draft["feedback"]:
        print(f"   Feedback: {draft['feedback']}")


def print_draft(question: Record, *, full: bool) -> None:
    print(f"Q ({question['format']}): {question['question']}")
    if question["format"] == "order":
        print(f"   order: {' < '.join(question['correct_options'])}")
    elif question["format"] != "free":
        for option in question["options"]:
            print(f"   [{'x' if option in question['correct_options'] else ' '}] {option}")
    else:
        print(f"A: {question['expected_answer']}")
        if question["accepted_answers"]:
            print(f"   also: {', '.join(question['accepted_answers'])}")
    if full:
        print(f"E: {question['explanation'] or '(none)'}")
        print(f"   topic: {question['topic']}")


if __name__ == "__main__":
    sys.exit(main())
