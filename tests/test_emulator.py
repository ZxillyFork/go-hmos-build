# Copyright 2026 The Go Authors. All rights reserved.
# Use of this source code is governed by a BSD-style
# license that can be found in the LICENSE file.

"""Offline transport regression tests, not HarmonyOS execution evidence."""

import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest import mock

PATH = Path(__file__).resolve().parents[1] / "scripts/emulator/run.py"
SPEC = importlib.util.spec_from_file_location("emulator", PATH)
emulator = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(emulator)


class GuestStatusTest(unittest.TestCase):
    def test_success_requires_actual_guest_marker(self):
        self.assertEqual(emulator.guest_result("PASS\nTOKEN=0\n", "TOKEN"), 0)

    def test_guest_failure_is_not_hdc_success(self):
        self.assertEqual(emulator.guest_result("panic\nTOKEN=139\r\n", "TOKEN"), 139)

    def test_disconnected_hdc_with_zero_host_status_fails(self):
        with self.assertRaises(emulator.Failure):
            emulator.guest_result("[Fail][E001005] Device not found or connected\n", "TOKEN")

    def test_echoed_or_duplicate_marker_does_not_pass(self):
        for text in ("printf TOKEN=0\n", "TOKEN=0\nTOKEN=0\n", "TOKEN=garbage\n"):
            with self.subTest(text=text), self.assertRaises(emulator.Failure):
                emulator.guest_result(text, "TOKEN")

    def test_transport_failure_overrides_guest_marker(self):
        with tempfile.TemporaryDirectory() as directory:
            runner = emulator.Runner(directory, directory)
            with mock.patch.object(runner, "run", return_value=(124, "TOKEN=0\n")):
                with self.assertRaisesRegex(emulator.Failure, "host exit 124"):
                    runner.shell("test", "true")

    def test_nonzero_guest_status_stops_test(self):
        with tempfile.TemporaryDirectory() as directory:
            runner = emulator.Runner(directory, directory)
            with mock.patch.object(runner, "run", return_value=(0, "GO_HMOS_EXIT_abc=42\n")), \
                 mock.patch.object(emulator.secrets, "token_hex", return_value="abc"):
                with self.assertRaisesRegex(emulator.Failure, "guest exit 42"):
                    runner.shell("test", "false")

    def test_license_does_not_accept_without_exact_approved_package(self):
        with tempfile.TemporaryDirectory() as directory:
            runner = emulator.Runner(directory, directory)
            with mock.patch.dict(emulator.os.environ, {"HARMONYOS_ACCEPTED_CLI_SHA256": "wrong"}), \
                 mock.patch.object(runner, "cli") as cli:
                with self.assertRaisesRegex(emulator.Failure, "approval"):
                    runner.install()
                self.assertNotIn("accept", repr(cli.call_args_list))


if __name__ == "__main__":
    unittest.main()
