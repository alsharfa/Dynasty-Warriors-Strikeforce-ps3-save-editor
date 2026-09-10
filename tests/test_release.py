"""Release regression checks using synthetic data, never personal save files."""
import hashlib
from importlib.machinery import SourceFileLoader
from importlib.util import module_from_spec, spec_from_loader
from pathlib import Path
import sys
import tempfile
import unittest
import zipfile

ROOT = Path(__file__).resolve().parents[1]
loader = SourceFileLoader("editor_under_test", str(ROOT / "Dynasty_Warriors_Strikeforce_PS3_Save_Editor.pyw"))
spec = spec_from_loader(loader.name, loader)
editor = module_from_spec(spec)
sys.modules[loader.name] = editor
loader.exec_module(editor)


class ReleaseTests(unittest.TestCase):
    def test_database_is_exact_verified_original(self):
        data = (ROOT / "reference/00006.bin").read_bytes()
        self.assertEqual(hashlib.sha256(data).hexdigest(),
                         "59b82c1afc76c905fa196a805a2a11f314764da35b6ed26c0089984ac23bf081")
        db = editor.WeaponMasterDB(data)
        self.assertEqual(len(db.record(298)), 100)
        with self.assertRaises(ValueError):
            editor.WeaponMasterDB(data[:-1])

    def test_edit_preserves_other_slots_and_unknown_bytes(self):
        original = bytes(range(256)) * (editor.APP_SIZE // 256) + bytes(range(editor.APP_SIZE % 256))
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "APP.BIN"
            path.write_bytes(original)
            doc = editor.SaveDocument()
            doc.load(path, auto_backup=False)
            for slot in range(3):
                doc.set_gold(slot, 123456)
                offset = slot * editor.SLOT_SIZE + editor.OFF_GOLD
                expected = original[:offset] + (123456).to_bytes(4, "big") + original[offset + 4:]
                self.assertEqual(bytes(doc.data), expected)
                self.assertEqual(doc.gold(slot), 123456)
                out = doc.export(Path(folder) / "edited.bin")
                self.assertEqual(out.read_bytes(), expected)
                doc.restore_original()
                self.assertEqual(bytes(doc.data), original)
                self.assertFalse(doc.dirty)

    def test_zip_export_preserves_other_members(self):
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / "source.zip"
            with zipfile.ZipFile(source, "w") as z:
                z.writestr("save/APP.BIN", bytes(editor.APP_SIZE))
                z.writestr("save/ICON0.PNG", b"untouched companion bytes")
            doc = editor.SaveDocument()
            doc.load(source, auto_backup=False)
            doc.set_gold(0, 42)
            output = doc.export(Path(folder) / "edited.zip")
            with zipfile.ZipFile(output) as z:
                self.assertIsNone(z.testzip())
                self.assertEqual(z.read("save/ICON0.PNG"), b"untouched companion bytes")
                self.assertEqual(z.read("save/APP.BIN"), bytes(doc.data))

    def test_truncated_save_is_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "APP.BIN"
            path.write_bytes(bytes(editor.APP_SIZE - 1))
            with self.assertRaisesRegex(ValueError, "Unexpected APP.BIN size"):
                editor.SaveDocument().load(path, auto_backup=False)


if __name__ == "__main__":
    unittest.main()
