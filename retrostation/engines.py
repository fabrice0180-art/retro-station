"""Téléchargement et installation des moteurs d'émulation (sur le PC / Mac de l'utilisateur).

- RetroArch + cœurs libretro (NES, SNES, GB/GBC/GBA, N64, Sega, Neo Geo)
- Dolphin (GameCube / Wii)
Tout est rangé dans ~/RetroStation/Moteurs.
"""
import re
import shutil
import subprocess
import tempfile
import urllib.request
import zipfile
from pathlib import Path

from . import paths
from .consoles import RETROARCH_CORES

UA = {"User-Agent": f"RetroStation/{paths.VERSION}"}
BUILDBOT = "https://buildbot.libretro.com"
DOLPHIN_PAGE = "https://dolphin-emu.org/download/"
RETROARCH_PAGE = "https://www.retroarch.com/?page=platforms"
NO_WINDOW = 0x08000000 if paths.IS_WINDOWS else 0

RA_DIR = paths.ENGINES / "RetroArch"
CORES_DIR = paths.ENGINES / "cores"
DOLPHIN_DIR = paths.ENGINES / "Dolphin"
SEVENZIP = paths.ENGINES / "7zr.exe"


class EngineError(Exception):
    pass


# ------------------------------------------------------------------ chemins
def _first_existing(cands):
    for c in cands:
        if c.exists():
            return c
    return None


def retroarch_exe():
    if paths.IS_WINDOWS:
        p = RA_DIR / "retroarch.exe"
        return p if p.exists() else None
    app = _first_existing([paths.ENGINES / "RetroArch.app", Path("/Applications/RetroArch.app"),
                           Path.home() / "Applications/RetroArch.app"])
    return app / "Contents/MacOS/RetroArch" if app else None


def core_path(core: str) -> Path:
    ext = "dll" if paths.IS_WINDOWS else "dylib"
    return CORES_DIR / f"{core}_libretro.{ext}"


def dolphin_exe():
    if paths.IS_WINDOWS:
        p = DOLPHIN_DIR / "Dolphin.exe"
        return p if p.exists() else None
    app = _first_existing([paths.ENGINES / "Dolphin.app", Path("/Applications/Dolphin.app"),
                           Path.home() / "Applications/Dolphin.app"])
    return app / "Contents/MacOS/Dolphin" if app else None


SHADERS_DIR = paths.ENGINES / "shaders"


def shaders_installed():
    return (SHADERS_DIR / "shaders_slang").exists() or (SHADERS_DIR / "shaders_glsl").exists()


def install_shaders(progress=None):
    """Effets d'écran (LCD, télé cathodique, lissage) de la bibliothèque libre libretro."""
    SHADERS_DIR.mkdir(parents=True, exist_ok=True)
    for i, pack in enumerate(("shaders_slang", "shaders_glsl")):
        with tempfile.TemporaryDirectory() as td:
            z = fetch_first([f"{BUILDBOT}/assets/frontend/{pack}.zip"], Path(td) / "s.zip",
                            (lambda f, i=i: progress((i + f) / 2)) if progress else None)
            with zipfile.ZipFile(z) as zf:
                zf.extractall(SHADERS_DIR / pack)


def status():
    return {
        "shaders": shaders_installed(),
        "retroarch": retroarch_exe() is not None,
        "cores": {c: core_path(c).exists() for c in RETROARCH_CORES},
        "dolphin": dolphin_exe() is not None,
    }


def everything_installed():
    s = status()
    return s["retroarch"] and s["dolphin"] and s["shaders"] and all(s["cores"].values())


# ------------------------------------------------------------------ téléchargement
def fetch(url, dest: Path = None, progress=None, timeout=60):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        if dest is None:
            return r.read()
        total = int(r.headers.get("Content-Length") or 0)
        done = 0
        tmp = dest.with_name(dest.name + ".part")
        with open(tmp, "wb") as f:
            while True:
                chunk = r.read(1 << 16)
                if not chunk:
                    break
                f.write(chunk)
                done += len(chunk)
                if progress and total:
                    progress(done / total)
        tmp.replace(dest)
    return dest


def fetch_first(urls, dest, progress=None):
    last = None
    for u in urls:
        try:
            return fetch(u, dest, progress, timeout=120)
        except Exception as e:  # 404, réseau…
            last = e
    raise EngineError(f"Téléchargement impossible ({last})")


def _run(cmd):
    r = subprocess.run(cmd, capture_output=True, text=True, creationflags=NO_WINDOW)
    if r.returncode != 0:
        raise EngineError((r.stderr or r.stdout or "erreur").strip()[:300])


def _extract_7z(archive: Path, dest: Path):
    if not SEVENZIP.exists():
        fetch("https://www.7-zip.org/a/7zr.exe", SEVENZIP)
    dest.mkdir(parents=True, exist_ok=True)
    _run([str(SEVENZIP), "x", str(archive), f"-o{dest}", "-y"])


def _find(root: Path, name: str):
    for p in root.rglob(name):
        return p
    return None


