from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "qa_privacy_scan", ROOT / "scripts" / "qa_privacy_scan.py"
)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
# Registered before execution: the module defines dataclasses, and @dataclass
# resolves annotations through sys.modules.
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)

# Synthetic values only. Each exists to prove a rule fires; the file is
# allowlisted for exactly these rules so the scanner does not flag itself.
FAKE_PHONE = "0812" + "3456789"
FAKE_GOOGLE_KEY = "AIza" + "b" * 35
FAKE_AWS_KEY = "AKIA" + "B" * 16
FAKE_ASSIGNMENT = 'api_key = "' + "z" * 20 + '"'
FAKE_EMAIL = "reviewer" + "@example.com"
# Assembled at runtime so this source file contains no key-header literal:
# scripts/check_repository.py scans tracked source text and would flag it.
FAKE_KEY_HEADER = "-----BEGIN " + "OPENSSH" + " PRIVATE KEY-----"


class RuleDetectionTest(unittest.TestCase):
    """Each rule must fire on its own shape."""

    def rules_for(self, text: str) -> set[str]:
        return {finding.rule for finding in MODULE.scan_text("some/file.py", text)}

    def test_detects_a_raw_indonesian_mobile_number(self) -> None:
        self.assertIn("indonesian_mobile", self.rules_for(f"hubungi {FAKE_PHONE}"))

    def test_detects_a_raw_email_address(self) -> None:
        self.assertIn("email_address", self.rules_for(FAKE_EMAIL))

    def test_detects_separated_and_prefixed_mobile_forms(self) -> None:
        for variant in (
            "0812-3456-789",
            "0812 3456 789",
            "+628123456789",
            "628123456789",
        ):
            with self.subTest(variant=variant):
                self.assertIn("indonesian_mobile", self.rules_for(variant))

    def test_detects_a_private_key_header(self) -> None:
        self.assertIn("private_key_block", self.rules_for(FAKE_KEY_HEADER))

    def test_detects_provider_key_shapes(self) -> None:
        self.assertIn("google_api_key", self.rules_for(FAKE_GOOGLE_KEY))
        self.assertIn("aws_access_key_id", self.rules_for(FAKE_AWS_KEY))

    def test_detects_a_credential_assigned_to_a_literal(self) -> None:
        self.assertIn("assigned_credential", self.rules_for(FAKE_ASSIGNMENT))


class FalsePositiveTest(unittest.TestCase):
    """Ordinary content must not be flagged, or the scan gets ignored."""

    def rules_for(self, text: str) -> set[str]:
        return {finding.rule for finding in MODULE.scan_text("some/file.py", text)}

    def test_postal_codes_and_years_are_not_phone_numbers(self) -> None:
        for benign in ("40111", "Jawa Barat 2023", "RT 03 RW 04", "No. 1"):
            with self.subTest(benign=benign):
                self.assertEqual(self.rules_for(benign), set())

    def test_an_empty_or_placeholder_credential_is_not_flagged(self) -> None:
        for benign in ('api_key = ""', "SECRET:", 'token = "short"'):
            with self.subTest(benign=benign):
                self.assertNotIn("assigned_credential", self.rules_for(benign))

    def test_a_reference_to_an_env_var_is_not_a_secret(self) -> None:
        benign = 'api_key = os.environ["ALAMATIN_GEOCODER_KEY"]'
        self.assertNotIn("assigned_credential", self.rules_for(benign))

    def test_a_village_code_is_not_a_phone_number(self) -> None:
        self.assertEqual(self.rules_for("32.73.05.1002"), set())


class AllowlistTest(unittest.TestCase):
    def test_an_allowlisted_pair_suppresses_only_that_rule(self) -> None:
        path, rule = next(iter(MODULE.ALLOWLIST))
        self.assertTrue(MODULE.allowed(path, rule))
        self.assertFalse(MODULE.allowed(path, "no_such_rule"))
        self.assertFalse(MODULE.allowed("other/path.py", rule))

    def test_every_allowlist_entry_states_a_reason(self) -> None:
        for key, reason in MODULE.ALLOWLIST.items():
            with self.subTest(entry=key):
                self.assertTrue(reason.strip(), "an exemption must state why")

    def test_every_allowlisted_rule_name_exists(self) -> None:
        known = {rule.name for rule in (*MODULE.SECRET_RULES, *MODULE.PII_RULES)}
        for _path, rule in MODULE.ALLOWLIST:
            with self.subTest(rule=rule):
                self.assertIn(rule, known)


class RepositoryScanTest(unittest.TestCase):
    """The repository itself must be clean. This is the acceptance criterion."""

    def test_no_secret_or_raw_pii_in_tracked_files(self) -> None:
        findings = MODULE.scan_repository()
        detail = "\n".join(
            f"{item.path}:{item.line}: {item.rule} -- {item.why}" for item in findings
        )
        self.assertEqual(findings, [], f"unexpected findings:\n{detail}")

    def test_findings_never_include_the_matched_text(self) -> None:
        # Reporting the value would copy the secret into logs and CI output.
        finding = MODULE.scan_text("x.py", f"hubungi {FAKE_PHONE}")[0]
        self.assertNotIn(FAKE_PHONE, str(finding.to_dict()))

    def test_binary_and_vendored_paths_are_skipped(self) -> None:
        for candidate in (
            ROOT / "web" / "node_modules" / "x.js",
            ROOT / "docs" / "diagram.png",
        ):
            with self.subTest(candidate=candidate.name):
                self.assertFalse(MODULE.scannable(candidate))


if __name__ == "__main__":
    unittest.main()
