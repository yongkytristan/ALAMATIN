from __future__ import annotations

import importlib.util
from pathlib import Path
import re
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "verify_clean_clone", ROOT / "scripts" / "verify_clean_clone.py"
)
assert SPEC and SPEC.loader
VERIFY = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = VERIFY
SPEC.loader.exec_module(VERIFY)

DOCKERFILE = ROOT / "Dockerfile"
DOCKERIGNORE = ROOT / ".dockerignore"
COMPOSE = ROOT / "docker-compose.yml"


class ContainerDefinitionTest(unittest.TestCase):
    """The image must be reproducible, minimal, and unprivileged."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.dockerfile = DOCKERFILE.read_text(encoding="utf-8")
        cls.dockerignore = DOCKERIGNORE.read_text(encoding="utf-8")
        cls.compose = COMPOSE.read_text(encoding="utf-8")

    def test_base_image_pins_a_python_version(self) -> None:
        # "python:latest" would let the interpreter drift under the code's
        # dataclass(slots=True) requirement.
        self.assertRegex(self.dockerfile, r"FROM python:3\.11")

    def test_dependencies_are_hash_verified(self) -> None:
        self.assertIn("--require-hashes", self.dockerfile)
        self.assertIn("requirements.lock", self.dockerfile)

    def test_image_serves_the_wired_entrypoint(self) -> None:
        # alamatin.api:app is the transport with unconfigured handlers and
        # answers 503 by design; serving it would ship a dead API.
        self.assertIn("alamatin.service:app", self.dockerfile)
        self.assertNotRegex(self.dockerfile, r"CMD.*alamatin\.api:app")

    def test_image_declares_a_healthcheck(self) -> None:
        self.assertIn("HEALTHCHECK", self.dockerfile)
        self.assertIn("/health", self.dockerfile)

    def test_image_runs_as_a_non_root_user(self) -> None:
        self.assertRegex(self.dockerfile, r"USER\s+alamatin")

    def test_build_fails_when_the_application_cannot_import(self) -> None:
        # Without this the failure appears as a restarting container instead of
        # a failed build.
        self.assertIn("import alamatin.service", self.dockerfile)

    def test_governed_data_is_excluded_by_default(self) -> None:
        lines = {line.strip() for line in self.dockerignore.splitlines()}
        for excluded in ("data", "tests", "docs", "experiments", "node_modules"):
            with self.subTest(path=excluded):
                self.assertIn(excluded, lines)

    def test_only_the_approved_reference_is_copied_in(self) -> None:
        copied = re.findall(r"^COPY\s+(\S+)", self.dockerfile, re.MULTILINE)
        data_copies = [path for path in copied if path.startswith("data")]
        self.assertEqual(
            data_copies, ["data/processed/jabar-reference-v1-verified.json"]
        )

    def test_no_secret_is_baked_into_the_image(self) -> None:
        for forbidden in ("SSH_KEY", "API_KEY=", "PASSWORD", "SECRET="):
            with self.subTest(token=forbidden):
                self.assertNotIn(forbidden, self.dockerfile)
        # .env must be *excluded* from the build context, so its presence in
        # .dockerignore is the correct state.
        ignored = {line.strip() for line in self.dockerignore.splitlines()}
        self.assertIn(".env", ignored)
        self.assertIn(".env.*", ignored)
        self.assertIn("!.env.example", ignored)

    def test_compose_declares_a_healthcheck_and_no_extra_services(self) -> None:
        self.assertIn("healthcheck", self.compose)
        self.assertIn("read_only: true", self.compose)
        self.assertIn("no-new-privileges", self.compose)


class CleanCloneVerifierTest(unittest.TestCase):
    """The verifier must actually verify, and fail with an actionable message."""

    def test_it_passes_on_this_checkout(self) -> None:
        report = VERIFY.run(offline=False)
        detail = "; ".join(
            f"{item['check']}: {item['detail']}"
            for item in report["checks"]
            if item["ok"] is False
        )
        self.assertTrue(report["ok"], detail)

    def test_it_checks_every_runtime_file(self) -> None:
        for name in VERIFY.REQUIRED_RUNTIME_FILES:
            with self.subTest(path=name):
                self.assertTrue((ROOT / name).is_file())

    def test_a_missing_runtime_file_is_named_in_the_error(self) -> None:
        original = VERIFY.REQUIRED_RUNTIME_FILES
        VERIFY.REQUIRED_RUNTIME_FILES = (*original, "src/alamatin/does_not_exist.py")
        try:
            with self.assertRaises(VERIFY.CheckFailed) as caught:
                VERIFY.check_runtime_files()
        finally:
            VERIFY.REQUIRED_RUNTIME_FILES = original
        self.assertIn("does_not_exist.py", str(caught.exception))

    def test_an_old_interpreter_is_rejected_with_the_reason(self) -> None:
        original = VERIFY.MIN_PYTHON
        VERIFY.MIN_PYTHON = (99, 0)
        try:
            with self.assertRaises(VERIFY.CheckFailed) as caught:
                VERIFY.check_interpreter()
        finally:
            VERIFY.MIN_PYTHON = original
        self.assertIn("dataclass(slots=True)", str(caught.exception))

    def test_the_report_records_the_network_requirement(self) -> None:
        report = VERIFY.run(offline=True)
        self.assertFalse(report["network_needed_at_runtime"])
        self.assertTrue(report["network_needed_to_install_dependencies"])

    def test_startup_needs_no_committed_secret(self) -> None:
        # Recorded as a check so a future change that starts requiring one is
        # caught here rather than at a demo.
        self.assertIn("no secret needed to start", VERIFY.check_no_secret_required())


if __name__ == "__main__":
    unittest.main()
