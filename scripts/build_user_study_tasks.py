#!/usr/bin/env python3
"""Generate counterbalanced user-study task sets (ALM-037).

Produces, per participant, 20 tasks split evenly between the manual condition
and the ALAMATIN condition, with two guarantees the protocol depends on:

* **no address appears in both conditions for the same participant** — otherwise
  the second exposure measures memory, not the tool;
* **the condition order alternates across participants** — so a learning or
  fatigue effect cannot be mistaken for a tool effect.

Ground truth for every task comes from the source dataset's gold labels, so
"errors found" and "errors missed" are scored against a recorded answer rather
than a facilitator's judgement.

Generated task sets contain address text. When the source is a governed dataset
they inherit its restrictions, so output goes to a gitignored directory by
default and only this generator, the protocol, and the schema are published.

Usage:
    python scripts/build_user_study_tasks.py --participants 4 --seed 20260823
    python scripts/build_user_study_tasks.py --participants 4 --write
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import random
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

DEFAULT_SOURCE = ROOT / "data" / "synthetic" / "val.json"
DEFAULT_OUTPUT_DIR = ROOT / "data" / "private" / "user-study"

TASKS_PER_PARTICIPANT = 20
CONDITIONS = ("manual", "alamatin")

#: Noise categories that represent a defect a reviewer is expected to catch.
#: Casing and separator noise alone are cosmetic and are not scored as errors.
SCORED_DEFECTS = frozenset(
    {
        "typo",
        "missing_provinsi",
        "missing_kodepos",
        "missing_rt_rw",
        "missing_city",
        "prefix_junk",
        "fused_admin",
        "fused_token",
        "bare_location",
        "district_only",
        "other_surface_form",
    }
)


class TaskBuildError(RuntimeError):
    """Raised when the requested design cannot be produced."""


def detokenize(tokens: list[str]) -> str:
    text = ""
    for token in tokens:
        if not text:
            text = token
        elif token in {",", ".", ";", ":"}:
            text += token
        else:
            text += " " + token
    return text


def load_source(path: Path) -> list[dict]:
    if not path.is_file():
        raise TaskBuildError(
            f"source dataset not found: {path.relative_to(ROOT).as_posix()}. "
            "A governed source lives in the custodian's environment; the public "
            "synthetic split is the default so this generator is runnable and "
            "testable anywhere."
        )
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload["examples"] if isinstance(payload, dict) else payload


def build_task(example: dict) -> dict[str, object]:
    """One task with its recorded ground truth."""

    from alamatin.pipeline import decode_bio

    tokens = example["tokens"]
    categories = list(example.get("categories", []))
    expected_defects = sorted(set(categories) & SCORED_DEFECTS)
    return {
        "task_id": example["id"],
        "address_text": detokenize(tokens),
        "ground_truth": {
            "components": decode_bio(tokens, example["labels"]),
            "noise_categories": categories,
            # What a reviewer is expected to notice. Cosmetic-only noise is
            # excluded so a participant is not penalised for ignoring casing.
            "expected_defects": expected_defects,
            "defect_count": len(expected_defects),
        },
    }


def build_design(
    examples: list[dict], participants: int, seed: int
) -> dict[str, object]:
    required = participants * TASKS_PER_PARTICIPANT
    if len(examples) < required:
        raise TaskBuildError(
            f"{participants} participants need {required} distinct addresses; "
            f"the source has {len(examples)}"
        )
    if not 3 <= participants <= 5:
        raise TaskBuildError("the protocol specifies 3 to 5 participants")

    rng = random.Random(seed)
    pool = list(examples)
    rng.shuffle(pool)

    sheets = []
    cursor = 0
    for index in range(participants):
        # Disjoint slice per participant: no address is reused across
        # participants either, so one facilitator's phrasing of a tricky address
        # cannot leak between sessions.
        chunk = pool[cursor : cursor + TASKS_PER_PARTICIPANT]
        cursor += TASKS_PER_PARTICIPANT

        half = TASKS_PER_PARTICIPANT // 2
        # Order alternates: odd-numbered participants start with ALAMATIN.
        first, second = (
            CONDITIONS if index % 2 == 0 else tuple(reversed(CONDITIONS))
        )
        blocks = [
            {
                "condition": first,
                "order": 1,
                "tasks": [build_task(item) for item in chunk[:half]],
            },
            {
                "condition": second,
                "order": 2,
                "tasks": [build_task(item) for item in chunk[half:]],
            },
        ]
        sheets.append(
            {
                # Identifier only. No name, contact, employer, or demographic is
                # collected or stored anywhere in this design.
                "participant_id": f"P{index + 1:02d}",
                "condition_order": [first, second],
                "blocks": blocks,
                "task_count": TASKS_PER_PARTICIPANT,
            }
        )

    return {
        "schema_version": "1.0.0",
        "design": {
            "participants": participants,
            "tasks_per_participant": TASKS_PER_PARTICIPANT,
            "conditions": list(CONDITIONS),
            "counterbalanced": True,
            "seed": seed,
            "within_participant_overlap": 0,
            "across_participant_overlap": 0,
            "notes": [
                "Each participant sees 10 addresses manually and 10 with "
                "ALAMATIN; no address appears in both conditions for the same "
                "participant, so a second exposure cannot measure memory.",
                "Condition order alternates across participants, so a learning "
                "or fatigue effect cannot be read as a tool effect.",
                "Ground truth comes from the source dataset's gold labels, not "
                "from a facilitator's judgement.",
            ],
        },
        "scored_defect_categories": sorted(SCORED_DEFECTS),
        "participants": sheets,
    }


def recording_schema() -> dict[str, object]:
    """The instrument. One row per task, plus one session record."""

    return {
        "schema_version": "1.0.0",
        "per_task_fields": {
            "participant_id": "P01..P05, identifier only",
            "task_id": "matches the task sheet",
            "condition": "manual | alamatin",
            "order": "1 or 2, the block this task belonged to",
            "seconds_to_decision": "wall-clock from address shown to decision recorded",
            "defects_found": "list of expected_defects the participant identified",
            "defects_missed": "expected_defects not identified; derived, not asked",
            "false_defects": "issues raised that are not in expected_defects",
            "corrections_accepted": "ALAMATIN condition only; suggestions the participant accepted",
            "corrections_rejected": "ALAMATIN condition only",
            "final_decision": "proceed | needs_confirmation | reject",
            "decision_matches_ground_truth": "derived from defect_count",
        },
        "per_session_fields": {
            "participant_id": "identifier only",
            "role_description": "free text, no employer name",
            "usability_ease": "1-5, 'the tool was easy to use'",
            "usability_trust": "1-5, 'I understood why it flagged an address'",
            "usability_reuse": "1-5, 'I would use this before printing a label'",
            "comments": "verbatim, stored only when quote_permission is true",
            "quote_permission": "true | false, recorded explicitly before any quote is used",
            "protocol_deviations": "free text; anything that departed from the protocol",
        },
        "anonymisation_rules": [
            "Participant identity is a sequential id. No name, contact, "
            "employer, or demographic field exists in the schema.",
            "Comments are stored verbatim only with quote_permission true, and "
            "are reviewed for identifying detail before any use.",
            "Raw session records stay in the custodian's restricted location. "
            "Only aggregates and permitted quotes are published.",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--participants", type=int, default=4)
    parser.add_argument("--seed", type=int, default=20260823)
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--write", action="store_true", help="write the task sheets")
    args = parser.parse_args()

    design = build_design(
        load_source(args.source), args.participants, args.seed
    )
    design["source"] = args.source.relative_to(ROOT).as_posix()

    if args.write:
        args.output_dir.mkdir(parents=True, exist_ok=True)
        tasks_path = args.output_dir / "task-sheets.json"
        schema_path = args.output_dir / "recording-schema.json"
        tasks_path.write_text(
            json.dumps(design, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        schema_path.write_text(
            json.dumps(recording_schema(), indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        print(f"wrote {tasks_path.relative_to(ROOT).as_posix()}")
        print(f"wrote {schema_path.relative_to(ROOT).as_posix()}")
        print(
            "  task sheets contain address text and inherit the source's "
            "restrictions; the output directory is gitignored."
        )
    else:
        summary = {
            "design": design["design"],
            "participants": [
                {
                    "participant_id": sheet["participant_id"],
                    "condition_order": sheet["condition_order"],
                    "task_count": sheet["task_count"],
                }
                for sheet in design["participants"]
            ],
        }
        print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
