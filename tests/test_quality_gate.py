from __future__ import annotations

import json
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from alamatin.address_normalizer import (  # noqa: E402
    ProvenancedValue,
    ValueSource,
    confirm_correction,
    propose_correction,
)
from alamatin.administrative_validator import (  # noqa: E402
    ADMINISTRATIVE_FIELDS,
    ADMINISTRATIVE_CONFLICT as VALIDATOR_CONFLICT,
    AMBIGUOUS_CANDIDATES as VALIDATOR_AMBIGUOUS,
    MISSING_FIELDS as VALIDATOR_MISSING,
    REFERENCE_COVERAGE_GAP as VALIDATOR_COVERAGE_GAP,
    VALID_CHAIN,
    AdministrativeValidationResult,
    ValidationCandidate,
)
from alamatin.quality_gate import (  # noqa: E402
    ADMINISTRATIVE_CONFLICT,
    AMBIGUOUS_ADMINISTRATIVE_CANDIDATES,
    CORRECTION_REQUIRES_CONFIRMATION,
    KELURAHAN_TIDAK_DITEMUKAN,
    KODEPOS_TIDAK_COCOK,
    MISSING_ADMINISTRATIVE_FIELDS,
    MISSING_HOUSE_LOCATOR,
    OUTSIDE_REFERENCE_COVERAGE,
    MISSING_STREET_LOCATOR,
    PERLU_KONFIRMASI,
    QUALITY_REASON_CODES,
    SIAP_DIPROSES,
    STATUS_PRECEDENCE,
    TIDAK_VALID,
    QualityGateError,
    QualityGateResult,
    QualityIssue,
    evaluate_quality_gate,
)


def candidate(code: str = "32.73.05.1002") -> ValidationCandidate:
    return ValidationCandidate(
        record_id=f"record-{code}",
        village_code=code,
        village_name="BRAGA",
        district_name="SUMUR BANDUNG",
        city_name="KOTA BANDUNG",
        province_name="JAWA BARAT",
        postal_codes=("40111",),
    )


def validation(
    *,
    status: str,
    reason: str,
    affected: tuple[str, ...] = (),
    missing: tuple[str, ...] = (),
    candidates: tuple[ValidationCandidate, ...] = (),
) -> AdministrativeValidationResult:
    return AdministrativeValidationResult(
        status=status,
        reason_codes=(reason,),
        affected_fields=affected,
        missing_fields=missing,
        candidates=candidates,
        reference_version="synthetic-fixture-v1",
    )


def valid_result() -> AdministrativeValidationResult:
    return validation(status="valid", reason=VALID_CHAIN, candidates=(candidate(),))


def pending_correction(field: str = "KOTA_KABUPATEN"):
    return propose_correction(
        field,
        ProvenancedValue("Bandun", ValueSource.EXTRACTED_BY_MODEL),
        "Bandung",
        evidence_source=ValueSource.INFERRED_FROM_HIERARCHY,
        rule_id="exact_parent_chain_v1",
    )


