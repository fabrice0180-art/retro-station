"""Bibliothèque de jeux : rangement par console, import en bloc, favoris."""
import json
import re
import shutil
import time
from dataclasses import dataclass, field
from pathlib import Path

from . import paths, arcadedb
from .consoles import CONSOLES, BY_ID

FLOPPY = {"amiga", "atarist"}   # jeux en plusieurs disquettes : un seul exemplaire affiché (disquette 1)
DISK_TAG = re.compile(r"\s*\((?:disk|disc|disquette)\s*(\d+)(?:\s*of\s*\d+)?\)", re.I)


def disk_number(name: str) -> int:
    m = DISK_TAG.search(name)
    return int(m.group(1)) if m else 0


ARCADE = {"arcade", "neogeo"}   # jeux nommés par un nom court (sf2.zip) : vrai titre via la liste FinalBurn Neo
from .detect import mame_support, strip_dup
from .detect import detect, companions, cue_files, gdi_files, m3u_files, clean_title, region_of


@dataclass
class Game:
    console: str
    path: Path
    title: str
    region: str
    key: str


def console_dir(cid: str) -> Path:
    return paths.GAMES / BY_ID[cid].name


# ------------------------------------------------------------------ lecture
class Library:
    def __init__(self):
        paths.ensure_dirs()
        for c in CONSOLES:
            console_dir(c.id).mkdir(parents=True, exist_ok=True)
        self.meta = self._load()
        self.games: list[Game] = []

    def _load(self):
        try:
            return json.loads(paths.LIBRARY_FILE.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}

    def save(self):
        tmp = paths.LIBRARY_FILE.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.meta, ensure_ascii=False, indent=1), encoding="utf-8")
        tmp.replace(paths.LIBRARY_FILE)

    def scan(self):
        """Liste les jeux, console par console (parcours rapide du disque)."""
        import os
        games = []
        for c in CONSOLES:
            d = console_dir(c.id)
            if not d.exists():
                continue
            exts = c.shown_exts
            files = []                       # (chemin relatif posix, chemin complet)
            stack = [(str(d), "")]
            while stack:
                folder, rel = stack.pop()
                try:
                    with os.scandir(folder) as it:
                        for e in it:
                            if e.name.startswith("."):
                                continue
                            if e.is_dir(follow_symlinks=False):
                                stack.append((e.path, rel + e.name + "/"))
                            elif os.path.splitext(e.name)[1].lower() in exts:
                                files.append((rel + e.name, e.path))
                except OSError:
                    continue
            hidden = set()
            for relp, full in files:
                if relp.lower().endswith(".m3u"):
                    hidden.update(os.path.normcase(str(x)) for x in m3u_files(Path(full)))
            for relp, full in files:
                name = relp.rsplit("/", 1)[-1]
                if c.id in FLOPPY and disk_number(name) > 1:
                    continue        # disquettes 2, 3… : chargées avec la disquette 1
                if c.id in ("mame", "arcade") and mame_support(os.path.splitext(name)[0]):
                    continue        # BIOS de MAME (model1io.zip…) : pas un jeu
                if name.lower() == "neogeo.zip" or name.startswith("[BIOS]") or (
                        hidden and os.path.normcase(full) in hidden):
                    continue
                key = f"{c.id}/{relp}"
                m = self.meta.get(key)
                stem = os.path.splitext(name)[0]
                title = (m or {}).get("title")
                region = region_of(stem)
                if not title and (c.id in ARCADE or c.id == "mame"):
                    long_name = arcade_title(c.id, stem)
                    if long_name:
                        title, region = clean_title(long_name), region_of(long_name)
                games.append(Game(c.id, Path(full), title or clean_title(stem), region, key))
        games.sort(key=lambda g: g.title.lower())
        self.games = games
        return games

    # méta-données
    def m(self, game: Game) -> dict:
        return self.meta.setdefault(game.key, {})

    def toggle_favorite(self, game: Game):
        m = self.m(game)
        m["fav"] = not m.get("fav", False)
        self.save()

    def record_play(self, game: Game, seconds: float):
        m = self.m(game)
        m["last"] = time.time()
        m["time"] = m.get("time", 0) + int(seconds)
        self.save()

    def remove(self, game: Game, delete_file: bool):
        if delete_file:
            for f in [game.path] + companions(game.path):
                try:
                    f.unlink()
                except OSError:
                    pass
        self.meta.pop(game.key, None)
        self.save()

    def counts(self):
        out = {c.id: 0 for c in CONSOLES}
        for g in self.games:
            out[g.console] += 1
        return out


