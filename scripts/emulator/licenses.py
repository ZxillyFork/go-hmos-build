#!/usr/bin/env python3
# Copyright 2026 The Go Authors. All rights reserved.
# Use of this source code is governed by a BSD-style
# license that can be found in the LICENSE file.

"""Fail-closed comparison with the owner's previously accepted CLI agreements.

This module never invokes the emulator, supplies input, or accepts agreements.
The caller must provide output from a *view* invocation with negative answers.
The package checksum is a separate prerequisite enforced by the runner.

Reference: https://github.com/Zxilly/cjv/actions/runs/37875586125
Commit: 7debad0f808bef5cdc5f2cda5cef08fae5908dd7
CLI archive SHA-256:
58da7359019e9360a8bb82da0cd1d3b3b26fedc338379f257849f2162e3ac1fc

Only normalized hashes are retained; proprietary agreement text is not copied.
The reference output contained two identical June 28, 2026 software agreements,
a July 7, 2026 wearable agreement, and an undated SDK agreement, in that order.
"""

import hashlib
from pathlib import Path
import re
import stat


SOFTWARE_TITLE = "HarmonyOS Software License and Service Agreement"
SDK_TITLE = "HarmonyOS SDK License Agreement"
SEPARATOR = "---------------------------------------"
# Hash normalization: remove standalone ordinal lines, strip line-end
# whitespace, strip outer whitespace, then UTF-8 with no trailing newline.
EXPECTED_AGREEMENTS = (
    (SOFTWARE_TITLE, "21cb6bd8dde8c9dcf07d71dfd660e4e83e82705c97ee5d4faf9cba6ca4cd8486"),
    (SOFTWARE_TITLE, "21cb6bd8dde8c9dcf07d71dfd660e4e83e82705c97ee5d4faf9cba6ca4cd8486"),
    (SOFTWARE_TITLE, "904adff5a8570fc4d0e5b21cd3951bc5633361182f79f2943857aafb474320b4"),
    (SDK_TITLE, "bbdff5dcabe39311e204275aad97c8db037adc5689f2e022acc923babede6421"),
)
# Exact files observed inside the checksum-verified archive in read-only run
# https://github.com/ZxillyFork/go-hmos-build/actions/runs/37880522300 .
EXPECTED_RESOURCES = (
    ("agreement/HarmonyOS_Software_Service_Agreement.txt", 85442,
     "24ee2a62413a84577631c35f5898b95245679e8e4e841b1cf31ed501adc4426b"),
    ("agreement/HarmonyOS_SDK_Agreement.txt", 17450,
     "8896d5474b8ab857cb62d635167cbecd94d5c5b85758887b98f8bae1c3e28c9e"),
)
ABORTED_VIEW = (
    "There are 2 license agreements that need to be reviewed.\n"
    "Do you want to continue? (y/N): License check aborted by user.\n"
)
_ORDINAL = re.compile(r"[1-3]/3:")
_RESOURCE_NAME = re.compile(r"license|licence|agreement|eula", re.IGNORECASE)
_MAX_OUTPUT_BYTES = 2 * 1024 * 1024


def normalize(text):
    """Normalize presentation whitespace only, preserving all agreement words."""
    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    return "\n".join(
        line.rstrip() for line in lines if not _ORDINAL.fullmatch(line.strip())
    ).strip()


def _parse(output):
    if not isinstance(output, str):
        raise ValueError("License view output must be text")
    if len(output.encode("utf-8")) > _MAX_OUTPUT_BYTES:
        raise ValueError("License view output exceeds the inspection limit")
    if any(ord(char) < 32 and char not in "\r\n\t" for char in output):
        raise ValueError("License view output contains unexpected control characters")
    # Only the exact separator emitted by this pinned CLI is recognized. Do not
    # discard unknown preambles, warnings, prompts, or text after an agreement:
    # those can indicate another agreement or a changed invocation/CLI format.
    lines = output.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    chunks = [[]]
    for line in lines:
        if line.strip() == SEPARATOR:
            chunks.append([])
        else:
            chunks[-1].append(line)
    if len(chunks) < 3:
        raise ValueError("License view did not contain complete agreement frames")
    if normalize("\n".join(chunks[0])) or normalize("\n".join(chunks[-1])):
        raise ValueError("Unrecognized license view text or incomplete outer frame")
    agreements = []
    for chunk in chunks[1:-1]:
        block = normalize("\n".join(chunk))
        if not block:
            continue
        title = block.split("\n", 1)[0]
        if title not in (SOFTWARE_TITLE, SDK_TITLE):
            raise ValueError("Unrecognized license view text or prompt wrapper")
        agreements.append((title, hashlib.sha256(block.encode("utf-8")).hexdigest()))
    return tuple(agreements)


