# Host tooling (fork additions)

Three host-side tools on top of the stock release flow. All are
read-only with respect to the console except where noted.

## `run.py doctor`

    python3 ghostldr/host/run.py doctor [--host <console-ip>]

Checks the whole boot chain from this computer and prints one
PASS / WARN / FAIL line per item: Python version, prebuilt core
integrity (`core.bin` size vs `core.json`), Lua payload size against
Luac0re's 500 KB cap, whether UDP 18194 / TCP 18195 are free (or
already owned by the recorder), whether the console's Lua loader
answers on 9026, and — when a dump and a name table are staged —
the title's import coverage summary. Exit code 1 if anything FAILs.
Doctor sends nothing to the console beyond a TCP connect probe.

## Boot preflight gate

`run.py boot` now runs `tools/import_report.py` over a staged
`build/ghost/app0` first (only when `build/nid/known_names.txt`
also exists; on trees that cannot run the checker it prints
"skipped" and boots as before). The summary line prints how the
title's functions bind — core-HLE, ext-HLE, title, host — and how
many are UNRESOLVED. Unresolved imports bind to stubs that return 0,
which looks like success to the title, so any unresolved count
refuses the boot. The full report is written to
`build/ghostldr/preflight.md` (and `.json`). To boot anyway:

    python3 ghostldr/host/run.py boot --force-preflight

## `tools/stub_report.py`

    python3 ghostldr/tools/stub_report.py build/ghostldr/run.log [--top N] [--json out.json]

Aggregates the stub lines the core logs at runtime (`UNRESOLVED
call: ...`, `DENIED call: ...`) into a ranked per-function hit
table: totals, distinct stubs, denied hits, and the anonymous
`UNRESOLVED call #<idx>` count. Use it after a session to decide
which HLE functions are worth implementing next — by what the
title actually called, not by what it imports.

## Log hints

When the core's extension fetch/start fails, it logs a terse
`ext: ...` line and the boot stops. run.py's log listener now
follows such lines with a `[hint]` line giving the plain-language
cause and the fix (firewall on TCP 18195, core/ext build mismatch,
corrupt blob, and so on).

## Core changes on the companion branch (`x0-fixes-core`)

Built on top of this branch; the native core changes there are:

- **SHA-256 pin for ext.bin.** run.py hashes the blob
  (`GHOSTLDR_EXT_SHA256`), ghostldr.lua writes the digest into the
  boot context, and `ext_fetch` verifies it (new `src/sha256.c`)
  after the CRC-32 screen. Contexts too old to carry the pin stay
  CRC-only; the receive log line says which check ran.
- **NID names survive boot.** Names `nid_to_name` resolves during
  boot are retained in a compact table when the 2.2 MB blob is
  freed at `ext_boot_done`, so runtime stub logs keep their names.
  Names never used during boot still return NULL. GHOST_API_VERSION
  is now 2 for the widened contract.
- **Extension placement defaults to a JIT block.** The small RX
  area capped the extension at ~48 KiB (32 KiB used) minus the
  stub reserve; a fresh JIT block is now tried first, the arena is
  the fallback, and `--ext-arena` forces the old order.
- **Title profiles.** Per-title constants are data now — see
  [title-profiles.md](title-profiles.md).