class QualityGateReasonCodeTests(unittest.TestCase):
    def test_valid_chain_is_ready_without_issues(self):
        result = evaluate_quality_gate(valid_result())
        self.assertEqual(result.status, SIAP_DIPROSES)
        self.assertFalse(result.issues)
        self.assertFalse(result.reason_codes)

    def test_postcode_conflict_uses_main_plan_reason_code(self):
        result = evaluate_quality_gate(
            validation(
                status="invalid",
                reason=VALIDATOR_CONFLICT,
                affected=("KODEPOS",),
                candidates=(candidate(),),
            )
        )
        self.assertEqual(result.status, TIDAK_VALID)
        self.assertEqual(result.reason_codes, (KODEPOS_TIDAK_COCOK,))
        issue = result.issues[0]
        self.assertEqual(issue.severity, "high")
        self.assertEqual(issue.affected_fields, ("KODEPOS",))

    def test_non_postcode_conflict_is_high_severity(self):
        result = evaluate_quality_gate(
            validation(
                status="invalid",
                reason=VALIDATOR_CONFLICT,
                affected=("KOTA_KABUPATEN",),
                candidates=(candidate(),),
            )
        )
        self.assertEqual(result.status, TIDAK_VALID)
        self.assertEqual(result.reason_codes, (ADMINISTRATIVE_CONFLICT,))

    def test_missing_fields_require_specific_clarification(self):
        result = evaluate_quality_gate(
            validation(
                status="incomplete",
                reason=VALIDATOR_MISSING,
                missing=("KECAMATAN", "KODEPOS"),
                candidates=(candidate(),),
            )
        )
        self.assertEqual(result.status, PERLU_KONFIRMASI)
        self.assertEqual(result.reason_codes, (MISSING_ADMINISTRATIVE_FIELDS,))
        self.assertEqual(
            result.issues[0].affected_fields,
            ("KECAMATAN", "KODEPOS"),
        )
        # The machine-readable identifiers stay in affected_fields, asserted
        # above. The prose names the same fields in a form a seller reads, so
        # this asserts the readable labels rather than the enum values.
        question = result.issues[0].clarification_question
        self.assertIn("kecamatan", question)
        self.assertIn("kode pos", question)

    def test_ambiguous_candidates_require_location_context(self):
        result = evaluate_quality_gate(
            validation(
                status="ambiguous",
                reason=VALIDATOR_AMBIGUOUS,
                candidates=(candidate("32.73.05.1002"), candidate("32.73.09.1001")),
            )
        )
        self.assertEqual(result.status, PERLU_KONFIRMASI)
        self.assertEqual(
            result.reason_codes,
            (AMBIGUOUS_ADMINISTRATIVE_CANDIDATES,),
        )
        self.assertIn("kota/kabupaten", result.issues[0].clarification_question)

    def test_coverage_gap_is_not_called_invalid(self):
        result = evaluate_quality_gate(
            validation(status="not_found", reason=VALIDATOR_COVERAGE_GAP)
        )
        self.assertEqual(result.status, PERLU_KONFIRMASI)
        self.assertEqual(result.reason_codes, (KELURAHAN_TIDAK_DITEMUKAN,))
        # The wording changed to name the value and cite the reference scope;
        # what must not change is the refusal to call a coverage gap a wrong
        # address. Asserted on meaning, not on one phrasing.
        message = result.issues[0].message
        self.assertIn("bukan bahwa alamat salah", message)
        self.assertIn("Jawa Barat", message)

    def test_pending_semantic_correction_requires_confirmation(self):
        result = evaluate_quality_gate(
            valid_result(), normalization_changes=(pending_correction(),)
        )
        self.assertEqual(result.status, PERLU_KONFIRMASI)
        self.assertEqual(
            result.reason_codes,
            (CORRECTION_REQUIRES_CONFIRMATION,),
        )

    def test_confirmed_or_deterministic_changes_do_not_emit_pending_reason(self):
        confirmed = confirm_correction(pending_correction(), user_confirmed=True)
        result = evaluate_quality_gate(
            valid_result(), normalization_changes=(confirmed,)
        )
        self.assertEqual(result.status, SIAP_DIPROSES)
        self.assertNotIn(CORRECTION_REQUIRES_CONFIRMATION, result.reason_codes)

    def test_every_reason_code_has_positive_and_negative_case(self):
        outcomes = {
            KODEPOS_TIDAK_COCOK: evaluate_quality_gate(
                validation(
                    status="invalid",
                    reason=VALIDATOR_CONFLICT,
                    affected=("KODEPOS",),
                    candidates=(candidate(),),
                )
            ),
            ADMINISTRATIVE_CONFLICT: evaluate_quality_gate(
                validation(
                    status="invalid",
                    reason=VALIDATOR_CONFLICT,
                    affected=("KECAMATAN",),
                    candidates=(candidate(),),
                )
            ),
            MISSING_ADMINISTRATIVE_FIELDS: evaluate_quality_gate(
                validation(
                    status="incomplete",
                    reason=VALIDATOR_MISSING,
                    missing=("KODEPOS",),
                    candidates=(candidate(),),
                )
            ),
            AMBIGUOUS_ADMINISTRATIVE_CANDIDATES: evaluate_quality_gate(
                validation(
                    status="ambiguous",
                    reason=VALIDATOR_AMBIGUOUS,
                    candidates=(candidate(), candidate("32.73.09.1001")),
                )
            ),
            KELURAHAN_TIDAK_DITEMUKAN: evaluate_quality_gate(
                validation(status="not_found", reason=VALIDATOR_COVERAGE_GAP)
            ),
            CORRECTION_REQUIRES_CONFIRMATION: evaluate_quality_gate(
                valid_result(), normalization_changes=(pending_correction(),)
            ),
            # An administratively perfect chain with nothing to find inside it.
            MISSING_STREET_LOCATOR: evaluate_quality_gate(
                valid_result(),
                submitted={
                    "KELURAHAN": "Braga",
                    "KECAMATAN": "Sumur Bandung",
                    "KOTA_KABUPATEN": "Kota Bandung",
                },
            ),
            # A street with no door: R01's returned-package case.
            MISSING_HOUSE_LOCATOR: evaluate_quality_gate(
                valid_result(), submitted={"JALAN": "Perum Griya Asri"}
            ),
            # A province the reference holds no rows for. Its verdict, whatever
            # it is, cannot be evidence about this address.
            OUTSIDE_REFERENCE_COVERAGE: evaluate_quality_gate(
                validation(
                    status="invalid",
                    reason=VALIDATOR_CONFLICT,
                    affected=("KECAMATAN",),
                    candidates=(candidate(),),
                ),
                submitted={
                    "JALAN": "Jalan Sudirman",
                    "NOMOR": "No. 1",
                    "PROVINSI": "DKI Jakarta",
                },
            ),
        }
        # A near-miss input that must NOT raise this reason code. A valid chain
        # would be a trivially passing negative for every code at once, so each
        # negative here is the neighbouring outcome most likely to be confused
        # with the positive case.
        negatives = {
            KODEPOS_TIDAK_COCOK: evaluate_quality_gate(
                validation(
                    status="invalid",
                    reason=VALIDATOR_CONFLICT,
                    affected=("KECAMATAN",),
                    candidates=(candidate(),),
                )
            ),
            ADMINISTRATIVE_CONFLICT: evaluate_quality_gate(
                validation(
                    status="invalid",
                    reason=VALIDATOR_CONFLICT,
                    affected=("KODEPOS",),
                    candidates=(candidate(),),
                )
            ),
            MISSING_ADMINISTRATIVE_FIELDS: evaluate_quality_gate(
                validation(status="not_found", reason=VALIDATOR_COVERAGE_GAP)
            ),
            AMBIGUOUS_ADMINISTRATIVE_CANDIDATES: evaluate_quality_gate(
                validation(
                    status="incomplete",
                    reason=VALIDATOR_MISSING,
                    missing=("KELURAHAN", "KECAMATAN"),
                    candidates=(candidate(),),
                )
            ),
            KELURAHAN_TIDAK_DITEMUKAN: evaluate_quality_gate(
                validation(
                    status="ambiguous",
                    reason=VALIDATOR_AMBIGUOUS,
                    candidates=(candidate(), candidate("32.73.09.1001")),
                )
            ),
            CORRECTION_REQUIRES_CONFIRMATION: evaluate_quality_gate(
                valid_result(),
                normalization_changes=(
                    confirm_correction(pending_correction(), user_confirmed=True),
                ),
            ),
            # A kampung name is a street locator, so the street code must not
            # fire even though this address has no house number.
            MISSING_STREET_LOCATOR: evaluate_quality_gate(
                valid_result(),
                submitted={"JALAN": "Kampung Cimanggu", "KELURAHAN": "Braga"},
            ),
            # RT/RW pins the door, so the house code must not fire for the
            # kampung addresses that are written that way.
            MISSING_HOUSE_LOCATOR: evaluate_quality_gate(
                valid_result(),
                submitted={"JALAN": "Kampung Cimanggu", "RT": "03", "RW": "05"},
            ),
            # A Jawa Barat address is inside coverage, so the coverage code must
            # not fire merely because a province was named.
            OUTSIDE_REFERENCE_COVERAGE: evaluate_quality_gate(
                valid_result(),
                submitted={
                    "JALAN": "Jalan Braga",
                    "NOMOR": "No. 5",
                    "PROVINSI": "Jawa Barat",
                },
            ),
        }
        self.assertEqual(set(outcomes), set(QUALITY_REASON_CODES))
        self.assertEqual(set(negatives), set(QUALITY_REASON_CODES))
        for reason_code, positive in outcomes.items():
            with self.subTest(reason_code=reason_code, case="positive"):
                self.assertIn(reason_code, positive.reason_codes)
            with self.subTest(reason_code=reason_code, case="negative"):
                self.assertNotIn(reason_code, negatives[reason_code].reason_codes)
                self.assertNotIn(
                    reason_code,
                    evaluate_quality_gate(valid_result()).reason_codes,
                )


