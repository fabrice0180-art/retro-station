"""Préparation et commande de lancement d'un jeu."""
import configparser
from pathlib import Path

from . import paths, engines, gamepad
from .consoles import BY_ID


class LaunchError(Exception):
    pass


# ------------------------------------------------------------------ BIOS
def missing_bios(cid: str):
    """Liste des groupes de BIOS indispensables qui manquent."""
    c = BY_ID[cid]
    missing = []
    for group in c.bios_required:
        found = any((paths.BIOS / f).exists() for f in group)
        if cid == "neogeo":
            found = found or (paths.GAMES / c.name / "neogeo.zip").exists()
        if not found:
            missing.append(group)
    return missing


# ------------------------------------------------------------------ RetroArch
def write_retroarch_cfg(fullscreen=True) -> Path:
    cfg = paths.ENGINES / "retrostation.cfg"
    vals = {
        "video_fullscreen": "true" if fullscreen else "false",
        "user_language": "2",                       # français
        "system_directory": str(paths.BIOS),
        "savefile_directory": str(paths.SAVES / "parties"),
        "savestate_directory": str(paths.SAVES / "etats"),
        "screenshot_directory": str(paths.SAVES / "captures"),
        "savestate_auto_save": "true",              # reprendre là où on s'était arrêté
        "savestate_auto_load": "true",
        "input_autodetect_enable": "true",          # manettes reconnues automatiquement
        "input_menu_toggle_gamepad_combo": "2",     # L3 + R3 = menu
        "input_quit_gamepad_combo": "4",            # Select + Start = quitter
        "quit_press_twice": "false",
        "pause_nonactive": "false",
        "menu_mouse_enable": "true",
        "menu_pointer_enable": "true",
        "log_to_file": "true",
        "log_to_file_timestamp": "false",
        "log_dir": str(paths.LOGS),
    }
    (paths.SAVES / "captures").mkdir(parents=True, exist_ok=True)
    cfg.write_text("".join(f'{k} = "{v}"\n' for k, v in vals.items()), encoding="utf-8")
    return cfg


# ------------------------------------------------------------------ Dolphin
DOLPHIN_USER = paths.SAVES / "Dolphin"
KB = "DInput/0/Keyboard Mouse"


def _q(s):
    return f"`{s}`"


GC_PAD = {
    "Device": "XInput/0/Gamepad",
    "Buttons/A": _q("Button A"), "Buttons/B": _q("Button B"),
    "Buttons/X": _q("Button X"), "Buttons/Y": _q("Button Y"),
    "Buttons/Z": _q("Shoulder R"), "Buttons/Start": _q("Start"),
    "Main Stick/Up": _q("Left Y+"), "Main Stick/Down": _q("Left Y-"),
    "Main Stick/Left": _q("Left X-"), "Main Stick/Right": _q("Left X+"),
    "C-Stick/Up": _q("Right Y+"), "C-Stick/Down": _q("Right Y-"),
    "C-Stick/Left": _q("Right X-"), "C-Stick/Right": _q("Right X+"),
    "Triggers/L": _q("Trigger L"), "Triggers/R": _q("Trigger R"),
    "Triggers/L-Analog": _q("Trigger L"), "Triggers/R-Analog": _q("Trigger R"),
    "D-Pad/Up": _q("Pad N"), "D-Pad/Down": _q("Pad S"),
    "D-Pad/Left": _q("Pad W"), "D-Pad/Right": _q("Pad E"),
}
GC_KB = {
    "Device": KB,
    "Buttons/A": _q("X"), "Buttons/B": _q("Z"), "Buttons/X": _q("C"), "Buttons/Y": _q("S"),
    "Buttons/Z": _q("D"), "Buttons/Start": _q("RETURN"),
    "Main Stick/Up": _q("UP"), "Main Stick/Down": _q("DOWN"),
    "Main Stick/Left": _q("LEFT"), "Main Stick/Right": _q("RIGHT"),
    "C-Stick/Up": _q("I"), "C-Stick/Down": _q("K"), "C-Stick/Left": _q("J"), "C-Stick/Right": _q("L"),
    "Triggers/L": _q("Q"), "Triggers/R": _q("W"),
    "D-Pad/Up": _q("T"), "D-Pad/Down": _q("G"), "D-Pad/Left": _q("F"), "D-Pad/Right": _q("H"),
}
MOUSE = lambda s: f"`{KB}:{s}`"  # noqa: E731
WII_PAD = {
    "Source": "1", "Device": "XInput/0/Gamepad", "Extension": "Nunchuk",
    "Buttons/A": f"{_q('Button A')} | {MOUSE('Click 0')}",
    "Buttons/B": f"{_q('Button B')} | {_q('Trigger R')} | {MOUSE('Click 1')}",
    "Buttons/1": _q("Button X"), "Buttons/2": _q("Button Y"),
    "Buttons/-": _q("Back"), "Buttons/+": _q("Start"), "Buttons/Home": _q("Thumb R"),
    "D-Pad/Up": _q("Pad N"), "D-Pad/Down": _q("Pad S"),
    "D-Pad/Left": _q("Pad W"), "D-Pad/Right": _q("Pad E"),
    # le pointeur suit la souris OU le stick droit
    "IR/Up": f"{_q('Right Y+')} | {MOUSE('Cursor Y-')}",
    "IR/Down": f"{_q('Right Y-')} | {MOUSE('Cursor Y+')}",
    "IR/Left": f"{_q('Right X-')} | {MOUSE('Cursor X-')}",
    "IR/Right": f"{_q('Right X+')} | {MOUSE('Cursor X+')}",
    "Shake/X": _q("Shoulder R"), "Shake/Y": _q("Shoulder R"), "Shake/Z": _q("Shoulder R"),
    "Nunchuk/Buttons/C": _q("Shoulder L"), "Nunchuk/Buttons/Z": _q("Trigger L"),
    "Nunchuk/Stick/Up": _q("Left Y+"), "Nunchuk/Stick/Down": _q("Left Y-"),
    "Nunchuk/Stick/Left": _q("Left X-"), "Nunchuk/Stick/Right": _q("Left X+"),
}
WII_KB = {
    "Source": "1", "Device": KB, "Extension": "Nunchuk",
    "Buttons/A": _q("Click 0"), "Buttons/B": _q("Click 1"),
    "Buttons/1": _q("1"), "Buttons/2": _q("2"),
    "Buttons/-": _q("Q"), "Buttons/+": _q("E"), "Buttons/Home": _q("RETURN"),
    "D-Pad/Up": _q("UP"), "D-Pad/Down": _q("DOWN"), "D-Pad/Left": _q("LEFT"), "D-Pad/Right": _q("RIGHT"),
    "IR/Up": _q("Cursor Y-"), "IR/Down": _q("Cursor Y+"),
    "IR/Left": _q("Cursor X-"), "IR/Right": _q("Cursor X+"),
    "Shake/X": _q("Click 2"), "Shake/Y": _q("Click 2"), "Shake/Z": _q("Click 2"),
    "Nunchuk/Buttons/C": _q("LCONTROL"), "Nunchuk/Buttons/Z": _q("LSHIFT"),
    "Nunchuk/Stick/Up": _q("W"), "Nunchuk/Stick/Down": _q("S"),
    "Nunchuk/Stick/Left": _q("A"), "Nunchuk/Stick/Right": _q("D"),
}


