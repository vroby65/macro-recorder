import unittest

from evdev import ecodes

from macro_recorder.core import MacroEvent
from macro_recorder.linux_input import (
    is_keyboard_device,
    is_pointer_activity,
    is_pointer_device,
    needs_uinput,
)


class DeviceSelectionTests(unittest.TestCase):
    def test_accepts_normal_keyboard(self):
        capabilities = {
            ecodes.EV_KEY: [ecodes.KEY_A, ecodes.KEY_ENTER, ecodes.KEY_SPACE]
        }

        self.assertTrue(is_keyboard_device(capabilities))

    def test_accepts_relative_mouse(self):
        capabilities = {
            ecodes.EV_KEY: [ecodes.BTN_LEFT],
            ecodes.EV_REL: [ecodes.REL_X, ecodes.REL_Y],
        }

        self.assertTrue(is_pointer_device(capabilities))

    def test_rejects_power_button(self):
        capabilities = {ecodes.EV_KEY: [ecodes.KEY_POWER]}

        self.assertFalse(is_keyboard_device(capabilities))
        self.assertFalse(is_pointer_device(capabilities))

    def test_recognises_touchpad_for_playback_stop(self):
        capabilities = {
            ecodes.EV_KEY: [ecodes.BTN_TOUCH, ecodes.BTN_TOOL_FINGER],
            ecodes.EV_ABS: [
                ecodes.ABS_X,
                ecodes.ABS_Y,
                ecodes.ABS_MT_POSITION_X,
                ecodes.ABS_MT_POSITION_Y,
            ],
        }

        self.assertTrue(is_pointer_device(capabilities))

    def test_detects_physical_pointer_activity(self):
        self.assertTrue(is_pointer_activity(ecodes.EV_REL, ecodes.REL_X, 2))
        self.assertTrue(is_pointer_activity(ecodes.EV_KEY, ecodes.BTN_LEFT, 1))
        self.assertTrue(
            is_pointer_activity(ecodes.EV_ABS, ecodes.ABS_MT_POSITION_X, 400)
        )
        self.assertFalse(is_pointer_activity(ecodes.EV_REL, ecodes.REL_X, 0))
        self.assertFalse(is_pointer_activity(ecodes.EV_KEY, ecodes.BTN_LEFT, 0))

    def test_mouse_buttons_share_the_absolute_pointer_backend(self):
        mouse_button = MacroEvent(0.0, ecodes.EV_KEY, ecodes.BTN_LEFT, 1)
        keyboard_key = MacroEvent(0.0, ecodes.EV_KEY, ecodes.KEY_A, 1)

        self.assertFalse(needs_uinput(mouse_button))
        self.assertTrue(needs_uinput(keyboard_key))


if __name__ == "__main__":
    unittest.main()
