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


FAILED = paths.ENGINES / "arcade-echecs.json"
_failed = None


def _failed_db():
    global _failed
    if _failed is None:
        try:
            _failed = json.loads(FAILED.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            _failed = {}
    return _failed


def mark_failed(game, core):
    """L'émulateur a refusé ce jeu (les listes peuvent dater d'une version plus ancienne) : on retient."""
    db = _failed_db()
    lst = db.setdefault(game.path.name.lower(), [])
    if core not in lst:
        lst.append(core)
    try:
        FAILED.write_text(json.dumps(db), encoding="utf-8")
    except OSError:
        pass


def failed_cores(game):
    return set(_failed_db().get(game.path.name.lower(), []))


class Incomplete(Exception):
    def __init__(self, best_core, missing, needs_zip):
        super().__init__("jeu d'arcade incomplet")
        self.best_core, self.missing, self.needs_zip = best_core, missing, needs_zip


def choose(game):
    """Renvoie (cœur, [zips utiles]) pour un jeu d'arcade, ou lève Incomplete."""
    order = ORDER.get(game.console, ())
    best = None
    known_anywhere = False
    ko = failed_cores(game)
    for core in order:
        if core in ko:
            continue
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


# ------------------------------------------------------------------ vérification et réparation de toute la collection
QUARANTINE = paths.ROOT / "Jeux" / "_Arcade incomplets (non jouables)"


def ensure_lists():
    """Télécharge les listes manquantes (FinalBurn Neo, MAME, MAME 2003-Plus)."""
    from . import arcadedb, mamedb
    if not ready("fbneo"):
        arcadedb.download()
    if not ready("mame"):
        mamedb.download()
    if not ready("mame2003_plus"):
        download_mame2003()
    return [c for c in CRC_FILES if ready(c)]


def _index(zips, progress=None):
    """Empreinte CRC -> (zip, nom de la puce), pour retrouver une puce rangée dans un autre .zip."""
    idx = {}
    for i, z in enumerate(zips):
        try:
            with zipfile.ZipFile(z) as zf:
                for info in zf.infolist():
                    if not info.is_dir() and info.CRC not in idx:
                        idx[info.CRC] = (z, info.filename)
        except (zipfile.BadZipFile, OSError):
            pass
        if progress and i % 300 == 0:
            progress(i / max(len(zips), 1))
    return idx


def _rebuild(game_path: Path, add):
    """Ajoute au .zip du jeu les puces trouvées ailleurs (add = [(nom_attendu, zip_source, nom_source)])."""
    tmp = game_path.with_suffix(".reparation.tmp")
    names = {n.lower() for n, _z, _s in add}
    with zipfile.ZipFile(game_path) as src, zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as out:
        for info in src.infolist():
            if info.filename.lower() not in names:      # une puce du même nom mais d'une autre version
                out.writestr(info, src.read(info.filename))
        for name, z, inner in add:
            with zipfile.ZipFile(z) as other:
                out.writestr(name, other.read(inner))
    os.replace(tmp, game_path)


def repair_all(games, progress=None):
    """Vérifie tous les jeux d'arcade ; complète ceux dont les puces manquantes existent dans un autre
    .zip de la collection. Renvoie (réparés [jeux], incomplets [(jeu, raison)], inconnus [jeux])."""
    arc = [g for g in games if g.console in ARCADE_CONSOLES]
    zips = list(dict.fromkeys([g.path for g in arc] +
                              [z for f in folders() if f.exists() for z in f.glob("*.zip")]))
    idx = _index(zips, (lambda f: progress(f * 0.4)) if progress else None)
    fixed, bad, unknown, needed_by_ok = [], [], [], set()
    pending = []
    for i, g in enumerate(arc):
        if progress and i % 200 == 0:
            progress(0.4 + 0.55 * i / max(len(arc), 1))
        try:
            _core, used = choose(g)
            needed_by_ok.update(str(u) for u in used)
            continue
        except Incomplete as e:
            err = e
        except Exception:
            continue
        if not any(check(c, g.path) is not None for c in CRC_FILES):
            unknown.append(g)
            continue
        # puces manquantes présentes ailleurs ? (réparation pour la version la plus proche)
        db = load(err.best_core) or {}
        entry = db.get(g.path.stem.lower(), {"r": []})
        have = set()
        for n in chain(db, g.path.stem.lower()):
            z = g.path if n == g.path.stem.lower() else find_zip(n, g.path.parent)
            if z:
                have |= zip_crcs(z)
        add, ok = [], True
        for crc, nm in entry["r"]:
            if crc in have:
                continue
            src = idx.get(crc)
            if not src:
                ok = False
                break
            add.append((nm, src[0], src[1]))
        if ok and add:
            try:
                _rebuild(g.path, add)
                _core, used = choose(g)
                fixed.append(g)
                needed_by_ok.update(str(u) for u in used)
                continue
            except Exception:
                pass
        why = f"{len(err.missing)} puce(s) manquante(s)"
        if err.needs_zip:
            why += ", il manque " + ", ".join(err.needs_zip)
        pending.append((g, why))
    # un jeu incomplet qui sert de « jeu principal » à un jeu qui marche reste à sa place
    bad = [(g, why) for g, why in pending if str(g.path) not in needed_by_ok]
    if progress:
        progress(1.0)
    return fixed, bad, unknown


def set_aside(game):
    """Range un jeu d'arcade non jouable à part (récupérable), hors de la bibliothèque."""
    import shutil
    dest = QUARANTINE / game.path.parent.name / game.path.name
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists():
        dest.unlink()
    shutil.move(str(game.path), str(dest))
    return dest
