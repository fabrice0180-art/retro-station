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
HANDHELDS = {"gb", "gbc", "gba", "gg", "ngp", "ngpc", "psp"}
DISPLAY_DEFAULTS = {"fullscreen": True, "bezel": "none", "bezel_color": "", "bezel_size": 82,
                    "screen_size": 100, "scale": "fit", "smooth": False, "effect": "none", "window": 4,
                    "dolphin_res": 3}
CONSOLES_3D = {"n64", "psp", "dreamcast"}           # résolution 3D augmentable dans RetroArch
SMOOTH_DEFAULT = {"n64", "psp", "dreamcast", "saturn"}
ASPECTS = {"gb": 10 / 9, "gbc": 10 / 9, "gg": 10 / 9, "gba": 3 / 2, "ngp": 20 / 19, "ngpc": 20 / 19,
           "psp": 480 / 272}
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
    if cid in HANDHELDS:            # consoles portables : contour + effet LCD par défaut
        d.update(bezel="handheld", bezel_color="Gris clair", effect="lcd")
    elif cid in SMOOTH_DEFAULT:     # consoles 3D : image affinée et lissée
        d.update(smooth=True, dolphin_res=4)
    else:                           # consoles de salon 2D : effet télé, fini les gros pixels carrés
        d.update(effect="crt")
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


RES3D_OPTIONS = {
    "n64": lambda f: {"mupen64plus-EnableNativeResFactor": str(f), "mupen64plus-rdp-plugin": "gliden64"},
    "psp": lambda f: {"ppsspp_internal_resolution": f"{480 * f}x{272 * f}"},
    "dreamcast": lambda f: {"reicast_internal_resolution": f"{640 * f}x{480 * f}"},
}


def write_core_options(cid, disp) -> Path:
    """Options des moteurs (fichier partagé, les réglages faits en jeu y sont gardés aussi)."""
    path = paths.ENGINES / "options-moteurs.cfg"
    lines = {}
    if path.exists():
        for ln in path.read_text(encoding="utf-8", errors="ignore").splitlines():
            if "=" in ln:
                k, v = ln.split("=", 1)
                lines[k.strip()] = v.strip()
    if cid in RES3D_OPTIONS:
        f = max(1, min(6, int(disp.get("dolphin_res", 4))))
        for k, v in RES3D_OPTIONS[cid](f).items():
            lines[k] = f'"{v}"'
    path.write_text("".join(f"{k} = {v}\n" for k, v in lines.items()), encoding="utf-8")
    return path


def screen_rect(cid, pct, W, H):
    """Écran du jeu centré, à pct % de la hauteur, aux proportions de la console."""
    asp = ASPECTS.get(cid, 4 / 3)
    h = H * pct / 100
    w = min(W, h * asp)
    h = w / asp
    return int((W - w) / 2), int((H - h) / 2), int(w), int(h)


