from __future__ import annotations

import subprocess
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class RepositoryStructureTest(unittest.TestCase):
    def test_required_directories_exist(self) -> None:
        for directory in ("data", "scripts", "src", "web", "tests", "docs"):
            with self.subTest(directory=directory):
                self.assertTrue((ROOT / directory).is_dir())

    def test_required_foundation_files_exist(self) -> None:
        for filename in (
            ".gitignore",
            ".env.example",
            "README.md",
            "CONTRIBUTING.md",
            "requirements.lock",
        ):
            with self.subTest(filename=filename):
                self.assertTrue((ROOT / filename).is_file())

    def test_repository_policy_check_passes(self) -> None:
        result = subprocess.run(
            [sys.executable, "scripts/check_repository.py"],
            cwd=ROOT,
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
