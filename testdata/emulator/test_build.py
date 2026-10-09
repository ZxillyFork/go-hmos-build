# Copyright 2026 The Go Authors. All rights reserved.
# Use of this source code is governed by a BSD-style
# license that can be found in the LICENSE file.

"""Offline manifest and failure-path checks, never target validation."""

import os
from pathlib import Path
import re
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/build-emulator-tests.sh"


class EmulatorBuildTest(unittest.TestCase):
    def run_script(self, **updates):
        env = dict(os.environ, **updates)
        return subprocess.run([str(SCRIPT)], env=env, capture_output=True, text=True)

    def source_fixture(self, root):
        (root / "src").mkdir()
        (root / "src/make.bash").touch()
        (root / "VERSION").write_text("offline-metadata-only\n")

    def test_missing_sdk_fails_closed(self):
        result = self.run_script(OHOS_NDK_HOME="")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Set OHOS_NDK_HOME", result.stderr)

    def test_wrong_architecture_fails_before_building(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.source_fixture(root)
            result = self.run_script(GO_SOURCE_ROOT=directory, GOARCH="arm64",
                                     OHOS_NDK_HOME=directory,
                                     GO_HMOS_CACHE_ROOT=str(root / "cache"))
            self.assertEqual(result.returncode, 2, result.stderr)
            self.assertIn("require GOARCH=amd64", result.stderr)

    def test_missing_compiler_fails_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.source_fixture(root)
            result = self.run_script(GO_SOURCE_ROOT=directory, GOARCH="amd64",
                                     OHOS_NDK_HOME=directory,
                                     GO_HMOS_CACHE_ROOT=str(root / "cache"))
            self.assertEqual(result.returncode, 2, result.stderr)
            self.assertIn("/llvm/bin/clang", result.stderr)

    def test_manifest_has_explicit_nonempty_selections(self):
        entries = {}
        manifest = ROOT / "testdata/emulator/stdlib-tests.tsv"
        for line in manifest.read_text().splitlines():
            if not line or line.startswith("#"):
                continue
            package, binary, selection, timeout = line.split("\t")
            self.assertNotIn(package, entries)
            self.assertRegex(package, r"^[a-z][a-z0-9/]*$")
            self.assertEqual(binary, package.replace("/", "_") + ".test")
            self.assertRegex(selection, r"^\^\(Test\w+(\|Test\w+)*\)\$$")
            names = selection[2:-2].split("|")
            self.assertEqual(len(names), len(set(names)))
            self.assertTrue(all(re.fullmatch(selection, name) for name in names))
            self.assertTrue(0 < int(timeout) <= 120)
            entries[package] = names
        self.assertEqual(len(entries), 18)
        self.assertTrue({"runtime", "time", "net", "os/signal", "runtime/pprof",
                         "crypto/x509", "math", "sync", "sync/atomic"} <= entries.keys())


if __name__ == "__main__":
    unittest.main()