def _ini_update(path: Path, section: str, values: dict, replace_section=False):
    cp = configparser.ConfigParser(interpolation=None, strict=False, delimiters=("=",))
    cp.optionxform = str
    if path.exists():
        try:
            cp.read(path, encoding="utf-8")
        except configparser.Error:
            cp = configparser.ConfigParser(interpolation=None, strict=False, delimiters=("=",))
            cp.optionxform = str
    if replace_section and cp.has_section(section):
        cp.remove_section(section)
    if not cp.has_section(section):
        cp.add_section(section)
    for k, v in values.items():
        cp.set(section, k, v)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        cp.write(f)


def prepare_dolphin(settings: dict):
    conf = DOLPHIN_USER / "Config"
    ini = conf / "Dolphin.ini"
    _ini_update(ini, "Interface", {"ConfirmStop": "False"})
    _ini_update(ini, "Display", {"Fullscreen": "True" if settings.get("fullscreen", True) else "False"})
    _ini_update(ini, "Analytics", {"PermissionAsked": "True", "Enabled": "False"})
    _ini_update(ini, "AutoUpdate", {"UpdateTrack": ""})
    # Commandes automatiques (Windows) : manette si branchée, sinon clavier + souris.
    if paths.IS_WINDOWS and settings.get("dolphin_controls", "auto") == "auto":
        pad = gamepad.connected()
        _ini_update(conf / "GCPadNew.ini", "GCPad1", GC_PAD if pad else GC_KB, replace_section=True)
        _ini_update(conf / "WiimoteNew.ini", "Wiimote1", WII_PAD if pad else WII_KB, replace_section=True)


# ------------------------------------------------------------------ commande
def build_command(game, settings: dict):
    """Renvoie (programme, arguments, dossier de travail)."""
    c = BY_ID[game.console]
    rom = str(game.path)
    if c.engine == "dolphin":
        exe = engines.dolphin_exe()
        if not exe:
            raise LaunchError("Dolphin (moteur GameCube / Wii) n'est pas encore installé.")
        prepare_dolphin(settings)
        return str(exe), ["-u", str(DOLPHIN_USER), "-b", "-e", rom], str(exe.parent)
    exe = engines.retroarch_exe()
    if not exe:
        raise LaunchError("RetroArch (moteur principal) n'est pas encore installé.")
    core = engines.core_path(c.core)
    if not core.exists():
        raise LaunchError(f"Le moteur « {c.core} » pour {c.name} n'est pas encore installé.")
    cfg = write_retroarch_cfg(settings.get("fullscreen", True))
    return str(exe), ["-L", str(core), rom, "--appendconfig", str(cfg)], str(exe.parent)
