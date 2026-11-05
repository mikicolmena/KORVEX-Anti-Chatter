"""Lógica del filtro anti-rebote, independiente de la plataforma.

Cada backend traduce los eventos del sistema a (código, tipo, instante) y
pregunta a DebounceFilter si el evento debe llegar al sistema o bloquearse.

Lógica "GAP": si una tecla vuelve a pulsarse menos de `threshold` segundos
después de haberse soltado, esa pulsación es un rebote. Se bloquea tanto la
pulsación como su liberación, para que el sistema nunca vea un estado
inconsistente. Las repeticiones automáticas de una tecla bloqueada también se
bloquean.
"""

import threading

DOWN, UP, REPEAT = "down", "up", "repeat"

_PASSED, _BLOCKED = 1, 2


class DebounceFilter:
    def __init__(self, modifier_codes=(), space_code=None):
        self.modifier_codes = frozenset(modifier_codes)
        self.space_code = space_code
        self.threshold = 0.050
        self.threshold_space = 0.120
        self.filter_all = True             # False -> solo `selected`
        self.selected = frozenset()
        self._lock = threading.Lock()
        self._down = {}
        self._last_up = {}

    # --- configuración (llamada desde el hilo de la interfaz) ---
    def set_threshold_ms(self, ms):
        self.threshold = ms / 1000.0

    def set_threshold_space_ms(self, ms):
        self.threshold_space = ms / 1000.0

    def set_selection(self, filter_all, codes):
        self.filter_all = bool(filter_all)
        self.selected = frozenset(int(c) for c in codes)

    def reset(self):
        with self._lock:
            self._down.clear()
            self._last_up.clear()

    def applies_to(self, code):
        if self.filter_all:
            return code not in self.modifier_codes
        return code in self.selected

    # --- decisión (llamada desde el hilo del backend) ---
    def process(self, code, kind, timestamp):
        """Devuelve (permitir, es_rebote)."""
        with self._lock:
            if kind == UP:
                state = self._down.pop(code, None)
                self._last_up[code] = timestamp
                return state != _BLOCKED, False

            state = self._down.get(code)
            if kind == REPEAT or state == _PASSED:
                # Autorepetición: sigue el destino de la pulsación original.
                return state != _BLOCKED, False
            if state == _BLOCKED:
                return False, False

            last_up = self._last_up.get(code)
            if last_up is not None and self.applies_to(code):
                limit = self.threshold_space if code == self.space_code else self.threshold
                if 0 <= timestamp - last_up < limit:
                    self._down[code] = _BLOCKED
                    return False, True

            self._down[code] = _PASSED
            return True, False