# ------------------------------------------------------------------ import
@dataclass
class ImportPlan:
    games: list = field(default_factory=list)      # (source, console)
    bios: list = field(default_factory=list)       # (source, cible relative)
    unknown: dict = field(default_factory=dict)    # extension -> {"files": [...], "candidates": (...)}
    skipped: int = 0
    rebuilt: list = field(default_factory=list)          # jeux d'arcade décompressés remis en .zip
    unnamed_arcade: list = field(default_factory=list)   # dossiers de puces dont le nom du jeu est inconnu


def expand(selection):
    for p in map(Path, selection):
        if p.is_dir():
            yield from (x for x in sorted(p.rglob("*")) if x.is_file())
        elif p.is_file():
            yield p


# ------------------------------------------------------------------ jeux d'arcade décompressés
# Un jeu d'arcade (MAME, FinalBurn Neo) est un .zip qui contient les puces de la borne
# (epr-14869.25, mpr-16491.32…). S'il a été décompressé, on refait le .zip tout seul.
STAGING = paths.ENGINES / "import-arcade"
_GENERIC_DIRS = {"roms", "rom", "mame", "arcade", "jeux", "games", "game", "downloads", "download",
                 "téléchargements", "telechargements", "bureau", "desktop", "documents", "nouveau dossier",
                 "new folder", "fbneo", "fba", "retrostation"}
_SET_NAME = re.compile(r"^[a-z0-9_]{2,20}$")


def _known_exts():
    from .consoles import CONSOLES as _C
    ex = set()
    for c in _C:
        ex.update(c.exts)
    return ex - {".bin", ".rom"}


def _chip_dir(d: Path):
    """Fichiers de puces d'une borne présents directement dans d (ou None)."""
    try:
        files = [f for f in d.iterdir() if f.is_file() and not f.name.startswith(".")]
    except OSError:
        return None
    if len(files) < 2:
        return None
    known = _known_exts()
    chips, odd = [], 0
    for f in files:
        try:
            n = f.stat().st_size
        except OSError:
            return None
        ext = f.suffix.lower()
        if ext in known or n > 256 << 20:
            return None                      # un vrai jeu (ou une archive) : ce n'est pas un jeu décompressé
        if n >= 256 and n & (n - 1) == 0:    # les puces ont une taille en puissance de 2
            chips.append(f)
        if ext not in (".bin", ".rom"):
            odd += 1                         # .25, .ic12, .u1… : extensions typiques des puces
    if len(chips) < 0.7 * len(files) or odd * 2 < len(files):
        return None
    return files


def _common_prefix(names):
    pre = names[0]
    for n in names[1:]:
        while not n.startswith(pre):
            pre = pre[:-1]
    return pre


def find_loose_arcade(selection):
    """Repère les jeux d'arcade décompressés. Renvoie (jeux, fichiers_concernés, non_nommés) ;
    jeux = [(nom_du_set, [fichiers], dossier)]."""
    dirs = []
    for p in map(Path, selection):
        if p.is_dir():
            dirs.append(p)
            dirs.extend(x for x in sorted(p.rglob("*")) if x.is_dir())
    chip = {d: f for d in dirs if (f := _chip_dir(d))}
    sets, used, unnamed = [], set(), []
    for d, files in chip.items():
        kids = [k for k in chip if k.parent == d]
        own = d.name.lower()
        name = None
        if kids:                              # jeu « fusionné » : le jeu principal + ses variantes en sous-dossiers
            pre = _common_prefix([k.name.lower() for k in kids])
            if _SET_NAME.match(own) and own not in _GENERIC_DIRS and all(k.name.lower().startswith(own) for k in kids):
                name = own
            elif len(pre) >= 3 and _SET_NAME.match(pre):
                name = pre
        if not name and d.parent in chip:     # variante : son nom de dossier est le nom du jeu
            name = own if _SET_NAME.match(own) else None
        if not name and _SET_NAME.match(own) and own not in _GENERIC_DIRS:
            name = own
        if not name:
            unnamed.append(d)
            continue
        sets.append((name, files, d))
        used.update(f.resolve() for f in files)
    return sets, used, unnamed


