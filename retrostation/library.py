"""Bibliothèque de jeux : rangement par console, import en bloc, favoris."""
import json
import shutil
import time
from dataclasses import dataclass, field
from pathlib import Path

from . import paths, arcadedb
from .consoles import CONSOLES, BY_ID

ARCADE = {"arcade", "neogeo"}   # jeux nommés par un nom court (sf2.zip) : vrai titre via la liste FinalBurn Neo
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
                if name.lower() == "neogeo.zip" or (hidden and os.path.normcase(full) in hidden):
                    continue
                key = f"{c.id}/{relp}"
                m = self.meta.get(key)
                stem = os.path.splitext(name)[0]
                title = (m or {}).get("title")
                region = region_of(stem)
                if not title and c.id in ARCADE:
                    long_name = arcadedb.title(stem)
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


def expand(selection):
    for p in map(Path, selection):
        if p.is_dir():
            yield from (x for x in sorted(p.rglob("*")) if x.is_file())
        elif p.is_file():
            yield p


def plan_import(selection) -> ImportPlan:
    files = list(expand(selection))
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
        jobs.append((src, dest_dir / src.name, True))
        for extra in companions(src):
            try:
                rel = extra.relative_to(src.parent)
            except ValueError:
                rel = Path(extra.name)
            jobs.append((extra, dest_dir / rel, False))
    for src, target in plan.bios:
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


def _name_of(game):
    if game.console in ARCADE:
        return arcadedb.title(game.path.stem) or game.path.stem
    return game.path.stem


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
    # 3) ROMs douteuses
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
