"""Build the portable Windows application with its required resources."""
from pathlib import Path
import platform
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
EXE_NAME = "Dynasty Warriors Strikeforce PS3 Save Editor"


def main():
    if sys.platform != "win32" or platform.architecture()[0] != "64bit":
        raise SystemExit("Build with 64-bit Python on Windows.")
    version = (ROOT / "VERSION").read_text().strip()
    if not re.fullmatch(r"\d+\.\d+\.\d+", version):
        raise SystemExit("VERSION must contain a numeric major.minor.patch version.")
    numbers = tuple(map(int, version.split("."))) + (0,)
    metadata = ROOT / "build" / "windows_version.txt"
    metadata.parent.mkdir(exist_ok=True)
    metadata.write_text(f'''VSVersionInfo(
  ffi=FixedFileInfo(filevers={numbers!r}, prodvers={numbers!r}, mask=0x3f,
    flags=0x0, OS=0x40004, fileType=0x1, subtype=0x0, date=(0, 0)),
  kids=[StringFileInfo([StringTable('040904B0', [
    StringStruct('FileDescription', '{EXE_NAME}'),
    StringStruct('FileVersion', '{version}'),
    StringStruct('ProductName', '{EXE_NAME}'),
    StringStruct('ProductVersion', '{version}'),
    StringStruct('OriginalFilename', '{EXE_NAME}.exe')])]),
    VarFileInfo([VarStruct('Translation', [1033, 1200])])])
''', encoding="utf-8")
    subprocess.run([
        sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean",
        "--onefile", "--windowed", "--noupx", "--name", EXE_NAME,
        "--version-file", str(metadata),
        "--add-data", "reference/00006.bin;reference",
        "--add-data", "VERSION;.",
        "Dynasty_Warriors_Strikeforce_PS3_Save_Editor.pyw",
    ], cwd=ROOT, check=True)


if __name__ == "__main__":
    main()
