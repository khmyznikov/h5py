"""Dependency-only compiler isolation; diagnostic fork branch, not production CI."""

import argparse
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import urllib.request
import zipfile


def run(command, name, *, cwd=None, check=True):
    print(subprocess.list2cmdline([str(arg) for arg in command]), flush=True)
    with (logs / f"{name}.log").open("w", encoding="utf-8") as log:
        process = subprocess.Popen(
            command, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, errors="replace",
        )
        for line in process.stdout:
            print(line, end="", flush=True)
            log.write(line)
        code = process.wait()
        log.write(f"\nExit code: {code} (0x{code & 0xffffffff:08X})\n")
    print(f"{name}: exit {code} (0x{code & 0xffffffff:08X})", flush=True)
    if check and code:
        raise subprocess.CalledProcessError(code, command)
    return code


def download(url, name):
    destination = root / name
    if not destination.exists():
        urllib.request.urlretrieve(url, destination)
        with zipfile.ZipFile(destination) as archive:
            archive.extractall(root)


parser = argparse.ArgumentParser()
parser.add_argument("--root", type=Path, required=True)
parser.add_argument("--generator", default="Ninja")
parser.add_argument("--expect-ice", action="store_true")
args = parser.parse_args()
root = args.root.resolve()
logs = root / "logs"
logs.mkdir(parents=True, exist_ok=True)

identity = {
    key: os.environ.get(key)
    for key in (
        "VCToolsVersion", "VCToolsInstallDir", "VSCMD_ARG_HOST_ARCH",
        "VSCMD_ARG_TGT_ARCH", "WindowsSDKVersion", "WindowsSdkDir",
        "CMAKE_GENERATOR_INSTANCE", "CMAKE_GENERATOR_TOOLSET", "CL", "LINK",
    )
}
identity["platform"] = platform.platform()
(logs / "environment.json").write_text(json.dumps(identity, indent=2))
run(["where.exe", "cl"], "where-cl")
run(["cl", "/Bv"], "compiler-version", check=False)
run(["cmake", "--version"], "cmake-version")

download("https://github.com/madler/zlib/archive/refs/tags/v1.3.2.zip", "zlib.zip")
download("https://github.com/HDFGroup/hdf5/archive/refs/tags/2.2.0.zip", "hdf5.zip")
zlib = root / "zlib-install"
run([
    "cmake", "-S", str(root / "zlib-1.3.2"), "-B", str(root / "zlib-build"),
    "-G", args.generator, "-DCMAKE_BUILD_TYPE=Release",
    f"-DCMAKE_INSTALL_PREFIX={zlib}",
], "zlib-configure")
run([
    "cmake", "--build", str(root / "zlib-build"),
    "--config", "Release", "--target", "install",
], "zlib-build")

os.environ["CL"] = f"/I{zlib / 'include'}"
os.environ["LINK"] = f"/LIBPATH:{zlib / 'lib'}"
build = root / "hdf5-build"
run([
    "cmake", "-S", str(root / "hdf5-2.2.0"), "-B", str(build),
    "-G", args.generator, "-DBUILD_SHARED_LIBS:BOOL=ON",
    "-DBUILD_STATIC_LIBS:BOOL=OFF", "-DBUILD_TESTING:BOOL=OFF",
    "-DCMAKE_BUILD_TYPE:STRING=RELEASE",
    "-DHDF5_BUILD_EXAMPLES:BOOL=OFF-DHDF5_BUILD_HL_LIB=ON",
    "-DHDF5_BUILD_TOOLS:BOOL=OFF", "-DHDF5_BUILD_UTILS:BOOL=OFF",
    "-DHDF5_ENABLE_ZLIB_SUPPORT=ON", f"-DZLIB_INCLUDE_DIR={zlib / 'include'}",
    f"-DZLIB_LIBRARY_RELEASE={zlib / 'lib' / 'z.lib'}",
    f"-DCMAKE_INSTALL_PREFIX={root / 'hdf5-install'}",
    "-DCMAKE_EXPORT_COMPILE_COMMANDS=ON",
], "hdf5-configure")
code = run([
    "cmake", "--build", str(build), "--config", "Release",
    "--target", "hdf5-shared", "--verbose", "--parallel", "1",
], "hdf5-build", check=False)
if args.expect_ice:
    diagnostic = (logs / "hdf5-build.log").read_text(encoding="utf-8")
    if not code or not all(
        marker in diagnostic
        for marker in ("H5Tinit_float.c", "fatal error C1001", "3765260340")
    ):
        raise RuntimeError("Expected H5Tinit_float.c compiler crash was not reproduced")
    print("Expected H5Tinit_float.c C1001 / 0xE06D5034 reproduced.", flush=True)
    sys.exit(0)
sys.exit(code)
