#!/usr/bin/env python3
"""Fail-closed checks of the actual packed app, not just source configuration."""
import json
from pathlib import Path
import sys
import zipfile


def validate(path):
    with zipfile.ZipFile(path) as z:
        names = z.namelist()
        if names.count("module.json") != 1:
            raise ValueError("expected exactly one packed module.json")
        module = json.loads(z.read("module.json"))
        app, mod = module["app"], module["module"]
        if app["bundleName"] != "org.gohmos.networktest":
            raise ValueError("unexpected app identity")
        if app.get("debug", app.get("debuggable")) is not True:
            raise ValueError("packed app is not debuggable")
        # HarmonyOS 6.1.1(24) is encoded as 60101024 by the official
        # 26.0.0 packer, rather than the bare OpenHarmony API integer 24.
        if (app.get("minAPIVersion") != 60101024 or
                app.get("targetAPIVersion") != 60101024 or
                app.get("compileSdkType") != "HarmonyOS" or
                mod.get("virtualMachine") != "ark24.0.0.0"):
            raise ValueError("packed app must target HarmonyOS 6.1.1(24)/Ark24")
        permissions = [p["name"] for p in mod.get("requestPermissions", [])]
        if permissions != ["ohos.permission.INTERNET"]:
            raise ValueError("packed app must declare only INTERNET")
        libs = sorted(n for n in names if n.endswith(".so"))
        expected = ["libs/x86_64/libgo_app_network.so", "libs/x86_64/libgohmos.so"]
        if libs != expected:
            raise ValueError(f"unexpected native library set: {libs}")
        for name in libs:
            elf = z.read(name)
            if elf[:6] != b"\x7fELF\x02\x01" or int.from_bytes(elf[18:20], "little") != 62:
                raise ValueError("non-x86_64 ELF in HAP")
        return module


if __name__ == "__main__":
    with zipfile.ZipFile(sys.argv[1]) as source:
        Path(sys.argv[2], "packed-module.json").write_bytes(source.read("module.json"))
    result = validate(sys.argv[1])
    print("PASS: unsigned debug HAP, API24, x86_64, INTERNET only")
