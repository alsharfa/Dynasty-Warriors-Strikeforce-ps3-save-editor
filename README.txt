Dynasty Warriors: Strikeforce PS3 Save Editor

PORTABLE WINDOWS APPLICATION
Extract the entire Windows x64 Portable ZIP to a folder.
Double-click Dynasty Warriors Strikeforce PS3 Save Editor.exe.
No Python installation, installer, or command window is needed to run the EXE.
The weapon database is embedded in the EXE.

SUPPORTED SAVE
PS3 BLES00825 only; decrypted APP.BIN of exactly 295,012 bytes (0x48064).
Keep a separate backup of your original save. Open the decrypted save folder,
ZIP, or APP.BIN, select the slot, edit the fields you want, and export to a new
filename. Re-encrypt / re-sign using your PS3 save workflow before copying back.
This application does not decrypt or resign saves. Other regions are unverified.

SOURCE PACKAGE
Install 64-bit Python 3.12 for Windows with tkinter.
Keep VERSION, the .pyw file, and reference/00006.bin together.
Double-click Dynasty_Warriors_Strikeforce_PS3_Save_Editor.pyw to run from source.
BUILD_PORTABLE_EXE.bat builds and checks a portable EXE in dist.
The first build needs internet access to install the pinned build dependency.

PACKAGE DETAILS
BUILD_INFO.json identifies the version, source commit, and file hashes.
SHA256SUMS.txt on the release page contains SHA-256 hashes for both ZIP files.
See README.md in the source package for features and developer instructions.
FORMAT_VERIFICATION.txt records historical format evidence from v4.0.0;
release packaging tests do not replace testing edited saves in the game.
