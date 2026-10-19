"""Cross-platform prerequisites; no rendering or production cache access."""
from pathlib import Path
import tempfile
import json
import unittest

from design import FrameRenderer
from store import write_json
from settings import ROOT


class PortabilityTests(unittest.TestCase):
    def test_fonts_have_distinct_regular_and_bold_faces(self):
        regular, bold = FrameRenderer.face(24), FrameRenderer.face(24, True)
        self.assertNotEqual(regular.get_file(), bold.get_file())
        self.assertEqual(Path(regular.get_file()).parent, ROOT / "assets" / "fonts")

    def test_atomic_replacement(self):
        with tempfile.TemporaryDirectory() as directory:
            write_json(Path(directory) / "example.json", {"value": 1})
            write_json(Path(directory) / "example.json", {"value": "भारत"})
            self.assertEqual(json.loads((Path(directory) / "example.json").read_text(encoding="utf-8")),
                             {"value": "भारत"})
