from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
SPEC = importlib.util.spec_from_file_location(
    "build_user_study_tasks", ROOT / "scripts" / "build_user_study_tasks.py"
)
assert SPEC and SPEC.loader
BUILDER = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = BUILDER
SPEC.loader.exec_module(BUILDER)

SOURCE = BUILDER.DEFAULT_SOURCE


def design(participants: int = 4, seed: int = 20260823) -> dict:
    return BUILDER.build_design(BUILDER.load_source(SOURCE), participants, seed)


@unittest.skipUnless(SOURCE.is_file(), "source split not present")
class DesignConstraintTest(unittest.TestCase):
    """The guarantees the protocol's validity depends on."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.design = design()

    def test_each_participant_gets_twenty_tasks(self) -> None:
        for sheet in self.design["participants"]:
            with self.subTest(participant=sheet["participant_id"]):
                total = sum(len(block["tasks"]) for block in sheet["blocks"])
                self.assertEqual(total, 20)
                self.assertEqual(sheet["task_count"], 20)

    def test_conditions_are_split_evenly(self) -> None:
        for sheet in self.design["participants"]:
            with self.subTest(participant=sheet["participant_id"]):
                sizes = [len(block["tasks"]) for block in sheet["blocks"]]
                self.assertEqual(sizes, [10, 10])
                self.assertEqual(
                    sorted(block["condition"] for block in sheet["blocks"]),
                    ["alamatin", "manual"],
                )

    def test_no_address_appears_in_both_conditions_for_one_participant(self) -> None:
        # A second exposure would measure memory, not the tool.
        for sheet in self.design["participants"]:
            with self.subTest(participant=sheet["participant_id"]):
                per_condition = {
                    block["condition"]: {task["task_id"] for task in block["tasks"]}
                    for block in sheet["blocks"]
                }
                self.assertEqual(
                    per_condition["manual"] & per_condition["alamatin"], set()
                )

    def test_no_address_is_shared_between_participants(self) -> None:
        seen: set[str] = set()
        for sheet in self.design["participants"]:
            ids = {
                task["task_id"]
                for block in sheet["blocks"]
                for task in block["tasks"]
            }
            with self.subTest(participant=sheet["participant_id"]):
                self.assertEqual(seen & ids, set())
            seen |= ids

    def test_condition_order_alternates_across_participants(self) -> None:
        orders = [
            tuple(sheet["condition_order"]) for sheet in self.design["participants"]
        ]
        # Both orders must be present, or order is a confound rather than a
        # controlled variable.
        self.assertEqual(len(set(orders)), 2)
        for index in range(1, len(orders)):
            self.assertNotEqual(orders[index], orders[index - 1])

    def test_the_design_is_reproducible_from_its_seed(self) -> None:
        first = design(seed=12345)
        second = design(seed=12345)
        self.assertEqual(first, second)

    def test_a_different_seed_produces_a_different_assignment(self) -> None:
        self.assertNotEqual(design(seed=1)["participants"], design(seed=2)["participants"])

    def test_participant_count_is_bounded_by_the_protocol(self) -> None:
        for count in (2, 6):
            with self.subTest(participants=count):
                with self.assertRaises(BUILDER.TaskBuildError):
                    design(participants=count)

    def test_an_insufficient_source_is_refused(self) -> None:
        with self.assertRaisesRegex(BUILDER.TaskBuildError, "distinct addresses"):
            BUILDER.build_design([{"id": "x", "tokens": ["a"], "labels": ["O"]}], 3, 1)


@unittest.skipUnless(SOURCE.is_file(), "source split not present")
class GroundTruthTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.tasks = [
            task
            for sheet in design()["participants"]
            for block in sheet["blocks"]
            for task in block["tasks"]
        ]

    def test_every_task_carries_recorded_ground_truth(self) -> None:
        for task in self.tasks[:40]:
            with self.subTest(task=task["task_id"]):
                truth = task["ground_truth"]
                self.assertTrue(task["address_text"].strip())
                self.assertTrue(truth["components"])
                self.assertEqual(truth["defect_count"], len(truth["expected_defects"]))

    def test_scored_defects_exclude_cosmetic_noise(self) -> None:
        # A participant must not be marked wrong for ignoring casing.
        for cosmetic in ("case_lower", "case_upper", "case_title", "separator", "abbreviation"):
            with self.subTest(category=cosmetic):
                self.assertNotIn(cosmetic, BUILDER.SCORED_DEFECTS)

    def test_at_least_some_tasks_carry_a_scored_defect(self) -> None:
        # A task set with no scored defect anywhere could not measure recall.
        with_defects = [task for task in self.tasks if task["ground_truth"]["defect_count"]]
        self.assertGreater(len(with_defects), 0)


class RecordingSchemaTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.schema = BUILDER.recording_schema()

    def test_every_required_measure_is_collected(self) -> None:
        fields = self.schema["per_task_fields"]
        for required in (
            "seconds_to_decision",
            "defects_found",
            "defects_missed",
            "false_defects",
            "corrections_accepted",
            "final_decision",
        ):
            with self.subTest(field=required):
                self.assertIn(required, fields)

    def test_usability_and_comments_are_collected(self) -> None:
        session = self.schema["per_session_fields"]
        for required in ("usability_ease", "usability_trust", "usability_reuse", "comments"):
            with self.subTest(field=required):
                self.assertIn(required, session)

    def test_quotes_require_explicit_permission(self) -> None:
        session = self.schema["per_session_fields"]
        self.assertIn("quote_permission", session)
        self.assertIn("quote_permission", session["comments"])

    def test_protocol_deviations_are_recordable(self) -> None:
        # The acceptance criterion requires deviations to be reported, which is
        # only possible if the instrument has somewhere to put them.
        self.assertIn("protocol_deviations", self.schema["per_session_fields"])

    def test_no_identifying_field_exists(self) -> None:
        # Field *keys* are checked, not the whole document: the prohibitions
        # themselves mention "employer", and matching prose would fail on the
        # very text that forbids the field.
        keys = {
            key.lower()
            for section in ("per_task_fields", "per_session_fields")
            for key in self.schema[section]
        }
        for forbidden in (
            "full_name",
            "name",
            "email",
            "phone",
            "employer",
            "company",
            "age",
            "gender",
        ):
            with self.subTest(field=forbidden):
                self.assertNotIn(forbidden, keys)

    def test_anonymisation_rules_are_stated(self) -> None:
        rules = " ".join(self.schema["anonymisation_rules"]).lower()
        self.assertIn("sequential id", rules)
        self.assertIn("restricted", rules)


if __name__ == "__main__":
    unittest.main()
