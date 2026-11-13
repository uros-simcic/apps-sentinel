from pathlib import Path
import tempfile
import unittest

from config import ConfigError, MAX_CONFIG_BYTES, load


class ConfigTests(unittest.TestCase):
    def test_valid_object(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.json"
            path.write_bytes(b'{"apps": [], "mode": "preview"}')
            self.assertEqual(
                load(path), {"apps": [], "mode": "preview"}
            )

    def test_invalid_configuration(self):
        cases = (
            b'{"owner": 1, "owner": 2}',
            b'{"nested": {"id": 1, "id": 2}}',
            b'{"value": NaN}',
            b'{"value": Infinity}',
            b'{"unfinished":',
            b'[]',
            b'\xff',
            b' ' * (MAX_CONFIG_BYTES + 1),
        )
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.json"
            for raw in cases:
                with self.subTest(raw_size=len(raw)):
                    path.write_bytes(raw)
                    with self.assertRaises(ConfigError):
                        load(path)

    def test_missing_file(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(ConfigError):
                load(Path(directory) / "missing.json")
