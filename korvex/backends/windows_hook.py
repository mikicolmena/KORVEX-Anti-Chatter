"""Backend Windows: hook de teclado de bajo nivel (WH_KEYBOARD_LL) con ctypes.

Las pulsaciones rebotadas se bloquean (no llegan a ninguna aplicación). Las
pulsaciones inyectadas por software (autoescritura de gestores de contraseñas,
macros, AutoHotkey…) se dejan pasar siempre sin filtrar.

Código de tecla = scan code | 0x100 si es tecla extendida, el mismo formato
que QKeyEvent.nativeScanCode() en Windows.
"""

import ctypes
import threading
import time
from ctypes import wintypes

from ..core import DOWN, UP
from ..i18n import tr

WH_KEYBOARD_LL = 13
HC_ACTION = 0
WM_KEYDOWN, WM_KEYUP, WM_SYSKEYDOWN, WM_SYSKEYUP = 0x0100, 0x0101, 0x0104, 0x0105
WM_QUIT = 0x0012
LLKHF_EXTENDED = 0x01
LLKHF_LOWER_IL_INJECTED = 0x02
LLKHF_INJECTED = 0x10

LRESULT = ctypes.c_ssize_t
HOOKPROC = ctypes.WINFUNCTYPE(LRESULT, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM)


class KBDLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [
        ("vkCode", wintypes.DWORD),
        ("scanCode", wintypes.DWORD),
        ("flags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.c_size_t),
    ]


_user32 = ctypes.WinDLL("user32", use_last_error=True)
_kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

_user32.SetWindowsHookExW.argtypes = [ctypes.c_int, HOOKPROC, wintypes.HINSTANCE, wintypes.DWORD]
_user32.SetWindowsHookExW.restype = wintypes.HHOOK
_user32.CallNextHookEx.argtypes = [wintypes.HHOOK, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM]
_user32.CallNextHookEx.restype = LRESULT
_user32.UnhookWindowsHookEx.argtypes = [wintypes.HHOOK]
_user32.UnhookWindowsHookEx.restype = wintypes.BOOL
_user32.GetMessageW.argtypes = [ctypes.POINTER(wintypes.MSG), wintypes.HWND, wintypes.UINT, wintypes.UINT]
_user32.GetMessageW.restype = wintypes.BOOL
_user32.PostThreadMessageW.argtypes = [wintypes.DWORD, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
_user32.PostThreadMessageW.restype = wintypes.BOOL
_user32.GetKeyNameTextW.argtypes = [wintypes.LONG, wintypes.LPWSTR, ctypes.c_int]
_user32.GetKeyNameTextW.restype = ctypes.c_int
_kernel32.GetCurrentThreadId.restype = wintypes.DWORD
_kernel32.GetModuleHandleW.argtypes = [wintypes.LPCWSTR]
_kernel32.GetModuleHandleW.restype = wintypes.HMODULE

_DOWN_MSGS = (WM_KEYDOWN, WM_SYSKEYDOWN)
_UP_MSGS = (WM_KEYUP, WM_SYSKEYUP)


class WindowsBackend:
    # Ctrl, Shift, Alt, Win (izquierda y derecha)
    MODIFIER_CODES = frozenset({0x1D, 0x11D, 0x2A, 0x36, 0x38, 0x138, 0x15B, 0x15C})
    SPACE_CODE = 0x39

    def __init__(self, key_filter, on_bounce, on_error):
        self.filter = key_filter
        self.on_bounce = on_bounce
        self.on_error = on_error
        self._thread = None
        self._thread_id = None
        self._ready = threading.Event()
        self._start_error = None
        self._proc = HOOKPROC(self._callback)   # referencia viva mientras exista el hook

    @staticmethod
    def code_from_qt(native_scan_code):
        code = native_scan_code & 0x1FF
        return code or None

    @staticmethod
    def key_name(code):
        lparam = ((code & 0xFF) << 16) | ((1 << 24) if code & 0x100 else 0)
        buf = ctypes.create_unicode_buffer(64)
        if _user32.GetKeyNameTextW(lparam, buf, len(buf)) > 0:
            return buf.value
        return f"0x{code:X}"

    def start(self):
        from . import BackendError
        self._ready.clear()
        self._start_error = None
        self._thread = threading.Thread(target=self._run, name="korvex-hook", daemon=True)
        self._thread.start()
        self._ready.wait(5)
        if self._start_error is not None:
            self._thread.join(1)
            self._thread = None
            raise BackendError(tr("err_hook", code=self._start_error))

    def stop(self):
        if self._thread and self._thread_id:
            _user32.PostThreadMessageW(self._thread_id, WM_QUIT, 0, 0)
            self._thread.join(2)
        self._thread = None
        self._thread_id = None

    def _run(self):
        self._thread_id = _kernel32.GetCurrentThreadId()
        hook = _user32.SetWindowsHookExW(WH_KEYBOARD_LL, self._proc, _kernel32.GetModuleHandleW(None), 0)
        if not hook:
            self._start_error = ctypes.get_last_error()
            self._ready.set()
            return
        self._ready.set()
        msg = wintypes.MSG()
        try:
            # Los hooks de bajo nivel necesitan un bucle de mensajes en su hilo.
            while _user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
                pass
        finally:
            _user32.UnhookWindowsHookEx(hook)

    def _callback(self, n_code, w_param, l_param):
        try:
            if n_code == HC_ACTION and (w_param in _DOWN_MSGS or w_param in _UP_MSGS):
                kb = ctypes.cast(l_param, ctypes.POINTER(KBDLLHOOKSTRUCT)).contents
                if not kb.flags & (LLKHF_INJECTED | LLKHF_LOWER_IL_INJECTED):
                    code = (kb.scanCode & 0xFF) | (0x100 if kb.flags & LLKHF_EXTENDED else 0)
                    if code & 0xFF:
                        kind = DOWN if w_param in _DOWN_MSGS else UP
                        allow, bounced = self.filter.process(code, kind, time.perf_counter())
                        if bounced:
                            self.on_bounce(code)
                        if not allow:
                            return 1
        except Exception:
            pass    # ante cualquier error, dejar pasar la tecla
        return _user32.CallNextHookEx(None, n_code, w_param, l_param)