def write_retroarch_cfg(disp: dict, bezel=None, confirm_quit=True, viewport=None, core_opts=None) -> Path:
    """bezel = (fichier .cfg du contour, (x, y, w, h) du trou) ou None."""
    paths.ENGINES.mkdir(parents=True, exist_ok=True)
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
        "input_menu_toggle_gamepad_combo": "4",     # Select + Start = menu (commandes, sauvegardes, quitter)
        "input_quit_gamepad_combo": "0",
        "quit_press_twice": "true" if confirm_quit else "false",   # Échap deux fois = quitter
        "input_remap_binds_enable": "true",
        "input_remapping_directory": str(paths.SAVES / "commandes"),
        "remap_save_on_exit": "true",               # les commandes modifiées en jeu sont gardées
        "notification_show_remap_load": "true",
        "pause_nonactive": "false",
        "menu_mouse_enable": "true",
        "menu_pointer_enable": "true",
        "log_to_file": "true",
        "log_to_file_timestamp": "false",
        "log_dir": str(paths.LOGS),
    }
    if core_opts:
        vals.update({"global_core_options": "true", "core_options_path": str(core_opts)})
    if not bezel and viewport:
        x, y, w, h = viewport
        vals.update({
            "input_overlay_enable": "false", "video_scale_integer": "false", "video_aspect_ratio_auto": "false",
            "aspect_ratio_index": "23", "custom_viewport_x": str(x), "custom_viewport_y": str(y),
            "custom_viewport_width": str(w), "custom_viewport_height": str(h),
        })
    elif bezel:
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
    (paths.SAVES / "commandes").mkdir(parents=True, exist_ok=True)
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
    _ini_update(ini, "Interface", {"ConfirmStop": "True" if settings.get("confirm_quit", True) else "False"})
    _ini_update(ini, "Display", {"Fullscreen": "True" if disp["fullscreen"] else "False"})
    _ini_update(conf / "GFX.ini", "Settings", {"InternalResolution": str(int(disp.get("dolphin_res", 3)))})
    _ini_update(ini, "Analytics", {"PermissionAsked": "True", "Enabled": "False"})
    _ini_update(ini, "AutoUpdate", {"UpdateTrack": ""})
    # Commandes automatiques (Windows) : manette si branchée, sinon clavier + souris.
    if paths.IS_WINDOWS and settings.get("dolphin_controls", "auto") == "auto":  # sinon : réglages faits dans Dolphin
        pad = gamepad.connected()
        _ini_update(conf / "GCPadNew.ini", "GCPad1", GC_PAD if pad else GC_KB, replace_section=True)
        _ini_update(conf / "WiimoteNew.ini", "Wiimote1", WII_PAD if pad else WII_KB, replace_section=True)


# ------------------------------------------------------------------ netteté Windows (mise à l'échelle)
def ensure_sharp_windows(exe):
    """Windows agrandit en flou les programmes qui ne gèrent pas la mise à l'échelle (125 %, 150 %…).
    On déclare RetroArch « compatible haute résolution » : image nette, à la vraie résolution de l'écran
    (et le jeu tombe pile dans son contour)."""
    if not paths.IS_WINDOWS:
        return
    try:
        import winreg
        key = winreg.CreateKey(winreg.HKEY_CURRENT_USER,
                               r"Software\Microsoft\Windows NT\CurrentVersion\AppCompatFlags\Layers")
        try:
            cur, _ = winreg.QueryValueEx(key, str(exe))
        except OSError:
            cur = ""
        if "HIGHDPIAWARE" not in cur:
            flags = [f for f in cur.replace("~", "").split() if f]
            winreg.SetValueEx(key, str(exe), 0, winreg.REG_SZ, "~ " + " ".join(flags + ["HIGHDPIAWARE"]))
        winreg.CloseKey(key)
    except Exception:
        pass


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
    ensure_sharp_windows(exe)
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
    viewport = None
    if not bezel and disp.get("fullscreen", True) and int(disp.get("screen_size", 100)) < 100:
        viewport = screen_rect(game.console, int(disp["screen_size"]), int(screen[0]), int(screen[1]))
    core_opts = write_core_options(game.console, disp)
    cfg = write_retroarch_cfg(disp, bezel, settings.get("confirm_quit", True), viewport, core_opts)
    args = ["-L", str(core), rom, "--appendconfig", str(cfg)]
    shader = find_shader(disp.get("effect", "none")) if use_shader else None
    if shader:
        args += ["--set-shader", str(shader)]
    return str(exe), args, str(exe.parent), bool(shader)


def dolphin_setup_command():
    """Ouvre Dolphin sans jeu, pour régler les manettes Wii / GameCube."""
    exe = engines.dolphin_exe()
    if not exe:
        raise LaunchError("Dolphin (moteur GameCube / Wii) n'est pas encore installé.")
    DOLPHIN_USER.mkdir(parents=True, exist_ok=True)
    return str(exe), ["-u", str(DOLPHIN_USER)], str(exe.parent)