def _copy_app_from_dmg(dmg: Path, app_name: str, dest_app: Path):
    mnt = Path(tempfile.mkdtemp(prefix="rs_dmg_"))
    _run(["hdiutil", "attach", "-nobrowse", "-readonly", "-mountpoint", str(mnt), str(dmg)])
    try:
        app = next((p for p in mnt.glob("*.app") if app_name.lower() in p.name.lower()), None)
        if not app:
            raise EngineError(f"{app_name}.app introuvable dans l'image disque")
        if dest_app.exists():
            shutil.rmtree(dest_app)
        _run(["ditto", str(app), str(dest_app)])
    finally:
        subprocess.run(["hdiutil", "detach", str(mnt), "-force"], capture_output=True)
    subprocess.run(["xattr", "-dr", "com.apple.quarantine", str(dest_app)], capture_output=True)


def latest_retroarch_version():
    try:
        html = fetch(BUILDBOT + "/stable/", timeout=30).decode("utf-8", "ignore")
        vers = set(re.findall(r"(\d+\.\d+\.\d+)/", html))
        return max(vers, key=lambda v: tuple(map(int, v.split(".")))) if vers else None
    except Exception:
        return None


# ------------------------------------------------------------------ installation
def install_retroarch(progress=None):
    v = latest_retroarch_version()
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        if paths.IS_WINDOWS:
            urls = ([f"{BUILDBOT}/stable/{v}/windows/x86_64/RetroArch.7z"] if v else []) + \
                   [f"{BUILDBOT}/nightly/windows/x86_64/RetroArch.7z"]
            arc = fetch_first(urls, td / "RetroArch.7z", progress)
            _extract_7z(arc, td / "x")
            exe = _find(td / "x", "retroarch.exe")
            if not exe:
                raise EngineError("retroarch.exe introuvable dans l'archive")
            shutil.copytree(exe.parent, RA_DIR, dirs_exist_ok=True)
        else:
            urls = []
            for base in ([f"{BUILDBOT}/stable/{v}"] if v else []) + [f"{BUILDBOT}/nightly"]:
                urls += [f"{base}/apple/osx/universal/RetroArch_Metal.dmg",
                         f"{base}/apple/osx/universal/RetroArch.dmg"]
            dmg = fetch_first(urls, td / "RetroArch.dmg", progress)
            _copy_app_from_dmg(dmg, "RetroArch", paths.ENGINES / "RetroArch.app")


def install_core(core: str, progress=None):
    CORES_DIR.mkdir(parents=True, exist_ok=True)
    if paths.IS_WINDOWS:
        url = f"{BUILDBOT}/nightly/windows/x86_64/latest/{core}_libretro.dll.zip"
    else:
        url = f"{BUILDBOT}/nightly/apple/osx/{paths.mac_arch()}/latest/{core}_libretro.dylib.zip"
    with tempfile.TemporaryDirectory() as td:
        z = fetch_first([url], Path(td) / "core.zip", progress)
        with zipfile.ZipFile(z) as zf:
            zf.extractall(CORES_DIR)


def install_dolphin(progress=None):
    html = fetch(DOLPHIN_PAGE, timeout=30).decode("utf-8", "ignore")
    suffix = r"-x64\.7z" if paths.IS_WINDOWS else r"-universal\.dmg"
    links = re.findall(r"https://dl\.dolphin-emu\.org/(?:releases|builds)/[^\"'\s<>]+?" + suffix, html)
    if not links:
        raise EngineError("lien de téléchargement Dolphin introuvable")
    links.sort(key=lambda u: "/releases/" not in u)  # versions stables d'abord
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        if paths.IS_WINDOWS:
            arc = fetch_first(links[:2], td / "dolphin.7z", progress)
            _extract_7z(arc, td / "x")
            exe = _find(td / "x", "Dolphin.exe")
            if not exe:
                raise EngineError("Dolphin.exe introuvable dans l'archive")
            shutil.copytree(exe.parent, DOLPHIN_DIR, dirs_exist_ok=True)
        else:
            dmg = fetch_first(links[:2], td / "dolphin.dmg", progress)
            _copy_app_from_dmg(dmg, "Dolphin", paths.ENGINES / "Dolphin.app")


def install_all(report=None, force=False):
    """Installe ce qui manque. report(texte, fraction_globale). Retourne la liste des erreurs."""
    paths.ensure_dirs()
    s = status()
    steps = []
    if force or not s["retroarch"]:
        steps.append(("RetroArch (moteur principal)", install_retroarch))
    for core, ok in s["cores"].items():
        if force or not ok:
            steps.append((f"Cœur {core}", lambda p, c=core: install_core(c, p)))
    if force or not s["dolphin"]:
        steps.append(("Dolphin (GameCube / Wii)", install_dolphin))
    if force or not s["shaders"]:
        steps.append(("Effets d'écran", install_shaders))
    errors = []
    n = max(len(steps), 1)
    for i, (label, fn) in enumerate(steps):
        if report:
            report(label, i / n)
        try:
            fn(lambda f, i=i, label=label: report and report(label, (i + f) / n))
        except Exception as e:
            errors.append(f"{label} : {e}")
    if report:
        report("Terminé", 1.0)
    return errors