class QualityGateCriticalFieldTests(unittest.TestCase):
    """The frozen scope confines high severity to reference-supported fields.

    ``docs/product-scope.md`` freezes ``KELURAHAN``, ``KECAMATAN``,
    ``KOTA_KABUPATEN``, ``PROVINSI``, and ``KODEPOS`` -- exactly
    ``ADMINISTRATIVE_FIELDS`` -- as the only critical deterministic validation
    fields, because only those can be compared against the versioned
    administrative reference. ``JALAN``, ``NOMOR``, ``RT``, ``RW``, and
    ``DETAIL_LOKASI`` stay useful for clarification, but their absence or form
    is never proof that an address is invalid.
    """

    def test_conflict_on_non_critical_field_is_rejected(self):
        with self.assertRaisesRegex(QualityGateError, "non-critical"):
            evaluate_quality_gate(
                validation(
                    status="invalid",
                    reason=VALIDATOR_CONFLICT,
                    affected=("JALAN",),
                    candidates=(candidate(),),
                )
            )

    def test_conflict_mixing_critical_and_non_critical_fields_is_rejected(self):
        with self.assertRaisesRegex(QualityGateError, "non-critical"):
            evaluate_quality_gate(
                validation(
                    status="invalid",
                    reason=VALIDATOR_CONFLICT,
                    affected=("KODEPOS", "DETAIL_LOKASI"),
                    candidates=(candidate(),),
                )
            )

    def test_every_critical_field_can_still_raise_a_conflict(self):
        for field in ADMINISTRATIVE_FIELDS:
            with self.subTest(field=field):
                result = evaluate_quality_gate(
                    validation(
                        status="invalid",
                        reason=VALIDATOR_CONFLICT,
                        affected=(field,),
                        candidates=(candidate(),),
                    )
                )
                self.assertEqual(result.status, TIDAK_VALID)

    def test_non_critical_field_may_still_require_confirmation(self):
        # A pending semantic suggestion on a non-critical field is legitimate;
        # it is medium severity and must not become TIDAK_VALID.
        result = evaluate_quality_gate(
            valid_result(), normalization_changes=(pending_correction("JALAN"),)
        )
        self.assertEqual(result.status, PERLU_KONFIRMASI)
        self.assertEqual(result.issues[0].affected_fields, ("JALAN",))


