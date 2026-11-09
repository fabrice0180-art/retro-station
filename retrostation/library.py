"""Bibliothèque de jeux : rangement par console, import en bloc, favoris."""
import json
import shutil
import time
from dataclasses import dataclass, field
from pathlib import Path

from . import paths
from .consoles import CONSOLES, BY_ID
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
        games = []
        for c in CONSOLES:
            d = console_dir(c.id)
            files = [p for p in d.rglob("*") if p.is_file() and p.suffix.lower() in c.shown_exts]
            hidden = set()
            for p in files:
                if p.suffix.lower() == ".m3u":
                    hidden.update(x.resolve() for x in m3u_files(p))
            for p in files:
                if p.resolve() in hidden or p.name.lower() == "neogeo.zip":
                    continue
                key = f"{c.id}/{p.relative_to(d).as_posix()}"
                m = self.meta.get(key, {})
                games.append(Game(c.id, p, m.get("title") or clean_title(p.stem),
                                  region_of(p.stem), key))
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
