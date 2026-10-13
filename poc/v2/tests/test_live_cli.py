"""Offline smoke CLI security checks: intentionally no API requests."""
import copy
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from v2_poc.coordinator import run
from v2_poc.live import BUNDLED_FIXTURE, FIXTURE_SHA256, read_bundled_fixture


class SmokeSafetyTests(unittest.TestCase):
    def test_bundled_fixture_hash_and_offline_run(self):
        self.assertEqual(len(FIXTURE_SHA256), 64)
        self.assertTrue(run(read_bundled_fixture(BUNDLED_FIXTURE))["simulation"])

    def test_refuse_other_path_even_when_content_identical(self):
        with tempfile.TemporaryDirectory() as directory:
            new_path = Path(directory) / "same.json"
            new_path.write_bytes(BUNDLED_FIXTURE.read_bytes())
            with self.assertRaisesRegex(ValueError, "only the bundled"):
                read_bundled_fixture(new_path)

    def test_refuse_changed_fixture_without_any_api_call(self):
        with patch("v2_poc.live.FIXTURE_SHA256", "0" * 64):
            with self.assertRaisesRegex(ValueError, "fixture changed"):
                read_bundled_fixture(BUNDLED_FIXTURE)

    def test_check_only_no_key_and_no_sdk_needed(self):
        process = subprocess.run(
            [sys.executable, "-m", "v2_poc.live", str(BUNDLED_FIXTURE), "--check-only"],
            cwd=BUNDLED_FIXTURE.parent.parent, text=True, capture_output=True, check=True,
        )
        status = json.loads(process.stdout)
        self.assertEqual(status["mode"], "offline_check_only")
        self.assertEqual(status["model_calls"], 0)
        self.assertFalse(status["writes_permitted"])
        self.assertEqual(status["max_specialist_calls"], 3)
        self.assertTrue(status["fixture_verified"])

    def test_refuse_api_without_flag(self):
        process = subprocess.run(
            [sys.executable, "-m", "v2_poc.live", str(BUNDLED_FIXTURE)],
            cwd=BUNDLED_FIXTURE.parent.parent, text=True, capture_output=True,
        )
        self.assertNotEqual(process.returncode, 0)
        self.assertIn("disabled", process.stderr)


if __name__ == "__main__":
    unittest.main()
