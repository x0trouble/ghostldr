"""The documentation's links, offline: every relative link in README.md,
docs/*.md and the other READMEs points at a file that exists, and a link to
a heading (`file.md#heading`) at a heading that file has, by GitHub's rules
for heading anchors.  Also: the pages for users name no Python tool, and the
release guide names the release's files.

    python3 -m unittest discover -s ghostldr/tests
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
LINK = re.compile(r"\]\(([^)\s]+)\)")


def doc_files() -> list[Path]:
    return ([ROOT / "README.md"] + sorted((ROOT / "docs").glob("*.md")) + sorted((ROOT / "ghostldr").rglob("README.md"))
            + [ROOT / "tools/contrib/README.md", ROOT / "plans/README.md"])


def user_text() -> dict[str, str]:
    """What users read: the README up to Building from source, the guide up to
    For developers, and the compatibility page."""
    readme = (ROOT / "README.md").read_text(encoding="utf-8").partition("## Building from source")[0]
    guide = (ROOT / "docs/using-the-release.md").read_text(encoding="utf-8").partition("## For developers")[0]
    return {"README.md": readme, "docs/using-the-release.md": guide,
            "docs/compatibility.md": (ROOT / "docs/compatibility.md").read_text(encoding="utf-8")}


def slug(heading: str) -> str:
    """GitHub's anchor for a heading: link text kept, lower case, punctuation
    other than '-' and '_' dropped, spaces to '-'."""
    text = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", heading).replace("`", "").strip().lower()
    return re.sub(r"[^\w\- ]", "", text).replace(" ", "-")


def without_code(text: str) -> str:
    return re.sub(r"```.*?```", "", text, flags=re.S)


def anchors(path: Path) -> set[str]:
    out: set[str] = set()
    seen: dict[str, int] = {}
    for line in without_code(path.read_text(encoding="utf-8")).splitlines():
        m = re.match(r"^#{1,6}\s+(.*?)\s*#*\s*$", line)
        if m:
            s = slug(m.group(1))
            n = seen.get(s, 0)
            seen[s] = n + 1
            out.add(s if n == 0 else f"{s}-{n}")
    return out


class Links(unittest.TestCase):
    def test_slug(self) -> None:
        self.assertEqual(slug("Every later session: ghostldr.lua alone"), "every-later-session-ghostldrlua-alone")
        self.assertEqual(slug("4. Boot"), "4-boot")
        self.assertEqual(slug("Save tools (Apollo Save Tool)"), "save-tools-apollo-save-tool")
        self.assertEqual(slug("`tools/stub_report.py`"), "toolsstub_reportpy")

    def test_every_relative_link_resolves(self) -> None:
        bad = []
        for f in doc_files():
            for m in LINK.finditer(without_code(f.read_text(encoding="utf-8"))):
                target = m.group(1)
                if re.match(r"^[a-z][a-z0-9+.-]*:", target):
                    continue  # https:, mailto:, ...
                path, _, frag = target.partition("#")
                path = path.split("?")[0]
                dest = (f.parent / path).resolve() if path else f
                where = f"{f.relative_to(ROOT)}: {target}"
                if not dest.exists():
                    bad.append(f"{where}: no such file")
                elif frag and dest.suffix == ".md" and frag not in anchors(dest):
                    bad.append(f"{where}: no such heading")
        self.assertEqual(bad, [], "\n".join(bad))


class ReleaseGuide(unittest.TestCase):
    def test_no_python_for_users(self) -> None:
        guide = (ROOT / "docs/using-the-release.md").read_text(encoding="utf-8")
        self.assertIn("## For developers", guide, "a For developers section")
        self.assertIn("## Building from source", (ROOT / "README.md").read_text(encoding="utf-8"))
        for name, text in user_text().items():
            for word in ("python3", "ghostldr.py", "run.py", "manager.py", "gfs_", ".py`", ".py "):
                self.assertNotIn(word, text.lower(), f"{name}: {word}")
            self.assertNotIn("app/", text, f"{name}: a link to the removed desktop app")

    def test_the_release_files_are_named(self) -> None:
        text = (ROOT / "docs/using-the-release.md").read_text(encoding="utf-8")
        for name in ("ghostldr.lua", "ghostldr-ext.bin", "ghostldr-elfldr.bin", "SHA256SUMS.txt",
                     "ghostldr-<version>-save-US-CUSA03474.zip",
                     "ghostldr-<version>-save-EU-CUSA03492.zip", "pkgextract-cli-macos", "pkgextract-cli-windows-x64.exe"):
            self.assertIn(name, text)
        for name in ("manager.lua", "README.txt", "ghostldr-<version>.zip"):
            self.assertNotIn(name, text, "no longer in a release")

    def test_both_ways_to_start(self) -> None:
        text = (ROOT / "docs/using-the-release.md").read_text(encoding="utf-8")
        for words in ("HALL OF FAME", "L1 + R1", "save resigning tool", "Apollo", "nc CONSOLE 9026 < ghostldr.lua",
                      "nc CONSOLE 9021 < ghostldr-ext.bin"):
            self.assertIn(words, text)


if __name__ == "__main__":
    unittest.main()
