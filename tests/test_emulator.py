# Copyright 2026 The Go Authors. All rights reserved.
# Use of this source code is governed by a BSD-style
# license that can be found in the LICENSE file.

"""Offline transport regression tests, not HarmonyOS execution evidence."""

import importlib.util
from pathlib import Path
import tempfile
import sys
import unittest
from unittest import mock

PATH = Path(__file__).resolve().parents[1] / "scripts/emulator/run.py"
SPEC = importlib.util.spec_from_file_location("emulator", PATH)
emulator = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(emulator)


class GuestStatusTest(unittest.TestCase):
    def test_host_command_timeout_is_bounded(self):
        with tempfile.TemporaryDirectory() as directory:
            runner = emulator.Runner(directory, directory)
            code, text = runner.run("timeout", [sys.executable, "-c", "import time; time.sleep(5)"],
                                    timeout=0.05, check=False)
            self.assertEqual(code, 124)
            self.assertIn("HOST TIMEOUT", text)

    def test_command_echo_is_excluded_from_guest_output(self):
        with tempfile.TemporaryDirectory() as directory:
            runner = emulator.Runner(directory, directory)
            code, text = runner.run("echo", [sys.executable, "-c", "print('actual output')"])
            self.assertEqual(code, 0)
            self.assertEqual(text, "actual output\n")

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

    def test_cleanup_race_preserves_original_failure_and_phase(self):
        with tempfile.TemporaryDirectory() as directory:
            runner = emulator.Runner(directory, directory)
            process = mock.Mock()
            process.poll.return_value = None

            def failed_test(payload):
                runner.phase = "cgo-and-abi"
                raise emulator.Failure("original cgo failure")

            with mock.patch.object(emulator.subprocess, "Popen", return_value=process), \
                 mock.patch.object(runner, "run", return_value=(0, "")), \
                 mock.patch.object(runner, "cli", return_value=(0, "")), \
                 mock.patch.object(runner, "shell", return_value=(0, "x86_64\n")), \
                 mock.patch.object(runner, "test", side_effect=failed_test), \
                 mock.patch.object(emulator.os, "killpg", side_effect=ProcessLookupError("exited")):
                with self.assertRaisesRegex(emulator.Failure, "original cgo failure"):
                    runner.boot(directory)
            self.assertEqual(runner.phase, "cgo-and-abi")


if __name__ == "__main__":
    unittest.main()
