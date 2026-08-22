from __future__ import annotations

import copy
import json
from pathlib import Path
import re
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from alamatin.administrative_validator import ADMINISTRATIVE_FIELDS  # noqa: E402
from alamatin.label_schema import ENTITY_TYPES  # noqa: E402
from alamatin.output_contract import (  # noqa: E402
    CONTRACT_RELATIVE_PATH,
    CONTRACT_VERSION,
    ContractValidationError,
    load_contract_schema,
    validate_contract_document,
)
from alamatin.quality_gate import (  # noqa: E402
    ADMINISTRATIVE_CONFLICT,
    CORRECTION_REQUIRES_CONFIRMATION,
    QUALITY_REASON_CODES,
    QUALITY_STATUSES,
    RULES_VERSION,
    SEVERITIES,
)


EXAMPLES = ROOT / "contracts" / "examples"


def read_example(name: str) -> dict:
    return json.loads((EXAMPLES / name).read_text(encoding="utf-8"))


def walk(value):
    yield value
    if isinstance(value, dict):
        for nested in value.values():
            yield from walk(nested)
    elif isinstance(value, list):
        for nested in value:
            yield from walk(nested)


class OutputContractSchemaTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.schema = load_contract_schema()

    def test_schema_is_draft_2020_12_and_resolves_all_refs(self):
        self.assertEqual(
            self.schema["$schema"],
            "https://json-schema.org/draft/2020-12/schema",
        )
        self.assertIn("request", self.schema["$defs"])
        self.assertIn("response", self.schema["$defs"])

    def test_every_frozen_example_validates_automatically(self):
        names = {path.name for path in EXAMPLES.glob("*.json")}
        self.assertEqual(
            names,
            {
                "success.request.json",
                "success.response.json",
                "ambiguity.request.json",
                "ambiguity.response.json",
                "invalid.request.json",
                "invalid.response.json",
                "external-failure.request.json",
                "external-failure.response.json",
            },
        )
        for name in sorted(names):
            with self.subTest(name=name):
                validate_contract_document(read_example(name), self.schema)

    def test_request_response_pairs_share_request_id(self):
        for scenario in ("success", "ambiguity", "invalid", "external-failure"):
            with self.subTest(scenario=scenario):
                request = read_example(f"{scenario}.request.json")
                response = read_example(f"{scenario}.response.json")
                self.assertEqual(request["request_id"], response["request_id"])

    def test_model_score_is_frozen_and_confidence_is_forbidden(self):
        self.assertNotIn("confidence", {key for item in walk(self.schema) if isinstance(item, dict) for key in item})
        success = read_example("success.response.json")
        model_value = success["components"][0]["result"]
        self.assertIn("model_score", model_value)
        invalid = copy.deepcopy(success)
        invalid["components"][0]["result"]["confidence"] = invalid["components"][0]["result"].pop("model_score")
        with self.assertRaises(ContractValidationError):
            validate_contract_document(invalid, self.schema)

    def test_every_pipeline_version_is_required(self):
        expected = {
            "contract", "model", "normalizer", "validator", "reference_data", "quality_gate"
        }
        response = read_example("success.response.json")
        self.assertEqual(set(response["versions"]), expected)
        for key in expected:
            with self.subTest(key=key):
                invalid = copy.deepcopy(response)
                del invalid["versions"][key]
                with self.assertRaises(ContractValidationError):
                    validate_contract_document(invalid, self.schema)

    def test_frontend_and_backend_reference_same_canonical_contract(self):
        source = (ROOT / "web" / "address-contract.js").read_text(encoding="utf-8")
        path = re.search(r'ADDRESS_CONTRACT_PATH = "([^"]+)"', source).group(1)
        version = re.search(r'ADDRESS_CONTRACT_VERSION = "([^"]+)"', source).group(1)
        self.assertEqual(path, CONTRACT_RELATIVE_PATH)
        self.assertEqual(version, CONTRACT_VERSION)
        self.assertTrue((ROOT / path).is_file())


class OutputContractInvariantTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.schema = load_contract_schema()

    def test_every_result_value_has_source_and_confirmation_state(self):
        response = read_example("success.response.json")
        for component in response["components"]:
            self.assertIn("source", component["result"])
            self.assertIn("confirmed", component["result"])
        self.assertIn("source", response["normalized_address"])
        self.assertIn("confirmed", response["normalized_address"])
        invalid = copy.deepcopy(response)
        del invalid["components"][0]["result"]["source"]
        with self.assertRaises(ContractValidationError):
            validate_contract_document(invalid, self.schema)

    def test_confirmation_requires_previous_value_and_user_provenance(self):
        response = read_example("success.response.json")
        correction = response["corrections"][0]
        self.assertIsNotNone(correction["previous_value"])
        self.assertEqual(correction["proposed_value"]["source"], "confirmed_by_user")
        invalid = copy.deepcopy(response)
        invalid["corrections"][0]["proposed_value"]["source"] = "inferred_from_hierarchy"
        invalid["corrections"][0]["proposed_value"]["confirmed"] = False
        with self.assertRaises(ContractValidationError):
            validate_contract_document(invalid, self.schema)

    def test_pending_correction_cannot_claim_user_confirmation(self):
        response = read_example("ambiguity.response.json")
        invalid = copy.deepcopy(response)
        invalid["corrections"][0]["user_confirmation"] = {
            "confirmed": True,
            "source": "confirmed_by_user",
            "confirmed_at": "2026-08-21T12:00:00Z",
        }
        with self.assertRaises(ContractValidationError):
            validate_contract_document(invalid, self.schema)

    def test_quality_status_is_explained_only_by_issues_and_rules(self):
        invalid = read_example("invalid.response.json")
        invalid["quality_gate"]["status"] = "SIAP_DIPROSES"
        with self.assertRaisesRegex(ContractValidationError, "disagrees"):
            validate_contract_document(invalid, self.schema)

    def test_external_failure_is_explicit_and_does_not_make_address_invalid(self):
        response = read_example("external-failure.response.json")
        self.assertEqual(response["geocoding"]["status"], "EXTERNAL_FAILURE")
        self.assertEqual(response["quality_gate"]["status"], "SIAP_DIPROSES")
        validate_contract_document(response, self.schema)

    def test_no_pii_entity_can_expose_a_raw_value_field(self):
        response = read_example("success.response.json")
        invalid = copy.deepcopy(response)
        invalid["pii"]["entities"] = [{
            "type": "PHONE", "start": 0, "end": 12,
            "redacted_value": "[PHONE_REDACTED]", "raw_value": "synthetic-secret"
        }]
        with self.assertRaises(ContractValidationError):
            validate_contract_document(invalid, self.schema)

    def test_audit_sequence_must_be_contiguous(self):
        response = read_example("success.response.json")
        response["audit_trail"][1]["sequence"] = 3
        with self.assertRaisesRegex(ContractValidationError, "contiguous"):
            validate_contract_document(response, self.schema)


class ContractMatchesQualityGateModuleTests(unittest.TestCase):
    """The wire contract and `alamatin.quality_gate` must not drift apart.

    The contract re-states quality-gate semantics for the frontend, so every
    restatement needs a test tying it back to the module that owns the rule.
    Without these, the contract can keep accepting a response the gate itself
    would refuse to produce.
    """

    @classmethod
    def setUpClass(cls):
        cls.schema = load_contract_schema()

    def test_component_field_enum_matches_canonical_entity_types(self):
        self.assertEqual(
            tuple(self.schema["$defs"]["field"]["enum"]),
            ENTITY_TYPES,
        )

    def test_status_enum_matches_quality_gate_statuses(self):
        self.assertEqual(
            set(self.schema["$defs"]["qualityGate"]["properties"]["status"]["enum"]),
            set(QUALITY_STATUSES),
        )

    def test_severity_enum_matches_quality_gate_severities(self):
        self.assertEqual(
            tuple(self.schema["$defs"]["qualityIssue"]["properties"]["severity"]["enum"]),
            SEVERITIES,
        )

    def test_reason_code_enum_matches_frozen_reason_codes(self):
        reason_code = self.schema["$defs"]["qualityIssue"]["properties"]["reason_code"]
        self.assertEqual(set(reason_code["enum"]), set(QUALITY_REASON_CODES))

    def test_rules_version_matches_quality_gate_rules_version(self):
        self.assertEqual(
            self.schema["$defs"]["qualityGate"]["properties"]["rules"]["properties"][
                "version"
            ]["const"],
            RULES_VERSION,
        )


class ContractCriticalFieldTests(unittest.TestCase):
    """High severity stays confined to reference-supported fields.

    ALM-024 confines high-severity conflicts to `ADMINISTRATIVE_FIELDS`, because
    only those can be contradicted by the governed reference. The contract has
    to refuse the same responses; otherwise it advertises a `TIDAK_VALID` on
    `JALAN` that the gate can no longer produce.
    """

    @classmethod
    def setUpClass(cls):
        cls.schema = load_contract_schema()

    def _high_severity_on(self, field: str) -> dict:
        response = read_example("invalid.response.json")
        issue = response["quality_gate"]["issues"][0]
        self.assertEqual(issue["severity"], "high")
        issue["reason_code"] = ADMINISTRATIVE_CONFLICT
        issue["affected_fields"] = [field]
        return response

    def test_high_severity_issue_cannot_affect_non_critical_field(self):
        for field in ("JALAN", "NOMOR", "RT", "RW", "DETAIL_LOKASI"):
            with self.subTest(field=field):
                with self.assertRaisesRegex(ContractValidationError, "non-critical"):
                    validate_contract_document(
                        self._high_severity_on(field), self.schema
                    )

    def test_high_severity_issue_may_affect_every_critical_field(self):
        for field in ADMINISTRATIVE_FIELDS:
            with self.subTest(field=field):
                validate_contract_document(self._high_severity_on(field), self.schema)

    def test_medium_issue_may_still_affect_a_non_critical_field(self):
        response = read_example("ambiguity.response.json")
        issue = response["quality_gate"]["issues"][0]
        self.assertEqual(issue["severity"], "medium")
        issue["reason_code"] = CORRECTION_REQUIRES_CONFIRMATION
        issue["affected_fields"] = ["JALAN"]
        validate_contract_document(response, self.schema)


if __name__ == "__main__":
    unittest.main()
