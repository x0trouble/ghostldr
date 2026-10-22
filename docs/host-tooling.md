# Host tooling (fork additions)

Host-side tools on top of the stock release flow. All are read-only
with respect to the console except where noted.

## `run.py doctor`

    python3 ghostldr/host/run.py doctor [--host <console-ip>]

Checks the whole boot chain from this computer and prints one
PASS / WARN / FAIL line per item: Python version, prebuilt core
integrity (`core.bin` size vs `core.json`), selector presence, Lua
payload size against Luac0re's 500 KB cap, whether UDP 18194 /
TCP 18195 / TCP 18196 are free (or the log port is already owned by
the recorder), whether the console's Lua loader answers on 9026,
and — when a dump and a name table are staged — the title's import
coverage summary. Exit code 1 if anything FAILs. Doctor sends
nothing to the console beyond a TCP connect probe.

## Boot preflight gate

`run.py boot` runs `tools/import_report.py` over a staged
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

When the core's extension fetch fails, it logs a terse `ext: ...`
line and the boot stops. run.py's log listener follows such lines
with a `[hint]` line giving the plain-language cause and the fix
(firewall on TCP 18195, core/ext build mismatch, corrupt blob,
SHA-256 mismatch, and so on). The table is `EXT_HINTS` in run.py.

## Core change: SHA-256 pin for ext.bin

run.py hashes the blob (`GHOSTLDR_EXT_SHA256`), ghostldr.lua
writes the digest's first 24 bytes into the boot context after
the firmware field, and `ext_fetch` verifies them (new
`src/sha256.c`) after the CRC-32 screen. 24 bytes — a 192-bit
pin — is what the context has before the profile slot; CRC-32
alone only proves the blob matches a header inside the same Lua
payload, while the pin is a second, independent check of the
bytes that are about to run as code. Payloads too old to carry
the pin stay CRC-only; the receive log line says which check ran
(`SHA-256 verified` / `no SHA-256 pin`). The selector blob keeps
its stock CRC check.

## Merge policy with upstream

This fork tracks upstream's main and keeps only what upstream does
not have. The first core branch also carried title profiles, NID
name retention, and a placement flip; when upstream shipped the
selector update it brought its own profiles (`host/profiles.py`,
`native/src/profile.c`), its own retention (`nid_keep`), and an
evolved arena — so those three were dropped in the merge rather
than forked twice. What remains fork-only is this page: doctor,
the preflight gate, stub_report, the log hints, and the SHA-256
pin.
