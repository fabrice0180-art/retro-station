"""Jeux d'arcade : vérifie qu'un .zip contient bien toutes les puces attendues, et choisit
l'émulateur qui correspond à sa version (FinalBurn Neo, MAME récent ou MAME 2003-Plus).

Chaque émulateur attend les jeux dans SA version : un même « f1dream.zip » peut être complet
pour MAME 2003-Plus et incomplet pour FinalBurn Neo. Les listes officielles (avec l'empreinte
CRC de chaque puce) sont téléchargées une fois, puis réduites et gardées dans Moteurs/.
"""
import html
import json
import os
import re
import threading
import zipfile
from pathlib import Path

from . import paths, engines

CRC_FILES = {
    "fbneo": paths.ENGINES / "crc-fbneo.json",
    "mame": paths.ENGINES / "crc-mame.json",
    "mame2003_plus": paths.ENGINES / "crc-mame2003.json",
}
MAME2003_DAT = ("https://raw.githubusercontent.com/libretro/mame2003-plus-libretro/master/"
                "metadata/mame2003-plus.xml")
CORE_NAMES = {"fbneo": "FinalBurn Neo", "mame": "MAME (version récente)", "mame2003_plus": "MAME 2003-Plus"}
ORDER = {"arcade": ("fbneo", "mame", "mame2003_plus"),
         "neogeo": ("fbneo", "mame", "mame2003_plus"),
         "mame": ("mame", "fbneo", "mame2003_plus")}
ARCADE_CONSOLES = tuple(ORDER)

_dbs = {}
_lock = threading.Lock()
_zip_cache = {}

# ------------------------------------------------------------------ lecture des listes
_START = re.compile(rb'<(game|machine)\s+name="([^"]+)"([^>]*)>')
_ROM = re.compile(rb'<rom\s+([^>]*?)/?>')
_ATTR = re.compile(rb'(\w+)="([^"]*)"')
_CMP_BLOCK = re.compile(rb'(?:^|\n)\s*(?:game|machine|resource)\s*\(\s*\n', re.I)
_CMP_ROM = re.compile(rb'rom\s*\(\s*(.*?)\s*\)\s*$', re.M)


def parse_crcs(data: bytes) -> dict:
    """{jeu: {"o": jeu_parent_ou_bios, "r": [[crc, nom], …]}} depuis une liste XML ou ClrMamePro."""
    db = {}
    starts = list(_START.finditer(data))
    if starts:
        for i, m in enumerate(starts):
            end = starts[i + 1].start() if i + 1 < len(starts) else len(data)
            attrs = dict(_ATTR.findall(m.group(3)))
            roms = []
            for r in _ROM.finditer(data, m.end(), end):
                a = dict(_ATTR.findall(r.group(1)))
                if a.get(b"status") == b"nodump" or b"crc" not in a:
                    continue
                try:
                    roms.append([int(a[b"crc"], 16), html.unescape(a.get(b"name", b"").decode("utf-8", "replace"))])
                except ValueError:
                    pass
            db[m.group(2).decode("utf-8", "replace").lower()] = {
                "o": (attrs.get(b"romof") or b"").decode().lower(), "r": roms}
        return db
    for blk in _CMP_BLOCK.split(data)[1:]:
        n = re.search(rb'^\s*name\s+"?([^"\n]+?)"?\s*$', blk, re.M)
        if not n:
            continue
        o = re.search(rb'^\s*romof\s+"?([^"\n]+?)"?\s*$', blk, re.M)
        roms = []
        for r in _CMP_ROM.finditer(blk):
            body = r.group(1)
            c = re.search(rb'crc\s+([0-9a-fA-F]{8})', body)
            nm = re.search(rb'name\s+"?([^"\s]+)"?', body)
            if c and b"nodump" not in body:
                roms.append([int(c.group(1), 16), nm.group(1).decode("utf-8", "replace") if nm else "?"])
        db[n.group(1).decode("utf-8", "replace").lower()] = {
            "o": o.group(1).decode().lower() if o else "", "r": roms}
    return db


def save(core: str, db: dict):
    f = CRC_FILES[core]
    f.parent.mkdir(parents=True, exist_ok=True)
    tmp = f.with_suffix(".tmp")
    tmp.write_text(json.dumps(db, separators=(",", ":")), encoding="utf-8")
    os.replace(tmp, f)
    _dbs[core] = db