def build_arcade_zip(name: str, files) -> Path:
    import zipfile
    STAGING.mkdir(parents=True, exist_ok=True)
    out = STAGING / f"{name}.zip"
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        for f in sorted(files, key=lambda x: x.name.lower()):
            z.write(f, f.name.lower())
    return out


def relocate_misfiled():
    """Range à la bonne place les .zip mis par erreur avec les bornes d'arcade (ex. des disquettes
    Amiga .ipf rangées dans « Arcade (MAME) »). Renvoie [(nom, console)]."""
    from .detect import sniff_zip_contents
    moved = []
    for cid in ("mame", "arcade"):
        d = console_dir(cid)
        if not d.exists():
            continue
        for f in list(d.iterdir()):
            if f.suffix.lower() != ".zip" or not f.is_file():
                continue
            clean = strip_dup(f.stem) + f.suffix
            if clean != f.name and not (d / clean).exists():
                try:                           # « model1io (1).zip » -> « model1io.zip »
                    f = f.rename(d / clean)
                    moved.append((clean, cid))
                except OSError:
                    pass
            if _SET_NAME.match(f.stem):        # nom court de borne (sf2, daytona…) : rien à vérifier
                continue
            c, _cands = sniff_zip_contents(f)
            if not c or c in ("mame", "arcade", "neogeo"):
                continue
            dest = console_dir(c) / f.name
            try:
                dest.parent.mkdir(parents=True, exist_ok=True)
                if dest.exists() and dest.stat().st_size == f.stat().st_size:
                    f.unlink()                 # déjà présent au bon endroit : copie en trop
                elif not dest.exists():
                    shutil.move(str(f), str(dest))
                else:
                    continue
                moved.append((f.name, c))
            except OSError:
                pass
    return moved


def plan_import(selection) -> ImportPlan:
    shutil.rmtree(STAGING, ignore_errors=True)
    loose, used, unnamed = find_loose_arcade(selection)
    files = [f for f in expand(selection) if f.resolve() not in used]
    # pistes déjà référencées par un .cue / .gdi / .m3u : elles suivront leur fichier principal
    referenced = set()
    for f in files:
        e = f.suffix.lower()
        if e == ".cue":
            referenced.update(x.resolve() for x in cue_files(f))
        elif e == ".gdi":
            referenced.update(x.resolve() for x in gdi_files(f))
        elif e == ".m3u":
            referenced.update(x.resolve() for x in m3u_files(f))
            for sub in m3u_files(f):
                referenced.update(x.resolve() for x in companions(sub))
    plan = ImportPlan()
    for name, chips, _d in loose:
        try:
            z = build_arcade_zip(name, chips)
        except OSError:
            plan.skipped += len(chips)
            continue
        plan.games.append((z, arcadedb.console_of(name) or "mame"))
        plan.rebuilt.append(name)
    plan.unnamed_arcade = [str(d) for d in unnamed]
    for f in files:
        if f.resolve() in referenced:
            continue
        d = detect(f)
        if d.kind == "game":
            plan.games.append((f, d.console))
        elif d.kind == "bios":
            plan.bios.append((f, d.bios_target))
        elif d.kind == "unknown" and d.candidates:
            grp = plan.unknown.setdefault(f.suffix.lower(), {"files": [], "candidates": d.candidates})
            grp["files"].append(f)
            grp["candidates"] = tuple(dict.fromkeys(grp["candidates"] + d.candidates))
        else:
            plan.skipped += 1
    return plan


def _transfer(src: Path, dst: Path, move: bool):
    dst.parent.mkdir(parents=True, exist_ok=True)
    if dst.exists() and dst.stat().st_size == src.stat().st_size:
        return False
    if move:
        shutil.move(str(src), str(dst))
    else:
        shutil.copy2(src, dst)
    return True


