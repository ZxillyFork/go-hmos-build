#!/usr/bin/env python3
"""Host libc tests only: these do not validate an OpenHarmony app."""
import hashlib
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parent


class NativeFixtureTest(unittest.TestCase):
    def test_pinned_core_source_bytes(self):
        self.assertEqual(
            hashlib.sha256((ROOT / "core_smoke.go").read_bytes()).hexdigest(),
            "5785013b6ca9e3b11231fc9760a4c3c97ccc2c2e8d3295d7c85b9f64e7fed1b4",
        )

    def run_native(self, *arguments):
        cc = os.environ.get("HOST_CC", "cc")
        if not shutil.which(cc):
            self.skipTest(f"host compiler not available: {cc}")
        with tempfile.TemporaryDirectory() as directory:
            binary = str(Path(directory) / "network-native-test")
            subprocess.run(
                [cc, "-std=c11", "-Wall", "-Wextra", "-Werror", "-O2",
                 "-I", str(ROOT), str(ROOT / "native.c"),
                 str(ROOT / "host/native_test.c"), "-o", binary,
                 "-Wl,--wrap=bind", "-Wl,--wrap=setsockopt",
                 "-Wl,--wrap=getifaddrs", "-Wl,--wrap=freeifaddrs", "-Wl,--wrap=poll"],
                check=True, timeout=60,
            )
            result = subprocess.run([binary, *arguments], timeout=30, text=True, capture_output=True)
            if result.returncode == 77:
                self.skipTest(result.stdout.strip())
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("host-only", result.stdout)

    def test_host_libc_operations_and_failure_paths(self):
        self.run_native()

    def test_host_libc_interfaces(self):
        self.run_native("--interfaces")


if __name__ == "__main__":
    unittest.main()