def load(core: str):
    if core in _dbs:
        return _dbs[core]
    f = CRC_FILES[core]
    db = None
    if f.exists():
        try:
            db = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            db = None
    _dbs[core] = db
    return db


def ready(core: str) -> bool:
    return CRC_FILES[core].exists()


def download_mame2003() -> bool:
    with _lock:
        if ready("mame2003_plus"):
            return True
        try:
            data = engines.fetch(MAME2003_DAT, timeout=300)
        except Exception:
            return False
        db = parse_crcs(data)
        if len(db) < 1000:
            return False
        save("mame2003_plus", db)
        return True


# ------------------------------------------------------------------ vérification
def folders():
    from .library import console_dir
    return [console_dir(c) for c in ("mame", "arcade", "neogeo")] + [paths.BIOS]


def zip_crcs(path: Path) -> set:
    try:
        st = path.stat()
    except OSError:
        return set()
    key = (str(path), st.st_mtime, st.st_size)
    if key not in _zip_cache:
        try:
            with zipfile.ZipFile(path) as z:
                _zip_cache[key] = {i.CRC for i in z.infolist() if not i.is_dir()}
        except (zipfile.BadZipFile, OSError):
            _zip_cache[key] = set()
    return _zip_cache[key]


def find_zip(name: str, near: Path = None):
    for d in ([near] if near else []) + folders():
        f = d / f"{name}.zip"
        if f.exists():
            return f
    return None


def chain(db: dict, name: str):
    """Le jeu, puis son jeu parent, puis le BIOS de sa carte (ex. sf2ua -> sf2 ; mslug -> neogeo)."""
    out, seen = [], set()
    while name and name not in seen and len(out) < 6:
        seen.add(name)
        out.append(name)
        name = (db.get(name) or {}).get("o", "")
    return out


def check(core: str, game_path: Path):
    """None si l'émulateur ne connaît pas ce jeu, sinon (manquants [noms], zips_utiles [chemins])."""
    db = load(core)
    if not db:
        return None
    name = game_path.stem.lower()
    entry = db.get(name)
    if not entry:
        return None
    have, used = set(), []
    for n in chain(db, name):
        z = game_path if n == name else find_zip(n, game_path.parent)
        if z:
            have |= zip_crcs(z)
            used.append(z)
    missing = [nm for crc, nm in entry["r"] if crc not in have]
    return missing, used


class Incomplete(Exception):
    def __init__(self, best_core, missing, needs_zip):
        super().__init__("jeu d'arcade incomplet")
        self.best_core, self.missing, self.needs_zip = best_core, missing, needs_zip


def choose(game):
    """Renvoie (cœur, [zips utiles]) pour un jeu d'arcade, ou lève Incomplete."""
    order = ORDER.get(game.console, ())
    best = None
    known_anywhere = False
    for core in order:
        res = check(core, game.path)
        if res is None:
            continue
        known_anywhere = True
        missing, used = res
        if not missing:
            return core, used
        if best is None or len(missing) < len(best[1]):
            best = (core, missing, used)
    if not known_anywhere:
        return (order[0] if order else None), [game.path]
    core, missing, _used = best
    db = load(core) or {}
    names = chain(db, game.path.stem.lower())[1:]
    absent = [n + ".zip" for n in names if not find_zip(n, game.path.parent)]
    raise Incomplete(core, missing, absent)


def launch_folder(game, used):
    """Dossier de lancement : le jeu + son parent + ses BIOS + les BIOS MAME, réunis par des liens
    (aucune copie) pour que l'émulateur trouve tout au même endroit."""
    from .detect import mame_support
    d = paths.ENGINES / "arcade-lancement"
    d.mkdir(parents=True, exist_ok=True)
    want = {Path(p).name.lower(): Path(p) for p in used}
    for folder in folders():
        if not folder.exists():
            continue
        for f in folder.glob("*.zip"):
            if f.name.lower() == "neogeo.zip" or mame_support(f.stem):
                want.setdefault(f.name.lower(), f)
    for src in want.values():
        dst = d / src.name
        try:
            if dst.exists():
                if os.path.samefile(dst, src) or (dst.stat().st_size == src.stat().st_size
                                                  and dst.stat().st_mtime >= src.stat().st_mtime):
                    continue
                dst.unlink()
            try:
                os.link(src, dst)
            except OSError:
                import shutil
                shutil.copy2(src, dst)
        except OSError:
            pass
    return d / game.path.name
