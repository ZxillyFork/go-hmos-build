#!/usr/bin/env python3
# Copyright 2026 The Go Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license in LICENSE.
"""Normal app-process tests. Never grant permissions or change device policy."""
import json
import os
from pathlib import Path
import re
import secrets
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "emulator"))
from run import Runner, Failure, TARGET, digest

BUNDLE = "org.gohmos.networktest"
REQUIRED = {
    "identity", "core.GoCheck", "native.raw_tcp_bind", "go.raw_tcp_bind",
    "native.raw_udp_bind", "go.raw_udp_bind", "native.raw_udp_broadcast",
    "go.raw_udp_broadcast", "native.tcp_roundtrip", "go.tcp_roundtrip",
    "native.udp_roundtrip", "go.udp_roundtrip", "native.getifaddrs",
    "go.net_interfaces", "interfaces.addresses_match",
}


def extract_report(text, token):
    if "GO_HMOS_APP_ERROR_" + token + ":" in text:
        raise Failure("N-API app reported an error; see app-hilog log")
    pattern = r"GO_HMOS_APP_" + re.escape(token) + r"_(\d+)_(\d+):([^\r\n]*)"
    pieces = {}
    total = None
    for match in re.finditer(pattern, text):
        index, count, part = int(match[1]), int(match[2]), match[3]
        if count < 1 or count > 200 or index >= count or (total is not None and count != total):
            raise Failure("invalid/inconsistent app report chunks")
        total = count
        if index in pieces and pieces[index] != part:
            raise Failure("conflicting duplicate report chunks")
        pieces[index] = part
    if total is None or len(pieces) != total:
        return None
    try:
        envelope = json.loads("".join(pieces[i] for i in range(total)))
    except (ValueError, KeyError) as error:
        raise Failure("invalid app JSON (possibly truncated hilog)") from error
    if envelope.get("token") != token:
        raise Failure("app token mismatch")
    return envelope["report"]


def validate_report(report):
    if report.get("schema_version") != 1 or report.get("core_revision") != "b637b8617624655906b737977f50de5280bf7f65":
        raise Failure("unexpected app schema or core revision")
    identity = report.get("identity", {})
    if identity.get("goos") != "openharmony" or identity.get("goarch") != "amd64":
        raise Failure("app did not prove true GOOS=openharmony/amd64")
    if not isinstance(identity.get("uid"), int) or identity["uid"] < 10000:
        raise Failure("tests were not executed under a normal app UID")
    if not isinstance(identity.get("pid"), int) or identity["pid"] < 1:
        raise Failure("app PID is missing")
    rows = report.get("checks", [])
    names = [row["name"] for row in rows]
    if len(set(names)) != len(names) or not REQUIRED.issubset(names):
        raise Failure("missing/duplicate mandatory app checks")
    for row in rows:
        process = row.get("process", {})
        if process.get("uid") != identity["uid"] or process.get("pid") != identity["pid"]:
            raise Failure("a native/Go check did not run in the reported app process")
    failed = [row["name"] for row in rows if row.get("passed") is not True]
    if sorted(report.get("failed", [])) != sorted(failed):
        raise Failure("inconsistent failed-check list")
    if report.get("overall_pass") is not True or failed:
        raise Failure("app checks failed: " + ", ".join(failed))


def app_services_ready(text):
    # bm emits this header and list only after obtaining BMS/installer proxies
    # and successfully reading the installed bundle list. A shell is ready much
    # earlier during a cold boot; zero exit status alone is insufficient.
    return ("error:" not in text.lower() and
            re.search(r"^ID: [0-9]+:\r?\n\t[A-Za-z0-9_.]+\r?$", text, re.M) is not None)


