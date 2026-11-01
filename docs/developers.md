# Developers

For homebrew developers and for working on ghostldr itself. To run a release, see [using-the-release.md](using-the-release.md). The design detail lives in the source's comments and the git history.

## The repository

| Path | What it is |
|---|---|
| `ghostldr/native/` | The loader core (C), which runs inside SWRR from the PS2 emulator's JIT buffer, and its two runtime modules: the extension (`ext/`, [its README](../ghostldr/native/ext/README.md)) and the game selector (`selector/`). |
| `ghostldr/lua/` | Scripts for Luac0re's loader: the bootstrap `ghostldr.lua`, the autoloader `auto.lua`, `manager.lua`, and the install receiver. |
| `ghostldr/host/` | Tools on a computer (Python), [below](#tools-on-a-computer). |
| `ghostldr/data/titles/` | Title profiles, [below](#title-profiles). |
| `ghostldr/tools/` | Build and analysis helpers: the extension packer and checker, the bundle maker, the import report, the stub report. |
| `ghostldr/tests/` | Offline tests. |
| `ghostldr/payloads/`, `host/payloads/` | Payloads for ghostldr's ELF loader, and dev payloads for jailbroken consoles. |
| `plans/`, `tools/contrib/` | Community memory plans and their collection server ([tools/contrib/README.md](../tools/contrib/README.md)). |
| `tools/` | `fetch_deps.sh`, `make_release.py`, `make_save.py`, and `release-README.txt` (the release's `README.txt`). |

## Building and testing

[README.md](../README.md#building-from-source) has the commands. In short:

- `tools/fetch_deps.sh` fetches the PS4 symbol names and Luac0re 2.4b into `build/`.
- `make -C ghostldr/native` builds the core, the extension and the selector, and the release's `ghostldr.lua`, `ghostldr-ext.bin` and `ghostldr-elfldr.bin` in `build/ghostldr/`.
- `python3 -m unittest discover -s ghostldr/tests` runs every test offline. Tests that need the build or a desktop Lua 5.3/5.4 skip without them. GitHub Actions runs them on macOS for every push and pull request.
- With your Ghost of Tsushima v2.18 dump in `build/ghost/app0/` (git ignores it), `ghostldr/tools/check_ext.py` also checks that the extension resolves its imports as before.

## Tools on a computer

The release needs none of these. They boot builds from a checkout and help with bringing up titles. Each finds the console on the network by itself; `PS_HOST=192.168.1.123` (or `PS_HOST_ID`) picks one.

| Tool | What it does |
|---|---|
| `ghostldr/host/run.py boot` | Builds, sends the core with SWRR at Luac0re's loader, serves the extension and selector, and logs the run to `build/ghostldr/run.log`. `--title`, `--app-root usb:/FOLDER`, `--select`, `--snap` (thread locations every 20 s), `--trace-opens`; `--help` lists the rest. |
| `ghostldr/host/run.py elfldr` | The ELF loader, served from the checkout. |
| `ghostldr/host/run.py doctor`, `logs` | Checks the computer and the console; shows the console's log. |
| `ghostldr.py` | Everyday commands over those: `copy` and `check` a USB drive, `boot`, `install`, `logs`, `elfldr`, and `resign` (another account's save into your own save of the game, through the ELF loader). |
| `ghostldr/host/gfs_pack.py`, `gfs_install.py` | Lay out and install a title into SWRR's saved data (`--list`, `--remove TITLE`). |
| `ghostldr/host/manager.py` | Starts `manager.lua` and prints its address and token. |
| `ghostldr/host/elf_send.py` | Sends a payload to the ELF loader and exits with its exit code. |
| `ghostldr/host/profiles.py` | `new`, `check`, `show` and `detect` title profiles. |
| `ghostldr/tools/import_report.py` | Lists every import of a dump and how it would bind, before the first boot. |
| `ghostldr/tools/stub_report.py` | Ranks the `UNRESOLVED call` lines of a log: the work list for a new title. |

## The ELF loader

ghostldr has an ELF loader that runs inside SWRR on a stock PS5, with no kernel exploit. Send it a payload and it runs, with its output coming back on the same connection. Then send the next one, without restarting SWRR. A payload gets SWRR's userland privileges and nothing more.

### Start it

- **On its own:** send `ghostldr.lua` to Luac0re's loader, then `ghostldr-elfldr.bin` to the port it asks for. The connection stays open with the loader's log.
- **Beside the game selector:** with `ghostldr-ext.bin`, the ELF loader listens beside the selector until a game is picked. When one is picked it waits for running payloads, then goes away before the game loads.
- **From a checkout:** `python3 ghostldr/host/run.py elfldr`.

Later sessions need `ghostldr.lua` alone: the bundle it took is cached. The port is 9021 on a stock console and 9022 on a jailbroken one, whose own ELF loader has 9021.

### Send a payload

```bash
nc 192.168.1.123 9021 < hello.elf
```

`nc` needs no options. Lines from the loader start with `[elfldr] `; the rest is the payload's stdout and stderr. The connection closes when the payload has finished, with its exit code:

```
[elfldr] payload 2: ELF (OpenOrbis/PS4 ABI), 32 KiB of code at 20007f8000 (in the 8 MiB JIT object), 64 KiB of data, 16 imports
hello from payload2, running inside SWRR (pid 96)
hello: exiting with code 7
[elfldr] payload 2 exited with code 7 after 0.254 s
```

Instead of an ELF, a client may send one line:

| Line | What it does |
|---|---|
| `status` | Lists the payloads that run. |
| `quit` | Stops the loader and gives SWRR back to Luac0re's loader (not while a payload runs). |
| `boot` | Stops the loader and boots games with the cached `ghostldr-ext.bin`. |
| `log` | That connection gets ghostldr's log from now on. |
| `forget` | Deletes the cached bundle. |
| `help` | Lists these. |

A ghostldr bundle sent to the port is kept for the next boot instead of run.

### What a payload gets

- **A thread** with a 2 MiB stack, and threads of its own with their thread-local variables.
- **Memory:** `mmap` and `malloc` from SWRR's direct memory, given back when the payload finishes.
- **Files** as SWRR sees them, and **sockets** (made by the JIT compiler process, since SWRR's own `socket()` fails on a PS5).
- **stdout and stderr** on its connection.
- **The end:** when none of its threads runs. `exit()` ends the thread that calls it, not SWRR. A thread that faults is reported and ends; SWRR and other payloads go on.

### Build a payload

**OpenOrbis.** Link as the [OpenOrbis PS4 toolchain](https://github.com/OpenOrbis/OpenOrbis-PS4-Toolchain)'s samples do and send the ELF that `ld.lld` writes (not the `.self`: its TLS alignment can misplace thread-local initial values):

```bash
TC=/path/to/PS4Toolchain
clang --target=x86_64-pc-freebsd12-elf -fPIC -funwind-tables -O2 -isysroot $TC -isystem $TC/include -c hello.c
ld.lld hello.o -o hello.elf -m elf_x86_64 -pie --script $TC/link.x --eh-frame-hdr -L$TC/lib -lc -lkernel $TC/lib/crt1.o
```

`ghostldr/tests/elfldr/` has samples (threads, a TCP echo server, a fault, a freestanding payload): `make -C ghostldr/tests/elfldr OO_PS4_TOOLCHAIN=$TC`.

**Freestanding.** A payload with no libc and no imports gets, in `rdi`, the arguments ps5-payload-sdk's payloads get, without kernel access:

```c
struct el_args {
    int (*sys_dynlib_dlsym)(int handle, const char *name, void *out); /* handle -1: any module */
    int *rwpipe, *rwpair;             /* NULL: no kernel R/W */
    long kpipe_addr, kdata_base_addr; /* 0 */
    int *payloadout;                  /* the exit code, if the payload sets it */
};
int payload_main(struct el_args *args);  /* its return value is the exit code */
```

**Which ELFs are taken:** position-independent x86-64 (`ET_DYN`) with code and writable data in separate 16 KiB pages (`-z max-page-size=0x4000 -z separate-code`): an `ld.lld -pie` ELF, a fake-signed SELF or OELF (with `run.py elfldr`; `ghostldr-elfldr.bin` has no NID table), or a freestanding ELF. Anything else is refused with the reason.

### Limits

- **No kernel:** no kernel R/W, no jailbreak, no other process's memory.
- **PS4 ABI only.** ps5-payload-sdk payloads are refused: their startup needs kernel R/W and PS5 libraries.
- **No new executable memory:** code runs only from views of the emulator's JIT objects, so a payload can't JIT. At most three payloads run at once, each with up to 16 MiB of code.
- **No killing a payload:** one whose threads never end keeps its slot until SWRR restarts.
- A payload must not install its own SIGSEGV, SIGBUS, SIGILL or SIGFPE handlers.
- A PS5 with Luac0re in SWRR only.

## Title profiles

`ghostldr/data/titles/<TITLE>.json` is merged over `default.json` and checked by `profiles.py check`. A profile binds to one build of the game by its `eboot.fingerprint`; on any other build the defaults apply. The release's `ghostldr.lua` carries every profile.

| Field | What it does |
|---|---|
| `title`, `name`, `version`, `notes` | The ID (the file's name), the name the selector shows when the game has no `param.sfo`, the version, free text. |
| `eboot.fingerprint` | `DT_SCE_FINGERPRINT` of `eboot.bin` (`profiles.py detect`). Needed for a memory plan, `exec` and `tls_sites`. |
| `pack` | The save prefix (`prefix`, Ghost's is `GHOST`) and the order files are packed in for saved-data installs. |
| `app_params` | `sceAppContentAppParamGetInt` values. |
| `save_blocks` | The size of `<prefix>SAVE`, in 32 KiB blocks. |
| `features` | `trace_opens`, `dialogs_auto`, `save_tool` (the selector asks whose saves, as for Apollo). |
| `memory` | `plan-free` (the default: a fixed budget, and a plan learned from earlier boots), or `plan`: tables in the executable to set or shrink, lazily backed allocations, byte patches, and parts of CPU-only heaps kept in a swap file. See Ghost's (`CUSA11456.json`) and Bloodborne's (`CUSA00900.json`). |
| `hle` | Up to 32 rules that answer one import without C: a return value, and constants written through pointer arguments. |
| `exec`, `tls_sites` | Code ranges for executables that need several JIT buffers, and thread-pointer loads to patch. |

Bringing up a title: boot it with `run.py boot --snap`, read `build/ghostldr/run.log`, and work down the `UNRESOLVED call` lines (`stub_report.py`). A call that can just succeed or fill in constants gets an HLE rule; one that needs logic gets C in the extension, one family per file in `ghostldr/native/ext/src/hle_<family>.c`.

## Games in saved data

An installed game lives in SWRR's save containers, each title under its prefix `<P>` (`G` and the title ID by default, `GCUSA12345`):

| Container | Holds |
|---|---|
| `<P>000`, `<P>001`, … | The game's files, 992 MiB per container. |
| `<P>INDEX` | Where each file is. |
| `<P>META` | Its name and art for the selector. |
| `<P>SAVE`, `<P>D001SAVE`, … | Its progress. Never removed with the install. |
| `GFSCATALOG` | The list of installed titles. |
| `GLDRCACHE`, `GLDRCONF`, `GLDRPLANS` | The cached bundle, the settings, the memory plans. |

SWRR's own save (`SLUS-20268`, `SLES-50366`) is never written. The layout is in `ghostldr/host/gfs_catalog.py` and `ghostldr/native/src/ghostfs.c`.

## Jak X

Jak X (EU CUSA07992, update 1.04) with UltraC0re 1.0.2 runs ghostldr from a checkout:

1. If Jak X's executable loads at `0x400000` on your console, patch UltraC0re's bootstrap: `python3 ghostldr/tools/ultrac0re_patch.py` on UltraC0re's `builds/jakx_ultrac0re.bin`, then UltraC0re's `scripts/craft/craft_ultrac0re.py` to rebuild its `VMC0.card`. Unpatched, the exploit hangs on a black screen. Resign the save for your account as UltraC0re's README says.
2. Trigger it: title screen, Load Profile, the UltraC0re profile, Adventure, then Triangle when the cutscene starts. Its loader listens on port 8888.
3. `python3 ghostldr/host/run.py boot` finds the loader by its port (`--loader-port 8888`). Install games with `gfs_install.py` or from a USB drive. Restart Jak X between big jobs: long installs have crashed it.

## Making a release

1. Tag the release commit, then build from a clean tree: the version comes from `git describe`.
2. **The decrypted saves**, from a decrypted Luac0re 2.4b save and US SWRR's `sce_sys/keystone` (a save carries its game's keystone):

   ```bash
   python3 tools/make_save.py --from LUAC0RE_SAVE --keystone-us CUSA03474.keystone --version v1.0.0 --out build/saves
   ```

3. **The encrypted saves**, one per region, on a jailbroken console with an FTP server as root on 2121 and that region's SWRR at Luac0re's loader:

   ```bash
   python3 ghostldr/host/resign_save.py lua copy --anyone --save build/saves/ghostldr-v1.0.0-save-EU-CUSA03492.zip
   python3 ghostldr/host/resign_save.py usb --anyone --name eu
   python3 ghostldr/host/resign_save.py lua delete
   ```

4. **The release:**

   ```bash
   python3 tools/make_release.py --version v1.0.0 --save LUAC0RE_SAVE --keystone-us CUSA03474.keystone \
       --encrypted-us build/resigned/us-CUSA03474-SLUS-20268.zip --encrypted-eu build/resigned/eu-CUSA03492-SLES-50366.zip \
       --deny-file ../deny.txt
   ```

   It writes the five files, `README.txt` from `tools/release-README.txt`, the flat zip, the two save zips and `SHA256SUMS.txt` into `build/release/`. Before writing, it checks every file for anything of this computer: private addresses other than the docs' examples, user folders, the user and host names, git's email, and the words in `--deny-file` (console names, account IDs: keep that file outside the repository).

The PKG tool is built apart from this: `python3 tools/pkgextract-cli/build.py` (the .NET 9 SDK; LibOrbisPkg comes from `tools/fetch_deps.sh` at a pinned commit, with `tools/pkgextract-cli/LibOrbisPkg.patch`) writes one executable per platform: `pkgextract-cli-macos` (NativeAOT, x64 and arm64 joined with `lipo`; needs macOS), `pkgextract-cli-linux-x64` and `-linux-arm64` (NativeAOT in the .NET SDK's Docker image; needs Docker) and `pkgextract-cli-windows-x64.exe` (.NET single-file, trimmed), with `SHA256SUMS.txt`; `--only` builds some. LibOrbisPkg (LGPL-3.0) is linked in: this source and `build.py` rebuild it with any copy of LibOrbisPkg, and `pkgextract-cli --licenses` prints the licences. The dev payloads are built apart too.
