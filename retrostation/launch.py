"""Préparation et commande de lancement d'un jeu."""
import configparser
from pathlib import Path

from . import paths, engines, gamepad
from .consoles import BY_ID


class LaunchError(Exception):
    pass


# ------------------------------------------------------------------ BIOS
IPF_PAGE_WIN = "http://www.softpres.org/download"
IPF_PAGE_MAC = "https://fs-uae.net/download#plugins"


def needs_capsimg(game) -> bool:
    """Les disquettes .ipf ont besoin de la bibliothèque CAPS (capsimg) dans le dossier BIOS."""
    if game.path.suffix.lower() != ".ipf":
        return False
    name = "capsimg.dll" if paths.IS_WINDOWS else "capsimg.so"
    return not any(p.name.lower() == name for p in paths.BIOS.glob("*"))


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
HANDHELDS = {"gb", "gbc", "gba", "gg", "ngp", "ngpc", "psp", "lynx"}
DISPLAY_DEFAULTS = {"fullscreen": True, "bezel": "none", "bezel_color": "", "bezel_size": 82,
                    "screen_size": 100, "scale": "fit", "smooth": False, "effect": "none", "window": 4,
                    "dolphin_res": 3}
CONSOLES_3D = {"n64", "psp", "dreamcast"}           # résolution 3D augmentable dans RetroArch
SMOOTH_DEFAULT = {"n64", "psp", "dreamcast", "saturn"}
ASPECTS = {"gb": 10 / 9, "gbc": 10 / 9, "gg": 10 / 9, "gba": 3 / 2, "ngp": 20 / 19, "ngpc": 20 / 19,
           "psp": 480 / 272, "lynx": 160 / 102}
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
    if cid == "amiga":
        try:
            from .library import collect_kickstarts
            collect_kickstarts()          # Kickstart rangés par erreur avec les jeux -> BIOS
        except Exception:
            pass
        # sans Kickstart dans le dossier BIOS : on choisit directement le Kickstart libre (AROS),
        # ce qui évite le message « Kickstart ROM not found » à chaque lancement
        have_kick = any(f.name.lower().startswith(("kick", "amiga-os-")) for f in paths.BIOS.glob("*"))
        lines["puae_kickstart"] = '"auto"' if have_kick else '"aros"'
        # un seul lecteur (DF0) : les disquettes se changent avec F6 / F7 / F5 (mode « plusieurs lecteurs »
        # désactivé, il empêchait de changer la disquette du lecteur DF0)
        lines["puae_floppy_multidrive"] = '"disabled"'
        # Les images .ipf sont en lecture seule : sans redirection, les jeux qui écrivent sur leur
        # disquette de données (ligues, équipes, scores — ex. Tip Off) la refusent en boucle.
        lines["puae_floppy_write_redirect"] = '"enabled"'

    if cid in ("arcade", "neogeo", "mame"):
        # MAME 2003-Plus : pas d'écran d'avertissement à valider avant chaque partie
        lines.setdefault("mame2003-plus_skip_disclaimer", '"enabled"')
        lines.setdefault("mame2003-plus_skip_warnings", '"enabled"')

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


NO_AUTOSTATE = {"amiga", "atarist"}   # ordinateurs à disquettes : la reprise auto peut figer le démarrage


def write_retroarch_cfg(disp: dict, bezel=None, confirm_quit=True, viewport=None, core_opts=None,
                        autostate=True) -> Path:
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
        "savestate_auto_save": "true" if autostate else "false",   # reprendre là où on s'était arrêté
        "savestate_auto_load": "true" if autostate else "false",
        "input_autodetect_enable": "true",          # manettes reconnues automatiquement
        "input_menu_toggle_gamepad_combo": "4",     # Select + Start = menu (commandes, sauvegardes, quitter)
        "input_quit_gamepad_combo": "0",
        "quit_press_twice": "true" if confirm_quit else "false",   # Échap deux fois = quitter
        "input_remap_binds_enable": "true",
        "input_remapping_directory": str(paths.SAVES / "commandes"),
        "remap_save_on_exit": "true",               # les commandes modifiées en jeu sont gardées
        "notification_show_remap_load": "true",
        # changer de disquette / de disque : F6 = éjecter / insérer, F7 = suivante, F5 = précédente
        # (le numéro choisi s'affiche à l'écran : « Disquette 2 / 2 »)
        "input_disk_eject_toggle": "f6", "input_disk_next": "f7", "input_disk_prev": "f5",
        "input_desktop_menu_toggle": "nul",
        "input_state_slot_decrease": "nul", "input_state_slot_increase": "nul",
        "video_font_enable": "true", "menu_enable_widgets": "true",
        "input_auto_game_focus": "0",               # le clavier n'est pas capturé : F5 / F6 / F7 marchent toujours
        "log_verbosity": "true", "frontend_log_level": "1", "libretro_log_level": "1",
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


