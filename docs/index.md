---
title: Dynasty Warriors Strikeforce PS3 Save Editor
layout: default
---

# Dynasty Warriors: Strikeforce PS3 Save Editor

A Windows editor for decrypted **BLES00825** PlayStation 3 saves.

## Download

[Get the latest release](https://github.com/alsharfa/Dynasty-Warriors-Strikeforce-ps3-save-editor/releases/latest).

Choose the **Windows x64 Portable ZIP**, extract it, and double-click the EXE.
Python and the weapon database are bundled. A clean source ZIP and SHA-256
checksums are available on the same release page.

## Use your save

1. Keep a separate backup and decrypt your PS3 save using your usual tools.
2. Open the save folder, ZIP, or `APP.BIN` in the editor.
3. Choose the save slot, edit your selected fields, and export to a new filename.
4. Re-encrypt / re-sign as needed before copying the save back to your PS3.

The expected `APP.BIN` size is **295,012 bytes** (`0x48064`). Only BLES00825 is
verified; other regions are not assumed compatible. The editor does not decrypt
or resign saves.

Features include officers, gold, weapons, storehouse materials, city upgrades,
collections, and story/request editing.

[Source, features, and build instructions](https://github.com/alsharfa/Dynasty-Warriors-Strikeforce-ps3-save-editor#readme)
