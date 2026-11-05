import unittest

from korvex.core import DOWN, REPEAT, UP, DebounceFilter

A, B, SPACE, SHIFT = 30, 48, 57, 42


class DebounceFilterTest(unittest.TestCase):
    def setUp(self):
        self.f = DebounceFilter(modifier_codes={SHIFT}, space_code=SPACE)

    def press(self, code, t_down, t_up):
        return self.f.process(code, DOWN, t_down), self.f.process(code, UP, t_up)

    def test_normal_typing_passes(self):
        self.assertEqual(self.press(A, 0.00, 0.08), ((True, False), (True, False)))
        self.assertEqual(self.press(A, 0.20, 0.28), ((True, False), (True, False)))

    def test_bounce_is_blocked_with_its_release(self):
        self.press(A, 0.00, 0.08)
        self.assertEqual(self.f.process(A, DOWN, 0.09), (False, True))
        self.assertEqual(self.f.process(A, UP, 0.095), (False, False))

    def test_autorepeat_follows_original_press(self):
        self.press(A, 0.00, 0.08)
        self.f.process(A, DOWN, 0.09)                         # rebote bloqueado
        self.assertEqual(self.f.process(A, REPEAT, 0.5), (False, False))
        self.assertEqual(self.f.process(A, DOWN, 0.6), (False, False))   # repetición estilo Windows
        self.f.process(A, UP, 0.7)
        self.assertEqual(self.f.process(A, DOWN, 1.0), (True, False))
        self.assertEqual(self.f.process(A, REPEAT, 1.5), (True, False))

    def test_space_uses_its_own_threshold(self):
        self.press(SPACE, 0.0, 0.05)
        self.assertEqual(self.f.process(SPACE, DOWN, 0.15), (False, True))   # 100 ms < 120 ms
        self.f.process(SPACE, UP, 0.16)
        self.press(A, 1.0, 1.05)
        self.assertEqual(self.f.process(A, DOWN, 1.15), (True, False))       # 100 ms > 50 ms

    def test_threshold_change(self):
        self.f.set_threshold_ms(20)
        self.press(A, 0.0, 0.05)
        self.assertEqual(self.f.process(A, DOWN, 0.08), (True, False))

    def test_modifiers_not_filtered_in_all_mode(self):
        self.press(SHIFT, 0.0, 0.01)
        self.assertEqual(self.f.process(SHIFT, DOWN, 0.02), (True, False))

    def test_selected_only_mode(self):
        self.f.set_selection(False, [A, SHIFT])
        self.press(B, 0.0, 0.01)
        self.assertEqual(self.f.process(B, DOWN, 0.02), (True, False))
        self.press(A, 0.0, 0.01)
        self.assertEqual(self.f.process(A, DOWN, 0.02), (False, True))
        self.press(SHIFT, 0.0, 0.01)                         # seleccionado explícitamente
        self.assertEqual(self.f.process(SHIFT, DOWN, 0.02), (False, True))

    def test_release_without_press_passes(self):
        self.assertEqual(self.f.process(A, UP, 1.0), (True, False))

    def test_reset_forgets_history(self):
        self.press(A, 0.0, 0.08)
        self.f.reset()
        self.assertEqual(self.f.process(A, DOWN, 0.09), (True, False))


if __name__ == "__main__":
    unittest.main()
