#!/usr/bin/env python3
"""Send the ghostldr bootstrap to Luac0re's remote Lua loader and show logs.

    python3 ghostldr/host/run.py probe            # core probe (flags=1)
    python3 ghostldr/host/run.py probe --diag     # PS4 diagnostic: boots nothing (docs/ps4.md)
    python3 ghostldr/host/run.py boot             # load and start the title
    python3 ghostldr/host/run.py logs             # only listen for UDP logs
    python3 ghostldr/host/run.py doctor           # fork: check this tree and network (docs/host-tooling.md)

A boot also serves the runtime extension (build/ghostldr/ext.bin: the NID
table and the extension's HLE code) on TCP 18195; the core fetches it first
and stops before touching the title when it cannot.  The game selector
(build/ghostldr/selector.bin, docs/selector.md) is served on TCP 18196: the
core runs it before the title when more than one title is installed, or with
--select.

Fork additions (docs/host-tooling.md): a boot first runs a preflight
coverage check when a local app0 and the NID name table are staged:
imports that would bind to stubs (which return 0 and look like success
to the title) refuse the boot unless --force-preflight is given.  The
full report lands in build/ghostldr/preflight.md.  The payload also
pins the extension's SHA-256 (GHOSTLDR_EXT_SHA256), which the core
verifies after the CRC-32 screen.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import socket
import subprocess
import sys
import threading
import time
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CORE = ROOT / "build/ghostldr/core.bin"
LAYOUT = ROOT / "build/ghostldr/core.json"
EXT = ROOT / "build/ghostldr/ext.bin"
SELECTOR = ROOT / "build/ghostldr/selector.bin"
BOOT_LUA = ROOT / "ghostldr/lua/ghostldr.lua"
from console import console_ip
import profiles
LOG_PORT = 18194
EXT_PORT = LOG_PORT + 1   # TCP
SEL_PORT = LOG_PORT + 2   # TCP
LUA_MAX = 500 * 1024      # Luac0re's remote Lua loader reads at most this much


def local_ip_for(host: str) -> str:
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        s.connect((host, 9))
        return s.getsockname()[0]


def build_core() -> None:
    try:
        subprocess.run(["make", "-s", "-C", str(ROOT / "ghostldr/native")], check=True)
    except (OSError, subprocess.CalledProcessError) as e:
        hint = " (a release's prebuilt core is there: add --no-build)" if CORE.exists() and EXT.exists() else ""
        raise SystemExit(f"building the core failed: {e}{hint}")


def build_payload(flags: int, log_ip: str, app_root: str, knobs: dict[str, int], ext: bytes = b"",
                  sel: bytes = b"") -> bytes:
    core = CORE.read_bytes()
    layout = json.loads(LAYOUT.read_text())
    text_size = (layout["__text_end"] + 0x3FFF) & ~0x3FFF
    if layout["__data_start"] != text_size:
        raise SystemExit(f"core data must start at the text page boundary ({text_size:#x})")
    header = "\n".join([
        f'GHOSTLDR_CORE_HEX = "{core.hex()}"',
        f"GHOSTLDR_TEXT_SIZE = {text_size:#x}",
        f"GHOSTLDR_IMAGE_SIZE = {layout['__image_end']:#x}",
        f'GHOSTLDR_LOG_IP = "{log_ip}"',
        f"GHOSTLDR_LOG_PORT = {LOG_PORT}",
        f"GHOSTLDR_FLAGS = {flags}",
        f'GHOSTLDR_APP_ROOT = "{app_root}"',
        f"GHOSTLDR_EXT_PORT = {EXT_PORT}",
        f"GHOSTLDR_EXT_SIZE = {len(ext)}",
        f"GHOSTLDR_EXT_CRC = {zlib.crc32(ext):#x}",
        # fork: pin the blob's SHA-256 in the (trusted) payload; the core
        # verifies it after the CRC screen (docs/host-tooling.md)
        *([f'GHOSTLDR_EXT_SHA256 = "{hashlib.sha256(ext).hexdigest()}"'] if ext else []),
        f"GHOSTLDR_SEL_PORT = {SEL_PORT}",
        f"GHOSTLDR_SEL_SIZE = {len(sel)}",
        f"GHOSTLDR_SEL_CRC = {zlib.crc32(sel):#x}",
        *[f"GHOSTLDR_{k.upper()}_MIB = {v}" for k, v in knobs.items()],
        "",
    ])
    payload = (header + BOOT_LUA.read_text()).encode()
    if len(payload) >= LUA_MAX:
        raise SystemExit(f"the Lua payload is {len(payload)} bytes; Luac0re reads at most {LUA_MAX}")
    return payload


class ExtServer(threading.Thread):
    """Serves ext.bin (or selector.bin) to the core: each connection gets the whole blob."""

    def __init__(self, blob: bytes, port: int = EXT_PORT, label: str = "extension") -> None:
        super().__init__(daemon=True)
        self.blob, self.label = blob, label
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            self.sock.bind(("0.0.0.0", port))
        except OSError as e:
            raise SystemExit(f"cannot serve the {label} on TCP {port}: {e}")
        self.sock.listen(4)
        self.sock.settimeout(0.5)
        self.stop = threading.Event()
        self.sent = threading.Event()

    def run(self) -> None:
        while not self.stop.is_set():
            try:
                conn, peer = self.sock.accept()
            except socket.timeout:
                continue
            with conn:
                conn.settimeout(30)
                try:
                    conn.sendall(self.blob)
                    self.sent.set()
                    print(f"{self.label}: sent {len(self.blob)} bytes to {peer[0]}", flush=True)
                except OSError as e:
                    print(f"{self.label}: sending to {peer[0]} failed: {e}"
                          + (" (the core closes it unread when no choice is needed)" if self.label == "selector" else ""),
                          flush=True)


# Fork: plain-language causes for the core's extension failure lines
# (ext.c ext_fetch/ext_validate/ext_start).
EXT_HINTS = (
    ("no extension from the computer",
     "the core could not fetch ext.bin: allow INBOUND TCP 18195 in this computer's firewall (the console connects to run.py)."),
    ("SHA-256 mismatch", "the served ext.bin differs from the payload's pinned digest: rebuild and re-run so payload and blob come from the same build."),
    ("CRC-32", "the served ext.bin differs from the payload header: do not mix a payload and a blob from different runs or builds."),
    ("implausible size", "the payload header and the served blob disagree on the extension's size; rebuild and retry."),
    ("receive failed", "the ext.bin transfer dropped mid-way; check the network path to the console and retry."),
    ("no memory for", "the console had no room for the extension blob; free memory on the console and retry."),
    ("not an extension blob", "what was served is not an ext.bin from this build; rebuild (make -C ghostldr/native) and retry."),
    ("built for API", "core and ext.bin come from different builds; rebuild both together (make -C ghostldr/native)."),
    ("bad image layout", "core and ext.bin come from different builds; rebuild both together (make -C ghostldr/native)."),
    ("NID table", "the blob's NID table failed validation; rebuild (make -C ghostldr/native) and retry."),
    ("no executable memory", "no placement could hold the extension's code this boot; retry, or test the other placement with --ext-jit."),
    ("ext_init failed", "the extension built and placed but its init failed; the lines above this one name the family that refused."),
)


def hint_for(line: str) -> str | None:
    for needle, hint in EXT_HINTS:
        if needle in line:
            return hint
    return None


class LogListener(threading.Thread):
    def __init__(self, logfile: Path | None) -> None:
        super().__init__(daemon=True)
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.bind(("0.0.0.0", LOG_PORT))
        self.sock.settimeout(0.5)
        self.lines: list[str] = []
        self.stop = threading.Event()
        self.logfile = logfile.open("a") if logfile else None

    def run(self) -> None:
        while not self.stop.is_set():
            try:
                data, _ = self.sock.recvfrom(65535)
            except socket.timeout:
                continue
            text = data.decode("utf-8", "replace")
            for line in text.splitlines():
                stamped = f"{time.strftime('%H:%M:%S')} {line}"
                print(stamped, flush=True)
                self.lines.append(line)
                if self.logfile:
                    self.logfile.write(stamped + "\n")
                    self.logfile.flush()
                hint = hint_for(line)
                if hint:
                    print(f"        [hint] {hint}", flush=True)
                    if self.logfile:
                        self.logfile.write(f"        [hint] {hint}\n")
                        self.logfile.flush()


def doctor(args: argparse.Namespace) -> int:
    """Fork: verify this tree and network before a boot (docs/host-tooling.md)."""
    rows: list[tuple[str, str, str]] = []

    def row(status: str, name: str, detail: str = "") -> None:
        rows.append((status, name, detail))

    v = sys.version_info
    row("PASS" if v >= (3, 11) else "FAIL", "python >= 3.11", f"{v.major}.{v.minor}.{v.micro}")
    for name, path in (("core.bin", CORE), ("core.json", LAYOUT), ("ext.bin", EXT)):
        row("PASS" if path.exists() else "FAIL", name,
            f"{path.stat().st_size} bytes" if path.exists() else "build it: make -C ghostldr/native")
    if SELECTOR.exists():
        row("PASS", "selector.bin", f"{SELECTOR.stat().st_size} bytes")
    else:
        row("WARN", "selector.bin", "absent: boots serve no game selector (fine with one title)")
    if CORE.exists() and LAYOUT.exists():
        try:
            want = json.loads(LAYOUT.read_text())["bin_size"]
            got = CORE.stat().st_size
            row("PASS" if got == want else "FAIL", "core.bin integrity",
                f"{got} bytes, core.json bin_size {want}")
        except (ValueError, KeyError) as e:
            row("FAIL", "core.json integrity", str(e))
    if CORE.exists() and LAYOUT.exists() and EXT.exists():
        try:
            payload = build_payload(0, "127.0.0.1", "ghostfs",
                                    {"gpu_heap": 0, "slack": 0, "pool1": 0, "cpu_heap": 0},
                                    EXT.read_bytes(), SELECTOR.read_bytes() if SELECTOR.exists() else b"")
            row("PASS" if len(payload) < LUA_MAX else "FAIL", "lua payload",
                f"{len(payload)} of {LUA_MAX} bytes")
        except SystemExit as e:
            row("FAIL", "lua payload", str(e))
    for name, port, proto in (("UDP 18194 (log)", LOG_PORT, socket.SOCK_DGRAM),
                              ("TCP 18195 (ext)", EXT_PORT, socket.SOCK_STREAM),
                              ("TCP 18196 (selector)", SEL_PORT, socket.SOCK_STREAM)):
        s = socket.socket(socket.AF_INET, proto)
        try:
            s.bind(("0.0.0.0", port))
            note = " (a running recorder owns the log port; that is fine)" if recorder_running() else ""
            row("PASS", name, f"free{note}")
        except OSError as e:
            row("FAIL", name, f"cannot bind: {e}")
        finally:
            s.close()
    if args.host:
        try:
            with socket.create_connection((args.host, 9026), timeout=3):
                row("PASS", "console :9026", args.host)
        except OSError as e:
            row("FAIL", "console :9026", f"{args.host}: {e} (is Luac0re's loader running?)")
    else:
        row("WARN", "console :9026", "not checked: pass --host <console-ip>")
    app0 = ROOT / "build/ghost/app0"
    names = ROOT / "build/nid/known_names.txt"
    if (app0 / "eboot.bin").exists() and names.exists():
        tool = ROOT / "ghostldr/tools/import_report.py"
        r = subprocess.run([sys.executable, str(tool), str(app0)], capture_output=True, text=True)
        last = (r.stdout.strip().splitlines() or ["no output"])[-1]
        row("PASS" if r.returncode == 0 else "WARN", "title dump preflight", last)
    elif app0.exists():
        row("WARN", "title dump", "app0 staged but no eboot.bin/name table; import coverage unchecked")
    else:
        row("WARN", "title dump", "no local app0 staged (normal for installed titles)")

    for status, name, detail in rows:
        print(f"{status:<4}  {name:<24} {detail}", flush=True)
    return 1 if any(s == "FAIL" for s, _, _ in rows) else 0


def preflight(force: bool) -> None:
    """Fork: coverage-gate a boot against a staged local app0.

    Skips cleanly when there is nothing to check against (no local
    app0, or a tree with no generated name table): the gate must never
    be the reason a boot fails on a tree that cannot run the checker.
    """
    app0 = ROOT / "build/ghost/app0"
    if not (app0 / "eboot.bin").exists():
        print("preflight: no local app0 at build/ghost/app0; skipped", flush=True)
        return
    if not (ROOT / "build/nid/known_names.txt").exists():
        print("preflight: build/nid/known_names.txt missing (no build in "
              "this tree); skipped", flush=True)
        return
    out_json = ROOT / "build/ghostldr/preflight.json"
    out_md = ROOT / "build/ghostldr/preflight.md"
    tool = ROOT / "ghostldr/tools/import_report.py"
    r = subprocess.run([sys.executable, str(tool), str(app0),
                        "--json", str(out_json), "--md", str(out_md)],
                       capture_output=True, text=True)
    if r.returncode != 0:
        tail = (r.stderr.strip().splitlines() or ["?"])[-1]
        print(f"preflight: coverage tool failed ({tail}); continuing "
              "without the gate", flush=True)
        return
    rep = json.loads(out_json.read_text())
    by = rep["summary"]["functions_by_class"]
    un = by.get("UNRESOLVED", 0)
    print(f"preflight: {rep['title']}: " +
          ", ".join(f"{k} {v}" for k, v in sorted(by.items())) +
          f" (report: build/ghostldr/preflight.md)", flush=True)
    if un and not force:
        raise SystemExit(
            f"preflight: {un} imports resolve to nothing; the title "
            "would call stubs that return 0.  See "
            "build/ghostldr/preflight.md, or pass --force-preflight.")


def recorder_running() -> int:
    """pid of a running recorder.py (it owns the log port), or 0."""
    try:
        pid = int((ROOT / "build/ghostldr/recorder.pid").read_text())
        os.kill(pid, 0)
        return pid
    except (OSError, ValueError):
        return 0


def send_lua(host: str, payload: bytes, port: int = 9026) -> None:
    with socket.create_connection((host, port), timeout=10) as s:
        s.sendall(payload)
        s.shutdown(socket.SHUT_WR)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=["probe", "boot", "logs", "lua", "doctor"])
    parser.add_argument("--no-build", action="store_true",
                        help="use the prebuilt core in build/ghostldr (from a release) instead of running make")
    parser.add_argument("--keep-host-memory", action="store_true",
                        help="boot without freeing SWRR's emulator direct-memory buffers first")
    parser.add_argument("--snap", action="store_true",
                        help="log every title thread's location every 20 s (watchdog)")
    parser.add_argument("--count-imports", action="store_true",
                        help="count calls to the title's imports; the watchdog prints the busiest (implies --snap)")
    parser.add_argument("--profile", action="store_true",
                        help="sample the title's main thread every 20 s and print its hottest stacks")
    parser.add_argument("--gpu-heap-mib", type=int, default=0,
                        help="size of the title's general GPU heap (default: its own 1390 MiB); "
                             "the streaming pool gets what this frees")
    parser.add_argument("--slack-mib", type=int, default=0, help="free memory left after the plan (default 128)")
    parser.add_argument("--pool1-mib", type=int, default=0, help="type-0 engine heap at 0x1100000000 (default 332)")
    parser.add_argument("--cpu-heap-mib", type=int, default=0, help="CPU malloc heap at 0x1000000000 (default 384)")
    parser.add_argument("--force-title-ready", action="store_true",
                        help="experiment: set the title world's ready flag from the watchdog")
    parser.add_argument("--ext-jit", action="store_true",
                        help="test: put the extension's code in a new JIT block instead of the core's RX area")
    parser.add_argument("--title", help="title to boot: one of the installed ones (ghostfs; default: the only one "
                        "installed) or the dump at --app-root (default: found by its eboot fingerprint)")
    parser.add_argument("--trace-opens", action="store_true",
                        help="log every file the title opens (capture_order.py turns run.log into an open order)")
    parser.add_argument("--dialog-cancel", action="store_true",
                        help="answer every system dialog with buttons by cancelling (to bisect a title hang)")
    parser.add_argument("--ime-fixed-name", action="store_true",
                        help="text input answers \"Player\" instead of the console user's name")
    parser.add_argument("--keep-remote-play", action="store_true",
                        help="dev: ignore the title's sceRemoteplayProhibit, so a Remote Play viewer keeps its picture")
    parser.add_argument("--select", action="store_true",
                        help="show the game selector even with one title installed or --title given "
                             "(docs/selector.md); every profile is sent and --title is not used")
    parser.add_argument("--select-font", choices=["auto", "builtin"], default="builtin",
                        help="selector text: the built-in Noto Sans (default), or try the console's system "
                             "font first (auto; experimental: it crashed SWRR on a 13.60 PS5)")
    parser.add_argument("--no-selector", action="store_true", help="do not serve the game selector")
    parser.add_argument("--force-preflight", action="store_true",
                        help="fork: boot even when the preflight coverage gate finds unresolved imports")
    parser.add_argument("--diag", action="store_true",
                        help="with probe: log what the loader needs to know about this console (PS4 support, "
                             "docs/ps4.md); boots and releases nothing")
    parser.add_argument("--boot-start-modules", action="store_true",
                        help="start IsGame modules (NpToolkit2, ...) at boot as before, not at the title's "
                             "sceSysmoduleLoadModule")
    parser.add_argument("--host", default=None, help="console address (default: looked up by host-id)")
    parser.add_argument("--wait", type=float, default=None,
                        help="seconds to keep printing the console's log (default: boot keeps listening until "
                             "Ctrl+C; probe and logs stop after 20 s)")
    parser.add_argument("--app-root", default="ghostfs",
                        help="where the title's app0 is: ghostfs (the installed titles, the default) or a "
                        "directory on a dev console, e.g. /data/ghost/app0")
    parser.add_argument("--file", type=Path, help="raw Lua file for mode=lua")
    parser.add_argument("--log", type=Path, default=ROOT / "build/ghostldr/run.log")
    args = parser.parse_args()
    if args.diag and args.mode != "probe":
        raise SystemExit("--diag goes with probe: run.py probe --diag")
    if args.mode == "doctor":   # fork: local checks only; never needs the console lookup
        return doctor(args)
    args.host = args.host or console_ip()

    recorder = recorder_running()
    listener = None if recorder else LogListener(args.log)
    if listener:
        listener.start()
    else:
        print(f"recorder (pid {recorder}) is logging to build/ghostldr/run.log", flush=True)
    if args.mode in ("probe", "boot"):
        if args.no_build:
            needed = (CORE, LAYOUT, EXT) if args.mode == "boot" else (CORE, LAYOUT)
            missing = [p.relative_to(ROOT) for p in needed if not p.exists()]
            if missing:
                raise SystemExit(f"--no-build needs {', '.join(map(str, missing))}")
        else:
            build_core()
        release = args.mode == "boot" and not args.keep_host_memory
        flags = (1 if args.mode == "probe" else 0) | (2 if release else 0) | (4 if args.snap or args.count_imports or args.profile else 0) \
            | (16 if args.profile else 0) \
            | (8 if args.count_imports else 0) | (32 if args.force_title_ready else 0) \
            | (64 if args.ext_jit else 0) | (128 if args.dialog_cancel else 0) | (256 if args.ime_fixed_name else 0) \
            | (512 if args.keep_remote_play else 0) | (1024 if args.boot_start_modules else 0) \
            | (2048 if args.select else 0) | (4096 if args.select_font == "builtin" else 0) \
            | (16384 if args.diag else 0)
        knobs = {"gpu_heap": args.gpu_heap_mib, "slack": args.slack_mib, "pool1": args.pool1_mib,
                 "cpu_heap": args.cpu_heap_mib}
        ext = EXT.read_bytes() if args.mode == "boot" else b""
        if ext:
            ext_server = ExtServer(ext)
            ext_server.start()
            print(f"serving the extension ({len(ext)} bytes) on TCP {EXT_PORT}", flush=True)
        sel = SELECTOR.read_bytes() if args.mode == "boot" and not args.no_selector and SELECTOR.exists() else b""
        if args.select and not sel:
            raise SystemExit(f"--select needs {SELECTOR.relative_to(ROOT)} (make -C ghostldr/native)")
        if sel:
            ExtServer(sel, SEL_PORT, "selector").start()
            print(f"serving the game selector ({len(sel)} bytes) on TCP {SEL_PORT}", flush=True)
        payload = build_payload(flags, local_ip_for(args.host), args.app_root, knobs, ext, sel)
        if args.select and args.title:   # every profile, so whichever title is picked gets its own
            print(f"--select: the selector picks the title (--title {args.title} is not used)", flush=True)
        try:   # the title profiles (host/profiles.py; read by native/src/profile.c)
            bundle = profiles.boot_bundle(None if args.select else args.title,
                                          ("trace_opens",) if args.trace_opens else ())
        except profiles.ProfileError as e:
            raise SystemExit(str(e))
        payload = f'GHOSTLDR_PROFILE_HEX = "{bundle.hex()}"\n'.encode() + payload
        if args.mode == "boot":   # fork: coverage gate (skips cleanly without a staged app0)
            preflight(args.force_preflight)
        print(f"sending {len(payload)} bytes of Lua to {args.host}:9026", flush=True)
        send_lua(args.host, payload)
        if ext and not ext_server.sent.wait(60):
            print(f"extension: the console did not fetch it (is TCP {EXT_PORT} open in this computer's firewall?)",
                  flush=True)
    elif args.mode == "lua":
        send_lua(args.host, args.file.read_bytes())
    if listener:
        wait = args.wait if args.wait is not None else (None if args.mode == "boot" else 90.0 if args.diag else 20.0)
        if wait is None:
            print("listening for the console's log; press Ctrl+C to stop (the game keeps running)", flush=True)
        try:
            if wait is None:
                while True:
                    time.sleep(3600)
            time.sleep(wait)
        except KeyboardInterrupt:
            pass
        listener.stop.set()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
