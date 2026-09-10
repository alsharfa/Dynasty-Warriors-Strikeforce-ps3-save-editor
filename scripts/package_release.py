"""Package explicit source files and a tested portable EXE; emit SHA-256 sums."""
import argparse
import hashlib
import json
from pathlib import Path
import platform
import re
import zipfile

ROOT = Path(__file__).resolve().parents[1]
FILES = [
    "Dynasty_Warriors_Strikeforce_PS3_Save_Editor.pyw", "VERSION", "README.md",
    "README.txt", "CHANGELOG.md", "FORMAT_VERIFICATION.txt", "RUN_EDITOR.vbs",
    "BUILD_PORTABLE_EXE.bat", "requirements-build.txt", ".gitignore",
    "reference/00006.bin", "scripts/build_windows.py", "scripts/smoke_test.py",
    "scripts/package_release.py", "tests/test_release.py",
    ".github/workflows/release.yml", "docs/index.md",
]


def digest(data):
    return hashlib.sha256(data).hexdigest()


def archive(path, prefix, contents):
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for name, data in sorted(contents.items()):
            info = zipfile.ZipInfo(prefix + "/" + name, (2026, 9, 10, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            z.writestr(info, data)
    with zipfile.ZipFile(path) as z:
        if z.testzip() is not None:
            raise RuntimeError(f"Corrupt archive: {path}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--exe", type=Path)
    parser.add_argument("--commit", required=True)
    parser.add_argument("--output", type=Path, default=ROOT / "release-dist")
    args = parser.parse_args()
    version = (ROOT / "VERSION").read_text().strip()
    if not re.fullmatch(r"\d+\.\d+\.\d+", version):
        raise SystemExit("Invalid VERSION")
    if not re.fullmatch(r"[0-9a-f]{40}", args.commit):
        raise SystemExit("--commit must be the full Git commit SHA")
    args.output.mkdir(parents=True, exist_ok=True)
    stem = f"Dynasty_Warriors_Strikeforce_PS3_Save_Editor_v{version}"
    source = {name: (ROOT / name).read_bytes() for name in FILES}
    info = {
        "version": version, "commit": args.commit,
        "repository": "https://github.com/alsharfa/Dynasty-Warriors-Strikeforce-ps3-save-editor",
        "python": platform.python_version(),
        "source_sha256": {name: digest(data) for name, data in sorted(source.items())},
    }
    if args.exe:
        from importlib.metadata import version as package_version
        info["pyinstaller"] = package_version("pyinstaller")
        executable = args.exe.read_bytes()
        if executable[:2] != b"MZ":
            raise SystemExit("Portable executable is not a Windows PE file")
        info["executable_sha256"] = digest(executable)
    manifest = json.dumps(info, indent=2, sort_keys=True).encode("utf-8") + b"\n"
    source["BUILD_INFO.json"] = manifest
    output = args.output / (stem + "_Source.zip")
    archive(output, stem + "_Source", source)
    assets = [output]
    if args.exe:
        portable = {
            args.exe.name: executable, "README.txt": source["README.txt"],
            "FORMAT_VERIFICATION.txt": source["FORMAT_VERIFICATION.txt"],
            "BUILD_INFO.json": manifest,
        }
        output = args.output / (stem + "_Windows_x64_Portable.zip")
        archive(output, stem + "_Windows_x64_Portable", portable)
        assets.append(output)
    sums = "".join(f"{digest(path.read_bytes())}  {path.name}\n" for path in sorted(assets))
    (args.output / "SHA256SUMS.txt").write_text(sums, encoding="utf-8", newline="\n")
    print(sums, end="")


if __name__ == "__main__":
    main()
