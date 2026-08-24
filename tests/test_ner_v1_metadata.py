from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "configs" / "ner-v1.json"
EXPERIMENT = ROOT / "experiments" / "ner-v1"


class NerV1MetadataTest(unittest.TestCase):
    @staticmethod
    def canonical_json_sha256(path: Path) -> str:
        document = json.loads(path.read_text(encoding="utf-8"))
        payload = json.dumps(
            document,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
        return hashlib.sha256(payload).hexdigest()

    def test_training_config_pins_revision_seed_and_best_model_selection(self) -> None:
        config = json.loads(CONFIG.read_text(encoding="utf-8"))

        self.assertEqual(config["base_model"]["name"], "bert-base-multilingual-cased")
        self.assertEqual(len(config["base_model"]["revision"]), 40)
        self.assertEqual(config["seed"], 42)
        self.assertTrue(config["training"]["load_best_model_at_end"])
        self.assertEqual(config["training"]["metric_for_best_model"], "f1")

    def test_dataset_hashes_match_the_governed_splits(self) -> None:
        manifest = json.loads(
            (EXPERIMENT / "run_manifest.json").read_text(encoding="utf-8")
        )
        for item in manifest["datasets"].values():
            path = ROOT / item["path"]
            digest = self.canonical_json_sha256(path)
            self.assertEqual(digest, item["canonical_json_sha256"])

    def test_label_map_covers_exactly_ten_canonical_entity_types(self) -> None:
        document = json.loads(
            (EXPERIMENT / "label_map.json").read_text(encoding="utf-8")
        )
        self.assertEqual(len(document["entity_types"]), 10)
        self.assertEqual(len(document["labels"]), 21)
        self.assertEqual(document["labels"][0], "O")
        for entity in document["entity_types"]:
            self.assertIn(f"B-{entity}", document["labels"])
            self.assertIn(f"I-{entity}", document["labels"])

    def test_selected_checkpoint_is_best_saved_dev_f1(self) -> None:
        metrics = json.loads(
            (EXPERIMENT / "metrics.json").read_text(encoding="utf-8")
        )
        best = max(metrics["dev_history"], key=lambda row: row["eval_f1"])
        self.assertEqual(best["epoch"], metrics["selection"]["selected_epoch"])
        self.assertEqual(best["eval_f1"], metrics["selection"]["value"])

    def test_smoke_prediction_covers_all_ten_entities(self) -> None:
        label_map = json.loads(
            (EXPERIMENT / "label_map.json").read_text(encoding="utf-8")
        )
        smoke = json.loads(
            (EXPERIMENT / "smoke_prediction.json").read_text(encoding="utf-8")
        )
        self.assertEqual(smoke["result"], "passed")
        self.assertEqual(
            set(smoke["entity_coverage"]),
            set(label_map["entity_types"]),
        )

    def test_release_manifest_points_to_a_content_addressed_asset(self) -> None:
        release = json.loads(
            (EXPERIMENT / "release_manifest.json").read_text(encoding="utf-8")
        )
        asset = release["asset"]
        self.assertEqual(release["release"]["tag"], "ner-v1.0.0")
        self.assertEqual(len(asset["sha256"]), 64)
        self.assertGreater(asset["bytes"], 0)
        self.assertIn("not redistributed", release["release"]["availability"])
        self.assertIn("not redistributed", asset["distribution"])
        self.assertNotIn("download_url", asset)

    def test_training_runner_can_be_imported_without_ml_dependencies(self) -> None:
        path = ROOT / "scripts" / "train_ner_v1.py"
        spec = importlib.util.spec_from_file_location("train_ner_v1", path)
        self.assertIsNotNone(spec)
        self.assertIsNotNone(spec.loader)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        loaded = module.load_config(CONFIG)
        self.assertEqual(loaded["run_id"], "alamatin-mbert-ner-v1-seed42")

    def test_runtime_dependencies_are_exactly_pinned(self) -> None:
        lock = (ROOT / "requirements" / "ner-v1.lock").read_text(encoding="utf-8")
        requirements = [
            line.strip()
            for line in lock.splitlines()
            if line.strip() and not line.lstrip().startswith("#")
        ]
        self.assertGreater(len(requirements), 0)
        self.assertTrue(all(requirement.count("==") == 1 for requirement in requirements))


if __name__ == "__main__":
    unittest.main()