# ------------------------------------------------------------------ jeux en plusieurs disquettes
FLOPPY_EXTS = (".adf", ".adz", ".dms", ".fdi", ".ipf", ".st", ".msa", ".stx", ".dim")


HD_EXTS = (".lha", ".hdf", ".hdz", ".slave")


def _zip_images(zf):
    """Images de disquette (ou de jeu WHDLoad) contenues dans un .zip, dans l'ordre des disquettes."""
    from .library import disk_number
    items = [i for i in zf.infolist() if not i.is_dir()]
    floppies = [i for i in items if i.filename.lower().endswith(FLOPPY_EXTS)]
    floppies.sort(key=lambda i: (disk_number(Path(i.filename).name) or 0, i.filename.lower()))
    hd = [i for i in items if i.filename.lower().endswith(HD_EXTS)]
    return floppies, hd


def blank_amiga_adf(path: Path, label: str = "SAUVEGARDE"):
    """Crée une disquette Amiga vierge formatée (AmigaDOS OFS, 880 Ko) : la « data disk » / disquette de
    sauvegarde que beaucoup de jeux demandent pour enregistrer équipes, scores et parties."""
    import datetime
    import struct
    blocks, size = 1760, 512
    data = bytearray(blocks * size)
    data[0:4] = b"DOS\x00"                       # bloc d'amorce (non amorçable)
    struct.pack_into(">I", data, 8, 880)
    days = (datetime.date.today() - datetime.date(1978, 1, 1)).days
    root = bytearray(size)
    struct.pack_into(">I", root, 0x000, 2)        # T_HEADER
    struct.pack_into(">I", root, 0x00C, 72)       # taille de la table de hachage
    struct.pack_into(">I", root, 0x138, 0xFFFFFFFF)   # carte des blocs valide
    struct.pack_into(">I", root, 0x13C, 881)      # bloc de la carte des blocs
    for off in (0x1A4, 0x1D8, 0x1E4):
        struct.pack_into(">III", root, off, days, 0, 0)
    name = label.encode("ascii", "ignore")[:30]
    root[0x1B0] = len(name)
    root[0x1B1:0x1B1 + len(name)] = name
    struct.pack_into(">I", root, 0x1FC, 1)        # ST_ROOT
    chk = -sum(struct.unpack(">128I", root)) & 0xFFFFFFFF
    struct.pack_into(">I", root, 0x014, chk)
    data[880 * size:881 * size] = root
    bm = bytearray(size)
    for blk in range(2, blocks):                  # 1 = bloc libre
        if blk in (880, 881):
            continue
        bit = blk - 2
        word = 1 + bit // 32
        val = struct.unpack_from(">I", bm, word * 4)[0] | (1 << (bit % 32))
        struct.pack_into(">I", bm, word * 4, val)
    chk = -sum(struct.unpack(">128I", bm)) & 0xFFFFFFFF
    struct.pack_into(">I", bm, 0, chk)
    data[881 * size:882 * size] = bm
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(bytes(data))


def save_disk_for(game) -> Path:
    """Disquette de sauvegarde propre à chaque jeu, gardée dans Sauvegardes/disquettes."""
    import re
    from .library import DISK_TAG
    base = re.sub(r'[<>:"/\\|?*]', "_", DISK_TAG.sub("", game.path.stem))
    f = paths.SAVES / "disquettes" / f"{base} - sauvegarde.adf"
    if not f.exists():
        blank_amiga_adf(f)
    return f


