import json
import tempfile
import unittest
from pathlib import Path

from host_config import DEFAULT_BINDINGS, load_settings, normalize_key_name, save_settings


class HostConfigTests(unittest.TestCase):
    def test_key_names_are_normalized(self):
        self.assertEqual(normalize_key_name("Key.ctrl_l"), "ctrl_l")
        self.assertEqual(normalize_key_name("Return"), "enter")

    def test_settings_round_trip_and_reserved_keys(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "settings.json"
            path.write_text(json.dumps({
                "slot": 4,
                "sensitivity": 175,
                "countdown": 5,
                "bindings": {"A": "g", "B": "f9"},
            }), encoding="utf-8")
            settings = load_settings(path)
            self.assertEqual(settings["slot"], 4)
            self.assertEqual(settings["sensitivity"], 175)
            self.assertEqual(settings["bindings"]["A"], "g")
            self.assertEqual(settings["bindings"]["B"], DEFAULT_BINDINGS["B"])
            save_settings(path, settings)
            self.assertEqual(load_settings(path)["bindings"]["A"], "g")


if __name__ == "__main__":
    unittest.main()