def execute_import(plan: ImportPlan, move=False, progress=None):
    """Copie (ou déplace) les fichiers. progress(i, total, nom)."""
    jobs = []
    for src, cid in plan.games:
        dest_dir = console_dir(cid)
        name = src.name
        if cid in ("mame", "arcade", "neogeo"):     # « sf2 (1).zip » -> « sf2.zip » (nom exact exigé)
            name = strip_dup(src.stem) + src.suffix
        jobs.append((src, dest_dir / name, True))
        for extra in companions(src):
            try:
                rel = extra.relative_to(src.parent)
            except ValueError:
                rel = Path(extra.name)
            jobs.append((extra, dest_dir / rel, False))
    for src, target in plan.bios:
        if target.startswith("kickzip:"):
            install_kickstart(src, target[8:])
            continue
        if target.startswith("mame:"):         # BIOS de MAME : à côté des jeux, sous son nom exact
            jobs.append((src, console_dir("mame") / target[5:], False))
            continue
        jobs.append((src, paths.BIOS / target, False))
        if target == "neogeo.zip":
            jobs.append((src, console_dir("neogeo") / "neogeo.zip", False))
    added = 0
    errors = []
    seen = set()
    for i, (src, dst, primary) in enumerate(jobs):
        if (src, dst) in seen:
            continue
        seen.add((src, dst))
        if progress:
            progress(i, len(jobs), src.name)
        try:
            # neogeo.zip copié deux fois : jamais déplacé avant la 2e copie
            mv = move and not (src.name.lower() == "neogeo.zip")
            if _transfer(src, dst, mv) and primary:
                added += 1
        except OSError as e:
            errors.append(f"{src.name} : {e}")
    if progress:
        progress(len(jobs), len(jobs), "")
    shutil.rmtree(STAGING, ignore_errors=True)
    return added, errors


# ------------------------------------------------------------------ ménage : doublons et ROMs douteuses
import re as _re
import zlib as _zlib
from functools import lru_cache as _lru

REGION_RANK = {"france": 0, "europe": 1, "world": 2, "monde": 2, "usa": 3, "japan": 4}
BAD_TAGS = [
    (r"\[b\d*\]", "copie abîmée [b]"),
    (r"\[o\d*\]", "copie trop grande [o]"),
    (r"\[h[^\]]*\]", "jeu modifié (hack)"),
    (r"\[t\d*\]", "version avec triche [t]"),
    (r"\[p\d*\]", "version pirate [p]"),
    (r"\(beta[^)]*\)", "version bêta"),
    (r"\(proto[^)]*\)", "prototype"),
    (r"\(demo[^)]*\)|\(sample\)", "démo"),
    (r"\(hack\)|\(pirate\)", "jeu modifié"),
]


@_lru(maxsize=None)
def _norm_title(stem):
    t = clean_title(stem).lower()
    t = _re.sub(r"^the\s+|,\s*the$", "", t)
    disc = _re.search(r"\((?:dis[ck]|cd)\s*(\d+)", stem.lower())   # disques 1, 2… = jeux distincts
    return _re.sub(r"[^a-z0-9]+", "", t) + (f"#d{disc.group(1)}" if disc else "")


def arcade_title(cid: str, stem: str):
    """Nom complet d'un jeu d'arcade d'après son nom court (sf2, daytona…), ou None."""
    if cid == "mame":
        from . import mamedb
        return mamedb.title(stem) or arcadedb.title(stem)
    if cid in ARCADE:
        return arcadedb.title(stem)
    return None


def _name_of(game):
    return arcade_title(game.console, game.path.stem) or game.path.stem


def _preference(game):
    return _pref_stem(_name_of(game))


@_lru(maxsize=None)
def _pref_stem(stem):
    """Plus petit = meilleure version à garder."""
    low = stem.lower()
    bad = any(_re.search(p, low) for p, _ in BAD_TAGS)
    region = min((REGION_RANK[w] for w in _re.findall(r"[a-z]+", " ".join(_re.findall(r"\(([^)]*)\)", low)))
                  if w in REGION_RANK), default=5)
    rev = _re.search(r"\(rev\s*([0-9a-z]+)\)|\(v\s*([0-9.]+)\)", low)
    rev_val = -(int(_re.sub(r"\D", "", (rev.group(1) or rev.group(2) or "0")) or 0)) if rev else 0
    return (bad, region, rev_val, len(low))


def _crc(path, limit=None):
    c = 0
    with open(path, "rb") as f:
        while True:
            b = f.read(1 << 20)
            if not b:
                break
            c = _zlib.crc32(b, c)
    return c


def bad_reason(game):
    low = game.path.stem.lower()
    for pat, why in BAD_TAGS:
        if _re.search(pat, low):
            return why
    try:
        size = game.path.stat().st_size
    except OSError:
        return "fichier introuvable"
    if size < 1024:
        return "fichier vide ou presque"
    if game.path.suffix.lower() == ".zip":
        import zipfile
        try:
            with zipfile.ZipFile(game.path) as z:
                if z.testzip() is not None:
                    return "archive .zip abîmée"
        except Exception:
            return "archive .zip illisible"
    return ""


