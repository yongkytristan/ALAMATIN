from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCOPE = ROOT / "docs" / "product-scope.md"
README = ROOT / "README.md"


class ProductScopeContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.scope = SCOPE.read_text(encoding="utf-8")
        cls.readme = README.read_text(encoding="utf-8")

    def test_readme_uses_and_links_the_frozen_positioning(self):
        positioning = (
            "ALAMATIN is a pre-fulfillment address quality gate that helps "
            "Indonesian seller\noperators identify incomplete, ambiguous, or "
            "administratively conflicting\naddress components and request human "
            "confirmation before a waybill is created."
        )
        self.assertIn(positioning, self.readme)
        self.assertIn("[docs/product-scope.md](docs/product-scope.md)", self.readme)

    def test_priority_and_out_of_scope_boundaries_are_explicit(self):
        for heading in (
            "### P0: required for the submission candidate",
            "### P1: useful but not required by P0",
            "### P2: post-submission backlog",
            "## Explicitly outside the current scope",
            "## Scope change control",
        ):
            self.assertIn(heading, self.scope)

    def test_statuses_and_critical_fields_are_frozen(self):
        for status in ("SIAP_DIPROSES", "PERLU_KONFIRMASI", "TIDAK_VALID"):
            self.assertIn(f"`{status}`", self.scope)
        for field in (
            "KELURAHAN",
            "KECAMATAN",
            "KOTA_KABUPATEN",
            "PROVINSI",
            "KODEPOS",
        ):
            self.assertIn(f"`{field}`", self.scope)

    def test_claim_boundary_names_every_prohibited_claim_class(self):
        required_boundaries = (
            "delivery risk score",
            "reduction in failed deliveries",
            "verified, accurate, or ground-truth physical location",
            "calibrated confidence or probability",
            "national, all-marketplace, or all-courier coverage",
            "causal conclusions from the four exploratory interviews",
        )
        for boundary in required_boundaries:
            self.assertIn(boundary, self.scope)


if __name__ == "__main__":
    unittest.main()
