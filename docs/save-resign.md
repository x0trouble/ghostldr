# Resigning a save without a jailbreak

A PS4 save belongs to one PlayStation account. Copy another account's save
onto your console and the game shows it as locked or corrupted: the account
ID inside the save (`sce_sys/param.sfo`) isn't yours. Resigning usually means
rewriting that ID, which needs a jailbroken console (Apollo, Save Wizard).

ghostldr does it differently, on a PS5 with no jailbreak: it puts the other
save's **files** into a save your own console already made for you. That save
keeps your account ID and the game's keystone, so the game loads it as yours.

> **Tested on a 13.60 PS5.** A 12.50 PS4 keeps a refused save mounted the
> same way (measured), but this tool hasn't been run on one yet. You need your
> own save of the game first: play it once so it makes one. Trophies aren't
> touched.

## What you need

- A PS5 (or PS4) with SWRR and Luac0re's loader, as for running a game
  ([using-the-release.md](using-the-release.md)). No jailbreak.
- A computer on the same network, with this repository (or a release).
- Your own save of the game on the console (play the game once).
- The other save, **decrypted**: what Apollo Save Tool exports, in either form:
  - **Copy save game to USB:** a folder `PS4/APOLLO/<user>_<TITLE>_<DIR>/`;
  - **Export save game to Zip:** a `.zip` with the save's folder in it;
  - or any folder holding the save's files.

  Saves people share for Apollo, and Apollo's own online save database, come
  like this. The save's `sce_sys/param.sfo` and `sce_sys/keystone`, when it
  has them, tell ghostldr the game and the save's name; nothing in `sce_sys`
  is ever written into your save.

## The steps

1. Start the game once if you never have, so it makes your save. Close it.
2. Start SWRR's loader: click the right half of the touchpad at PRESS
   START, then OPTIONS → HALL OF FAME.
3. On the computer:

   ```bash
   python3 ghostldr.py resign "Jak X (other account).zip"
   ```

   It starts ghostldr's ELF loader in SWRR, sends the files, and ghostldr
   writes them into your save of that game. Before anything changes, your
   save's present files come back to the computer, into a folder beside the
   one you named (`CUSA07992-SCUS-97429-before-resign-<time>`): that is your
   undo. Files your save has and the other save doesn't are removed, but
   only when ghostldr has the game's keystone (from the save, or
   `--keystone`); without it they stay.

   When the save doesn't name its game or folder (no `param.sfo`), add them:
   `--game CUSA12345 --dir SAVEDATA00` (the folder name your own save has;
   Apollo shows it). `--keystone FILE` gives the game's keystone when the
   save has none.
4. **Close SWRR**: PS button, then on SWRR's tile Options → Close
   Application (or start another game). The PS5 writes the save as SWRR
   closes; until then nothing is kept.
5. Start the game and load the save.

