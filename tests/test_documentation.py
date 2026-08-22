"""Tests for the documentation checker (ALM-039).

The checker's value is entirely in what it *rejects*. A checker that passes
because its patterns never match anything is worse than none at all, so every
check here is proved non-vacuous against a fixture that must fail, and the
real documentation set is asserted clean.

Fixtures are written under a temporary directory inside the repository, because
``check_file`` reports paths relative to the repository root.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
import shutil
import unittest

ROOT = Path(__file__).resolve().parents[1]


def _load_module():
    path = ROOT / "scripts" / "check_documentation.py"
    spec = importlib.util.spec_from_file_location("check_documentation", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


checker = _load_module()


class DocumentationSetTest(unittest.TestCase):
    """The documentation actually in the repository must pass."""

    def test_repository_documentation_is_clean(self) -> None:
        report = checker.run()
        self.assertEqual(
            report["problems"], [], f"{report['problem_count']} problem(s)"
        )

    def test_the_check_is_not_vacuous(self) -> None:
        # A pass is only meaningful if documents were actually read.
        report = checker.run()
        self.assertGreater(report["documents_checked"], 20)

    def test_index_exists_and_lists_the_core_documents(self) -> None:
        text = (ROOT / "docs" / "README.md").read_text(encoding="utf-8")
        for name in (
            "architecture.md",
            "limitations.md",
            "evaluation-results.md",
            "release-candidate.md",
        ):
            self.assertIn(name, text)


class FileCheckTest(unittest.TestCase):
    """Each per-file check must reject the thing it claims to reject."""

    def setUp(self) -> None:
        self.scratch = ROOT / ".doc-check-fixtures"
        self.scratch.mkdir(exist_ok=True)
        self.addCleanup(shutil.rmtree, self.scratch, ignore_errors=True)

    def _write(self, name: str, text: str) -> Path:
        path = self.scratch / name
        path.write_text(text, encoding="utf-8", newline="\n")
        return path

    def test_clean_document_passes(self) -> None:
        path = self._write("clean.md", "# Title\n\nOrdinary prose.\n")
        self.assertEqual(checker.check_file(path), [])

    def test_unfinished_markers_are_rejected(self) -> None:
        for marker in ("TODO", "TBD", "FIXME", "XXX", "Lorem ipsum"):
            with self.subTest(marker=marker):
                path = self._write("m.md", f"# Title\n\n{marker}: finish this.\n")
                problems = checker.check_file(path)
                self.assertTrue(problems, f"{marker} was not flagged")

    def test_unfilled_angle_bracket_slots_are_rejected(self) -> None:
        table = self._write("t.md", "| metric | value |\n|---|---|\n| f1 | <number> |\n")
        self.assertTrue(checker.check_file(table))
        line = self._write("v.md", "Result: <value>\n")
        self.assertTrue(checker.check_file(line))

    def test_the_word_placeholder_in_prose_is_allowed(self) -> None:
        # The checker must not punish writing *about* placeholders.
        path = self._write(
            "prose.md", "The schema uses a placeholder value of null here.\n"
        )
        self.assertEqual(checker.check_file(path), [])

    def test_broken_relative_link_is_rejected(self) -> None:
        path = self._write("link.md", "See [gone](does-not-exist.md).\n")
        problems = checker.check_file(path)
        self.assertTrue(any("broken link" in problem for problem in problems))

    def test_resolving_relative_link_passes(self) -> None:
        self._write("target.md", "# Target\n")
        path = self._write("source.md", "See [target](target.md).\n")
        self.assertEqual(checker.check_file(path), [])

    def test_external_and_anchor_links_are_not_resolved(self) -> None:
        path = self._write(
            "ext.md",
            "[site](https://example.org/x) [mail](mailto:a@b.c) [here](#section)\n",
        )
        self.assertEqual(checker.check_file(path), [])

    def test_non_utf8_file_is_rejected(self) -> None:
        # cp1252 mangling of an ellipsis has happened in this repository before.
        path = self.scratch / "cp1252.md"
        path.write_bytes(b"# Title\n\nTruncated\x85 here.\n")
        problems = checker.check_file(path)
        self.assertTrue(any("not valid UTF-8" in problem for problem in problems))


class IndexCheckTest(unittest.TestCase):
    """The index check must match nested documents by path, not by filename."""

    def setUp(self) -> None:
        self.scratch = ROOT / ".doc-index-fixtures"
        (self.scratch / "docs" / "research").mkdir(parents=True, exist_ok=True)
        self.addCleanup(shutil.rmtree, self.scratch, ignore_errors=True)

        self.original_root = checker.ROOT
        self.original_index = checker.INDEX
        checker.ROOT = self.scratch
        checker.INDEX = self.scratch / "docs" / "README.md"

        def restore() -> None:
            checker.ROOT = self.original_root
            checker.INDEX = self.original_index

        self.addCleanup(restore)

        self.nested = self.scratch / "docs" / "research" / "deep.md"
        self.nested.write_text("# Deep\n", encoding="utf-8", newline="\n")

    def _index(self, body: str) -> None:
        checker.INDEX.write_text(body, encoding="utf-8", newline="\n")

    def test_nested_document_listed_by_path_is_accepted(self) -> None:
        # The bug this test pins: a basename comparison reported this missing.
        self._index("# Index\n\n- [Deep](research/deep.md)\n")
        self.assertEqual(checker.check_index([checker.INDEX, self.nested]), [])

    def test_unlisted_document_is_reported(self) -> None:
        self._index("# Index\n\nNothing listed.\n")
        problems = checker.check_index([checker.INDEX, self.nested])
        self.assertTrue(any("not listed" in problem for problem in problems))

    def test_index_listing_a_missing_document_is_reported(self) -> None:
        self._index("# Index\n\n- [Deep](research/deep.md)\n- [Ghost](ghost.md)\n")
        problems = checker.check_index([checker.INDEX, self.nested])
        self.assertTrue(any("missing document" in problem for problem in problems))

    def test_absent_index_is_reported(self) -> None:
        problems = checker.check_index([self.nested])
        self.assertTrue(any("missing" in problem for problem in problems))


if __name__ == "__main__":
    unittest.main()
