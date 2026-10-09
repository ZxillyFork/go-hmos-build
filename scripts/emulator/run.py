#!/usr/bin/env python3
# Copyright 2026 The Go Authors. All rights reserved.
# Use of this source code is governed by a BSD-style
# license that can be found in the LICENSE file.

"""Bounded official x64 emulator checks. Never substitute a host execution."""

import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import secrets
import shlex
import shutil
import signal
import struct
import subprocess
import sys
import time
import zipfile


MANIFEST = json.loads(Path(__file__).with_name("cli.json").read_text())
TARGET = "127.0.0.1:15555"
GUEST = "/data/local/tmp/go-hmos-ci"
NAME = "go_hmos_amd64_ci"


class Failure(Exception):
    pass


def digest(path):
    with Path(path).open("rb") as source:
        return hashlib.file_digest(source, "sha256").hexdigest()


def guest_result(output, marker):
    """HDC may exit zero even when disconnected. Require the guest's status."""
    matches = re.findall(r"^" + re.escape(marker) + r"=(\d+)\r?$", output, re.M)
    if len(matches) != 1:
        raise Failure("HDC transport: missing or duplicate guest exit marker")
    return int(matches[0])


class Runner:
    def __init__(self, root, logs):
        self.root = Path(root).resolve()
        self.logs = Path(logs).resolve()
        self.logs.mkdir(parents=True, exist_ok=True)
        self.emulator = self.root / "command-line-tools/emulator/Emulator"
        self.tools = self.root / "command-line-tools/sdk/default/openharmony/toolchains"
        self.images = self.root / "images"
        self.instances = self.root / "instances"
        self.phase = "initialization"
        self.results = []

    def record(self, name, **fields):
        row = {"name": name, "phase": self.phase, **fields}
        self.results.append(row)
        with (self.logs / "results.jsonl").open("a") as output:
            output.write(json.dumps(row) + "\n")
        print(json.dumps(row), flush=True)

    def env(self):
        env = dict(os.environ)
        env.update(QT_QPA_PLATFORM="offscreen",
                   QT_QPA_PLATFORM_PLUGIN_PATH=str(self.emulator.parent / "plugins/platforms"),
                   LD_LIBRARY_PATH=f"{self.emulator.parent}:{self.emulator.parent / 'lib'}:{self.tools}")
        return env

    def run(self, label, command, timeout=120, *, check=True, env=None, cwd=None,
            quiet=False, input_text=None):
        path = self.logs / (label + ".log")
        print(f"{self.phase}: {label}, timeout={timeout}s", flush=True)
        with path.open("w") as output:
            output.write("$ " + shlex.join(map(str, command)) + "\n")
            output.flush()
            proc = subprocess.Popen(list(map(str, command)), stdout=output,
                                    stderr=subprocess.STDOUT,
                                    stdin=subprocess.PIPE if input_text is not None else subprocess.DEVNULL,
                                    env=env, cwd=cwd, start_new_session=True)
            deadline = time.monotonic() + timeout
            pending_input = input_text.encode() if input_text is not None else None
            shown = 0
            while True:
                try:
                    proc.communicate(pending_input, timeout=min(30, max(0.001, deadline - time.monotonic())))
                    code = proc.returncode
                    break
                except subprocess.TimeoutExpired:
                    pending_input = None
                    # Leave progress in the live Actions log as well as the
                    # artifact; the job-log API is unavailable until completion.
                    progress = path.read_text(errors="replace")
                    if not quiet and len(progress) > shown:
                        print(progress[shown:][-4000:], flush=True)
                    shown = len(progress)
                    if time.monotonic() >= deadline:
                        try:
                            os.killpg(proc.pid, signal.SIGKILL)
                        except ProcessLookupError:
                            pass
                        try:
                            proc.communicate(timeout=10)
                        except subprocess.TimeoutExpired:
                            output.write("\nProcess did not exit after SIGKILL\n")
                        output.write(f"\nHOST TIMEOUT after {timeout}s\n")
                        code = 124
                        break
        text = path.read_text(errors="replace")
        if not quiet:
            print(text[-16000:], flush=True)
        self.record(label, exit_code=code)
        if check and code:
            raise Failure(f"{label}: exit {code}; see {path.name}")
        # Keep commands out of the returned text; a command can contain markers.
        return code, text.split("\n", 1)[1]

    def cli(self, label, *args, **kwargs):
        return self.run(label, [self.emulator, *args], env=self.env(),
                        cwd=self.emulator.parent, **kwargs)

    def hardware(self):
        self.phase = "virtualization"
        if platform.machine() != "x86_64":
            raise Failure("Only native Linux/x86_64 is supported; ARM is not tested")
        self.run("hardware", ["sh", "-c", "uname -a; id; df -h /; ls -l /dev/kvm"], check=False)
        try:
            with open("/dev/kvm", "rb+") as device:
                api = fcntl.ioctl(device.fileno(), 0xAE00, 0)
                vm = fcntl.ioctl(device.fileno(), 0xAE01, 0)
                os.close(vm)
        except OSError as error:
            raise Failure(f"KVM_CREATE_VM unavailable: {error}") from error
        self.record("KVM_CREATE_VM", api=api, passed=True)

    def download(self):
        self.phase = "download"
        self.root.mkdir(parents=True, exist_ok=True)
        if self.emulator.exists():
            raise Failure("Refusing a stale CLI installation; choose an empty root")
        archive = self.root / MANIFEST["archive"]
        self.run("download-cli", ["curl", "--proto", "=https", "--proto-redir", "=https",
                 "--fail", "--location", "--retry", "2", "--connect-timeout", "30",
                 "--max-time", "900", "--output", archive, MANIFEST["url"]], timeout=2800)
        actual = digest(archive)
        self.record("cli-checksum", sha256=actual, expected=MANIFEST["sha256"])
        if actual != MANIFEST["sha256"]:
            raise Failure("CLI SHA-256 mismatch; nothing was extracted or executed")
        shutil.copyfile(Path(__file__).with_name("cli.json"), self.logs / "cli-source.json")
        with zipfile.ZipFile(archive) as source:
            (self.logs / "cli-members.txt").write_text("\n".join(source.namelist()) + "\n")
            for item in source.infolist():
                if item.filename.startswith("/") or ".." in Path(item.filename).parts:
                    raise Failure("Unsafe CLI archive member")
        self.run("extract-cli", ["unzip", "-q", archive, "command-line-tools/emulator/*",
                 "command-line-tools/sdk/default/openharmony/toolchains/hdc",
                 "command-line-tools/sdk/default/openharmony/toolchains/libusb_shared.so",
                 "-d", self.root], timeout=180)
        archive.unlink()
        with self.emulator.open("rb") as source:
            header = source.read(20)
        if header[:6] != b"\x7fELF\x02\x01" or struct.unpack_from("<H", header, 18)[0] != 62:
            raise Failure("CLI is not the expected ELF64 x86_64 executable")
        self.cli("version", "-version")
        self.cli("help", "-help")

    def install(self):
        self.phase = "license"
        # This exact checksum was previously accepted in the owner's linked run.
        # Changing the package requires re-reviewing its agreements, not carrying
        # forward approval to new terms. Viewing with EOF never answers yes.
        if os.environ.get("HARMONYOS_ACCEPTED_CLI_SHA256") != MANIFEST["sha256"]:
            self.cli("license-view", "-license", check=False, timeout=30, input_text="n\n")
            raise Failure("Explicit approval of this CLI's agreements is required")
        # List available license resources and view with negative answers before
        # any acceptance. Missing/changed agreement text must stop the workflow.
        candidates = []
        for path in sorted(self.emulator.parent.rglob("*")):
            if path.is_file() and re.search("license|agreement|eula", path.name, re.I):
                candidates.append({"path": str(path.relative_to(self.emulator.parent)),
                                   "size": path.stat().st_size, "sha256": digest(path)})
        self.record("license-resources", files=candidates)
        _, text = self.cli("license-view", "-license", check=False, timeout=30,
                           input_text="n\nn\nn\nn\nn\n")
        from licenses import verify
        verify(self.emulator.parent, text)
        self.cli("license", "-license", "accept")
        self.phase = "image-download"
        self.cli("image-catalog", "-imageList", "-deviceType", "2in1", "-downloaded", "false", timeout=180)
        try:
            self.cli("install-image", "-install", "-deviceType", "2in1", "-osVersion",
                     MANIFEST["image_version"], "-imageRoot", self.images, "-force", timeout=2400)
        finally:
            self.run("image-files", ["find", self.images, "-maxdepth", "5", "-type", "f",
                                     "-printf", "%P %s bytes\n"], check=False)
        systems = list(self.images.glob("system-image/HarmonyOS-6.1.1/pc*/system.img"))
        if len(systems) != 1:
            raise Failure("Expected exactly one official PC system image after installation")
        self.record("system-image", path=str(systems[0].relative_to(self.images)),
                    size=systems[0].stat().st_size, sha256=digest(systems[0]))
        self.run("hdc-version", [self.tools / "hdc", "-v"], env=self.env())
        self.phase = "emulator-configuration"
        self.instances.mkdir(exist_ok=True)
        # -stop and -logZip consult defaults, unlike -start and -create. Configure
        # these once so cleanup addresses this isolated instance, not another one.
        self.cli("configure", "-config", "-instancePath", self.instances, "-imageRoot", self.images)
        self.cli("create", "-create", NAME, "-deviceType", "2in1", "-osVersion",
                 MANIFEST["image_version"], "-imageRoot", self.images, "-instancePath",
                 self.instances, "-storage", "6", "-memory", "4", "-hotBoot", "false")
        if not (self.instances / NAME).is_dir():
            raise Failure("CLI reported success without creating the requested instance")

    def shell(self, label, command, timeout=150, *, check=True):
        marker = "GO_HMOS_EXIT_" + secrets.token_hex(12)
        wrapped = f"( {command} ); status=$?; printf '\\n{marker}=%s\\n' \"$status\""
        code, output = self.run(label, [self.tools / "hdc", "-t", TARGET, "shell", wrapped],
                                timeout=timeout, env=self.env(), check=False)
        if code:
            raise Failure(f"HDC transport/timeout for {label}: host exit {code}")
        status = guest_result(output, marker)
        self.record(label + "-guest", exit_code=status)
        if check and status:
            raise Failure(f"{label}: guest exit {status}")
        return status, output

    def boot(self, payload):
        self.phase = "emulator-boot"
        output = (self.logs / "start.log").open("w")
        command = [self.emulator, "-start", NAME, "-instancePath", self.instances,
                   "-imageRoot", self.images, "-hdcPort", "15555", "-bootMode", "reset", "-noWindow"]
        process = subprocess.Popen(list(map(str, command)), stdout=output, stderr=subprocess.STDOUT,
                                   stdin=subprocess.DEVNULL, env=self.env(), cwd=self.emulator.parent,
                                   start_new_session=True)
        try:
            deadline = time.monotonic() + 300
            attempt = 0
            while time.monotonic() < deadline:
                attempt += 1
                self.run(f"connect-{attempt}", [self.tools / "hdc", "tconn", TARGET],
                         timeout=15, check=False, env=self.env(), quiet=True)
                try:
                    _, text = self.shell(f"ready-{attempt}", "uname -m", timeout=15)
                    if "x86_64" not in text.splitlines():
                        raise Failure("Unexpected guest architecture: " + text)
                    break
                except Failure as error:
                    self.record("boot-wait", attempt=attempt, detail=str(error))
                if process.poll() not in (None, 0):
                    raise Failure(f"Emulator launcher exited {process.returncode}")
                time.sleep(5)
            else:
                raise Failure("No verified x86_64 HDC shell within 300 seconds")
            self.phase = "guest-identification"
            self.shell("guest-identity", "id; uname -a; param get const.ohos.fullname; "
                       "param get const.ohos.apiversion; getconf PAGE_SIZE; "
                       "ls -l /lib/ld-musl-x86_64.so.1 /system/lib64/libc.so; mount", check=False)
            self.test(payload)
        finally:
            original_phase = self.phase
            self.phase = "cleanup"
            # Diagnostics must never prevent the stop attempt or hide a test failure.
            try:
                self.cli("collect-logs", "-logZip", NAME, "-logPath", self.logs / "emulator-logs",
                         check=False, timeout=45)
            except (Failure, OSError) as error:
                self.record("collect-logs-error", detail=str(error))
            try:
                self.cli("stop", "-stop", NAME, check=False, timeout=30)
            except (Failure, OSError) as error:
                self.record("stop-error", detail=str(error))
            try:
                if process.poll() is None:
                    try:
                        os.killpg(process.pid, signal.SIGTERM)
                        process.wait(timeout=15)
                    except subprocess.TimeoutExpired:
                        try:
                            os.killpg(process.pid, signal.SIGKILL)
                            process.wait(timeout=5)
                        except (OSError, subprocess.TimeoutExpired) as error:
                            self.record("kill-error", detail=str(error))
                    except OSError as error:
                        self.record("terminate-error", detail=str(error))
                output.close()
                print((self.logs / "start.log").read_text(errors="replace")[-16000:], flush=True)
            except OSError as error:
                self.record("cleanup-error", detail=str(error))
            finally:
                self.phase = original_phase

    def test(self, payload):
        self.phase = "file-transfer"
        payload = Path(payload).resolve()
        rows = []
        for line in (payload / "stdlib-tests.tsv").read_text().splitlines():
            if line and not line.startswith("#"):
                fields = line.split("\t")
                if len(fields) != 4 or not fields[3].isdigit() or not 1 <= int(fields[3]) <= 300:
                    raise Failure("Invalid stdlib test manifest")
                rows.append(fields)
        if not rows:
            raise Failure("Empty stdlib test manifest")
        files = {"hello", "loader", "libgo_hmos_test.so", "libgo_hmos_netgo.so", "emulator-native-probe",
                 "emulator-smoke", "emulator-cgo-smoke", *(row[1] for row in rows)}
        self.shell("prepare-guest", f"mkdir -p {GUEST}/home {GUEST}/tmp")
        for name in sorted(files):
            if not re.fullmatch(r"[a-zA-Z0-9_.-]+", name) or not (payload / name).is_file():
                raise Failure(f"Missing or unsafe payload filename: {name}")
            self.run("send-" + name, [self.tools / "hdc", "-t", TARGET, "file", "send",
                     payload / name, GUEST + "/" + name], env=self.env(), timeout=90)
            sha = digest(payload / name)
            self.shell("verify-" + name, f"cd {GUEST} && test \"$(sha256sum {name} | cut -d ' ' -f 1)\" = {sha} && chmod 755 {name}")
        prefix = f"cd {GUEST} && export HOME={GUEST}/home TMPDIR={GUEST}/tmp GOMAXPROCS=4 && "
        self.phase = "native-abi"
        _, native = self.shell("native-abi", prefix + "./emulator-native-probe")
        if "PASS: OpenHarmony native C ABI" not in native:
            raise Failure("Native C ABI probe did not report success")
        self.phase = "runtime-startup"
        _, hello = self.shell("hello", prefix + "./hello")
        if "openharmony/amd64 (runtime.GOOS=openharmony)" not in hello:
            raise Failure("hello did not prove runtime.GOOS=openharmony/amd64")
        self.phase = "runtime"
        failures = []
        status, text = self.shell("runtime-smoke", prefix + "./emulator-smoke", check=False)
        if status or "PASS: emulator-smoke" not in text:
            failures.append("runtime-smoke")
        self.phase = "cgo-and-abi"
        status, text = self.shell("cgo-smoke", prefix + "./emulator-cgo-smoke", check=False)
        if status or "PASS: emulator-cgo-smoke" not in text:
            failures.append("cgo-smoke")
        for lib in ("libgo_hmos_test.so", "libgo_hmos_netgo.so"):
            status, text = self.shell("dlopen-" + lib, prefix + "./loader ./" + lib, check=False)
            if status or "PASS: dlopen" not in text or "PASS: 100 interface-discovery calls" not in text:
                failures.append("dlopen-" + lib)
        self.phase = "stdlib"
        for package, binary, pattern, seconds in rows:
            status, text = self.shell("stdlib-" + package.replace("/", "_"), prefix +
                                 shlex.join(["./" + binary, "-test.v", "-test.short", "-test.count=1",
                                             "-test.timeout=" + seconds + "s", "-test.run=" + pattern]),
                                 timeout=int(seconds) + 30, check=False)
            invalid = bool(status)
            if not re.search(r"^=== RUN\s+Test", text, re.M) or not re.search(r"^PASS\r?$", text, re.M):
                invalid = True
            if "no tests to run" in text:
                invalid = True
            passed = re.findall(r"^--- PASS: (Test\w+)", text, re.M)
            skipped = re.findall(r"^--- SKIP: (Test\w+)", text, re.M)
            selected = set(re.findall(r"Test\w+", pattern))
            started = set(re.findall(r"^=== RUN\s+(Test\w+)\s*$", text, re.M))
            missing = sorted(selected - started)
            self.record("stdlib-cases", package=package, passed=passed, skipped=skipped, missing=missing)
            if invalid or not passed or missing:
                failures.append(package)
        if failures:
            self.phase = "target-tests"
            raise Failure("Target test groups failed: " + ", ".join(failures))
        self.phase = "complete"
        self.record("device-execution", passed=True, architecture="amd64",
                    scope="hello/runtime/cgo/dlopen/netgo/focused-stdlib; not the full Go suite")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("hardware", "download", "install", "test"))
    parser.add_argument("--root", default=os.environ.get("EMULATOR_ROOT", "/tmp/go-hmos-emulator"))
    parser.add_argument("--logs", default="emulator-diagnostics")
    parser.add_argument("--payload", default="openharmony-out/amd64")
    args = parser.parse_args()
    runner = Runner(args.root, args.logs)
    try:
        if args.action == "test":
            runner.boot(args.payload)
        else:
            getattr(runner, args.action)()
    except (Failure, OSError, ValueError) as error:
        runner.record("failure", detail=str(error))
        if os.environ.get("GITHUB_STEP_SUMMARY"):
            with open(os.environ["GITHUB_STEP_SUMMARY"], "a") as output:
                output.write(f"FAILED: {runner.phase}: {error}\n")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