def analyze(games, progress=None):
    """Repère les copies identiques, les versions multiples d'un même jeu et les ROMs douteuses.
    Renvoie une liste de groupes : {"kind", "title", "console", "items": [(jeu, raison, à_retirer)]}."""
    groups = []
    flagged = set()
    by_console = {}
    for g in games:
        by_console.setdefault(g.console, []).append(g)
    done, total = 0, max(len(games), 1)
    for cid, gs in by_console.items():
        # 1) copies identiques (même taille, puis même empreinte)
        by_size = {}
        for g in gs:
            try:
                by_size.setdefault(g.path.stat().st_size, []).append(g)
            except OSError:
                pass
        for same in by_size.values():
            if len(same) < 2:
                continue
            by_crc = {}
            for g in same:
                try:
                    by_crc.setdefault(_crc(g.path), []).append(g)
                except OSError:
                    pass
            for dup in by_crc.values():
                if len(dup) > 1:
                    dup.sort(key=_preference)
                    items = [(dup[0], "à garder", False)] + [(g, "copie identique", True) for g in dup[1:]]
                    groups.append({"kind": "identique", "title": dup[0].title, "console": cid, "items": items})
                    flagged.update(g.key for g in dup[1:])
        # 2) plusieurs versions du même jeu (régions, révisions…)
        by_title = {}
        for g in gs:
            if g.key not in flagged:
                by_title.setdefault(_norm_title(_name_of(g)), []).append(g)
        for vers in by_title.values():
            if len(vers) > 1:
                vers.sort(key=_preference)
                items = [(vers[0], "version conseillée", False)]
                items += [(g, "autre version" + (f" ({g.region})" if g.region else ""), True) for g in vers[1:]]
                groups.append({"kind": "versions", "title": vers[0].title, "console": cid, "items": items})
        done += len(gs)
        if progress:
            progress(done / total)
    # 3) jeux d'arcade : vérification puce par puce, réparation si possible, sinon proposés au rangement
    try:
        from . import romcheck
        if any(g.console in romcheck.ARCADE_CONSOLES for g in games):
            if progress:
                progress(0.0)
            romcheck.ensure_lists()
            fixed, ko, _unknown = romcheck.repair_all(games, progress)
            if fixed:
                groups.append({"kind": "repares", "title": "Jeux d'arcade réparés", "console": "",
                               "items": [(g, "complété avec des puces trouvées dans ta collection", False)
                                         for g in fixed]})
            if ko:
                groups.append({"kind": "arcade", "title": "Jeux d'arcade qui ne pourront pas démarrer",
                               "console": "", "items": [(g, why, True) for g, why in ko]})
    except Exception:
        pass
    # 4) ROMs douteuses
    bad_items = []
    for g in games:
        why = bad_reason(g)
        if why:
            bad_items.append((g, why, True))
    if bad_items:
        groups.append({"kind": "douteuse", "title": "ROMs douteuses", "console": "", "items": bad_items})
    return groups


def preferred_only(games):
    """Une seule version par jeu (la meilleure), pour un affichage sans doublons."""
    best = {}
    for g in games:
        k = (g.console, _norm_title(_name_of(g)))
        if k not in best or _preference(g) < _preference(best[k]):
            best[k] = g
    keep = set(id(g) for g in best.values())
    return [g for g in games if id(g) in keep]


# ------------------------------------------------------------------ export vers une autre machine
EXPORT_STYLES = {
    "retrostation": "Rétro Station (noms en clair : « Super Nintendo », « Mega Drive »…)",
    "batocera": "Batocera / Recalbox / Knulli / consoles portables rétro (snes, megadrive…)",
}
BATOCERA = {"nes": "nes", "snes": "snes", "gb": "gb", "gbc": "gbc", "gba": "gba", "n64": "n64", "gc": "gamecube",
            "wii": "wii", "sms": "mastersystem", "md": "megadrive", "gg": "gamegear", "segacd": "segacd",
            "32x": "sega32x", "saturn": "saturn", "dreamcast": "dreamcast", "psp": "psp", "a2600": "atari2600",
            "a5200": "atari5200", "a7800": "atari7800", "lynx": "lynx", "jaguar": "jaguar", "atarist": "atarist",
            "amiga": "amiga500", "arcade": "fbneo", "mame": "mame", "neogeo": "neogeo", "neocd": "neogeocd",
            "ngp": "ngp", "ngpc": "ngpc"}


