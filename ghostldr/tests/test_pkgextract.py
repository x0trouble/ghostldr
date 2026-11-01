"""tools/pkgextract-cli (docs/developers.md "Making a release"): builds it and
upstream LibOrbisPkg's PkgTool, makes a small fake PKG with PkgTool and
extracts it: every file back, one folder of it, and the refusals (not a PKG,
a retail-like PKG, an output folder in use); and the built-in licences.  Skips without a .NET 9 SDK or
without build/LibOrbisPkg (tools/fetch_deps.sh).

    python3 -m unittest discover -s ghostldr/tests
"""

from __future__ import annotations

import os
import re
import shutil
import struct
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
LIB = ROOT / "build/LibOrbisPkg"
OUT = ROOT / "build/pkgextract-cli"
CONTENT_ID = "UP0000-TEST00001_00-PKGEXTRACTTEST01"
FILES = {
    "eboot.bin": bytes(range(256)) * 1200,
    "dir/a.txt": b"hello\n",
    "dir/sub/b.dat": b"abc\n" * 50000,
}
GP4 = """<?xml version="1.0"?>
<psproject fmt="gp4" version="1000">
  <volume>
    <volume_type>pkg_ps4_app</volume_type>
    <volume_id>PS4VOLUME</volume_id>
    <volume_ts>2020-01-01 00:00:00</volume_ts>
    <package content_id="{cid}" passcode="00000000000000000000000000000000" storage_type="digital50" app_type="full" c_date="2020-01-01" />
    <chunk_info chunk_count="1" scenario_count="1">
      <chunks><chunk id="0" layer_no="0" label="Chunk #0" /></chunks>
      <scenarios default_id="0"><scenario id="0" type="sp" initial_chunk_count="1" label="Scenario #0">0</scenario></scenarios>
    </chunk_info>
  </volume>
  <files img_no="0">
    <file targ_path="sce_sys/param.sfo" orig_path="sce_sys/param.sfo" />
{files}
  </files>
  <rootdir>
    <dir targ_name="sce_sys" />
    <dir targ_name="dir"><dir targ_name="sub" /></dir>
  </rootdir>
</psproject>
"""
SFO = [  # name, type, value, max size
    ("CONTENT_ID", "utf8", CONTENT_ID, "48"),
    ("TITLE_ID", "utf8", "TEST00001", "12"),
    ("CATEGORY", "utf8", "gd", "4"),
    ("ATTRIBUTE", "int", "0", ""),
    ("FORMAT", "utf8", "obs", "4"),
    ("PUBTOOLVER", "int", "0", ""),
    ("APP_VER", "utf8", "01.00", "8"),
    ("VERSION", "utf8", "01.00", "8"),
]


def dotnet() -> str | None:
    exe = shutil.which("dotnet")
    if not exe:
        return None
    try:
        sdks = subprocess.run([exe, "--list-sdks"], capture_output=True, text=True, timeout=60).stdout
    except (OSError, subprocess.SubprocessError):
        return None
    return exe if any(int(m) >= 9 for m in re.findall(r"^(\d+)\.", sdks, re.M)) else None


DOTNET = dotnet()
ENV = dict(os.environ, DOTNET_CLI_TELEMETRY_OPTOUT="1", DOTNET_NOLOGO="1",
           DOTNET_ROLL_FORWARD="Major")  # PkgTool targets .NET Core 3.0


