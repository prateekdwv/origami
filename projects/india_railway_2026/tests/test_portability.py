"""Cross-platform prerequisites; no rendering or production cache access."""
from pathlib import Path
import subprocess
import sys
import tempfile
import json
import unittest
from zoneinfo import ZoneInfo

from design import font
from store import Store, write_json
from settings import ROOT


class PortabilityTests(unittest.TestCase):
    def test_fonts_have_distinct_regular_and_bold_faces(self):
        regular, bold = font(24), font(24, True)
        self.assertGreater(regular.getlength("India Railway"), 0)
        self.assertNotEqual(regular.path, bold.path)
        self.assertEqual(Path(regular.path).parent, ROOT / "assets" / "fonts")

    def test_india_timezone(self):
        from datetime import datetime, timedelta
        self.assertEqual(datetime(2026, 10, 10, tzinfo=ZoneInfo("Asia/Kolkata")).utcoffset(),
                         timedelta(hours=5, minutes=30))

    def test_atomic_replacement_and_process_lock(self):
        with tempfile.TemporaryDirectory() as directory:
            store = Store(directory)
            store.save()
            write_json(Path(directory) / "example.json", {"value": 1})
            write_json(Path(directory) / "example.json", {"value": "भारत"})
            self.assertEqual(json.loads((Path(directory) / "example.json").read_text(encoding="utf-8")),
                             {"value": "भारत"})
            script = (
                "from store import Store\n"
                "import sys\n"
                "try:\n"
                "    with Store(sys.argv[1]).locked(): pass\n"
                "except RuntimeError:\n"
                "    sys.exit(23)\n"
            )
            def attempt():
                return subprocess.run([sys.executable, "-B", "-c", script, directory],
                                      cwd=ROOT, capture_output=True, text=True)
            with store.locked():
                result = attempt()
                self.assertEqual(result.returncode, 23, result.stderr)
            result = attempt()
            self.assertEqual(result.returncode, 0, result.stderr)
            with self.assertRaisesRegex(ValueError, "release test"):
                with store.locked():
                    raise ValueError("release test")
            result = attempt()
            self.assertEqual(result.returncode, 0, result.stderr)
