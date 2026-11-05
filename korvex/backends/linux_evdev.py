"""Backend Linux: captura exclusiva (grab) de los teclados físicos con evdev y
reenvío de las pulsaciones válidas por un teclado virtual uinput.

Funciona igual en X11, Wayland y consola. Necesita acceso de lectura/escritura
a /dev/input/event* (teclados) y a /dev/uinput; el paquete .deb lo concede al
usuario de la sesión activa mediante una regla udev con `uaccess`.
"""

import errno
import glob
import os
import selectors
import struct
import threading
import time

import evdev
from evdev import ecodes

from ..core import DOWN, REPEAT, UP
from ..i18n import tr

VIRTUAL_NAME = "KORVEX Anti-Chatter"
VIRTUAL_PHYS = "korvex-antichatter"
RESCAN_INTERVAL = 2.0

_EVENT_STRUCT = struct.Struct("llHHi")   # struct input_event (timeval, type, code, value)
_KIND = {0: UP, 1: DOWN, 2: REPEAT}
_BUS_VIRTUAL = 0x06


def _is_button(code):
    # Botones de ratón/touchpad/mando (BTN_*) que algunos teclados incluyen:
    # no se filtran para no romper el doble clic.
    return 0x100 <= code < 0x160 or 0x2C0 <= code < 0x300


def _is_physical_keyboard(dev):
    if dev.name.startswith(VIRTUAL_NAME) or (dev.phys or "").startswith(VIRTUAL_PHYS):
        return False
    if not dev.phys or dev.info.bustype == _BUS_VIRTUAL or dev.phys == "py-evdev-uinput":
        # Dispositivos virtuales (autoescritura, macros, otros remapeadores):
        # no se filtran para no comerse pulsaciones generadas por software.
        return False
    keys = dev.capabilities().get(ecodes.EV_KEY, [])
    return ecodes.KEY_A in keys and ecodes.KEY_Z in keys and ecodes.KEY_SPACE in keys


class _Grabbed:
    def __init__(self, dev, ui):
        self.dev = dev
        self.ui = ui
        self.led_ok = True