class QualityGateContractTests(unittest.TestCase):
    def test_every_issue_contains_complete_stable_contract(self):
        result = evaluate_quality_gate(
            validation(
                status="invalid",
                reason=VALIDATOR_CONFLICT,
                affected=("KOTA_KABUPATEN", "KODEPOS"),
                candidates=(candidate(),),
            ),
            normalization_changes=(pending_correction("JALAN"),),
        )
        payload = json.loads(json.dumps(result.to_response_dict()))
        self.assertEqual(payload["status"], TIDAK_VALID)
        self.assertEqual(payload["rules"]["precedence"][0]["status"], TIDAK_VALID)
        for issue in payload["issues"]:
            self.assertEqual(
                set(issue),
                {
                    "reason_code",
                    "severity",
                    "message",
                    "affected_fields",
                    "clarification_question",
                    "source_reason_code",
                },
            )
            self.assertTrue(issue["clarification_question"].endswith("?"))

    def test_high_severity_always_wins_over_confirmation_issue(self):
        result = evaluate_quality_gate(
            validation(
                status="invalid",
                reason=VALIDATOR_CONFLICT,
                affected=("KODEPOS",),
                candidates=(candidate(),),
            ),
            normalization_changes=(pending_correction(),),
        )
        self.assertEqual(result.status, TIDAK_VALID)
        self.assertEqual(
            result.reason_codes,
            (KODEPOS_TIDAK_COCOK, CORRECTION_REQUIRES_CONFIRMATION),
        )
        self.assertEqual(STATUS_PRECEDENCE[0][0], TIDAK_VALID)

    def test_status_cannot_disagree_with_issues(self):
        issue = QualityIssue(
            reason_code=KODEPOS_TIDAK_COCOK,
            severity="high",
            message="Kode pos bertentangan dengan referensi.",
            affected_fields=("KODEPOS",),
            clarification_question="Kode pos mana yang benar?",
            source_reason_code=VALIDATOR_CONFLICT,
        )
        with self.assertRaisesRegex(QualityGateError, "inconsistent"):
            QualityGateResult(status=SIAP_DIPROSES, issues=(issue,))

    def test_unsupported_validator_reason_is_rejected(self):
        unsupported = validation(status="valid", reason="UNKNOWN_REASON")
        with self.assertRaisesRegex(QualityGateError, "unsupported validator"):
            evaluate_quality_gate(unsupported)


if __name__ == "__main__":
    unittest.main()
