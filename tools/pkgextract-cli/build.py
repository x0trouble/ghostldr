#!/usr/bin/env python3
"""Build pkgextract-cli's release files: one executable per platform.

    python3 tools/pkgextract-cli/build.py [--out DIR] [--only PLATFORM ...] [--version VERSION]
                                          [--deny WORD ...]

Runs tools/fetch_deps.sh (LibOrbisPkg at its pinned commit, into build/),
then builds into DIR (default build/pkgextract-cli):

    pkgextract-cli-macos              NativeAOT, x64 and arm64 in one (lipo); needs macOS
    pkgextract-cli-linux-x64          NativeAOT, built in the .NET SDK's Docker image
    pkgextract-cli-linux-arm64        (NativeAOT can't cross-compile to Linux); needs Docker
    pkgextract-cli-windows-x64.exe    .NET single-file, self-contained, trimmed (NativeAOT
                                      for Windows needs a Windows computer)
    SHA256SUMS.txt                    the executables

--only builds some of them (macos, linux-x64, linux-arm64, windows-x64). The
licences are built in: pkgextract-cli --licenses prints them. LibOrbisPkg
(LGPL-3.0) is linked in; anyone can rebuild with their own copy from this
source. Like tools/make_release.py, it stops if a file holds a user folder
path, this computer's names or a --deny word.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import os
import platform
import re
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
LIB = REPO / "build/LibOrbisPkg"
PLATFORMS = ["macos", "linux-x64", "linux-arm64", "windows-x64"]
# the .NET SDK 9.0 image (both architectures), pinned for repeatable Linux builds
SDK_IMAGE = "mcr.microsoft.com/dotnet/sdk:9.0@sha256:7e3a4bd66701a451823db2028154ae16ff191bc452596ba618ef4d0c58f9cd01"
# runs in that image: /repo is this repository (read-only), /out the output; $1 the runtime, $2 the version
LINUX_BUILD = r"""set -e
apt-get update -qq >/dev/null
apt-get install -y -qq clang zlib1g-dev >/dev/null
mkdir -p /w/tools /w/build
cp -r /repo/tools/pkgextract-cli /w/tools/
cp /repo/LICENSE /w/
tar -C /repo/build --exclude=bin --exclude=obj -cf - LibOrbisPkg | tar -C /w/build -xf -
cd /w
DOTNET_CLI_TELEMETRY_OPTOUT=1 DOTNET_NOLOGO=1 dotnet publish tools/pkgextract-cli/pkgextract-cli.csproj \
    -c Release -r "$1" -p:PkgAot=true -p:Version="$2" -p:PathMap=/w=/ghostldr -o /w/publish >/w/log 2>&1 ||
    { cat /w/log; exit 1; }
