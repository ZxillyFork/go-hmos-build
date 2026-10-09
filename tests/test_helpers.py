# Copyright 2026 The Go Authors. All rights reserved.
# Use of this source code is governed by a BSD-style
# license that can be found in the LICENSE file.

"""Offline regression tests: these fake SDKs are never target validation."""
import hashlib
import io
import json
import os
import re
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
        for revision in ("main", "v1.27.2", "a" * 39, "A" * 40, "0" * 40,
                         "a" * 40 + "\ncore_sha=main"):
            with self.subTest(revision=revision):
                self.assertNotEqual(run("source-pin.py", args=("--revision", revision)).returncode, 0)

    def test_manifest_repository_and_bootstrap(self):
        manifest = json.loads((ROOT / "source.json").read_text())
        self.assertEqual(manifest["repository"], "ZxillyFork/go-hmos")
        self.assertEqual(manifest["bootstrap_version"], "1.27.2")


class HostEnvironmentTest(unittest.TestCase):
    def test_security_tests_use_current_module_defaults(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "src").mkdir()
            (root / "src/make.bash").touch()
            (root / "VERSION").write_text("go1.27.2-hmos-devel\n")
            (root / "bin").mkdir()
            go = root / "bin/go"
            go.write_text('''#!/usr/bin/env python3
import json, os, sys
with open(os.environ["MOCK_HOST_LOG"], "a") as log:
    log.write(json.dumps({"args": sys.argv[1:], "cwd": os.getcwd(),
                          "module": os.environ.get("GO111MODULE"),
                          "gopath": os.environ.get("GOPATH")}) + "\\n")
if sys.argv[1] == "tool":
    print("go1.27.2-hmos-devel buildID=offline-fixture")
''')
            go.chmod(0o755)
            log = root / "host.jsonl"
            result = run("test-host.sh", env={"GO_SOURCE_ROOT": directory,
                         "GO_HMOS_CACHE_ROOT": str(root / "cache"),
                         "MOCK_HOST_LOG": str(log)})
            self.assertEqual(result.returncode, 0, result.stderr)
            calls = [json.loads(line) for line in log.read_text().splitlines()]
            security = [call for call in calls if "-count=1" in call["args"]]
            self.assertEqual(len(security), 3)
            for call in security:
                self.assertEqual(call["cwd"], str(root / "src"))
                self.assertEqual(call["module"], "on")
                self.assertEqual(call["gopath"], str(root / "cache/gopath"))
            self.assertIn("crypto/tls", security[0]["args"])
            self.assertIn("os", security[1]["args"])
            self.assertIn("-race", security[2]["args"])


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


class WorkflowTest(unittest.TestCase):
    def test_job_environment_uses_supported_contexts(self):
        workflow = (ROOT / ".github/workflows/openharmony.yml").read_text()
        allowed = {"github", "needs", "strategy", "matrix", "vars", "secrets", "inputs"}
        # This workflow's job-level env entries are six-space uppercase keys.
        # runner is available at step scope, but invalid at job env scope.
        for line in workflow.splitlines():
            if re.match(r"^ {6}[A-Z_]+:", line):
                for context in re.findall(r"\$\{\{\s*(\w+)\.", line):
                    self.assertIn(context, allowed, line)


class BuildPreconditionTest(unittest.TestCase):
    def test_missing_sdk_fails_closed(self):
        result = run("build.sh", env={"OHOS_NDK_HOME": ""})
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Set OHOS_NDK_HOME", result.stderr)

    def test_fixture_build_uses_relative_package_path(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "src").mkdir()
            (root / "src/make.bash").touch()
            (root / "VERSION").write_text("go1.27.2-hmos-devel\n")
            fixtures = root / "src/cmd/cgo/internal/testcshared/testdata/openharmony"
            for name in ("library/main.go", "hello/main.go", "loader.c"):
                target = fixtures / name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.touch()
            native = root / "native"
            (native / "llvm/bin").mkdir(parents=True)
            (native / "sysroot/usr/include").mkdir(parents=True)
            for name in ("clang", "clang++", "llvm-readelf"):
                tool = native / "llvm/bin" / name
                tool.write_text("#!/bin/sh\nexit 0\n")
                tool.chmod(0o755)
            (root / "bin").mkdir()
            go = root / "bin/go"
            go.write_text("#!/usr/bin/env python3\nimport json,os,sys\n"
                          "from pathlib import Path\n"
                          "if sys.argv[1] == 'build':\n"
                          "    Path(os.environ['MOCK_BUILD_LOG']).write_text(json.dumps({'cwd':os.getcwd(),'args':sys.argv[1:]}))\n"
                          "    sys.exit(77)\n")
            go.chmod(0o755)
            git = root / "bin/git"
            git.write_text("#!/bin/sh\nprintf '%s\\n' aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa\n")
            git.chmod(0o755)
            log = root / "build.json"
            out = root / "out"
            result = run("build.sh", env={"OHOS_NDK_HOME": str(native),
                         "GO_SOURCE_ROOT": directory, "GOARCH": "arm64",
                         "GO_HMOS_CACHE_ROOT": str(root / "cache"), "OUT_DIR": str(out),
                         "PATH": str(root / "bin") + os.pathsep + os.environ["PATH"],
                         "MOCK_BUILD_LOG": str(log)})
            self.assertEqual(result.returncode, 77, result.stderr)
            invocation = json.loads(log.read_text())
            self.assertEqual(invocation["cwd"], str(fixtures))
            self.assertEqual(invocation["args"][-1], "./library")
            self.assertIn("exit_status=77", (out / "build-status.txt").read_text())
            script = (ROOT / "scripts/build.sh").read_text()
            self.assertNotIn('"$fixtures/library"', script)
            self.assertNotIn('"$fixtures/hello"', script)

    def test_unsupported_architecture(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "src").mkdir()
            (root / "src/make.bash").touch()
            (root / "VERSION").write_text("go1.27.2-hmos-devel\n")
            result = run("build.sh", env={"OHOS_NDK_HOME": directory,
                         "GO_SOURCE_ROOT": directory, "GOARCH": "riscv64",
                         "GO_HMOS_CACHE_ROOT": str(root / "cache")})
            self.assertEqual(result.returncode, 2)
            self.assertIn("unsupported GOARCH=riscv64", result.stderr)


if __name__ == "__main__":
    unittest.main()
