# Title profiles (fork)

Everything the core used to hardcode per title — the memory
planner's table offsets and pool sizes in `budget.c`, the
lazy-backing call sites, the heap-accounting object offsets in
`hooks.c` — now lives in one struct, `struct title_profile`
(`ghost.h`, `native/src/profile.c`), chosen at boot before any
module is loaded.

## The built-in profile

With no host profile, the core uses its built-in: Ghost of
Tsushima CUSA11456 v2.18, byte-for-byte the constants the code
always shipped with. `titles/CUSA11456.json` is the same profile
in data form; a unit test (`test_title_profile.py`) encodes the
JSON and compares it against the built-in values so the two can
never drift apart silently.

## Sending another title's profile

    python3 ghostldr/host/run.py boot --title-profile titles/CUSA99999.json

`tools/title_profile.py` encodes the JSON into a flat array of 48
u64 words; `run.py` embeds it in the Lua payload as
`GHOSTLDR_PROFILE`, `ghostldr.lua` writes it to fresh memory and
points the boot context at it, and `profile_select()` validates
(magic, version, counts, offset and size bounds) and adopts it.
Anything malformed keeps the built-in and logs why.

Safety does not rest on the profile being right: budget still
verifies the streaming-pool table's contents in the title's own
text before patching it, and the diagnostic hooks still match
prologues byte for byte. A wrong profile patches nothing.

## What a profile cannot carry

The diagnostic hooks in `hooks.c` are compiled C that reads one
title's engine internals (heap objects, movie player, warp state
machine). Their *offsets* are profile data; the hook code itself
is not. A profile therefore declares `builtin_hooks`: profiles
for titles the compiled hooks were not written for must leave it
false, and `hooks_patch_text` then skips patching (with a log
line) instead of applying another title's hooks. Porting the
hooks to a new title remains source work, like it always was;
the planner no longer is.

## JSON fields

| field | meaning |
|---|---|
| `title_id` | CUSA id; the first 8 chars become the profile tag |
| `builtin_hooks` | the compiled-in hooks fit this title |
| `stream_pool_table` | eboot offset of the streaming-pool mode table |
| `stream_pool` | its 6 mode sizes in bytes (verified against the text before patching) |
| `knobs[]` | `{table, knob_slot, name, default_mib}` — other planner tables resized by run.py's `--*-mib` flags; `knob_slot` is the boot-context slot (4, 6, 7), `name` one of `general GPU heap`, `type-0 engine heap`, `CPU malloc heap` |
| `fixed_mib` | mode-0 reservations other than the pools, total |
| `remainder_mib` | the planner's general-heap remainder |
| `slack_mib` | free memory left for late allocations (default when `--slack-mib` is 0) |
| `lazy_total_mib` | full size of the lazily backed reservations |
| `lazy_reserve_mib` | physical memory kept for their commits |
| `movie_reserve_mib` | memory reserved for the video decoder |
| `min_pool_mib` | streaming-pool floor |
| `lazy_sites` | eboot offsets (return addresses) whose allocations vdm backs lazily |
| `heap_obj0`, `heap_obj1` | heap object offsets for the hooks' live-usage accounting |

`budget.c`'s header comment explains how the Ghost numbers were
measured; a new title's profile needs the same measurements from
its own planner tables.
