from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from alamatin.reference_hierarchy import (  # noqa: E402
    REFERENCE_SCHEMA_VERSION,
    ReferenceHierarchy,
    ReferenceRow,
    ReferenceValidationError,
    SourceReference,
    normalize_name,
    normalize_region_code,
)
from build_reference_hierarchy import build_reference  # noqa: E402


PRIMARY_FIXTURE = ROOT / "tests" / "fixtures" / "open_data_jabar_postal_sample.csv"
CROSSCHECK_FIXTURE = ROOT / "tests" / "fixtures" / "reference_crosscheck_sample.csv"
CATALOG = ROOT / "data" / "sources.json"


def sample_row(
    *,
    village_code: str = "32.73.05.1002",
    village_name: str = "BRAGA",
    district_code: str = "32.73.05",
    district_name: str = "SUMUR BANDUNG",
    postal_codes: tuple[str, ...] = ("40111",),
    aliases: tuple[str, ...] = (),
) -> ReferenceRow:
    return ReferenceRow(
        province_code="32",
        province_name="JAWA BARAT",
        city_code="32.73",
        city_name="KOTA BANDUNG",
        district_code=district_code,
        district_name=district_name,
        village_code=village_code,
        village_name=village_name,
        village_aliases=aliases,
        postal_codes=postal_codes,
        sources=(SourceReference("fixture_source", "fixture-v1"),),
    )


class ReferenceHierarchyTest(unittest.TestCase):
    def test_normalization_is_exact_but_case_and_punctuation_insensitive(self) -> None:
        self.assertEqual(normalize_name("  Kota-Bandung "), "kota bandung")
        self.assertNotEqual(normalize_name("Suka Maju"), normalize_name("Sukamaju"))
        self.assertEqual(normalize_region_code("3273051002", "village"), "32.73.05.1002")

    def test_exact_lookup_accepts_alias_and_parent_context(self) -> None:
        hierarchy = ReferenceHierarchy(
            [sample_row(aliases=("BRAGA KULON",))]
        )
        result = hierarchy.lookup(
            village="braga-kulon", district="Sumur Bandung", postal_code="40111"
        )
        self.assertEqual(result.status, "exact")
        self.assertEqual(result.match.village_code, "32.73.05.1002")

    def test_ambiguous_village_name_returns_all_candidates(self) -> None:
        hierarchy = ReferenceHierarchy(
            [
                sample_row(
                    village_code="32.73.05.1002",
                    village_name="SUKAMAJU",
                ),
                sample_row(
                    village_code="32.73.09.1001",
                    village_name="SUKAMAJU",
                    district_code="32.73.09",
                    district_name="CIBEUNYING KIDUL",
                ),
            ]
        )
        result = hierarchy.lookup(village="Sukamaju")
        self.assertEqual(result.status, "ambiguous")
        self.assertEqual(len(result.candidates), 2)
        narrowed = hierarchy.lookup(village="Sukamaju", district="Cibeunying Kidul")
        self.assertEqual(narrowed.status, "exact")

    def test_invalid_parent_chain_is_rejected(self) -> None:
        with self.assertRaisesRegex(ReferenceValidationError, "does not belong"):
            sample_row(
                district_code="32.01.01",
                district_name="CIBINONG",
                village_code="32.01.01.1001",
            )

    def test_duplicate_village_code_is_rejected(self) -> None:
        row = sample_row()
        with self.assertRaisesRegex(ReferenceValidationError, "duplicate canonical"):
            ReferenceHierarchy([row, row])

    def test_json_document_round_trip(self) -> None:
        hierarchy = ReferenceHierarchy([sample_row()])
        document = hierarchy.to_document(build={"catalog_version": "fixture"})
        loaded = ReferenceHierarchy.from_document(document)
        self.assertEqual(document["schema_version"], REFERENCE_SCHEMA_VERSION)
        self.assertEqual(loaded.rows, hierarchy.rows)


class ReferenceBuilderTest(unittest.TestCase):
    def test_builder_filters_jawa_barat_and_records_conflicts(self) -> None:
        hierarchy, build, exceptions = build_reference(
            PRIMARY_FIXTURE, [CROSSCHECK_FIXTURE], CATALOG
        )
        self.assertEqual(len(hierarchy.rows), 4)
        self.assertEqual(build["scope"], "Jawa Barat")
        self.assertTrue(all(row.sources for row in hierarchy.rows))
        self.assertTrue(
            all(source.snapshot for row in hierarchy.rows for source in row.sources)
        )
        self.assertIn(
            "SUKA MAJU",
            hierarchy.by_village_code("3273091001").village_aliases,
        )
        self.assertNotIn(
            "BRAGA KULON",
            hierarchy.by_village_code("3273051002").village_aliases,
        )
        kinds = {item["kind"] for item in exceptions}
        self.assertIn("name_difference", kinds)
        self.assertIn("postal_code_conflict", kinds)
        self.assertTrue(all(item["status"] == "documented" for item in exceptions))

    def test_builder_output_is_reproducible_and_loadable(self) -> None:
        first = build_reference(PRIMARY_FIXTURE, [CROSSCHECK_FIXTURE], CATALOG)
        second = build_reference(PRIMARY_FIXTURE, [CROSSCHECK_FIXTURE], CATALOG)
        first_document = first[0].to_document(build=first[1], exceptions=first[2])
        second_document = second[0].to_document(build=second[1], exceptions=second[2])
        self.assertEqual(first_document, second_document)
        self.assertEqual(
            ReferenceHierarchy.from_document(first_document).lookup(village="SUKAMAJU").status,
            "ambiguous",
        )

    def test_cli_writes_reference_and_separate_exception_report(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "reference.json"
            exception_output = Path(directory) / "exceptions.json"
            result = subprocess.run(
                [
                    sys.executable,
                    "scripts/build_reference_hierarchy.py",
                    "--open-data-jabar",
                    str(PRIMARY_FIXTURE),
                    "--crosscheck",
                    str(CROSSCHECK_FIXTURE),
                    "--output",
                    str(output),
                    "--exceptions-output",
                    str(exception_output),
                ],
                cwd=ROOT,
                capture_output=True,
                text=True,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(len(ReferenceHierarchy.from_json(output).rows), 4)
            exceptions = json.loads(exception_output.read_text(encoding="utf-8"))
            self.assertGreater(len(exceptions["exceptions"]), 0)


if __name__ == "__main__":
    unittest.main()