@unittest.skipUnless(DOTNET, "needs a .NET 9 SDK (dotnet)")
@unittest.skipUnless((LIB / "LibOrbisPkg.Core").is_dir(), "needs build/LibOrbisPkg: run tools/fetch_deps.sh")
class PkgExtract(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        def build(project: Path, *extra: str) -> None:
            r = subprocess.run([DOTNET, "build", "-c", "Release", str(project), *extra],
                               capture_output=True, text=True, env=ENV, timeout=600)
            if r.returncode:
                raise AssertionError(f"dotnet build {project.name} failed:\n{r.stdout}{r.stderr}")

        build(ROOT / "tools/pkgextract-cli")
        build(LIB / "PkgTool.Core", "-o", str(OUT / "pkgtool"))
        cls.tool = OUT / "bin/Release/net9.0/pkgextract-cli.dll"
        cls.tmp = tempfile.TemporaryDirectory()
        base = Path(cls.tmp.name)
        src = base / "src"
        (src / "sce_sys").mkdir(parents=True)
        for rel, data in FILES.items():
            (src / rel).parent.mkdir(parents=True, exist_ok=True)
            (src / rel).write_bytes(data)
        sfo = src / "sce_sys/param.sfo"
        cls.pkgtool("sfo_new", sfo)
        for name, kind, value, size in SFO:
            cls.pkgtool("sfo_setentry", "--value", value, "--type", kind, *(["--maxsize", size] if size else []), sfo, name)
        listed = "\n".join(f'    <file targ_path="{r}" orig_path="{r}" />' for r in FILES)
        (src / "test.gp4").write_text(GP4.format(cid=CONTENT_ID, files=listed))
        (base / "pkg").mkdir()
        cls.pkgtool("pkg_build", src / "test.gp4", base / "pkg")
        cls.pkg = base / "pkg" / f"{CONTENT_ID}.pkg"
        cls.base = base

    @classmethod
    def tearDownClass(cls) -> None:
        cls.tmp.cleanup()

    @classmethod
    def pkgtool(cls, *args) -> None:
        r = subprocess.run([DOTNET, str(OUT / "pkgtool/PkgTool.Core.dll"), *map(str, args)],
                           capture_output=True, text=True, env=ENV, timeout=300)
        if r.returncode:
            raise AssertionError(f"PkgTool {args[0]} failed:\n{r.stdout}{r.stderr}")

    def run_tool(self, *args) -> subprocess.CompletedProcess:
        return subprocess.run([DOTNET, str(self.tool), *map(str, args)],
                              capture_output=True, text=True, env=ENV, timeout=300)

    def out(self, name: str) -> Path:
        return self.base / "out" / name

    def test_every_file(self) -> None:
        r = self.run_tool(self.pkg, self.out("all"))
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn(CONTENT_ID, r.stdout)
        got = {p.relative_to(self.out("all")).as_posix() for p in self.out("all").rglob("*") if p.is_file()}
        self.assertTrue(set(FILES) <= got, got)
        for rel, data in FILES.items():
            self.assertEqual((self.out("all") / rel).read_bytes(), data, rel)
        # the entries: param.sfo and the rest of sce_sys, from the PKG's entry table
        self.assertIn(CONTENT_ID.encode(), (self.out("all") / "sce_sys/param.sfo").read_bytes())
        self.assertFalse([p for p in got if p.endswith(".part")])
        self.assertFalse(any(p.name == "manifest.json" for p in self.out("all").parent.iterdir()))

    def test_one_folder(self) -> None:
        r = self.run_tool(self.pkg, self.out("dir"), "dir/")
        self.assertEqual(r.returncode, 0, r.stderr)
        got = sorted(p.relative_to(self.out("dir")).as_posix() for p in self.out("dir").rglob("*") if p.is_file())
        self.assertEqual(got, ["dir/a.txt", "dir/sub/b.dat"])
        r = self.run_tool(self.pkg, self.out("di"), "di")  # a path, not a prefix
        self.assertEqual(r.returncode, 2)
        self.assertIn("nothing in", r.stderr)
        self.assertFalse(self.out("di").exists())

    def test_refusals(self) -> None:
        self.assertEqual(self.run_tool("--help").returncode, 0)
        self.assertEqual(self.run_tool(self.pkg).returncode, 1)
        r = self.run_tool(self.base / "src/test.gp4", self.out("x"))
        self.assertEqual((r.returncode, "not a PS4 PKG" in r.stderr), (2, True), r.stderr)
        used = self.out("used")
        used.mkdir(parents=True)
        (used / "keep.txt").write_text("mine")
        r = self.run_tool(self.pkg, used)
        self.assertEqual((r.returncode, "not empty" in r.stderr), (2, True), r.stderr)
        self.assertEqual(sorted(p.name for p in used.iterdir()), ["keep.txt"])

    def test_licences(self) -> None:
        r = self.run_tool("--licenses")
        self.assertEqual(r.returncode, 0, r.stderr)
        commit = (LIB / ".pkgextract-patched").read_text().strip()
        for text in (commit, "MIT License", "GNU LESSER GENERAL PUBLIC LICENSE", "GNU GENERAL PUBLIC LICENSE",
                     ".NET Runtime uses third-party"):
            self.assertIn(text, r.stdout)

    def test_retail_like(self) -> None:
        # Break the zero passcode's digest and the fake-key copy of the image
        # key, as in a retail PKG: neither fake key path opens it.
        data = bytearray(self.pkg.read_bytes())
        count, table = struct.unpack_from(">I", data, 0x10)[0], struct.unpack_from(">I", data, 0x18)[0]
        keys = next(struct.unpack_from(">I", data, table + 32 * i + 16)[0] for i in range(count)
                    if struct.unpack_from(">I", data, table + 32 * i)[0] == 0x10)
        data[keys + 0x20:keys + 0x40] = bytes(32)                       # digest of key 0
        data[keys + 0x400:keys + 0x500] = b"\xff" * 256  # key 3
        retail = self.base / "retail.pkg"
        retail.write_bytes(data)
        r = self.run_tool(retail, self.out("retail"))
        self.assertEqual(r.returncode, 2)
        self.assertIn("only fake-signed", r.stderr.lower().replace("\n", " "))


if __name__ == "__main__":
    unittest.main()
