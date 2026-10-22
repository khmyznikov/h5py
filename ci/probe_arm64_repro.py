"""Record compile-only controls for the reduced ARM64 MSVC internal error."""

import argparse
import json
import os
from pathlib import Path
import subprocess


parser = argparse.ArgumentParser()
parser.add_argument("--output", type=Path, required=True)
parser.add_argument("--compiler", default="cl")
parser.add_argument("--expect-ice", action="store_true")
args = parser.parse_args()
args.output.mkdir(parents=True, exist_ok=True)
source = Path(__file__).with_name("msvc_arm64_repro.c").resolve()
environment = {
    key: os.environ.get(key)
    for key in (
        "VCToolsVersion", "VCToolsInstallDir", "VSCMD_ARG_HOST_ARCH",
        "VSCMD_ARG_TGT_ARCH", "WindowsSDKVersion", "WindowsSdkDir",
    )
}
(args.output / "environment.json").write_text(json.dumps(environment, indent=2))
results = []
for name, flags in (
    ("O2", ["/O2"]),
    ("Od", ["/Od"]),
    ("O1", ["/O1"]),
    ("O2-Ob0", ["/O2", "/Ob0"]),
    ("O2-Oi-", ["/O2", "/Oi-"]),
    ("O2-fp-strict", ["/O2", "/fp:strict"]),
    ("O1-Oi", ["/O1", "/Oi"]),
    ("Od-Oi", ["/Od", "/Oi"]),
):
    command = [
        args.compiler, "/nologo", "/c", "/std:c11", *flags,
        "/Fo" + str((args.output / f"{name}.obj").resolve()), str(source),
    ]
    if name == "O2":
        command.insert(1, "/Bv")
    process = subprocess.run(command, capture_output=True, text=True, errors="replace")
    code = process.returncode & 0xffffffff
    diagnostic = process.stdout + process.stderr
    text = subprocess.list2cmdline(command) + "\n" + diagnostic
    text += f"\nExit: {process.returncode} (0x{code:08X})\n"
    (args.output / f"{name}.log").write_text(text, encoding="utf-8")
    print(text, flush=True)
    results.append({"name": name, "exit_hex": f"0x{code:08X}"})
    if name == "O2":
        expected = 0xE06D5034 if args.expect_ice else 0
        if code != expected or (args.expect_ice and "C1001" not in diagnostic):
            raise RuntimeError(f"Unexpected /O2 result: 0x{code:08X}, expected 0x{expected:08X}")
    elif name in ("Od", "O1", "O2-Oi-", "O2-fp-strict", "Od-Oi") and code:
        raise RuntimeError(f"Control {name} failed: 0x{code:08X}")
(args.output / "results.json").write_text(json.dumps(results, indent=2))