def _compare(output, expected):
    """Pure comparison helper; verify() always supplies the pinned baseline."""
    actual = _parse(output)
    if len(actual) != len(expected):
        raise ValueError(
            f"Incomplete or extra license agreements: expected {len(expected)}, "
            f"found {len(actual)}"
        )
    # Do not use sets: the two identical software agreements are intentional.
    for ordinal, (observed, accepted) in enumerate(zip(actual, expected), 1):
        if observed != accepted:
            raise ValueError(
                f"License agreement {ordinal} differs from the accepted baseline "
                f"(observed SHA-256 {observed[1]})"
            )


def _resource_inventory(emulator_parent):
    """List candidate resources without interpreting or trusting their content."""
    root = Path(emulator_parent)
    if not root.is_dir():
        raise ValueError("Extracted emulator directory is missing")
    candidates = []
    for path in sorted(root.rglob("*")):
        if _RESOURCE_NAME.search(path.name):
            kind = "symlink (not inspected)" if path.is_symlink() else "resource"
            candidates.append(f"{path.relative_to(root)} [{kind}]")
    return candidates


def _resource_text(emulator_parent):
    """Read only the exact two regular resources from the verified CLI layout."""
    root = Path(emulator_parent)
    directory = root / "agreement"
    if root.is_symlink() or directory.is_symlink() or not directory.is_dir():
        raise ValueError("License resource directory is missing or a symlink")
    expected = {row[0] for row in EXPECTED_RESOURCES}
    actual = set()
    for path in root.rglob("*"):
        relative = path.relative_to(root).as_posix()
        if relative == "agreement":
            continue
        if relative.startswith("agreement/") or _RESOURCE_NAME.search(path.name):
            if path.is_symlink() or not stat.S_ISREG(path.lstat().st_mode):
                raise ValueError(f"License resource is not a regular file: {relative}")
            actual.add(relative)
    if actual != expected:
        raise ValueError(
            "License resource inventory differs: "
            f"missing={sorted(expected - actual)}, extra={sorted(actual - expected)}"
        )
    contents = []
    for relative, size, checksum in EXPECTED_RESOURCES:
        path = root / relative
        if path.stat().st_size != size:
            raise ValueError(f"License resource size differs: {relative}")
        data = path.read_bytes()
        if len(data) != size or hashlib.sha256(data).hexdigest() != checksum:
            raise ValueError(f"License resource SHA-256 differs: {relative}")
        try:
            contents.append(data.decode("utf-8"))
        except UnicodeDecodeError as error:
            raise ValueError(f"License resource is not UTF-8: {relative}") from error
    return contents


def _frame_resource_text(contents):
    """Convert local presentation wrappers to the same fully checked frames.

    Exact raw file hashes have already been verified. Every non-wrapper byte
    remains part of a document's normalized digest; unknown text is not dropped.
    """
    documents = []
    current = []
    for content in contents:
        for line in content.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
            if line.strip() == SEPARATOR or _ORDINAL.fullmatch(line.strip()):
                continue
            if line in (SOFTWARE_TITLE, SDK_TITLE):
                if current:
                    documents.append("\n".join(current))
                current = [line]
            elif current:
                current.append(line)
            elif line.strip():
                raise ValueError("Unrecognized preamble in local license resources")
    if current:
        documents.append("\n".join(current))
    return SEPARATOR + "\n" + ("\n" + SEPARATOR + "\n").join(documents) + "\n" + SEPARATOR + "\n"


def verify(emulator_parent: Path, cli_view_output: str):
    """Return None only for the exact complete, previously accepted collection.

    Raise ValueError on missing/extra/changed agreements or unfamiliar output.
    The exact two-resource negative-answer banner permits a local-resource
    comparison only after complete inventory, byte sizes, and SHA-256 checks.
    Every extracted document must still match the prior emitted-text baseline.
    """
    try:
        candidates = _resource_inventory(emulator_parent)
    except OSError as error:
        raise ValueError(f"Could not inspect local license resources: {error}") from error
    print("License resource candidates: " + (", ".join(candidates) or "none"))
    if cli_view_output == ABORTED_VIEW:
        try:
            cli_view_output = _frame_resource_text(_resource_text(emulator_parent))
        except OSError as error:
            raise ValueError(f"Could not read local license resources: {error}") from error
    _compare(cli_view_output, EXPECTED_AGREEMENTS)
    print(f"Verified {len(EXPECTED_AGREEMENTS)} previously accepted agreement texts")
