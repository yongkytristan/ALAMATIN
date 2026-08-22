from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
SPEC = importlib.util.spec_from_file_location(
    "build_release_manifest", ROOT / "scripts" / "build_release_manifest.py"
)
assert SPEC and SPEC.loader
BUILDER = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = BUILDER
SPEC.loader.exec_module(BUILDER)

MANIFEST_PATH = ROOT / "experiments" / "release-candidate" / "manifest.json"


class ManifestExistsTest(unittest.TestCase):
    def test_the_manifest_is_committed(self) -> None:
        self.assertTrue(
            MANIFEST_PATH.is_file(),
            "the release candidate must be recorded, not implied by the code",
        )


@unittest.skipUnless(MANIFEST_PATH.is_file(), "no release manifest recorded")
class FrozenComponentsTest(unittest.TestCase):
    """The freeze has teeth only if drift fails a check."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.stored = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
        cls.current = BUILDER.build()

    def test_every_frozen_file_still_matches_its_digest(self) -> None:
        stored = {item["path"]: item["sha256"] for item in self.stored["frozen_files"]}
        drift = [
            item["path"]
            for item in self.current["frozen_files"]
            if stored.get(item["path"]) != item["sha256"]
        ]
        self.assertEqual(
            drift, [], f"frozen file(s) changed without re-freezing: {drift}"
        )

    def test_the_frozen_set_covers_the_whole_decision_path(self) -> None:
        # A module that can change an answer but is not frozen would make the
        # manifest a decoration.
        frozen = {item["path"] for item in self.stored["frozen_files"]}
        for required in (
            "src/alamatin/pii.py",
            "src/alamatin/regex_baseline.py",
            "src/alamatin/address_normalizer.py",
            "src/alamatin/administrative_validator.py",
            "src/alamatin/quality_gate.py",
            "src/alamatin/pipeline.py",
            "src/alamatin/output_contract.py",
            "contracts/address-api.v1.schema.json",
            "data/processed/jabar-reference-v1-verified.json",
            "requirements.lock",
        ):
            with self.subTest(path=required):
                self.assertIn(required, frozen)

    def test_declared_versions_match_the_code(self) -> None:
        self.assertEqual(
            self.stored["declared_versions"], self.current["declared_versions"]
        )

    def test_decision_rules_match_the_code(self) -> None:
        self.assertEqual(self.stored["decision_rules"], self.current["decision_rules"])

    def test_the_recorded_statuses_and_codes_are_the_frozen_ones(self) -> None:
        from alamatin.quality_gate import QUALITY_REASON_CODES, QUALITY_STATUSES

        rules = self.stored["decision_rules"]
        self.assertEqual(set(rules["operational_statuses"]), set(QUALITY_STATUSES))
        self.assertEqual(set(rules["reason_codes"]), set(QUALITY_REASON_CODES))

    def test_no_threshold_participates_in_the_decision(self) -> None:
        self.assertIsNone(self.stored["decision_rules"]["thresholds"])


@unittest.skipUnless(MANIFEST_PATH.is_file(), "no release manifest recorded")
class ReleaseScopeTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.stored = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))

    def test_no_p1_feature_is_in_the_release_candidate(self) -> None:
        # The frozen scope forbids a P1 implementation entering the release
        # candidate after the freeze.
        included = [
            name
            for name, decision in self.stored["p1_features"].items()
            if decision["in_release_candidate"]
        ]
        self.assertEqual(included, [])

    def test_every_p1_decision_states_a_reason(self) -> None:
        for name, decision in self.stored["p1_features"].items():
            with self.subTest(feature=name):
                self.assertTrue(decision["reason"].strip())

    def test_geocoding_is_recorded_as_disabled_and_is_disabled(self) -> None:
        from alamatin.geocoding import GeocodingService

        self.assertFalse(
            self.stored["p1_features"]["ALM-029 consent-gated geocoding"][
                "in_release_candidate"
            ]
        )
        self.assertFalse(GeocodingService().enabled)

    def test_the_checkpoint_is_recorded_as_not_served(self) -> None:
        checkpoint = self.stored["model_checkpoint"]
        self.assertFalse(checkpoint["served_in_release_candidate"])
        self.assertEqual(
            checkpoint["runtime_extractor"], self.stored["declared_versions"]["extractor"]
        )

    def test_the_runtime_extractor_matches_what_the_pipeline_reports(self) -> None:
        from alamatin.pipeline import REGEX_EXTRACTOR_VERSION

        self.assertEqual(
            self.stored["model_checkpoint"]["runtime_extractor"],
            REGEX_EXTRACTOR_VERSION,
        )


@unittest.skipUnless(MANIFEST_PATH.is_file(), "no release manifest recorded")
class SealedTestAuthorizationTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.sealed = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))["sealed_test"]

    def test_exactly_one_opening_is_authorized(self) -> None:
        self.assertEqual(self.sealed["authorized_openings"], 1)

    def test_the_no_tuning_declaration_is_recorded(self) -> None:
        declaration = self.sealed["no_tuning_declaration"]
        self.assertIn("never quietly selected", declaration)
        self.assertIn("documented", declaration)

    def test_the_declaration_states_its_provenance(self) -> None:
        # A declaration without provenance cannot be audited later.
        self.assertTrue(self.sealed["declaration_provenance"].strip())


if __name__ == "__main__":
    unittest.main()
