# Compatibility

What runs with ghostldr, where, and the known limits. To run it, see [using-the-release.md](using-the-release.md).

## Consoles

| | Status |
|---|---|
| **PS5, firmware 13.60 and later** | Supported, with SWRR US (CUSA03474) or EU (CUSA03492) and Luac0re 2.4b. |
| **PS4** | Homebrew and small titles only. |
| **Jak X with UltraC0re** | Experimental. |

### On a PS4

- **Memory:** the PS4's kernel gives PS2 Classics such as SWRR 2.5 GiB of memory, and this can't be lifted. Ghost of Tsushima needs about 4 GiB, so big games can't run.
- **Games come from SWRR's saved data only.** The PS4 can't give SWRR a USB drive, so install games over the network (about 40 MB/s on a PS4 Pro).
- **The selector marks every game's dump** `May not run on PS4` and asks before it starts one. Homebrew isn't marked.
- **No ELF loader** (`ghostldr-elfldr.bin` is refused), and no return to the selector after a game.
- **The log** stays in `/temp0/ghostldr.log`.
- **The autoloader save** works (tested with Apollo Save Tool on a 12.50 PS4 with GoldHEN).
- Tested on a PS4 Pro at 12.50. The 2.5 GiB limit is the same on 9.60.

### In Jak X

ghostldr can use *Jak X: Combat Racing* in place of SWRR: the EU PS2 Classic (CUSA07992, update 1.04) with [UltraC0re](https://github.com/matem6/UltraC0re) 1.0.2 in place of Luac0re. Ghost of Tsushima plays there, in its PS4 Pro mode.

- **For developers for now.** UltraC0re's save needs a small patch on consoles where Jak X loads at a fixed address, and the release's two-file boot hasn't been tried there. [developers.md](developers.md#jak-x) has the tested way.
- **Its loader is on port 8888**, not 9026, and it takes about 6 minutes to reach (Jak X's intro can't be skipped).
- **Installs and progress are separate** from SWRR's: Jak X keeps its own saved data.
- No autoloader save, and no return to the selector after a game.

## Games

| Game | Status |
|---|---|
| **Ghost of Tsushima** v2.18 (CUSA11456) | Plays. The most tested title: menus, movies, New Game, Continue, saving. From a USB drive it reaches its menu in about 35 seconds. |
| **Bloodborne** 1.09 (CUSA00900) | Plays: loading, playing and saving. Its memory plan is built in. |
| **Other PS4 games** | Boot as far as their imports and memory allow. |
| **PS5 games** | Can't run: SWRR runs in PS4 mode. The selector leaves them out. |

Use the dump of the version listed: a game's memory plan and fixes apply to that build only. Another version runs as an unknown game.

**Tried a game?** Report it with the [game compatibility form](https://github.com/asylumexp/ghostldr/issues/new/choose), with the boot's log from the USB drive.

## Homebrew

OpenOrbis homebrew runs from a USB drive or from saved data, with no setup per title. It gets:

- its own files in `/app0`, and `/data` (kept in a save container of its own);
- memory, threads and thread-local variables;
- the screen, the controller, audio and FreeType fonts;
- OpenGL ES 2 through Piglet, drawn on the console's GPU (homebrew built on SDL2's PS4 port);
- network sockets;
- save data, and save data memory;
- its `printf` output in ghostldr's log.

Homebrew made for jailbroken consoles runs too, as far as it doesn't need the kernel: there is no kernel access, and jailbreak calls get a stand-in answer. Exiting a homebrew goes back to the selector on a PS5.

Tested: the OpenOrbis samples (hello world, fonts, input, audio, exceptions, libraries) and ghostldr's own test programs. PS4-Xplorer 1.34 boots, but shows its firmware menu again on every launch, so it isn't listed as compatible.

## Apollo Save Tool

Apollo Save Tool for PS4 runs under ghostldr on a stock PS5, on the saves of the console's signed-in users.

[apollo.md](apollo.md) lists what it can and can't do.

- **Whose saves:** the selector asks which user's saves to open, then looks for that user's saves (the first time can take two minutes; hold Circle to cancel).
- **What works:** Apply cheats, Import decrypted save files, Copy save game to HDD, and resign, into a save the game already has. An import copies its files over the save and deletes nothing.
- **Close SWRR afterwards.** A box at the bottom of the screen says so: the system commits the save when SWRR closes. Apollo's own "success" message isn't the end.
- **Refused, with a message** that says why and "Nothing was changed":
  - the files don't fit (a save's size is fixed);
  - a file would have to be removed and there is no keystone for the game.
- **What can't work** on a stock console: a new save for a game that has none (start the game and save once, then copy over that save), another account's saves, trophies, encrypted saves on USB, and activating accounts.

## Known limits

- **Memory.** SWRR has 4.5 GiB on a PS5. A game that needs more needs a memory plan, which only Ghost and Bloodborne have so far; others learn one over their first boots. "The game needs more memory than SWRR has" means it can't run yet.
- **Code size.** Game code can run only in the PS2 emulator's JIT memory, about 65 MiB in all. Larger executables are spread over it. "There's no room for the game's code" means it didn't fit, or the last game left too little: restart SWRR.
- **USB drives:** up to four drives and 64 games, four folders deep, paths up to about 250 bytes. FAT32 holds no file of 4 GiB or more. The PS5 must use the drive as USB storage, not extended storage.
- **Dumps:** decrypted, with the update merged in. DLC isn't loaded.
- **Progress** is in SWRR's saved data, per SWRR region and PSN user, never on the drive.
- **System dialogs** are drawn only over games that draw with the CPU (most homebrew). Over other games (Ghost, Bloodborne) they are answered at once.
- **The selector** shows names in Japanese, Chinese and Korean as the title ID, and has no sound.
- **Back to the selector:** system libraries a game loaded stay loaded, and a few of its threads may be parked until SWRR closes.
