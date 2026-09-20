import unittest
from controller import PadState, clamp


class ControllerTests(unittest.TestCase):
    def test_clamp_and_invalid_values(self):
        self.assertEqual(clamp(2, -1, 1), 1)
        self.assertEqual(clamp("bad", -1, 1), 0)

    def test_state_is_sanitized(self):
        state = PadState.from_message({
            "lx": 2,
            "ly": -2,
            "lt": 4,
            "buttons": ["A", "DPAD_UP", "INVALID"],
        })
        self.assertEqual(state.lx, 1)
        self.assertEqual(state.ly, -1)
        self.assertEqual(state.lt, 1)
        self.assertEqual(state.buttons, {"A", "DPAD_UP"})



if __name__ == "__main__":
    unittest.main()
