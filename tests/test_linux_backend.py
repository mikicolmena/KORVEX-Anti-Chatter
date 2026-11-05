"""Pruebas del backend Linux con dispositivos simulados (no necesitan permisos)."""

import os
import tempfile
import unittest
from types import SimpleNamespace
from unittest import mock

try:
    from evdev import InputEvent, ecodes as e
    from korvex.backends import linux_evdev as L
except ImportError:          # Windows o sin python3-evdev
    L = None

from korvex.core import DebounceFilter


def ev(t, etype, code, value):
    return InputEvent(int(t), int(round((t % 1) * 1e6)), etype, code, value)


class FakeUI:
    def __init__(self):
        self.out = []
        self.fd, self._w = os.pipe()

    def write_event(self, event):
        self.out.append((event.type, event.code, event.value))

    def push_raw(self, *events):
        os.write(self._w, b"".join(L._EVENT_STRUCT.pack(0, 0, *x) for x in events))

    def close(self):
        for fd in (self.fd, self._w):
            try:
                os.close(fd)
            except OSError:
                pass


class FakeDev:
    def __init__(self, events=(), name="Teclado", phys="usb-1/input0", bustype=3, keys=None):
        self.events = list(events)
        self.leds = []
        self.fd = 99
        self.name = name
        self.phys = phys
        self.info = SimpleNamespace(bustype=bustype)
        self.keys = keys if keys is not None else [e.KEY_A, e.KEY_Z, e.KEY_SPACE]
        self.closed = self.grabbed = False

    def read(self):
        return iter(self.events)

    def write(self, *args):
        self.leds.append(args)

    def capabilities(self):
        return {e.EV_KEY: self.keys}

    def active_keys(self):
        return []

    def grab(self):
        self.grabbed = True

    def ungrab(self):
        self.grabbed = False

    def close(self):
        self.closed = True


@unittest.skipIf(L is None, "requiere Linux y python3-evdev")
class LinuxBackendTest(unittest.TestCase):
    def setUp(self):
        self.filter = DebounceFilter(L.LinuxBackend.MODIFIER_CODES, L.LinuxBackend.SPACE_CODE)
        self.bounces = []
        self.backend = L.LinuxBackend(self.filter, self.bounces.append, lambda msg: None)

    def grabbed(self, events):
        ui, dev = FakeUI(), FakeDev(events)
        self.addCleanup(ui.close)
        self.backend._grabbed["/dev/input/event3"] = L._Grabbed(dev, ui)
        return ui, dev

    def test_bounce_is_not_forwarded(self):
        ui, _ = self.grabbed([
            ev(0.00, e.EV_MSC, e.MSC_SCAN, 4), ev(0.00, e.EV_KEY, e.KEY_A, 1), ev(0.00, e.EV_SYN, 0, 0),
            ev(0.08, e.EV_KEY, e.KEY_A, 0), ev(0.08, e.EV_SYN, 0, 0),
            ev(0.09, e.EV_KEY, e.KEY_A, 1), ev(0.09, e.EV_SYN, 0, 0),      # rebote
            ev(0.095, e.EV_KEY, e.KEY_A, 0), ev(0.095, e.EV_SYN, 0, 0),
        ])
        self.backend._forward("/dev/input/event3")
        keys = [x for x in ui.out if x[0] == e.EV_KEY]
        self.assertEqual(keys, [(e.EV_KEY, e.KEY_A, 1), (e.EV_KEY, e.KEY_A, 0)])
        self.assertEqual(self.bounces, [e.KEY_A])

    def test_mouse_buttons_are_never_filtered(self):
        ui, _ = self.grabbed([
            ev(0.00, e.EV_KEY, e.BTN_LEFT, 1), ev(0.01, e.EV_KEY, e.BTN_LEFT, 0),
            ev(0.02, e.EV_KEY, e.BTN_LEFT, 1), ev(0.03, e.EV_KEY, e.BTN_LEFT, 0),
        ])
        self.backend._forward("/dev/input/event3")
        self.assertEqual(len(ui.out), 4)
        self.assertEqual(self.bounces, [])

    def test_leds_are_copied_to_physical_keyboard(self):
        ui, dev = self.grabbed([])
        ui.push_raw((e.EV_LED, e.LED_CAPSL, 1), (e.EV_SYN, 0, 0))
        self.backend._forward_leds("/dev/input/event3")
        self.assertEqual(dev.leds, [(e.EV_LED, e.LED_CAPSL, 1)])

    def test_virtual_devices_are_not_captured(self):
        self.assertTrue(L._is_physical_keyboard(FakeDev()))
        self.assertFalse(L._is_physical_keyboard(FakeDev(phys="")))
        self.assertFalse(L._is_physical_keyboard(FakeDev(bustype=0x06)))
        self.assertFalse(L._is_physical_keyboard(FakeDev(name="KORVEX Anti-Chatter (x)")))
        self.assertFalse(L._is_physical_keyboard(FakeDev(keys=[e.KEY_VOLUMEUP])))

    def test_reused_event_node_is_rescanned(self):
        """Un ratón ignorado en event5 se desconecta y un teclado ocupa el mismo event5."""
        inode = {"value": 100}
        devices = {"value": FakeDev(name="Ratón", keys=[e.BTN_LEFT])}
        fake_stat = lambda path: SimpleNamespace(st_ino=inode["value"], st_rdev=1)
        with mock.patch.object(L.glob, "glob", return_value=["/dev/input/event5"]), \
                mock.patch.object(L.os, "stat", side_effect=fake_stat), \
                mock.patch.object(L.evdev, "InputDevice", side_effect=lambda p: devices["value"]), \
                mock.patch.object(L.evdev.UInput, "from_device", side_effect=lambda *a, **k: FakeUI()):
            self.backend._scan()
            self.assertIn("/dev/input/event5", self.backend._ignored)
            self.assertEqual(self.backend._grabbed, {})

            inode["value"] = 101                       # nodo nuevo con el mismo nombre
            devices["value"] = FakeDev(name="Teclado")
            self.backend._scan()
            self.assertIn("/dev/input/event5", self.backend._grabbed)
            self.assertTrue(devices["value"].grabbed)
        self.backend._grabbed["/dev/input/event5"].ui.close()

    def test_busy_keyboard_is_retried(self):
        dev = FakeDev()
        dev.grab = mock.Mock(side_effect=OSError(16, "Device or resource busy"))
        self.backend._pending["/dev/input/event7"] = dev
        self.backend._try_grab_pending()
        self.assertNotIn("/dev/input/event7", self.backend._ignored)   # se volverá a intentar
        self.assertNotIn("/dev/input/event7", self.backend._grabbed)

    def test_seat_ownership(self):
        with tempfile.NamedTemporaryFile("w", delete=False) as f:
            f.write(f"ACTIVE=2\nACTIVE_UID={os.getuid()}\n")
        self.addCleanup(os.remove, f.name)
        self.assertTrue(L._seat_is_ours(f.name))
        with open(f.name, "w") as fh:
            fh.write(f"ACTIVE=c1\nACTIVE_UID={os.getuid() + 1}\n")
        self.assertFalse(L._seat_is_ours(f.name))
        with open(f.name, "w") as fh:
            fh.write("SESSIONS=2\n")                       # nadie activo en el asiento
        self.assertFalse(L._seat_is_ours(f.name))
        self.assertTrue(L._seat_is_ours("/no/existe"))       # sin logind: se asume que sí


if __name__ == "__main__":
    unittest.main()