class AppRunner(Runner):
    def diagnose_app(self, prefix):
        commands = {
            "boot": "param get bootevent.boot.completed; param get bootevent.bms.main.bundles.ready",
            "bundles": "bm dump -a",
            "hilog-help": "hilog -h",
            "hilog": "hilog -z 400",
        }
        for name, command in commands.items():
            try:
                self.shell(prefix + "-" + name, command, timeout=20, check=False)
            except (Failure, OSError) as error:
                self.record("app-diagnostic-error", probe=name, detail=str(error))

    def wait_for_app_services(self):
        self.phase = "app-service-readiness"
        deadline = time.monotonic() + 300
        attempt = 0
        while time.monotonic() < deadline:
            attempt += 1
            try:
                status, text = self.shell(f"app-service-ready-{attempt}", "bm dump -a",
                                          timeout=min(15, max(0.1, deadline-time.monotonic())),
                                          check=False)
                if status == 0 and app_services_ready(text):
                    self.record("app-services", passed=True, attempts=attempt)
                    self.shell("app-boot-completed", "param get bootevent.boot.completed", timeout=15, check=False)
                    self.shell("app-hilog-help", "hilog -h", timeout=15, check=False)
                    return
            except Failure as error:
                self.record("app-service-wait", attempt=attempt, detail=str(error))
            time.sleep(min(5, max(0, deadline-time.monotonic())))
        self.diagnose_app("app-readiness-failure")
        raise Failure("BMS/installer service not ready within 300 seconds; HAP was not installed")

    def test(self, payload):
        payload = Path(payload).resolve()
        hap = payload / "entry-default-unsigned.hap"
        if not hap.is_file():
            raise Failure("missing normal debug HAP")
        self.wait_for_app_services()
        self.phase = "app-install"
        self.record("app-package", sha256=digest(hap), permissions=["ohos.permission.INTERNET"],
                    signing="unsigned normal simulator install; no verifier changes")
        code, text = self.run("app-install", [self.tools / "hdc", "-t", TARGET, "install", hap],
                              env=self.env(), timeout=120, check=False)
        if code or not re.search(r"(?:install bundle successfully|install successfully)", text, re.I):
            self.diagnose_app("app-install-failure")
            raise Failure("ordinary HAP install failed; inspect app-install.log and diagnostics; no signing/security workaround applied")
        self.shell("app-bundle", f"bm dump -n {BUNDLE}", check=False)
        token = secrets.token_hex(16)
        self.phase = "app-launch"
        _, start = self.shell("app-start", f"aa start -a EntryAbility -b {BUNDLE} -m entry --ps token {token}")
        if not re.search(r"start ability successfully", start, re.I):
            raise Failure("normal ability launch did not report success")
        self.phase = "app-network"
        deadline = time.monotonic() + 180
        report = None
        attempt = 0
        while time.monotonic() < deadline:
            attempt += 1
            _, log = self.shell("app-hilog", "hilog -x -T GoHmosApp", timeout=min(20, max(0.1, deadline - time.monotonic())), check=False)
            report = extract_report(log, token)
            if report is not None:
                break
            time.sleep(min(5, max(0, deadline - time.monotonic())))
        if report is None:
            self.diagnose_app("app-report-missing")
            raise Failure("no complete fresh app report within 180 seconds")
        (self.logs / "app-report.json").write_text(json.dumps(report, indent=2) + "\n")
        self.record("app-report", report=report)
        identity = report.get("identity", {})
        pid = identity.get("pid")
        if isinstance(pid, int) and pid > 0:
            _, process = self.shell("app-process", f"cat /proc/{pid}/status; "
                                   f"cat /proc/{pid}/attr/current; cat /proc/{pid}/cmdline", check=False)
            uid_line = re.search(r"^Uid:\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s*$", process, re.M)
            pid_line = re.search(r"^Pid:\s+(\d+)\s*$", process, re.M)
            if (BUNDLE not in process or not uid_line or not pid_line or
                    int(pid_line[1]) != pid or
                    any(int(value) != identity.get("uid") for value in uid_line.groups())):
                raise Failure("reported PID/UID was not verified as the installed application")
        validate_report(report)
        self.phase = "complete"
        self.record("app-execution", passed=True, architecture="amd64", uid=identity["uid"],
                    scope="normal INTERNET-only app; same-process native C and Go loopback/options/interfaces")
        summary = os.environ.get("GITHUB_STEP_SUMMARY")
        if summary:
            with open(summary, "a") as output:
                output.write("PASS: normal x64 debug HAP with only INTERNET; native C and Go app network checks.\n")
                output.write("No ARM, physical device, public Internet/DNS, release signing or complete Go suite was tested.\n")


def main():
    runner = AppRunner(os.environ["EMULATOR_ROOT"], "app-diagnostics")
    try:
        runner.boot(".app-out")
    except (Failure, OSError, ValueError) as error:
        runner.record("failure", detail=str(error))
        summary = os.environ.get("GITHUB_STEP_SUMMARY")
        if summary:
            with open(summary, "a") as output:
                output.write(f"FAILED: {runner.phase}: {error}\n")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