class LinuxBackend:
    MODIFIER_CODES = frozenset({
        ecodes.KEY_LEFTCTRL, ecodes.KEY_RIGHTCTRL, ecodes.KEY_LEFTSHIFT, ecodes.KEY_RIGHTSHIFT,
        ecodes.KEY_LEFTALT, ecodes.KEY_RIGHTALT, ecodes.KEY_LEFTMETA, ecodes.KEY_RIGHTMETA,
    })
    SPACE_CODE = ecodes.KEY_SPACE

    def __init__(self, key_filter, on_bounce, on_error):
        self.filter = key_filter
        self.on_bounce = on_bounce
        self.on_error = on_error
        self._thread = None
        self._stop = threading.Event()
        self._wake_r = self._wake_w = None
        self._grabbed = {}       # path -> _Grabbed
        self._pending = {}       # path -> InputDevice (esperando a que se suelten las teclas)
        self._ignored = set()    # rutas que no son teclados físicos o no se pueden capturar
        self._sel = None

    # ------------------------------------------------------------------ API
    @staticmethod
    def code_from_qt(native_scan_code):
        # En X11 y Wayland, el keycode XKB es el código evdev + 8.
        return native_scan_code - 8 if native_scan_code > 8 else None

    @staticmethod
    def key_name(code):
        name = ecodes.KEY.get(code) or ecodes.BTN.get(code)
        if isinstance(name, (list, tuple)):
            name = name[0]
        if not name:
            return str(code)
        name = name.replace("KEY_", "")
        return name if len(name) <= 1 else name.replace("_", " ").title()

    def start(self):
        self._check_access()
        self._stop.clear()
        self._ignored.clear()
        self._wake_r, self._wake_w = os.pipe()
        self._scan()
        if not self._grabbed and not self._pending:
            self._close_pipe()
            raise self._diagnose_no_keyboard()
        self._thread = threading.Thread(target=self._run, name="korvex-evdev", daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()
        if self._wake_w is not None:
            try:
                os.write(self._wake_w, b"x")
            except OSError:
                pass
        if self._thread and self._thread is not threading.current_thread():
            self._thread.join(timeout=2)
        self._thread = None
        self._release_all()
        self._close_pipe()

    # ------------------------------------------------------------ internos
    def _check_access(self):
        from . import BackendError
        if not os.path.exists("/dev/uinput"):
            raise BackendError(tr("err_no_uinput"))
        if not os.access("/dev/uinput", os.R_OK | os.W_OK):
            raise BackendError(tr("err_linux_perm", detail="/dev/uinput"))

    def _diagnose_no_keyboard(self):
        from . import BackendError
        denied = [p for p in glob.glob("/dev/input/event*") if not os.access(p, os.R_OK | os.W_OK)]
        if denied:
            return BackendError(tr("err_linux_perm", detail="/dev/input/event*"))
        return BackendError(tr("err_no_keyboard"))

    def _close_pipe(self):
        for fd in (self._wake_r, self._wake_w):
            if fd is not None:
                try:
                    os.close(fd)
                except OSError:
                    pass
        self._wake_r = self._wake_w = None

    def _scan(self):
        known = set(self._grabbed) | set(self._pending) | self._ignored
        for path in sorted(glob.glob("/dev/input/event*")):
            if path in known:
                continue
            try:
                dev = evdev.InputDevice(path)
            except OSError:
                continue            # sin permiso o desconectado
            try:
                if _is_physical_keyboard(dev):
                    self._pending[path] = dev
                    continue
            except OSError:
                pass
            self._ignored.add(path)
            dev.close()
        self._try_grab_pending()

    def _try_grab_pending(self):
        for path, dev in list(self._pending.items()):
            try:
                if dev.active_keys():
                    continue        # no capturar con teclas pulsadas: se quedarían "atascadas"
                ui = evdev.UInput.from_device(
                    dev, name=f"{VIRTUAL_NAME} ({dev.name})"[:79], phys=VIRTUAL_PHYS,
                    filtered_types=(ecodes.EV_SYN, ecodes.EV_FF, ecodes.EV_REP))
                try:
                    dev.grab()
                except OSError:
                    ui.close()
                    raise
            except OSError as e:
                del self._pending[path]
                if e.errno != errno.ENODEV:
                    self._ignored.add(path)   # p. ej. EBUSY: otro programa ya lo captura
                try:
                    dev.close()
                except OSError:
                    pass
                continue
            del self._pending[path]
            g = self._grabbed[path] = _Grabbed(dev, ui)
            self._watch(path, g)

    def _watch(self, path, g):
        if self._sel is None:
            return
        self._sel.register(g.dev.fd, selectors.EVENT_READ, ("dev", path))
        try:
            self._sel.register(g.ui.fd, selectors.EVENT_READ, ("led", path))
        except (OSError, ValueError, KeyError):
            g.led_ok = False

    def _unwatch(self, fd):
        if self._sel is not None:
            try:
                self._sel.unregister(fd)
            except (KeyError, ValueError, OSError):
                pass

    def _drop(self, path):
        g = self._grabbed.pop(path, None)
        if not g:
            return
        # Dejar de vigilar ANTES de cerrar, para que un fd reutilizado no colisione.
        self._unwatch(g.dev.fd)
        self._unwatch(g.ui.fd)
        for action in (g.dev.ungrab, g.dev.close, g.ui.close):
            try:
                action()
            except (OSError, AttributeError):
                pass

    def _release_all(self):
        for path in list(self._grabbed):
            self._drop(path)
        for dev in self._pending.values():
            try:
                dev.close()
            except OSError:
                pass
        self._pending.clear()

    def _run(self):
        try:
            self._loop()
        except Exception as e:      # nunca dejar el teclado capturado si algo falla
            self._release_all()
            self.on_error(str(e))

    def _loop(self):
        self._sel = selectors.DefaultSelector()
        self._sel.register(self._wake_r, selectors.EVENT_READ, None)
        for path, g in self._grabbed.items():
            self._watch(path, g)
        last_scan = time.monotonic()
        try:
            while not self._stop.is_set():
                timeout = 0.1 if self._pending else RESCAN_INTERVAL
                for key, _ in self._sel.select(timeout):
                    if key.data is None:
                        return
                    kind, path = key.data
                    if path not in self._grabbed:
                        continue
                    if kind == "dev":
                        self._forward(path)
                    else:
                        self._forward_leds(path)

                if self._pending:
                    self._try_grab_pending()
                now = time.monotonic()
                if now - last_scan >= RESCAN_INTERVAL:
                    last_scan = now
                    self._scan()
        finally:
            sel, self._sel = self._sel, None
            sel.close()

    def _forward(self, path):
        g = self._grabbed[path]
        try:
            events = list(g.dev.read())
        except BlockingIOError:
            return
        except OSError:
            self._drop(path)        # teclado desconectado
            return
        try:
            for ev in events:
                if ev.type == ecodes.EV_KEY and ev.value in _KIND and not _is_button(ev.code):
                    allow, bounced = self.filter.process(ev.code, _KIND[ev.value], ev.timestamp())
                    if bounced:
                        self.on_bounce(ev.code)
                    if not allow:
                        continue
                g.ui.write_event(ev)
        except OSError:
            self._drop(path)

    def _forward_leds(self, path):
        """El sistema enciende los LED (Bloq Mayús…) en el teclado virtual;
        se copian al teclado físico."""
        g = self._grabbed[path]
        if not g.led_ok:
            return
        try:
            data = os.read(g.ui.fd, _EVENT_STRUCT.size * 32)
        except BlockingIOError:
            return
        except OSError:
            g.led_ok = False          # fd no legible: dejar de vigilarlo
            self._unwatch(g.ui.fd)
            return
        for offset in range(0, len(data) - _EVENT_STRUCT.size + 1, _EVENT_STRUCT.size):
            _, _, etype, code, value = _EVENT_STRUCT.unpack_from(data, offset)
            if etype == ecodes.EV_LED:
                try:
                    g.dev.write(ecodes.EV_LED, code, value)
                except OSError:
                    pass
