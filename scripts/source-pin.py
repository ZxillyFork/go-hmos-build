#!/usr/bin/env python3
# Copyright 2026 The Go Authors. All rights reserved.
# Use of this source code is governed by a BSD-style
# license that can be found in the LICENSE file.
"""Resolve a reviewed source pin; never allow moving branch or tag names."""
import argparse
import json
from pathlib import Path
import re

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--revision", default="", help="Explicit 40-character core commit SHA")
parser.add_argument("--allow-unset", action="store_true",
                    help="Print an empty result when the default revision is not yet pinned")
args = parser.parse_args()
pin = json.loads((Path(__file__).resolve().parent.parent / "source.json").read_text())
if pin["repository"] != "ZxillyFork/go-hmos":
    parser.error("source repository must be ZxillyFork/go-hmos")
revision = args.revision or pin["revision"]
if not revision and args.allow_unset:
    print("")
    raise SystemExit(0)
if not re.fullmatch(r"[0-9a-f]{40}", revision) or revision == "0" * 40:
    parser.error("source revision must be a nonzero, full lowercase commit SHA")
print(revision)
