# Dynasty Warriors: Strikeforce PS3 Save Editor

**Dynasty Warriors: Strikeforce PS3 Save Editor** is a Windows save-game editor for **Dynasty Warriors: Strikeforce on PlayStation 3 (PS3)**.

**Verified target:** BLES00825  
**Save payload:** decrypted `APP.BIN`  
**Expected APP.BIN size:** `0x48064` (295,012 bytes)

## Download v4.0.1

Download the **Windows x64 Portable ZIP** from [Releases](https://github.com/alsharfa/Dynasty-Warriors-Strikeforce-ps3-save-editor/releases/latest), extract it, and double-click the EXE. Python is bundled; no installer or command window is needed to run it.

The release also includes a clean **Source ZIP** and **SHA256SUMS.txt**. Each ZIP contains `BUILD_INFO.json` with the exact source commit and file hashes. The previous v4.0.0 release remains available unchanged.

On Windows, compare a ZIP hash with its entry in SHA256SUMS.txt using PowerShell:

```powershell
Get-FileHash .\Dynasty_Warriors_Strikeforce_PS3_Save_Editor_v4.0.1_Windows_x64_Portable.zip -Algorithm SHA256
```

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

1. Install 64-bit Python 3.12 for Windows with tkinter using the normal Python installer.
2. Keep `VERSION`, `Dynasty_Warriors_Strikeforce_PS3_Save_Editor.pyw`, and the `reference` folder together.
3. Double-click `Dynasty_Warriors_Strikeforce_PS3_Save_Editor.pyw`.

`RUN_EDITOR.vbs` is also included as a no-console launcher.

## Build a portable EXE

Run `BUILD_PORTABLE_EXE.bat`. It creates a local virtual environment, installs the pinned PyInstaller version, runs the regression and GUI startup checks, then builds and checks:

```text
dist\Dynasty Warriors Strikeforce PS3 Save Editor.exe
```

The EXE embeds `reference/00006.bin` and `VERSION`. The first build requires internet access. The official Windows x64 release is built and startup-tested on Windows Server 2022 using 64-bit Python 3.12.

## Save usage

1. Decrypt the PS3 save so `APP.BIN` is editable.
2. Open the save folder, save ZIP, or `APP.BIN` in the editor.
3. Choose the correct save slot.
4. Edit only what you want.
5. Export the edited save.
6. Re-encrypt / re-sign as required by your PS3 save workflow before copying it back.

## Verification

The v4.0.0 format verification notes record checks against a supplied BLES00825 executable and real 295,012-byte `APP.BIN` samples. See `FORMAT_VERIFICATION.txt` for that historical evidence. These samples are not included in the repository, and v4.0.1 does not claim a new in-game verification.

The v4.0.1 release workflow tests synthetic save round-trips, preservation of other slots/unknown bytes, rejection of truncated saves, and the exact original weapon database hash. It then starts both the source GUI and the actual packaged EXE from a separate directory, checks the version and bundled database, and checks ZIP integrity before publication. Save offsets and editing behavior are unchanged.

## Release maintenance

The repository now contains the actual source. No split archive reconstruction is required. `VERSION` supplies the window title, Windows executable metadata, and release filenames.

Pull requests build and test without publishing. A push to `main` runs the Windows checks, creates the two ZIPs and checksums, and publishes a new version from the exact tested commit. Already published versions are preserved; bump `VERSION` and update `CHANGELOG.md` for a new release. A manual workflow run builds artifacts without publishing.

Only the application, bundled reference database, documentation, build scripts, checks, and workflow are included in the source package. Personal saves, executable game files, temporary output, and obsolete archive chunks are excluded.

## Related PlayStation Save Editors

- [Knights Contract PS3 Save Editor](https://github.com/alsharfa/Knights-Contract-PS3-Save-Editor)
- [Driveclub PS4 Save Editor](https://github.com/alsharfa/Driveclub-PS4-Save-Editor-)
- [Final Fantasy XIII-2 PS3 Save Editor](https://github.com/alsharfa/Final-Fantasy-XIII-2-PS3-Save-Editor)
- [PSN Account ID Tool](https://github.com/alsharfa/PSN-Account-ID-Tool)

## Search Terms

Dynasty Warriors Strikeforce PS3 Save Editor · Dynasty Warriors Strikeforce Save Editor · Dynasty Warriors Strikeforce APP.BIN editor · PS3 save editor · PlayStation 3 save editor · BLES00825 save editor

## Important

This project intentionally targets **BLES00825**. Other regional layouts are not assumed to be identical unless separately verified.