To check from the computer afterwards (start SWRR's loader again first):

```bash
python3 ghostldr.py resign "Jak X (other account).zip" --check
```

To undo: run step 3 with the backup folder as the source.

### With Apollo Save Tool under ghostldr

Apollo running under ghostldr gets the same writes with or without the game's
keystone. With one (its built-in files, `/data/ghostldr/keystones/<TITLE>.keystone`,
or one ghostldr learns from a decrypted save on USB), the initial copy uses a
normal read-only fingerprint mount. Without one it uses the H-RACE. Apollo
works on that copy; when it is done with it, the change is written into the
save, and a box at the bottom of the screen says to close SWRR from the PS
button menu to finish saving (it stays until SWRR closes; Apollo's own
"success" message is not the end). That covers Apollo's **Apply cheats**,
**Import decrypted save files**, **Copy save game to HDD** (into a save that
exists) and **resign**; what Apollo writes into `sce_sys` (its resign's
account-ID change) isn't written, and isn't needed. A copy to the HDD for a
game that has **no save yet** can't be made: a save made here would carry
SWRR's keystone, which the game refuses; the box says to start the game and
save once, then copy over that save.

**Copy save game to HDD** and **Import decrypted save files** copy the files
over the save (Apollo 2.4.0 mounts the save and copies the decrypted folder,
or the one file, onto it, as it does on a jailbroken PS4): nothing is deleted
first, so a file the save has and the imported save lacks stays in the save.
Before anything is written, ghostldr compares Apollo's copy with the save as
it was (kept beside the copy when it was made) and refuses, with a box that
says why, when the write can't be done whole:

- **A file would have to be removed** (Apollo, or another tool, deleted one
  from its copy) and there is no keystone for the game: the H-RACE can't
  remove files. The box says, for example, *Can't import: CUSA12345's save
  has 1 file(s) the imported save doesn't (first: data/slot2.bin), and
  without the game's keystone ghostldr can't remove them.* With the keystone
  the file is removed.
- **The files don't fit**: a save's size is fixed (no write here can grow
  its image). The files may use what the save's files use now plus its free
  space as the save service lists it (`sceSaveDataDirNameSearch`'s free
  blocks); if the service has no numbers, the save's `SAVEDATA_BLOCKS` from
  its `param.sfo` less the file system's share (48 blocks) and `sce_sys`.
  Sizes count in 32 KiB blocks, each file at least one, each folder one. The
  box gives the numbers: *They need 992 KiB; its files have room for 576 KiB
  (a 3.0 MiB save)*.

Either way it ends with *Nothing was changed*: the save service isn't asked
for anything, and Apollo's copy goes back to the save as it is, so Apollo
shows the save unchanged the next time it opens it. Otherwise the files are
written and the box says to close SWRR, as above.

## How it works

The console's save service checks a save **after** it has decrypted it,
mounted it and made it visible to the app (as `/savedataN`). Asked to mount
another game's save for writing, it refuses (the save's keystone isn't
SWRR's), and unmounts it again without force. ghostldr opens files inside the
save in the moment between the two; while they are open, that unmount fails,
and the save stays mounted for writing. ghostldr writes through those open
files, then closes them; the save stays mounted until SWRR closes, when the
system's forced unmount writes it to the save image. Measured on a 13.60 PS5
and a 12.50 PS4 (`research/apollo` in the lab workspace).

Once the mount is refused, no path into the save works any more, and SWRR
can't open, make or remove anything relative to an open folder (`openat`,
`mkdirat` and `unlinkat` are refused on the PS5). So everything that needs a
name happens in that moment, in the racing threads: first a pin
(`sce_sys/param.sfo`, which only the mounted save has, and which keeps it
mounted), then every file and folder of the source is opened (missing ones
made), then, once all of them are held, what the source lacks is removed.

What the writer does (`ghostldr/native/ext/src/save_race.c`):

- with the game's keystone: mounts your save read-only first, lists it and
  copies it aside (sent back to the computer as the undo);
- holds every file and folder the source has before a byte changes; if one
  can't be held, nothing is written (empty files or folders it made for the
  source in that moment stay, and the result says so);
- removes what the source lacks (only with the keystone, after the copy),
  rewrites the files (any size), and reads everything back and compares it
  with the source;
- never touches `sce_sys`, and never SWRR's own saves (your Luac0re save,
  ghostldr's containers): it refuses the running title's and its host's.

## Limits

- **A console that unmounts a refused save at once** would keep nothing that
  was written; ghostldr checks for that and stops (neither the 13.60 PS5 nor
  the 12.50 PS4 measured does it).
- **The save keeps its size.** It can't grow past the free space your own
  save has; removing what the source lacks happens before the files are
  rewritten, which helps.
- **Your own save of the game must exist** (play once). A save can't be made
  this way: one SWRR creates carries SWRR's keystone, which the game refuses.
- **One write per save per SWRR session.** The save stays mounted until SWRR
  closes; close it before writing the same save again.
- **Encrypted saves of another account** (the system's own USB copies,
  `PS4/SAVEDATA/<account>/...`) can't be read on a stock console: the save
  service refuses another account's save before showing it. The owner (or
  anyone with Apollo on a jailbroken console) can export it decrypted first.
- At most 190 files and folders (the source's and your save's together), 8
  folders deep.

## For developers

- `ghostldr/host/resign.py` (the computer's side; `ghostldr.py resign` wraps
  it), `ghostldr/payloads/resign.c` (the console's: an ELF for ghostldr's ELF
  loader, `make -C ghostldr/payloads OO_PS4_TOOLCHAIN=...`), and the writer
  in `ghostldr/native/ext/src/save_race.c`, exported to payloads as
  `ghostldr_save_race_write` / `ghostldr_save_race_check`.
- Before a save tool's or FTP's copy is written, `save_import_check`
  (`save_race.c`) compares it with `<copy>.base`, the save as it was, and
  sizes both up; `savedata_foreign_space` (`hle_savedata.c`) asks the save
  service for the save's free blocks.
- Offline tests: `test_save_race.py` runs the writer and the save-tool path
  (`hle_fsvsh.c`, including Apollo's copy-over imports: written, refused for a
  removal without the keystone, refused when too big, with the save and the
  copy left as they were) against a fake console that models the PS5's save
  service;
  `test_resign.py` the computer's side against a stand-in console.
