#!/usr/bin/env python3
"""Encode a title profile JSON into the flat u64 array profile.c parses.

A title profile carries every per-title constant the core needs:
the memory planner's table offsets and pool sizes, the lazy-backing
call sites, and the heap-accounting object offsets (docs in
docs/title-profiles.md). titles/CUSA11456.json is the built-in
Ghost of Tsushima profile in data form; the values must match
profile.c's built-in exactly (test_title_profile.py checks).

    python3 ghostldr/tools/title_profile.py titles/CUSA11456.json
        -> prints the 48 words as a Lua table literal

run.py --title-profile <file> embeds the same array in the payload.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

MAGIC = 0x4750524F46303031  # "GPROF001"
VERSION = 1
WORDS = 48
KNOB_NAMES = {"general GPU heap": 0, "type-0 engine heap": 1, "CPU malloc heap": 2}


def encode(profile: dict) -> list[int]:
    knobs = profile.get("knobs", [])
    sites = profile.get("lazy_sites", [])
    pool = profile["stream_pool"]
    if len(pool) != 6:
        raise ValueError("stream_pool must have exactly 6 entries (one per memory mode)")
    if len(knobs) > 4:
        raise ValueError("at most 4 knobs fit the profile format")
    if len(sites) > 8:
        raise ValueError("at most 8 lazy sites fit the profile format")
    w = [0] * WORDS
    w[0] = MAGIC
    w[1] = VERSION
    tag = str(profile["title_id"]).encode()[:8].ljust(8, b"\0")
    w[2] = int.from_bytes(tag, "little")
    w[3] = 1 if profile.get("builtin_hooks") else 0
    w[4] = len(knobs)
    w[5] = int(profile["stream_pool_table"])
    for i, v in enumerate(pool):
        w[6 + i] = int(v)
    for i, k in enumerate(knobs):
        base = 12 + 4 * i
        w[base] = int(k["table"])
        w[base + 1] = int(k["knob_slot"])
        w[base + 2] = KNOB_NAMES[k["name"]]
        w[base + 3] = int(k.get("default_mib", 0))
    w[28] = int(profile["fixed_mib"])
    w[29] = int(profile["remainder_mib"])
    w[30] = int(profile["slack_mib"])
    w[31] = int(profile["lazy_total_mib"])
    w[32] = int(profile["lazy_reserve_mib"])
    w[33] = int(profile["movie_reserve_mib"])
    w[34] = int(profile["min_pool_mib"])
    w[35] = len(sites)
    for i, s in enumerate(sites):
        w[36 + i] = int(s)
    w[44] = int(profile.get("heap_obj0", 0))
    w[45] = int(profile.get("heap_obj1", 0))
    return w


def load_words(path: Path) -> list[int]:
    return encode(json.loads(Path(path).read_text()))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("profile", type=Path, help="a titles/<id>.json profile")
    args = ap.parse_args(argv)
    words = load_words(args.profile)
    print("{" + ", ".join(f"{v:#x}" for v in words) + "}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
