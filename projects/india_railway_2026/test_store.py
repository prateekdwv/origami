"""Cache locking must exclude another process and release on context exit."""
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from store import Store


class LockTests(unittest.TestCase):
    def test_process_exclusion_and_release(self):
        with tempfile.TemporaryDirectory() as directory:
            store = Store(directory)
            command = [sys.executable, "-c",
                       "from store import Store; import sys\n"
                       "with Store(sys.argv[1]).locked(): pass", directory]
            def attempt():
                return subprocess.run(command, cwd=Path(__file__).resolve().parent,
                                      capture_output=True, text=True, timeout=30)
            with store.locked():
                blocked = attempt()
                self.assertNotEqual(blocked.returncode, 0)
                self.assertIn("holds the cache lock", blocked.stderr)
            released = attempt()
            self.assertEqual(released.returncode, 0, released.stderr)
