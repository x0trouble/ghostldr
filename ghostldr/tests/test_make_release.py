"""tools/make_release.py, offline:
the three files, their checksums, the reproducible zip make_save uses, and the
check that nothing of the maintainer's computer goes out.

    python3 -m unittest discover -s ghostldr/tests
"""

from __future__ import annotations

import hashlib
import importlib.util
import io
import tempfile
import unittest
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location("make_release", ROOT / "tools/make_release.py")
R = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(R)


def fake_tree(base: Path) -> Path:
    built = base / "build"
    built.mkdir()
    for n in R.BUILT:
        (built / n).write_bytes(n.encode() + b"\x00payload\x00/user/home/\x00192.168.1.123\x00" + bytes(range(256)))
    return built


class PersonalData(unittest.TestCase):
    def found(self, data: bytes, words=()) -> list[str]:
        return R.find_personal("f", data, list(words))

    def test_private_addresses_but_the_docs_examples(self) -> None:
        for ip in ("192.168.7.77", "10.1.2.3", "172.20.0.5", "169.254.1.1", "100.64.0.1"):
            self.assertTrue(self.found(f"connect {ip}:9026".encode()), ip)
        for ip in sorted(R.EXAMPLE_IPS) + ["8.8.8.8", "255.255.255.255", "0.0.0.0", "1.2.3.4"]:
            self.assertEqual(self.found(f"see {ip} here".encode()), [], ip)
        self.assertEqual(self.found(b"version 1.192.168.7.77.2"), [], "part of a longer dotted number")
        self.assertEqual(self.found(b"999.168.1.1"), [])

    def test_user_folders(self) -> None:
        self.assertTrue(self.found(b"\x00/Users/someone/ghostldr\x00"))
        self.assertTrue(self.found(b"/home/someone/x"))
        self.assertTrue(self.found(b"C:\\Users\\someone\\x"))
        self.assertEqual(self.found(b"\x00/user/home/\x00/user/home/10000001/savedata\x00"), [],
                         "the console's own /user/home paths")

    def test_words_any_case(self) -> None:
        self.assertTrue(self.found(b"a console called MyPs5Name", ["myps5name"]))
        self.assertEqual(self.found(b"nothing here", ["myps5name"]), [])

    def test_this_computer_is_in_the_words(self) -> None:
        words = R.personal_words(["extra"])
        self.assertIn(str(Path.home()), words)
        self.assertIn("extra", words)

    def test_deny_file(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "deny.txt"
            p.write_text("# private\nConsoleOne\n\n  0x1234abcd  # an account\n")
            self.assertEqual(R.read_deny_file(p), ["ConsoleOne", "0x1234abcd"])


class Release(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.base = Path(self.tmp.name)
        self.built = fake_tree(self.base)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def files(self) -> dict[str, bytes]:
        return R.collect(self.built)

    def test_the_three_files(self) -> None:
        self.assertEqual(sorted(self.files()), sorted(R.BUILT))

    def test_writes_files_and_sums(self) -> None:
        out = self.base / "out"
        R.make(out, self.files(), [])
        self.assertEqual(sorted(p.name for p in out.iterdir()), sorted(list(R.BUILT) + [R.SUMS]))
        # the release page's SHA256SUMS.txt: every file beside it
        sums = dict(reversed(line.split("  ")) for line in (out / R.SUMS).read_text().splitlines())
        self.assertEqual(sorted(sums), sorted(R.BUILT))
        for n, h in sums.items():
            self.assertEqual(hashlib.sha256((out / n).read_bytes()).hexdigest(), h, n)

    def test_reproducible(self) -> None:
        a, b = self.base / "a", self.base / "b"
        R.make(a, self.files(), [])
        R.make(b, self.files(), [])
        for p in a.iterdir():
            self.assertEqual(p.read_bytes(), (b / p.name).read_bytes(), p.name)

    def test_refuses_personal_data_and_writes_nothing(self) -> None:
        (self.built / "ghostldr.lua").write_text("-- built at /Users/someone/ghostldr for 192.168.7.77\n")
        out = self.base / "out"
        with self.assertRaises(SystemExit) as cm:
            R.make(out, self.files(), [])
        self.assertIn("192.168.7.77", str(cm.exception))
        self.assertIn("/Users/someone", str(cm.exception))
        self.assertFalse(out.exists())

    def test_a_missing_build_file_stops_it(self) -> None:
        (self.built / "ghostldr-ext.bin").unlink()
        with self.assertRaises(SystemExit) as cm:
            self.files()
        self.assertIn("ghostldr-ext.bin", str(cm.exception))

    def test_zip_bytes(self) -> None:
        data = R.zip_bytes({"b": b"2", "a": b"1"})
        self.assertEqual(data, R.zip_bytes({"a": b"1", "b": b"2"}), "reproducible")
        z = zipfile.ZipFile(io.BytesIO(data))
        self.assertEqual(z.namelist(), ["a", "b"])
        for info in z.infolist():
            self.assertEqual(info.date_time, R.ZIP_TIME)
            self.assertEqual(info.external_attr >> 16, 0o644)


if __name__ == "__main__":
    unittest.main()