cp /w/publish/pkgextract-cli "/out/pkgextract-cli-$1"
"""

_spec = importlib.util.spec_from_file_location("make_release", REPO / "tools/make_release.py")
_release = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_release)


def die(msg: str) -> None:
    sys.exit(f"build.py: {msg}")


def pinned_commit() -> str:
    m = re.search(r"^LIBORBISPKG=([0-9a-f]{40})$", (REPO / "tools/fetch_deps.sh").read_text(), re.M)
    if not m:
        die("no LIBORBISPKG=<commit> in tools/fetch_deps.sh")
    return m.group(1)


def csproj_version() -> str:
    m = re.search(r"<Version>([^<]+)</Version>", (HERE / "pkgextract-cli.csproj").read_text())
    return m.group(1) if m else "0.0.0"


def run(cmd: list[str], what: str) -> None:
    env = dict(os.environ, DOTNET_CLI_TELEMETRY_OPTOUT="1", DOTNET_NOLOGO="1")
    r = subprocess.run(cmd, env=env, capture_output=True, text=True)
    if r.returncode:
        die(f"{what} failed:\n{r.stdout}{r.stderr}")


def fresh_lib() -> None:
    # LibOrbisPkg built fresh each time: a test's debug build of it holds this computer's paths
    for d in ("bin", "obj"):
        shutil.rmtree(LIB / "LibOrbisPkg.Core" / d, ignore_errors=True)


def publish(dotnet: str, rid: str, version: str, dest: Path, *extra: str) -> Path:
    shutil.rmtree(dest, ignore_errors=True)
    fresh_lib()
    run([dotnet, "publish", str(HERE / "pkgextract-cli.csproj"), "-c", "Release", "-r", rid, "-o", str(dest),
         f"-p:Version={version}", "-p:ContinuousIntegrationBuild=true",
         f"-p:PathMap={REPO}=/ghostldr", *extra], f"dotnet publish -r {rid}")
    return dest


def build_macos(dotnet: str, version: str, work: Path) -> bytes:
    if platform.system() != "Darwin":
        die("the macOS build needs macOS (NativeAOT links with Xcode's tools); skip it with --only")
    halves = [publish(dotnet, rid, version, work / rid, "-p:PkgAot=true") / "pkgextract-cli"
              for rid in ("osx-x64", "osx-arm64")]
    out = work / "pkgextract-cli-macos"
    run(["lipo", "-create", *map(str, halves), "-output", str(out)], "lipo")
    return out.read_bytes()


def build_linux(arch: str, version: str, work: Path) -> bytes:
    docker = shutil.which("docker")
    if not docker:
        die("the Linux builds need Docker; skip them with --only")
    rid = f"linux-{arch}"
    work.mkdir(parents=True, exist_ok=True)
    out = work / f"pkgextract-cli-{rid}"
    out.unlink(missing_ok=True)
    fresh_lib()
    run([docker, "run", "--rm", "--platform", f"linux/{'amd64' if arch == 'x64' else 'arm64'}",
         "-v", f"{REPO}:/repo:ro", "-v", f"{work.resolve()}:/out", SDK_IMAGE,
         "bash", "-c", LINUX_BUILD, "build", rid, version], f"the {rid} build in Docker")
    return out.read_bytes()


def personal(name: str, data: bytes, words: list[str]) -> list[str]:
    # No user folder or name of this computer. Addresses: the runtime's
    # version numbers look like them.
    return [f for f in _release.find_personal(name, data, words) if "the address" not in f]


def build_windows(dotnet: str, version: str, work: Path, words: list[str]) -> bytes:
    dest = publish(dotnet, "win-x64", version, work / "win-x64", "--self-contained", "true",
                   "-p:PublishSingleFile=true", "-p:IncludeNativeLibrariesForSelfExtract=true",
                   "-p:EnableCompressionInSingleFile=true", "-p:PublishTrimmed=true")
    files = sorted(p.name for p in dest.iterdir() if p.suffix != ".pdb")  # LibOrbisPkg's symbols
    if files != ["pkgextract-cli.exe"]:
        die(f"win-x64: expected one file, got {files}")
    # the .exe is compressed: check the trimmed DLLs it bundles
    linked = REPO / "build/pkgextract-cli/obj/Release/net9.0/win-x64/linked"
    bad = [f for dll in sorted(linked.glob("*.dll")) for f in personal(f"win-x64 {dll.name}", dll.read_bytes(), words)]
    if not any(linked.glob("*.dll")) or bad:
        die("refusing to package:\n  " + "\n  ".join(bad or [f"win-x64: nothing in {linked} to check"]))
    return (dest / "pkgextract-cli.exe").read_bytes()


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--out", type=Path, default=REPO / "build/pkgextract-cli")
    ap.add_argument("--only", action="append", choices=PLATFORMS, help="only this platform (repeatable)")
    ap.add_argument("--version", default=csproj_version())
    ap.add_argument("--deny", action="append", default=[], help="a word no file may contain")
    args = ap.parse_args(argv)

    dotnet = os.environ.get("DOTNET") or shutil.which("dotnet")
    if not dotnet and set(args.only or PLATFORMS) - {"linux-x64", "linux-arm64"}:
        die("needs the .NET 9 SDK (dotnet)")
    subprocess.run(["sh", str(REPO / "tools/fetch_deps.sh")], check=True, stdout=subprocess.DEVNULL)
    if (LIB / ".pkgextract-patched").read_text().strip() != pinned_commit():
        die("build/LibOrbisPkg is not at the pinned commit")

    words = _release.personal_words(args.deny)
    work = args.out / "work"
    args.out.mkdir(parents=True, exist_ok=True)
    made: dict[str, bytes] = {}
    for plat in args.only or PLATFORMS:
        print(f"building {plat}", file=sys.stderr)
        if plat == "macos":
            name, data = "pkgextract-cli-macos", build_macos(dotnet, args.version, work)
        elif plat == "windows-x64":
            name, data = "pkgextract-cli-windows-x64.exe", build_windows(dotnet, args.version, work, words)
        else:
            name, data = f"pkgextract-cli-{plat}", build_linux(plat.split("-")[1], args.version, work)
        bad = personal(name, data, words)
        if bad:
            die("refusing to package:\n  " + "\n  ".join(bad))
        made[name] = data
        path = args.out / name
        path.write_bytes(data)
        path.chmod(0o755)

    sums = "".join(f"{hashlib.sha256(made[n]).hexdigest()}  {n}\n" for n in sorted(made))
    (args.out / "SHA256SUMS.txt").write_text(sums)
    for n in sorted(made):
        print(f"{n}  {len(made[n])} bytes  {hashlib.sha256(made[n]).hexdigest()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
