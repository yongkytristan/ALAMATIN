"""Tests for the executable parts of the evaluation protocol."""

from __future__ import annotations

import unittest

from src.alamatin.evaluation_metrics import (
    binary_recall,
    canonical_json_sha256,
    critical_exact_match,
    entity_metrics,
    entity_metrics_by_type,
    extract_bio_entities,
    false_correction_rate,
    latency_summary_ms,
    nearest_rank_percentile,
)


class EvaluationMetricTests(unittest.TestCase):
    def test_extracts_exact_spans_with_exclusive_end(self) -> None:
        spans = extract_bio_entities(
            ["B-JALAN", "I-JALAN", "O", "B-KODEPOS"]
        )
        self.assertEqual(
            spans,
            frozenset({("JALAN", 0, 2), ("KODEPOS", 3, 4)}),
        )

    def test_partial_overlap_is_one_false_positive_and_one_false_negative(self) -> None:
        result = entity_metrics(
            [["B-JALAN", "I-JALAN", "O"]],
            [["B-JALAN", "O", "O"]],
        )
        self.assertEqual(
            (result.true_positive, result.false_positive, result.false_negative),
            (0, 1, 1),
        )
        self.assertEqual(result.f1, 0.0)

    def test_micro_metrics_and_per_type_metrics(self) -> None:
        gold = [["B-JALAN", "O", "B-KODEPOS"]]
        predicted = [["B-JALAN", "O", "B-PROVINSI"]]
        micro = entity_metrics(gold, predicted)
        by_type = entity_metrics_by_type(gold, predicted)
        self.assertEqual(
            (micro.true_positive, micro.false_positive, micro.false_negative),
            (1, 1, 1),
        )
        self.assertEqual(micro.f1, 0.5)
        self.assertEqual(by_type["JALAN"].true_positive, 1)
        self.assertEqual(by_type["KODEPOS"].false_negative, 1)
        self.assertEqual(by_type["PROVINSI"].false_positive, 1)

    def test_critical_exact_match_ignores_noncritical_detail(self) -> None:
        result = critical_exact_match(
            [["B-JALAN", "O", "B-DETAIL_LOKASI"]],
            [["B-JALAN", "O", "O"]],
        )
        self.assertEqual(
            (result.numerator, result.denominator, result.rate),
            (1, 1, 1.0),
        )

    def test_critical_exact_match_rejects_extra_critical_span(self) -> None:
        result = critical_exact_match(
            [["B-JALAN", "O"]],
            [["B-JALAN", "B-NOMOR"]],
        )
        self.assertEqual(result.rate, 0.0)

    def test_binary_recall_and_no_positive_denominator(self) -> None:
        result = binary_recall([True, True, False], [True, False, True])
        self.assertEqual(
            (result.true_positive, result.false_negative, result.recall),
            (1, 1, 0.5),
        )
        self.assertIsNone(binary_recall([False], [True]).recall)

    def test_false_correction_rate_and_no_proposal_denominator(self) -> None:
        result = false_correction_rate([True, False, True, False])
        self.assertEqual(
            (result.numerator, result.denominator, result.rate),
            (2, 4, 0.5),
        )
        self.assertIsNone(false_correction_rate([]).rate)

    def test_nearest_rank_latency_percentiles(self) -> None:
        values = list(range(1, 101))
        self.assertEqual(nearest_rank_percentile(values, 50), 50)
        self.assertEqual(nearest_rank_percentile(values, 95), 95)
        summary = latency_summary_ms(values)
        self.assertEqual(
            (summary.sample_count, summary.p50_ms, summary.p95_ms),
            (100, 50, 95),
        )

    def test_manifest_hash_is_canonical_and_change_sensitive(self) -> None:
        first = canonical_json_sha256({"b": 2, "a": [1, "x"]})
        reordered = canonical_json_sha256({"a": [1, "x"], "b": 2})
        changed = canonical_json_sha256({"a": [1, "y"], "b": 2})
        self.assertEqual(first, reordered)
        self.assertNotEqual(first, changed)
        self.assertEqual(len(first), 64)

    def test_rejects_mismatched_or_invalid_sequences(self) -> None:
        with self.assertRaisesRegex(ValueError, "token count differs"):
            entity_metrics([["O"]], [["O", "O"]])
        with self.assertRaisesRegex(ValueError, "orphan I-tag"):
            extract_bio_entities(["I-JALAN"])


if __name__ == "__main__":
    unittest.main()
