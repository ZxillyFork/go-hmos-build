#!/usr/bin/env python3
"""Validate release identity and create transparent, unsigned build provenance."""
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]


def config():
    release = json.loads((ROOT / "sdk-release.json").read_text())
    source = json.loads((ROOT / "source.json").read_text())
    if not re.fullmatch(r"go1\.\d+\.\d+-hmos\.\d+", release["release_tag"]):
        raise ValueError("release_tag must be a versioned HMOS prerelease")
    if not re.fullmatch(r"go1\.\d+\.\d+-hmos-devel", release["go_version"]):
        raise ValueError("expected distinct HMOS compiler identity")
    if release["release_tag"].split("-hmos")[0] != release["go_version"].split("-hmos")[0]:
        raise ValueError("release and compiler base versions differ")
    if (release["host_os"], release["host_arch"]) != ("linux", "amd64"):
        raise ValueError("only tested linux/amd64 host packages are supported")
    for sha in (release["setup_go_commit"], source["revision"]):
        if not re.fullmatch(r"[0-9a-f]{40}", sha) or sha == "0" * 40:
            raise ValueError("full nonzero commit SHA required")
    if source["repository"] != "ZxillyFork/go-hmos":
        raise ValueError("unexpected source repository")
    return release, source


def provenance():
    release, source = config()
    build_sha = subprocess.check_output(["git", "-C", str(ROOT), "rev-parse", "HEAD"], text=True).strip()
    run_id = os.environ.get("GITHUB_RUN_ID")
    return {
        "schema_version": 1,
        "release_tag": release["release_tag"],
        "go_version": release["go_version"],
        "host": "linux/amd64",
        "targets": ["openharmony/amd64", "openharmony/arm64"],
        "source_repository": source["repository"],
        "source_commit": source["revision"],
        "source_branch": "hmos-release-branch.go1.27",
        "build_repository": "ZxillyFork/go-hmos-build",
        "build_commit": build_sha,
        "build_run_url": f"https://github.com/ZxillyFork/go-hmos-build/actions/runs/{run_id}" if run_id else None,
        "bootstrap_version": source["bootstrap_version"],
        "setup_go_commit": release["setup_go_commit"],
        "native_sdk_included": False,
        "provenance_kind": "unsigned build metadata; not a cryptographic attestation",
    }


def manifest(directory):
    release, _ = config()
    data = json.loads((directory / "provenance.json").read_text())
    archive = f'{release["go_version"]}.linux-amd64.tar.gz'
    with (directory / archive).open("rb") as stream:
        digest = hashlib.file_digest(stream, "sha256").hexdigest()
    data.update({
        "archive": archive,
        "sha256": digest,
        "download_url": f'https://github.com/ZxillyFork/go-hmos-build/releases/download/{release["release_tag"]}/{archive}',
        "setup_go_version": release["go_version"][2:],
        "setup_go_download_base_url": f'https://github.com/ZxillyFork/go-hmos-build/releases/download/{release["release_tag"]}',
    })
    return data


def main():
    command = sys.argv[1]
    release, source = config()
    if command == "check":
        print(f'{release["release_tag"]}: {source["repository"]}@{source["revision"]}')
    elif command == "provenance":
        print(json.dumps(provenance(), indent=2))
    elif command == "manifest":
        print(json.dumps(manifest(Path(sys.argv[2])), indent=2))
    elif command == "notes":
        data = manifest(Path(sys.argv[2]))
        print(f'''# Go-HMOS Linux SDK {release["release_tag"]}

Experimental Linux/amd64-hosted Go toolchain. Supports cross-compilation for
OpenHarmony/HarmonyOS amd64 and arm64 with a separately obtained native SDK.
No Huawei proprietary SDK or emulator package is included.

- Core: https://github.com/{source["repository"]}/commit/{source["revision"]}
- Build: https://github.com/ZxillyFork/go-hmos-build/commit/{data["build_commit"]}
- Build run: {data["build_run_url"]}
- Compiler identity: `{release["go_version"]}`
- Archive SHA-256: `{data["sha256"]}`

Use the pinned official `actions/setup-go@{release["setup_go_commit"]}` with
`go-version: {data["setup_go_version"]}`, `cache: false`, `token: ''`, and
`go-download-base-url: {data["setup_go_download_base_url"]}`.
Set `GOTOOLCHAIN=local` to prevent automatic replacement by stock Go.
See `docs/linux-sdk.md` at the build commit for checksum validation and cross-linking.

Publication is gated by host tests, official setup-go loading and both target
cross-link checks. The workflow also downloads the published assets, verifies
checksums, and reruns official setup-go after publication. Consult the final run
status for that last verification. This is not evidence of ARM device execution
or a stable production release. Provenance is unsigned build metadata.
''')
    else:
        raise ValueError("unknown command")


if __name__ == "__main__":
    main()
