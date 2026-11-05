"""Backend Linux: captura exclusiva (grab) de los teclados físicos con evdev y
reenvío de las pulsaciones válidas por un teclado virtual uinput.

Funciona igual en X11, Wayland y consola. Necesita acceso de lectura/escritura
a /dev/input/event* (teclados) y a /dev/uinput; el paquete .deb lo concede al
usuario de la sesión activa mediante una regla udev con `uaccess`.
"""

import glob
import os
import selectors
import struct
import threading
import time

import logging

import evdev
from evdev import ecodes

from ..core import DOWN, REPEAT, UP
from ..i18n import tr

log = logging.getLogger(__name__)

VIRTUAL_NAME = "KORVEX Anti-Chatter"
VIRTUAL_PHYS = "korvex-antichatter"
RESCAN_INTERVAL = 2.0
SEAT_CHECK_INTERVAL = 0.5
SEAT_FILE = "/run/systemd/seats/seat0"

_EVENT_STRUCT = struct.Struct("llHHi")   # struct input_event (timeval, type, code, value)
_KIND = {0: UP, 1: DOWN, 2: REPEAT}
_BUS_VIRTUAL = 0x06


def _device_id(path):
    """Identidad del nodo: Linux reutiliza los nombres eventN, pero cada nodo nuevo
    tiene otro inode."""
    try:
        st = os.stat(path)
    except OSError:
        return None
    return st.st_ino, st.st_rdev


def _seat_is_ours(seat_file=SEAT_FILE):
    """False si otro usuario tiene ahora la sesión activa del asiento
    (cambio rápido de usuario o pantalla de inicio de sesión)."""
    try:
        with open(seat_file, encoding="utf-8") as f:
            for line in f:
                if line.startswith("ACTIVE_UID="):
                    return line.strip().split("=", 1)[1] == str(os.getuid())
    except OSError:
        return True          # sin systemd-logind: no se puede saber, se asume que sí
    return False             # asiento sin sesión activa


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
        self._ignored = {}       # ruta -> identidad de nodos que no son teclados físicos
        self._seat_owned = True
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
        self._seat_owned = _seat_is_ours()
        self._wake_r, self._wake_w = os.pipe()
        self._scan()
        if self._seat_owned and not self._grabbed and not self._pending:
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
        if not self._seat_owned:
            return
        for path in sorted(glob.glob("/dev/input/event*")):
            if path in self._grabbed or path in self._pending:
                continue
            ident = _device_id(path)
            if ident is None or self._ignored.get(path) == ident:
                continue
            try:
                dev = evdev.InputDevice(path)
            except OSError:
                continue            # sin permiso o desconectado: se reintenta en el próximo escaneo
            try:
                if _is_physical_keyboard(dev):
                    self._pending[path] = dev
                    continue
            except OSError:
                pass
            self._ignored[path] = ident
            dev.close()
        self._try_grab_pending()

    def _try_grab_pending(self):
        for path, dev in list(self._pending.items()):
            try:
                if dev.active_keys():
                    continue        # no capturar con teclas pulsadas: se quedarían "atascadas"
            except OSError:
                self._discard_pending(path)
                continue
            try:
                dev.grab()          # primero el grab (barato): si está ocupado, se reintenta luego
            except OSError:
                self._discard_pending(path)     # EBUSY (otro programa lo captura) o desconectado
                continue
            try:
                ui = evdev.UInput.from_device(
                    dev, name=f"{VIRTUAL_NAME} ({dev.name})"[:79], phys=VIRTUAL_PHYS,
                    filtered_types=(ecodes.EV_SYN, ecodes.EV_FF, ecodes.EV_REP))
            except Exception as e:
                log.warning("No se pudo crear el teclado virtual para %s: %s", dev.name, e)
                try:
                    dev.ungrab()
                except OSError:
                    pass
                self._discard_pending(path, ignore=True)
                continue
            del self._pending[path]
            g = self._grabbed[path] = _Grabbed(dev, ui)
            self._watch(path, g)
            log.info("Teclado capturado: %s (%s)", dev.name, path)

    def _discard_pending(self, path, ignore=False):
        dev = self._pending.pop(path, None)
        if ignore:
            ident = _device_id(path)
            if ident is not None:
                self._ignored[path] = ident
        if dev is not None:
            try:
                dev.close()
            except OSError:
                pass

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
        log.info("Teclado liberado: %s", path)
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
            log.exception("Error en el backend evdev")
            self._release_all()
            self.on_error(str(e))

    def _loop(self):
        self._sel = selectors.DefaultSelector()
        self._sel.register(self._wake_r, selectors.EVENT_READ, None)
        for path, g in self._grabbed.items():
            self._watch(path, g)
        last_scan = last_seat_check = time.monotonic()
        try:
            while not self._stop.is_set():
                timeout = 0.1 if self._pending else SEAT_CHECK_INTERVAL
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

                now = time.monotonic()
                if now - last_seat_check >= SEAT_CHECK_INTERVAL:
                    last_seat_check = now
                    owned = _seat_is_ours()
                    if owned != self._seat_owned:
                        self._seat_owned = owned
                        if owned:
                            log.info("La sesión vuelve a estar activa: se recapturan los teclados")
                            last_scan = 0          # escanear ya
                        else:
                            # Otro usuario usa el equipo: soltar el teclado para que sus
                            # pulsaciones no pasen por este proceso.
                            log.info("Otro usuario tiene la sesión activa: se liberan los teclados")
                            self._release_all()
                if self._pending:
                    self._try_grab_pending()
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