def prepare_floppy_game(game):
    """Prépare un jeu Amiga / Atari ST pour l'émulateur :
    - les .zip sont décompressés (l'émulateur lit alors l'image de disquette directement) ;
    - toutes les disquettes d'un jeu (fichiers « Disk 1 », « Disk 2 »… ou plusieurs images dans un même
      zip) sont réunies dans une liste .m3u pour pouvoir changer de disquette en cours de partie.
    Renvoie le fichier à lancer (ou None : on lance le fichier tel quel)."""
    import hashlib
    import re
    import zipfile
    from .library import DISK_TAG, disk_number
    if game.console not in ("amiga", "atarist"):
        return None
    base = DISK_TAG.sub("", game.path.stem)
    sources = [(disk_number(game.path.name), game.path)]
    if disk_number(game.path.name):
        sources = sorted((disk_number(f.name), f) for f in game.path.parent.iterdir()
                         if f.suffix.lower() == game.path.suffix.lower() and DISK_TAG.sub("", f.stem) == base)
    cache = paths.ENGINES / "disquettes" / hashlib.md5(f"{game.console}|{base}".encode("utf-8")).hexdigest()[:10]
    cache.mkdir(parents=True, exist_ok=True)
    disks = []          # chemins des images, dans l'ordre
    for _n, f in sources:
        if f.suffix.lower() != ".zip":
            disks.append(f)
            continue
        try:
            with zipfile.ZipFile(f) as z:
                floppies, hd = _zip_images(z)
                if not floppies and hd and len(sources) == 1:
                    out = cache / Path(hd[0].filename).name
                    if not out.exists() or out.stat().st_size != hd[0].file_size:
                        out.write_bytes(z.read(hd[0]))
                    return out                      # jeu WHDLoad : lancé directement
                for info in floppies:
                    out = cache / f"{len(disks) + 1:02d}{Path(info.filename).suffix.lower()}"
                    if not out.exists() or out.stat().st_size != info.file_size:
                        out.write_bytes(z.read(info))
                    disks.append(out)
        except (zipfile.BadZipFile, OSError):
            continue
    if not disks:
        return None
    labels = [f"Disquette {i} / {len(disks)}" for i in range(1, len(disks) + 1)]
    if game.console == "amiga":       # + une disquette de sauvegarde vierge (« data disk »)
        disks.append(save_disk_for(game))
        labels.append("Disquette de sauvegarde (vierge)")
    if len(disks) == 1:
        return disks[0]
    m3u = cache / (re.sub(r'[<>:"/\\|?*]', "_", base) + ".m3u")
    m3u.write_text("".join(f"{d}|{lab}\n" for d, lab in zip(disks, labels)), encoding="utf-8")
    return m3u


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
    core_id = c.core
    if game.console in ("arcade", "neogeo", "mame"):
        # chaque émulateur d'arcade attend les jeux dans SA version : on prend celui qui correspond
        from . import romcheck
        forced = settings.get("_force_core")
        if forced:                                  # « Essayer quand même »
            core_id, used = forced, [game.path] + [p for p in (romcheck.find_zip(n, game.path.parent) for n in
                                                    romcheck.chain(romcheck.load(forced) or {},
                                                                   game.path.stem.lower())[1:]) if p]
        else:
            core_id, used = romcheck.choose(game)      # peut lever romcheck.Incomplete
        core_id = core_id or c.core
        rom = str(romcheck.launch_folder(game, used))
    core = engines.core_path(core_id)
    if not core.exists():
        raise LaunchError(f"Le moteur « {core_id} » pour {c.name} n'est pas encore installé.")
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
    cfg = write_retroarch_cfg(disp, bezel, settings.get("confirm_quit", True), viewport, core_opts,
                              autostate=game.console not in NO_AUTOSTATE)
    prepared = prepare_floppy_game(game)
    if prepared:
        rom = str(prepared)
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


def forget_resume(game) -> int:
    """Efface la reprise automatique d'un jeu (il redémarrera depuis le début). Renvoie le nombre de fichiers."""
    from .library import DISK_TAG
    stems = {game.path.stem, DISK_TAG.sub("", game.path.stem)}
    n = 0
    root = paths.SAVES / "etats"
    if root.exists():
        for f in root.rglob("*.state.auto*"):
            if f.name.split(".state.auto")[0] in stems:
                try:
                    f.unlink()
                    n += 1
                except OSError:
                    pass
    return n


def failure_reason():
    """Explication en clair d'un jeu qui s'est fermé tout de suite (d'après le journal de RetroArch)."""
    import re
    f = paths.LOGS / "retroarch.log"
    try:
        log = f.read_text(encoding="utf-8", errors="ignore")[-20000:]
    except OSError:
        return ""
    lost = re.findall(r"(\S+) NOT FOUND \(tried in ([^)]*)\)", log)
    if lost:
        zips = []
        for _rom, where in lost:
            for z in where.split():
                if z not in zips:
                    zips.append(z)
        roms = ", ".join(r for r, _ in lost[:6]) + ("…" if len(lost) > 6 else "")
        extra = [z for z in zips[:-1]] if len(zips) > 1 else []
        msg = f"Il manque des puces au jeu : {roms}."
        if extra:
            msg += ("\n\nElles sont cherchées dans : " + ", ".join(z + ".zip" for z in zips) +
                    ".\nIl te manque sans doute : " + ", ".join(z + ".zip" for z in extra) +
                    " (le jeu principal ou le BIOS de la borne : importe-le dans Rétro Station, "
                    "il sera rangé tout seul).")
        else:
            msg += "\n\nCe fichier n'est pas dans la version attendue par l'émulateur, ou il est incomplet."
        return msg
    if "Driver not found" in log or "Unknown system" in log:
        return ("Ce fichier n'est pas un jeu d'arcade reconnu (le nom du .zip doit être le nom court du jeu, "
                "ex. sf2.zip, et le fichier ne doit pas venir d'une autre console).")
    return ""
