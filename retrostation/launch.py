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
HANDHELDS = {"gb", "gbc", "gba", "gg", "ngp", "ngpc"}
DISPLAY_DEFAULTS = {"fullscreen": True, "bezel": "none", "bezel_color": "", "bezel_size": 82,
                    "scale": "fit", "smooth": False, "effect": "none", "window": 4, "dolphin_res": 3}
EFFECTS = {"none": "Aucun", "lcd": "Écran LCD (grille de pixels)", "crt": "Télé cathodique (lignes)",
           "smooth": "Lissage intelligent (xBRZ)"}
SHADER_FILES = {
    "lcd": ["lcd-grid-v2.slangp", "lcd3x.slangp", "lcd-grid-v2.glslp", "lcd3x.glslp"],
    "crt": ["crt-easymode.slangp", "crt-lottes.slangp", "crt-geom.slangp", "crt-easymode.glslp", "crt-geom.glslp"],
    "smooth": ["xbrz-freescale.slangp", "xbrz-freescale-multipass.slangp", "scalefx.slangp", "xbrz-freescale.glslp"],
}


def display_for(settings: dict, cid: str) -> dict:
    """Réglages d'affichage d'une console (valeurs par défaut + choix de l'utilisateur)."""
    d = dict(DISPLAY_DEFAULTS)
    if cid in HANDHELDS:   # consoles portables : contour + effet LCD par défaut
        d.update(bezel="handheld", bezel_color="Gris clair", effect="lcd")
    d["fullscreen"] = settings.get("fullscreen", True)
    d.update(settings.get("display", {}).get(cid, {}))
    return d


_shader_cache = {}


def find_shader(effect: str):
    if effect not in SHADER_FILES:
        return None
    if effect in _shader_cache:
        return _shader_cache[effect]
    roots = [paths.ENGINES / "shaders", engines.RA_DIR / "shaders"]
    ra = engines.retroarch_exe()
    if ra and paths.IS_MAC:
        roots.append(ra.parent.parent / "Resources" / "shaders")
    found = None
    for name in SHADER_FILES[effect]:
        for root in roots:
            if root.exists():
                found = next(root.rglob(name), None)
                if found:
                    break
        if found:
            break
    _shader_cache[effect] = found
    return found


def write_retroarch_cfg(disp: dict, bezel=None) -> Path:
    """bezel = (fichier .cfg du contour, (x, y, w, h) du trou) ou None."""
    cfg = paths.ENGINES / "retrostation.cfg"
    vals = {
        "video_fullscreen": "true" if (disp["fullscreen"] or bezel) else "false",
        "video_windowed_fullscreen": "true",
        "video_scale": str(int(disp.get("window", 4))),
        "video_smooth": "true" if disp.get("smooth") else "false",
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
    if bezel:
        ovl, (x, y, w, h) = bezel
        vals.update({
            "input_overlay_enable": "true", "input_overlay": str(ovl), "input_overlay_opacity": "1.000000",
            "input_overlay_scale": "1.000000", "input_overlay_scale_landscape": "1.000000",
            "input_overlay_hide_in_menu": "true", "input_overlay_auto_scale": "false",
            "video_scale_integer": "false", "video_aspect_ratio_auto": "false",
            "aspect_ratio_index": "23",              # « personnalisé » : le jeu se cale dans le trou
            "custom_viewport_x": str(x), "custom_viewport_y": str(y),
            "custom_viewport_width": str(w), "custom_viewport_height": str(h),
        })
    else:
        vals.update({
            "input_overlay_enable": "false",
            "video_scale_integer": "true" if disp.get("scale") == "integer" else "false",
            "video_aspect_ratio_auto": "true",
            "aspect_ratio_index": "22",              # proportions d'origine de la console
        })
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


def prepare_dolphin(settings: dict, cid: str = "wii"):
    disp = display_for(settings, cid)
    conf = DOLPHIN_USER / "Config"
    ini = conf / "Dolphin.ini"
    _ini_update(ini, "Interface", {"ConfirmStop": "False"})
    _ini_update(ini, "Display", {"Fullscreen": "True" if disp["fullscreen"] else "False"})
    _ini_update(conf / "GFX.ini", "Settings", {"InternalResolution": str(int(disp.get("dolphin_res", 3)))})
    _ini_update(ini, "Analytics", {"PermissionAsked": "True", "Enabled": "False"})
    _ini_update(ini, "AutoUpdate", {"UpdateTrack": ""})
    # Commandes automatiques (Windows) : manette si branchée, sinon clavier + souris.
    if paths.IS_WINDOWS and settings.get("dolphin_controls", "auto") == "auto":
        pad = gamepad.connected()
        _ini_update(conf / "GCPadNew.ini", "GCPad1", GC_PAD if pad else GC_KB, replace_section=True)
        _ini_update(conf / "WiimoteNew.ini", "Wiimote1", WII_PAD if pad else WII_KB, replace_section=True)


# ------------------------------------------------------------------ commande
def build_command(game, settings: dict, use_shader=True, screen=(1920, 1080)):
    """Renvoie (programme, arguments, dossier de travail, effet utilisé ?)."""
    c = BY_ID[game.console]
    rom = str(game.path)
    if c.engine == "dolphin":
        exe = engines.dolphin_exe()
        if not exe:
            raise LaunchError("Dolphin (moteur GameCube / Wii) n'est pas encore installé.")
        prepare_dolphin(settings, game.console)
        return str(exe), ["-u", str(DOLPHIN_USER), "-b", "-e", rom], str(exe.parent), False
    exe = engines.retroarch_exe()
    if not exe:
        raise LaunchError("RetroArch (moteur principal) n'est pas encore installé.")
    core = engines.core_path(c.core)
    if not core.exists():
        raise LaunchError(f"Le moteur « {c.core} » pour {c.name} n'est pas encore installé.")
    disp = display_for(settings, game.console)
    bezel = None
    if disp.get("bezel", "none") != "none":
        try:
            from . import bezels
            bezel = bezels.render_overlay(game.console, disp["bezel"], disp.get("bezel_color", ""),
                                          int(disp.get("bezel_size", 82)), int(screen[0]), int(screen[1]))
        except Exception:
            bezel = None   # pas de contour plutôt qu'un jeu qui ne démarre pas
    cfg = write_retroarch_cfg(disp, bezel)
    args = ["-L", str(core), rom, "--appendconfig", str(cfg)]
    shader = find_shader(disp.get("effect", "none")) if use_shader else None
    if shader:
        args += ["--set-shader", str(shader)]
    return str(exe), args, str(exe.parent), bool(shader)
