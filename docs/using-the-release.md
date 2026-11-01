# Using the release

This page takes a ghostldr release from download to gameplay on a stock PS5. You need no jailbreak, no Python and no program left running on a computer. Every game and homebrew goes the same way; [compatibility.md](compatibility.md) says what is known to work.

## What you need

- **A PS5 on firmware 13.60 or later** with *Star Wars Racer Revenge* (SWRR), US (CUSA03474) or EU (CUSA03492), where Luac0re 2.4b already works: its loader starts when you open HALL OF FAME. The SWRR disc must be in the PS5.
- **Your own dump of the game:** the folder with `eboot.bin` in it, with `sce_module/`, `sce_sys/` and the game's data, decrypted, with its update merged in. A fake-signed PS4 PKG works too: the release's PKG tool turns it into that folder.
- **An exFAT USB drive** with room for the games (recommended). Without one, games go into SWRR's saved data over the network.
- **A way to start ghostldr**, one of:
  - the autoloader save: Save Wizard, or a jailbroken PS4 with Apollo Save Tool, to get it onto the console once;
  - something that sends a file over the network: `nc` on macOS or Linux, or a payload-sender app on a phone or on Windows.

Both regions of SWRR work the same way, but each keeps its own saved data. Play a game from the same region every time.

## The release's files

