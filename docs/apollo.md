# Apollo Save Tool in ghostldr

[Apollo Save Tool](https://github.com/bucanero/apollo-ps4) for PS4 runs under ghostldr like a game: put it on the USB drive or install it, and start it from the selector. It works on a stock PS5, without a jailbreak, so it can't do everything it does on a jailbroken console. This page lists what it can and can't do there.

## What works

- **The saves of the console's signed-in users.** The selector asks which user's saves to open, then looks for them. The first time can take two minutes; hold Circle to cancel.
- **Apply cheats** to a save.
- **Export** a save's decrypted files to the USB drive.
- **Import decrypted save files** into a save the game already has. An import copies its files over the save and deletes nothing.
- **Copy save game to HDD** and resign, into a save the game already has.

## Close SWRR afterwards

The system commits a changed save only when SWRR closes. A box at the bottom of the screen says so. Apollo's own "success" message isn't the end: close SWRR from the PS button menu before you start the game whose save you changed.

## What's refused

Apollo shows a message that says why, and "Nothing was changed", when:

- **the files don't fit:** a save's size is fixed when the game creates it;
- **a file would have to be removed** and there is no keystone for the game.

## What can't work on a stock console

- **A new save** for a game that has none. Start the game, save once, then copy over that save.
- **Another account's saves.**
- **Users who aren't signed in.** Each user has to be signed in on the PS5 for their saves to be reached.
- **PS5 game saves.** Only PS4 saves can be reached.
- **Encrypted saves on USB.** Use decrypted saves.
- **Trophies**, and **activating accounts**.

Something not listed here doesn't work? Report it with the [bug report form](https://github.com/asylumexp/ghostldr/issues/new/choose).
