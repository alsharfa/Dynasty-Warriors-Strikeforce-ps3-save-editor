# Dynasty Warriors: Strikeforce PS3 Save Editor

A save editor for **Dynasty Warriors: Strikeforce** on PlayStation 3.

**Verified target:** BLES00825  
**Save payload:** decrypted `APP.BIN`  
**Expected APP.BIN size:** `0x48064` (295,012 bytes)

## Features

- Gold editing
- Named 42-officer editor
  - Level and EXP
  - Six weapon proficiencies
  - Six ability stats
  - Main / Sub weapon selection
  - Active-officer runtime synchronization
- Equipped weapon editor using the bundled `reference/00006.bin` weapon database
- Storehouse Items / Materials
  - Material names
  - Ownership
  - Editable quantities
  - Replace one / replace all matching material
  - All-material preset
- City Upgrade
  - Six facility levels
  - Six facility EXP values
- Collections / Unlocks
  - Weapons
  - Orbs
  - Chi Skills
  - Officer Cards
  - Treasures
  - Collector trophy preparation
- Story / Requests
  - StorySet records
  - Quest, chapter and request unlock support
- Restore Original and changed-byte tracking
- Validation before export
- Automatic backup when possible
- Folder, ZIP and raw `APP.BIN` workflows

## Verified save layout

```text
APP.BIN total : 0x48064 = 295,012 bytes
Slot 1        : 0x00000 .. 0x17FFF
Slot 2        : 0x18000 .. 0x2FFFF
Slot 3        : 0x30000 .. 0x47FFF
Global tail   : 0x48000 .. 0x48063
```

The editor preserves unknown bytes and patches only selected fields. When `PARAM.SFO` is available it verifies `TITLE_ID` and rejects saves that are not BLES00825 rather than assuming another region uses the same layout.

## Run without a command window

1. Install Python 3 for Windows with tkinter using the normal Python installer.
2. Keep `Dynasty_Warriors_Strikeforce_PS3_Save_Editor.pyw` and the `reference` folder together.
3. Double-click `Dynasty_Warriors_Strikeforce_PS3_Save_Editor.pyw`.

`RUN_EDITOR.vbs` is also included as a no-console launcher.

## Build a portable EXE

Run `BUILD_PORTABLE_EXE.bat`. It installs PyInstaller and builds:

```text
dist\Dynasty Warriors Strikeforce PS3 Save Editor.exe
```

The EXE embeds `reference/00006.bin`.

## Save usage

1. Decrypt the PS3 save so `APP.BIN` is editable.
2. Open the save folder, save ZIP, or `APP.BIN` in the editor.
3. Choose the correct save slot.
4. Edit only what you want.
5. Export the edited save.
6. Re-encrypt / re-sign as required by your PS3 save workflow before copying it back.

## Verification

The current build was verified against the supplied BLES00825 executable and multiple real 295,012-byte `APP.BIN` samples. See `FORMAT_VERIFICATION.txt` for technical notes.

## Important

This project intentionally targets **BLES00825**. Other regional layouts are not assumed to be identical unless separately verified.
