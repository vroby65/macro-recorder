import unittest

from evdev import ecodes

from macro_recorder.core import CapturedEvent, build_macro


class BuildMacroTests(unittest.TestCase):
    def test_orders_events_from_multiple_input_threads(self):
        events = [
            CapturedEvent(10.20, ecodes.EV_ABS, ecodes.ABS_X, 800),
            CapturedEvent(10.10, ecodes.EV_KEY, ecodes.KEY_A, 1),
            CapturedEvent(10.20, ecodes.EV_ABS, ecodes.ABS_Y, 450),
        ]

        macro = build_macro(events, started_at=10.0)

        self.assertEqual(
            [event.code for event in macro[:3]],
            [ecodes.KEY_A, ecodes.ABS_X, ecodes.ABS_Y],
        )
        self.assertAlmostEqual(macro[0].delay, 0.10)
        self.assertAlmostEqual(macro[1].delay, 0.10)
        self.assertAlmostEqual(macro[2].delay, 0.0)

    def test_preserves_delays_from_recording_start(self):
        events = [
            CapturedEvent(10.25, ecodes.EV_KEY, ecodes.KEY_A, 1),
            CapturedEvent(10.40, ecodes.EV_KEY, ecodes.KEY_A, 0),
        ]

        macro = build_macro(events, started_at=10.0)

        self.assertAlmostEqual(macro[0].delay, 0.25)
        self.assertAlmostEqual(macro[1].delay, 0.15)

    def test_discards_events_generated_while_clicking_stop(self):
        events = [
            CapturedEvent(20.10, ecodes.EV_KEY, ecodes.KEY_A, 1),
            CapturedEvent(20.20, ecodes.EV_KEY, ecodes.KEY_A, 0),
            CapturedEvent(21.00, ecodes.EV_REL, ecodes.REL_X, -5),
            CapturedEvent(21.10, ecodes.EV_KEY, ecodes.BTN_LEFT, 1),
        ]

        macro = build_macro(events, started_at=20.0, discard_since=20.90)

        self.assertEqual([event.code for event in macro], [ecodes.KEY_A, ecodes.KEY_A])

    def test_releases_keys_still_held_when_recording_stops(self):
        events = [CapturedEvent(30.10, ecodes.EV_KEY, ecodes.KEY_LEFTSHIFT, 1)]

        macro = build_macro(events, started_at=30.0)

        self.assertEqual(macro[-2].event_type, ecodes.EV_KEY)
        self.assertEqual(macro[-2].code, ecodes.KEY_LEFTSHIFT)
        self.assertEqual(macro[-2].value, 0)
        self.assertEqual(macro[-1].event_type, ecodes.EV_SYN)
        self.assertEqual(macro[-1].code, ecodes.SYN_REPORT)


if __name__ == "__main__":
    unittest.main()
