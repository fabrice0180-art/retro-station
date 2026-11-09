"""Lecture de la manette dans les menus (Windows : XInput, sans dépendance).

Sur Mac, la manette fonctionne dans les jeux (RetroArch / Dolphin la gèrent) ;
les menus de Rétro Station se pilotent à la souris et au clavier.
"""
import ctypes
import time
from . import paths

UP, DOWN, LEFT, RIGHT = 0x0001, 0x0002, 0x0004, 0x0008
START, BACK = 0x0010, 0x0020
LB, RB = 0x0100, 0x0200
A, B, X, Y = 0x1000, 0x2000, 0x4000, 0x8000


class _Pad(ctypes.Structure):
    _fields_ = [("wButtons", ctypes.c_ushort), ("bLeftTrigger", ctypes.c_ubyte),
                ("bRightTrigger", ctypes.c_ubyte), ("sThumbLX", ctypes.c_short),
                ("sThumbLY", ctypes.c_short), ("sThumbRX", ctypes.c_short),
                ("sThumbRY", ctypes.c_short)]


class _State(ctypes.Structure):
    _fields_ = [("dwPacketNumber", ctypes.c_ulong), ("Gamepad", _Pad)]


_xinput = None
if paths.IS_WINDOWS:
    for dll in ("xinput1_4", "xinput1_3", "xinput9_1_0"):
        try:
            _xinput = getattr(ctypes.windll, dll)
            break
        except OSError:
            continue

AVAILABLE = _xinput is not None
_last = None
_next_scan = 0.0


def read():
    """Renvoie (boutons, stick_x, stick_y) de la 1re manette branchée, ou None."""
    global _last, _next_scan
    if not _xinput:
        return None
    st = _State()
    # interroger une manette absente est lent : on ne recherche qu'une fois par seconde
    if _last is None:
        if time.monotonic() < _next_scan:
            return None
        _next_scan = time.monotonic() + 1.0
        slots = range(4)
    else:
        slots = [_last]
    for i in slots:
        if _xinput.XInputGetState(i, ctypes.byref(st)) == 0:
            _last = i
            g = st.Gamepad
            b = g.wButtons
            dead = 16000
            if g.sThumbLY > dead: b |= UP
            if g.sThumbLY < -dead: b |= DOWN
            if g.sThumbLX < -dead: b |= LEFT
            if g.sThumbLX > dead: b |= RIGHT
            return b
    _last = None
    return None


def connected() -> bool:
    return read() is not None


def escape_pressed() -> bool:
    """Touche Échap enfoncée (même si une autre fenêtre est active)."""
    if not paths.IS_WINDOWS:
        return False
    return bool(ctypes.windll.user32.GetAsyncKeyState(0x1B) & 0x8000)