def export_folder(cid, style):
    return BATOCERA.get(cid, cid) if style == "batocera" else BY_ID[cid].name


def export_games(games, dest: Path, style="retrostation", include_bios=True, progress=None):
    """Copie les jeux (avec leurs pistes / disques) rangés par console. Renvoie (copiés, ignorés, erreurs)."""
    dest = Path(dest)
    roms_root = dest / "roms" if style == "batocera" else dest / "Jeux"
    jobs = []
    for g in games:
        folder = roms_root / export_folder(g.console, style)
        base = g.path.parent
        for f in [g.path] + companions(g.path):
            try:
                rel = f.relative_to(base)
            except ValueError:
                rel = Path(f.name)
            jobs.append((f, folder / rel))
        if g.console == "neogeo" or g.console == "arcade":
            nb = console_dir("neogeo") / "neogeo.zip"
            if nb.exists():
                jobs.append((nb, folder / "neogeo.zip"))
    if include_bios and paths.BIOS.exists():
        bios_root = dest / ("bios" if style == "batocera" else "BIOS")
        for f in paths.BIOS.rglob("*"):
            if f.is_file() and not f.name.startswith("."):
                jobs.append((f, bios_root / f.relative_to(paths.BIOS)))
    copied, skipped, errors, seen = 0, 0, [], set()
    for i, (src, dst) in enumerate(jobs):
        if dst in seen:
            continue
        seen.add(dst)
        if progress:
            progress(i, len(jobs), src.name)
        try:
            dst.parent.mkdir(parents=True, exist_ok=True)
            if dst.exists() and dst.stat().st_size == src.stat().st_size:
                skipped += 1
                continue
            shutil.copy2(src, dst)
            copied += 1
        except OSError as e:
            errors.append(f"{src.name} : {e}")
    if progress:
        progress(len(jobs), len(jobs), "")
    return copied, skipped, errors


# ------------------------------------------------------------------ Kickstart rangés avec les jeux
import re as _re2
import zipfile as _zip2

KICK_REVS = [  # (révision, modèle obligatoire dans le nom) -> nom attendu par l'émulateur Amiga
    ("33.180", "a500", "kick33180.A500"), ("34.005", "a500", "kick34005.A500"),
    ("37.175", "a500 plus", "kick37175.A500"), ("37.350", "a600", "kick37350.A600"),
    ("40.063", "a600", "kick40063.A600"), ("40.068", "a1200", "kick40068.A1200"),
    ("40.068", "a4000)", "kick40068.A4000"), ("40.060", "cd32", "kick40060.CD32"),
]


def kickstart_target(name: str):
    """« [BIOS] Kickstart (…) (v1.3) (Rev 34.005) (A500, A2000).zip » -> « kick34005.A500 »."""
    low = name.lower()
    if "kickstart" not in low or "[bios]" not in low or "beta" in low or "proto" in low:
        return None
    m = _re2.search(r"rev\s*(\d+\.\d+)", low)
    if not m:
        return None
    rev = m.group(1)
    for r, model, target in KICK_REVS:
        if r == rev and model in low:
            if "ext" in low and "cd32" in low:
                return target + ".ext"
            return target
    return None


def install_kickstart(src: Path, target: str) -> bool:
    dest = paths.BIOS / target
    if dest.exists():
        return False
    paths.BIOS.mkdir(parents=True, exist_ok=True)
    try:
        if src.suffix.lower() == ".zip":
            with _zip2.ZipFile(src) as z:
                roms = [i for i in z.infolist() if not i.is_dir() and 64 * 1024 <= i.file_size <= 1024 * 1024]
                if len(roms) != 1:      # Kickstart en deux moitiés (A1200 / A4000) : pas utilisable tel quel
                    return False
                dest.write_bytes(z.read(roms[0]))
        else:
            shutil.copy2(src, dest)
        return True
    except (OSError, _zip2.BadZipFile):
        return False


def collect_kickstarts():
    """Range dans BIOS les Kickstart trouvés dans le dossier des jeux Amiga. Renvoie le nombre ajouté."""
    d = console_dir("amiga")
    n = 0
    if d.exists():
        for f in d.iterdir():
            t = kickstart_target(f.name)
            if t and install_kickstart(f, t):
                n += 1
    return n
