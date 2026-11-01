ghostldr @VERSION@
==================

ghostldr runs PS4 game dumps and OpenOrbis homebrew inside Star Wars Racer
Revenge (SWRR) on a stock PS5, through Luac0re: no jailbreak, no Python, no
program on a computer.

Supported: every PS5 firmware from 13.60, with SWRR US (CUSA03474) or EU
(CUSA03492) and Luac0re 2.4b. A PS4 runs homebrew and small titles only.
Jak X with UltraC0re is experimental.

The files
  ghostldr.lua          the bootstrap: Luac0re's loader runs it (port 9026)
  ghostldr-ext.bin      ghostldr and the game selector (port 9021)
  ghostldr-elfldr.bin   the ELF loader instead of the games (PS5)
  manager.lua           install games and back up saves, without ghostldr
  SHA256SUMS.txt        checks them: shasum -a 256 -c SHA256SUMS.txt
On the release page: the autoloader saves (ghostldr-@VERSION@-save-*.zip)
and pkgextract-cli (turns a fake-signed PS4 PKG into a game folder).

1. Your games: copy each dump's folder (the one with eboot.bin in it) to an
   exFAT USB drive, in a folder of any name, and plug the drive into the PS5.
   No drive? Install games over the network from the game selector.
2. Start SWRR, click the right half of the touchpad at PRESS START, then
   OPTIONS > HALL OF FAME.
3. Start ghostldr, one of two ways:
   a. The autoloader: import your region's save once (Apollo Save Tool on a
      jailbroken PS4, or the encrypted save resigned with Save Wizard on a
      PS5). Then HALL OF FAME opens the game selector by itself. Hold
      L1+R1 until Luac0re's loader shows to skip it.
   b. Two files, from a computer or a phone's payload-sender app, once
      Luac0re's loader listens on 9026 (CONSOLE is the PS5's IP address):
          nc CONSOLE 9026 < ghostldr.lua
          nc CONSOLE 9021 < ghostldr-ext.bin
      On Linux use nc -N for the first. Next time, send ghostldr.lua alone.
4. The game selector shows your games: Cross starts one. Square opens
   Settings: what is wrong with a game or a drive, Install over network
   (into saved data or onto a USB drive, from a browser, while that screen
   is open), the logs, Advanced, and Close ghostldr.
   L1+R1+Options+touchpad in a game brings the selector back.

Every failure is explained on the TV. Each boot's log is a file in
ghostldr/logs on the USB drive.

The guide: https://github.com/asylumexp/ghostldr/blob/@VERSION@/docs/using-the-release.md
