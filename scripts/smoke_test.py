"""Launch the actual GUI from an unrelated directory and check its resources."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--exe", type=Path)
    args = parser.parse_args()
    command = [str(args.exe.resolve())] if args.exe else [
        sys.executable, str(ROOT / "Dynasty_Warriors_Strikeforce_PS3_Save_Editor.pyw")]
    with tempfile.TemporaryDirectory(prefix="DWSF smoke test ") as folder:
        report_path = Path(folder) / "report.json"
        subprocess.run(command + ["--smoke-test", str(report_path)],
                       cwd=folder, check=True, timeout=120)
        report = json.loads(report_path.read_text(encoding="utf-8"))
    expected = hashlib.sha256((ROOT / "reference/00006.bin").read_bytes()).hexdigest()
    assert report["ok"], report
    assert report["version"] == (ROOT / "VERSION").read_text().strip(), report
    assert report["version"] in report["title"], report
    assert report["frozen"] == bool(args.exe), report
    assert report["weapon_records"] == 299, report
    assert report["weapon_database_sha256"] == expected, report
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
