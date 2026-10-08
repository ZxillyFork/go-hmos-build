# Copyright 2026 The Go Authors. All rights reserved.
# Use of this source code is governed by a BSD-style
# license that can be found in the LICENSE file.

"""Offline regression tests: these fake SDKs are never target validation."""
import hashlib
import io
import json
import os
from pathlib import Path
import stat
import subprocess
import tarfile
import tempfile
import unittest
import zipfile

ROOT = Path(__file__).resolve().parent.parent


def run(script, *, env=None, args=()):
    environment = dict(os.environ)
    environment.update(env or {})
    return subprocess.run([str(ROOT / "scripts" / script), *args], env=environment,
                          capture_output=True, text=True)


class SourcePinTest(unittest.TestCase):
    def test_explicit_sha(self):
        result = run("source-pin.py", args=("--revision", "a" * 40))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), "a" * 40)

    def test_moving_or_malformed_refs_rejected(self):
        for revision in ("main", "v1.27.1", "a" * 39, "A" * 40, "0" * 40,
                         "a" * 40 + "\ncore_sha=main"):
            with self.subTest(revision=revision):
                self.assertNotEqual(run("source-pin.py", args=("--revision", revision)).returncode, 0)

    def test_manifest_repository_and_bootstrap(self):
        manifest = json.loads((ROOT / "source.json").read_text())
        self.assertEqual(manifest["repository"], "ZxillyFork/go-hmos")
        self.assertEqual(manifest["bootstrap_version"], "1.27.1")


class SDKDownloadTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.path = Path(self.temporary.name)
        self.bin = self.path / "bin"
        self.bin.mkdir()
        self.download = self.path / "download"
        self.fixture = self.path / "sdk.tar.gz"
        self.checksum = self.path / "sdk.sha256"
        curl = self.bin / "curl"
        curl.write_text('''#!/usr/bin/env python3
import os
from pathlib import Path
import shutil
import sys
args = sys.argv[1:]
url = next(arg for arg in args if arg.startswith("https://"))
assert url.startswith("https://repo.huaweicloud.com/openharmony/os/6.1-Release/")
target = args[args.index("-o") + 1]
source = os.environ["MOCK_CHECKSUM"] if url.endswith(".sha256") else os.environ["MOCK_ARCHIVE"]
shutil.copyfile(source, target)
''')
        curl.chmod(0o755)
        self.env = {"PATH": str(self.bin) + os.pathsep + os.environ["PATH"],
                    "SDK_DOWNLOAD_DIR": str(self.download),
                    "MOCK_ARCHIVE": str(self.fixture), "MOCK_CHECKSUM": str(self.checksum)}
        self.make_archive()

    def make_archive(self, *, compiler=True):
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as archive:
            for name in ("clang-15", "llvm-readelf"):
                if name.startswith("clang") and not compiler:
                    continue
                info = zipfile.ZipInfo("native/llvm/bin/" + name)
                info.create_system = 3
                info.external_attr = (stat.S_IFREG | 0o755) << 16
                archive.writestr(info, "#!/bin/sh\nexit 0\n")
            if compiler:
                for name in ("clang", "clang++"):
                    info = zipfile.ZipInfo("native/llvm/bin/" + name)
                    info.create_system = 3
                    info.external_attr = (stat.S_IFLNK | 0o777) << 16
                    archive.writestr(info, "clang-15")
            archive.writestr("native/sysroot/usr/include/pthread.h", "/* offline fixture */\n")
        data = buffer.getvalue()
        with tarfile.open(self.fixture, "w:gz") as archive:
            info = tarfile.TarInfo("ohos-sdk/linux/native-linux-test.zip")
            info.size = len(data)
            archive.addfile(info, io.BytesIO(data))
        self.checksum.write_text(hashlib.sha256(self.fixture.read_bytes()).hexdigest() + "\n")

    def test_discovers_valid_clang_symlinks(self):
        result = run("download-sdk.sh", env=self.env)
        self.assertEqual(result.returncode, 0, result.stderr)
        native = Path((self.download / "native-path.txt").read_text().strip())
        self.assertTrue((native / "llvm/bin/clang").is_symlink())
        self.assertTrue(os.access(native / "llvm/bin/clang", os.X_OK))
        self.assertEqual((self.download / "sdk.sha256").read_bytes(), self.checksum.read_bytes())
        self.assertEqual(list(self.download.glob(".sdk-download.*")), [])

    def test_checksum_mismatch_fails_before_extraction(self):
        self.checksum.write_text("0" * 64 + "\n")
        result = run("download-sdk.sh", env=self.env)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("FAILED", result.stdout)
        self.assertFalse((self.download / "native-path.txt").exists())
        self.assertFalse((self.download / "extracted").exists())

    def test_html_checksum_fails_closed(self):
        self.checksum.write_text("<html>Site Unavailable</html>\n")
        result = run("download-sdk.sh", env=self.env)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("official checksum unavailable or invalid", result.stderr)

    def test_missing_compiler_reports_layout(self):
        self.make_archive(compiler=False)
        result = run("download-sdk.sh", env=self.env)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("actual SDK layout", result.stderr)
        self.assertFalse((self.download / "native-path.txt").exists())

    def test_existing_sdk_is_not_overwritten(self):
        self.download.mkdir()
        marker = self.download / "native-path.txt"
        marker.write_text("keep existing SDK\n")
        result = run("download-sdk.sh", env=self.env)
        self.assertEqual(result.returncode, 2)
        self.assertEqual(marker.read_text(), "keep existing SDK\n")


class BuildPreconditionTest(unittest.TestCase):
    def test_missing_sdk_fails_closed(self):
        result = run("build.sh", env={"OHOS_NDK_HOME": ""})
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Set OHOS_NDK_HOME", result.stderr)

    def test_unsupported_architecture(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "src").mkdir()
            (root / "src/make.bash").touch()
            (root / "VERSION").write_text("go1.27.1-hmos-devel\n")
            result = run("build.sh", env={"OHOS_NDK_HOME": directory,
                         "GO_SOURCE_ROOT": directory, "GOARCH": "riscv64",
                         "GO_HMOS_CACHE_ROOT": str(root / "cache")})
            self.assertEqual(result.returncode, 2)
            self.assertIn("unsupported GOARCH=riscv64", result.stderr)


if __name__ == "__main__":
    unittest.main()