Download them from the [release page](https://github.com/asylumexp/ghostldr/releases/latest).

| File | What it is |
|---|---|
| `ghostldr.lua` | The bootstrap. Luac0re's loader runs it. |
| `ghostldr-ext.bin` | ghostldr itself, with the game selector. `ghostldr.lua` keeps it on the PS5 after the first time. |
| `ghostldr-elfldr.bin` | The [ELF loader](developers.md#the-elf-loader) on its own, for payloads without games (PS5). |
| `manager.lua` | A web page for installing games and backing up saves, without booting ghostldr ([below](#without-the-selector-managerlua)). |
| `README.txt` | The short version of this page. |
| `SHA256SUMS.txt` | The files' checksums. |
| `ghostldr-<version>.zip` | The six files above in one zip. |
| `ghostldr-<version>-save-US-CUSA03474.zip`, `ghostldr-<version>-save-EU-CUSA03492.zip` | The [autoloader save](#a-the-autoloader-save), one per SWRR region. Each holds it twice: decrypted, for Apollo Save Tool, and encrypted, for Save Wizard. |
| `pkgextract-cli-windows-x64.exe`, `pkgextract-cli-macos`, `pkgextract-cli-linux-x64`, `pkgextract-cli-linux-arm64` | A tool for your computer that extracts a fake-signed PS4 PKG into a game folder for the USB drive. One file, nothing to install. The macOS one runs on Intel and Apple silicon alike. |

Use one release's files together: `ghostldr.lua` takes only its own release's `ghostldr-ext.bin`. To check the downloads, run `shasum -a 256 --ignore-missing -c SHA256SUMS.txt` in their folder.

## 1. Put your games on a USB drive

Plug the drive into a computer and copy the game's folder onto it as it is: the folder with `eboot.bin` in it, with everything in it. Any folder name works, up to four folders down, and games sit side by side:

```
<drive>/
    Ghost of Tsushima (CUSA11456)/      eboot.bin, sce_module/, sce_sys/, ...
    Games/
        bloodborne/
            app0/                       eboot.bin, ...
```

- **A PKG:** run the PKG tool for your computer from a terminal with the `.pkg` and a new folder, for example `pkgextract-cli-windows-x64.exe MyGame.pkg MyGame` on Windows, then copy the folder it writes onto the drive. On macOS and Linux, make it runnable first (`chmod +x pkgextract-cli-macos`, then `./pkgextract-cli-macos MyGame.pkg MyGame`); macOS may also need `xattr -d com.apple.quarantine pkgextract-cli-macos` once, and Linux needs OpenSSL (`libssl`). Only fake-signed PKGs open; a retail PKG needs a console's keys.
- **The title ID** comes from the game's `sce_sys/param.sfo`. A dump without one (Ghost's often hasn't) needs the ID in its folder's name, like `Ghost of Tsushima (CUSA11456)`.
- **exFAT or FAT32.** FAT32 holds no file of 4 GiB or more, and many games have one.
- **USB storage, not extended storage.** The PS5 must list the drive as USB storage. Up to four drives are read at once.
- **Updates** must be merged into the dump. DLC isn't loaded.
- **Names and pictures** in the selector come from the game's `sce_sys` (`param.sfo`, `icon0.png`, `pic1.png`).
- Your other files on the drive are left alone.

Then plug the drive into the PS5. No drive? Go on: the game selector can [install a game over the network](#install-over-the-network).

## 2. Start ghostldr

Start SWRR, click the right half of the touchpad at PRESS START, then go to **OPTIONS → HALL OF FAME**. That runs Luac0re. What happens next depends on how ghostldr is started.

Never save from SWRR's own menus, and never confirm a "corrupted, will be deleted" prompt.

### A. The autoloader save

The autoloader is Luac0re's save with ghostldr in it. With it, HALL OF FAME opens the game selector by itself. It replaces SWRR's save (Luac0re's) on that account: copy yours off first if you want to keep it.

Unzip your region's `ghostldr-<version>-save-...zip` onto the root of a USB drive, so that its `PS4` folder is at the top, and plug the drive into the console. The save belongs to no account, so it is resigned to yours on the way in.

- **A jailbroken PS4, with Apollo Save Tool:**
  1. In Apollo, delete SWRR's save: **HDD Saves**, the SWRR save (`SLUS-20268` or `SLES-50366`), **Delete**. Use Apollo, not the PS4's Settings: there all of SWRR's saved data is one item, installed games included.
  2. **USB Saves**, the ghostldr save, **Copy save game to HDD**. Apollo writes your account into it as it copies.
- **A PS5, with Save Wizard:**
  1. Resign the encrypted save in `PS4/SAVEDATA/0000000000000000/<title ID>/` to your PSN profile.
  2. Put it on the drive as `PS4/SAVEDATA/<your account ID, 16 hex digits>/<title ID>/`.
  3. Import it: **Settings → Saved Data and Game/App Settings → Saved Data (PS4) → Copy or Delete from USB Drive**.
- **A PS5, through a jailbroken PS4:** fake-activate a PS4 user with your PS5 account's ID (Apollo → User Tools → Activate PS4 Accounts), copy the save to that user with Apollo as above, copy it to USB with the PS4's own **Copy to USB Storage Device**, then import it on the PS5.

Then, each time:

- **OPTIONS → HALL OF FAME opens the game selector** after Luac0re's exploit. Nothing is sent.
- **To skip it**, hold **L1 + R1** from choosing HALL OF FAME until Luac0re's loader shows. You get Luac0re's own loader on port 9026, which takes any script, `ghostldr.lua` included.
- **However ghostldr ends** (Close ghostldr, a failure shown on the TV), Luac0re's loader listens on 9026 after it.
- **A new release:** import its save. To try a release without a new save, hold L1 + R1 and send its two files ([B](#b-send-two-files)).
- **To remove it,** import Luac0re's own save again.

### B. Send two files

HALL OF FAME starts Luac0re's loader. Wait until it says it is listening on port 9026; if the exploit failed, close SWRR and try again. Find the PS5's address in **Settings → Network → Connection Status → View Connection Status → IPv4 Address**. It is `CONSOLE` below.

Send the bootstrap to Luac0re's loader:

```bash
nc CONSOLE 9026 < ghostldr.lua
```

The TV shows ghostldr's prompt, with the port to send to:

```
Send ghostldr-ext.bin (games)
or ghostldr-elfldr.bin (ELF loader)
to 192.168.1.123:9021
```

Within five minutes, send ghostldr:

```bash
nc CONSOLE 9021 < ghostldr-ext.bin
```

The game selector opens on the TV. `nc` shows ghostldr's log until you press Ctrl+C (that stops the log, not the game).

- **On Linux**, add `-N` to the first command (`nc -N CONSOLE 9026 < ghostldr.lua`), or `-q 0` with the traditional netcat. Luac0re runs a script only when its connection ends.
- **A payload-sender app** works for both files. It may close the connection right away; only the log is lost.
- **On a jailbroken PS5**, whose own ELF loader has 9021, the prompt says `9022`: send it there.
- **Something else sent** (another release's file, one cut short) is refused with the reason, and the prompt keeps waiting.

**Every later session, send `ghostldr.lua` alone.** The first `ghostldr-ext.bin` is kept in SWRR's saved data (`GLDRCACHE`, 16 MiB), so the game selector opens at once.

- **A new release:** its `ghostldr.lua` says `Version mismatch` and asks for its own `ghostldr-ext.bin`, which replaces the old one.
- **The log:** while the selector shows on a PS5, `printf 'log\n' | nc CONSOLE 9021` makes that connection the log, the game's included. Each boot's log is also on the USB drive ([below](#logs)).
- **Clearing the cache:** delete `GLDRCACHE` ([Removing it](#removing-it)). The next `ghostldr.lua` asks for `ghostldr-ext.bin` again.

## 3. The game selector

The selector shows every game it found, on the USB drives and installed in SWRR's saved data.

| Button | What it does |
|---|---|
| Left / Right, L1 / R1 | Move along the row (L1 and R1 jump five). |
| Cross | Start the game. |
| Options | The game's details: title ID, version, where it is, and what's wrong with it. |
| Triangle | Look for games again: a game copied onto the drive shows, one taken off goes. |
| Square | Settings (so does the gear at the end of the row). |

The first boot of a game takes a minute or two. A game's progress goes into SWRR's saved data (`GHOSTSAVE` for Ghost), never onto the drive. The same game on a drive and installed shares its progress.

On a PS5, the [ELF loader](developers.md#the-elf-loader) also listens beside the selector until you pick a game.

### Settings

Up and Down choose a section, Right or Cross goes in, Left or Circle comes back out.

- **Games:** each game with `Ready`, or what is wrong and what to do. PS5 games found on a drive aren't listed (SWRR runs PS4 games); a line counts them. **Cross on an installed game deletes it**, after a Yes. Its saves stay.
- **USB drives:** each drive, its file system, size and free space, the games on it and the folders that can't start. **Look again** reads the drives again after you plug one in.
- **Network:** the PS5's address, the ports ghostldr uses, and [Install over network](#install-over-the-network).
- **Logs:** **Write logs to the USB drive** (on by default).
- **Advanced:** **Show the system's dialogs**, **Plan memory automatically**, **Keep Remote Play on**, **Share learned memory plans** (off: sends the memory plans this console learns to ghostldr's collection), **Use community memory plans** (on: a game starts from the plan other consoles shared), **Saves in FTP** (off: [below](#saves-over-ftp)), and **Reset to defaults**. A game's Options panel can turn its community plan off for that game alone.
- **Game art:** **Fetch missing art** (off) gives a game without pictures some from SteamGridDB or IGDB, found by its name. It needs your own key: a SteamGridDB API key, or an IGDB Client ID and Client Secret. Type them on the on-screen keyboard there.
- **About:** the version, the console and SWRR's region, and **Close ghostldr**, which goes back to Luac0re's loader.

Settings are kept in SWRR's saved data (`GLDRCONF`). If a boot with changed switches stops before the selector shows, the next boot leaves them out once and says "Settings > Advanced is left out of this boot", so a switch can't lock you out.

## Install over the network

The selector can install a game from a browser on a computer or phone on the same network. Nothing else is needed on that device.

1. **In the selector:** Settings → Network → **Install over network**. The TV shows an address to open and a QR code of it. Installs are taken **only while this screen is open**: there is no password. Circle closes it.
2. **Open the address** in the browser and choose the game: **Choose folder…** (the folder with `eboot.bin`) on a computer, or **Choose .zip…** (a `.zip` of that folder) on a phone or computer.
3. **Check** the name, title ID, version and size the page read.
4. **Install to:** **Saved data** (the default), or a USB drive in the PS5, shown with its free space (`USB drive 1 — 412.3 GB free`). Then **Install**.

The page shows the progress, the speed and the time left. Keep the page open, the device awake and the PS5 out of rest mode until it says the game is installed.

- **Saved data** takes about 35 minutes for a 50 GB game (the PS5 writes saved data at 22–25 MB/s). The game joins the row when it's done.
- **A USB drive** gets the game's files as they are, in `ghostldr/<title ID>/app0`. On a boot from the drive's games it joins the row; otherwise it shows the next time ghostldr starts.
- **Not enough space,** or a file of 4 GiB or more for a FAT32 drive: the page says so before anything is written.
- **Interrupted:** the page carries on by itself. Closed it? Choose the same game again and Install: what's on the PS5 already is kept.
- **Removing:** the page's list of installed games has a **Remove** button, or use Settings → Games. A game's progress stays.

### Without the selector: manager.lua

`manager.lua` serves the same install page without booting ghostldr, into saved data only. It also downloads and restores saves.

1. With Luac0re's loader listening, send it: `nc CONSOLE 9026 < manager.lua`.
2. Open `http://CONSOLE:8090/` in a browser. Type the token the TV shows into the page: it is needed to install, restore or delete anything. **Install a game** opens the install page.
3. **Exit** on the page gives Luac0re's loader back.

## Back to the game selector

On a PS5, the selector comes back when a game ends, without restarting SWRR:

- **L1 + R1 + Options + touchpad**, held together for a moment, stops the game. Nothing is saved that the game didn't save itself.
- **A game that quits or crashes** shows ghostldr's page for a few seconds (Cross skips it), then the selector.

On a PS4 or in Jak X the game ends as before: SWRR closes after a quit, and a crash's page stays. Then close SWRR from the PS button menu and start it again before the next boot. Do the same if the next game says "There's no room for the game's code."

## The FTP server

While the selector or a game runs, the PS5 serves FTP on port **1212**. Any FTP client works (FileZilla, WinSCP, Cyberduck): passive mode, any user name and password, no encryption.

| Path | What it is |
|---|---|
| `/ghostldr_usb` | The first USB drive (`/ghostldr_usb2`, `3`, `4` for the others), read and write. |
| `/saves` | Every signed-in user's saves, with **Saves in FTP** on. |
| `/temp0/ghostldr.log` | The log. |

Leave SWRR's own folders (`/app0`, `/savedata0`) alone. Anyone on your network can reach the server while it runs, so use it on a network you trust. Copying games with the drive plugged into a computer is quicker.

### Saves over FTP

With Settings → Advanced → **Saves in FTP** on, `/saves/<user>/<title ID>/` holds each signed-in user's saves: SWRR's, the games' you play under ghostldr (read only), and other games' that something names (a save folder on the USB drive, a save tool's list).

- **Changing another game's save** writes it a few seconds after the last change. **Close SWRR afterwards**: the system commits the save when SWRR closes.
- Without the game's keystone, files can't be removed from its save, and no save can grow past its size. Such a change is refused and the save stays as it was.
- SWRR's own saves are never written.

## When something goes wrong

ghostldr says every failure on the TV: what went wrong, what to do, and where the log is.

- **A boot that stops** shows its message in the system's dialog. Press OK: Luac0re's loader says "The boot stopped" and takes `ghostldr.lua` again. If you press OK on that second dialog too and the TV goes black, close SWRR from the PS button menu, start it again and open HALL OF FAME.
- **A game that crashes or quits** shows ghostldr's page ([Back to the game selector](#back-to-the-game-selector)).
- **A game that stops drawing** gets a notification; it may come back by itself.
- **The system's own error** ("Something went wrong with this game or app", CE-108255-1) is a crash ghostldr couldn't catch. Press OK and start SWRR again. If it happens at the same place again, this game may not work with ghostldr yet.

### Common problems

- **"No games found." or "No games on the USB drive."** Check Settings → USB drives (try **Look again**) and Settings → Games, which says what is wrong with each folder. Folders deeper than four levels aren't searched.
- **"The game's folder doesn't say which game it is."** Name the folder after the title ID, like `My Game (CUSA12345)`, or copy the dump's `sce_sys/param.sfo` with it.
- **"The game's files are encrypted."** Dump the game again with a dumper that decrypts `eboot.bin` and `sce_module`.
- **"The game needs more memory than SWRR has."** This game can't run with ghostldr yet (on a PS4, most games can't).
- **"There's no room for the game's code."** Close SWRR, start it again and boot again. If it keeps happening, the game is too big for now.
- **Reads from the drive time out** (each read fails after about 25 seconds): unplug the drive and plug it in again, preferably in a rear port. A bus-powered drive beside another one may need a port of its own or a powered hub. If it still fails, restart the PS5.
- **The drive was pulled out** while a game runs: the game waits and the TV says so. Plug the same drive back in, in any port, and the game carries on. **Rest mode** with a game running is fine too.
- **`Version mismatch`, or a file refused as damaged:** the files are from different releases. Use one release's files together.
- **The PS5 asks for the disc:** the SWRR disc must be in the console.

### Logs

With a USB drive in the PS5, each boot's log is a file on it, `ghostldr/logs/NNNN_YYYY-MM-DD_HHMM.log`, and the 30 newest are kept. Read it on a computer, or attach it to a [bug report](https://github.com/asylumexp/ghostldr/issues/new/choose). Without a drive, the log is `/temp0/ghostldr.log` inside SWRR, which the FTP server shows. It is gone when SWRR closes.

## Removing it

- **A game on the USB drive:** delete its folder on a computer.
- **An installed game:** Settings → Games, Cross on it, Yes. Or **Remove** on the install page.
- **By hand:** **Settings → Saved Data and Game/App Settings → Saved Data (PS4) → Console Storage → Star Wars Racer Revenge** lists everything ghostldr keeps. A game's install is `<prefix>000`, `<prefix>001`, …, `<prefix>INDEX` and `<prefix>META` (`GHOST…` for Ghost). ghostldr's cache is `GLDRCACHE` and its settings are `GLDRCONF`.
- **Keep** the games' progress (`<prefix>SAVE`, such as `GHOSTSAVE`) and SWRR's own save (`SLUS-20268` on US SWRR, `SLES-50366` on EU) unless you mean to remove them too.

## For developers

Building from source, the tools on a computer and making a release are in [developers.md](developers.md).
