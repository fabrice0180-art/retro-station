"""Jaquettes : téléchargées depuis la base libre libretro-thumbnails, puis gardées en cache."""
from __future__ import annotations

import re
import urllib.parse
from pathlib import Path

from . import paths, engines
from .consoles import BY_ID
from .detect import clean_title

HOSTS = ["https://thumbnails.libretro.com/{sys}/Named_Boxarts/{name}.png",
         "https://raw.githubusercontent.com/libretro-thumbnails/{repo}/master/Named_Boxarts/{name}.png"]


def _safe(name: str) -> str:
    # règle libretro : ces caractères deviennent « _ »
    return re.sub(r'[&*/:`<>?\\|"]', "_", name)


def cover_file(game) -> Path:
    return paths.COVERS / game.console / f"{game.path.stem}.png"


def custom_cover(game) -> Path:
    return paths.COVERS / game.console / f"{game.path.stem}.perso.png"


def best_cover(game):
    for p in (custom_cover(game), cover_file(game)):
        if p.exists() and p.stat().st_size > 0:
            return p
    return None


def _candidates(game):
    stem = game.path.stem
    if game.console in ("arcade", "neogeo", "mame"):
        from .library import arcade_title
        full = arcade_title(game.console, stem)
        if not full:
            return []
        return [_safe(full)]
    title = clean_title(stem)
    names = [stem]
    first = re.match(r"^(.*?\([^)]*\))", stem)
    if first:
        names.append(first.group(1))
    names += [f"{title} (Europe)", f"{title} (USA)", f"{title} (World)"]
    return list(dict.fromkeys(_safe(n) for n in names))


# ------------------------------------------------------------------ index des images (recherche souple)
# Les noms de fichiers varient beaucoup (« Zelda (1989)(Nintendo)(FR)[!] » contre « Legend of Zelda,
# The (Europe) »). On récupère une fois la liste des images de chaque console et on compare les titres
# simplifiés : beaucoup plus de jaquettes trouvées, et une seule requête par jeu.
INDEX_DIR = paths.COVERS / "_index"
LISTING = "https://thumbnails.libretro.com/{sys}/{kind}/"
_indexes = {}
_REGION_ORDER = ("france", "europe", "world", "usa", "japan")


def norm_title(s: str) -> str:
    s = s.lower().replace("&", " and ").replace("_", " ")
    s = re.sub(r"[\(\[].*?[\)\]]", " ", s)
    s = re.sub(r"^(.*?),\s*(the|le|la|les|l')\s*(\s-.*)?$", r"\2 \1\3", s.strip())
    s = re.sub(r"\b(the|a|an)\b", " ", s)
    s = re.sub(r"\b(ii)\b", "2", re.sub(r"\b(iii)\b", "3", re.sub(r"\b(iv)\b", "4", s)))
    return re.sub(r"[^a-z0-9]+", "", s)


def index(system: str, kind: str = "Named_Boxarts"):
    """{titre simplifié: [noms d'images]} pour une console (téléchargé une fois, gardé 30 jours)."""
    import json
    import time
    key = (system, kind)
    if key in _indexes:
        return _indexes[key]
    f = INDEX_DIR / f"{_safe(system)} - {kind}.json"
    names = None
    try:
        if f.exists() and time.time() - f.stat().st_mtime < 30 * 86400:
            names = json.loads(f.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        names = None
    if names is None:
        try:
            html = engines.fetch(LISTING.format(sys=urllib.parse.quote(system), kind=kind),
                                 timeout=60).decode("utf-8", "replace")
            names = sorted({urllib.parse.unquote(m)[:-4] for m in re.findall(r'href="([^"?/]+\.png)"', html)})
            if names:
                f.parent.mkdir(parents=True, exist_ok=True)
                f.write_text(json.dumps(names, ensure_ascii=False), encoding="utf-8")
        except Exception:
            names = None
    idx = None
    if names:
        idx = {}
        for n in names:
            idx.setdefault(norm_title(n), []).append(n)
    _indexes[key] = idx
    return idx


def fuzzy_names(game, system, kind, wanted=None):
    """Images de l'index qui correspondent au jeu, la meilleure région d'abord."""
    idx = index(system, kind)
    if not idx:
        return []
    keys = [norm_title(w) for w in (wanted or [clean_title(game.path.stem)])]
    found = []
    for k in keys:
        if k and k in idx:
            found = idx[k]
            break
    if not found:
        return []
    reg = (game.region or "").lower()

    def rank(n):
        low = n.lower()
        r = 0 if reg and reg in low else 1
        for i, rg in enumerate(_REGION_ORDER):
            if rg in low:
                return (r, i, len(n))
        return (r, len(_REGION_ORDER), len(n))
    return sorted(found, key=rank)[:2]


def download_cover(game) -> Path | None:
    """Essaie plusieurs noms ; mémorise l'échec pour ne pas réessayer à chaque lancement."""
    dest = cover_file(game)
    miss = dest.with_suffix(".absent")
    if best_cover(game):
        return best_cover(game)
    if miss.exists():
        return None
    system = BY_ID[game.console].thumbs
    if not system:
        return None
    cands = _candidates(game)
    if not cands:
        return None          # nom du jeu pas encore connu (liste d'arcade en cours) : on réessaiera
    dest.parent.mkdir(parents=True, exist_ok=True)
    arcade = game.console in ("arcade", "neogeo", "mame")
    # arcade : beaucoup de bornes n'ont pas d'affiche -> écran titre, puis image du jeu
    kinds = ("Named_Boxarts", "Named_Titles", "Named_Snaps") if arcade else ("Named_Boxarts",)
    systems = [system]
    if arcade:
        systems += [s for s in ("FBNeo - Arcade Games", "MAME") if s != system]
    import urllib.error
    net_error = False

    def get(url):
        nonlocal net_error
        try:
            data = engines.fetch(url, timeout=20)
        except urllib.error.HTTPError as e:
            if e.code not in (404, 410):
                net_error = True
            return None
        except Exception:
            net_error = True           # pas de réseau, délai dépassé… : on réessaiera plus tard
            return None
        return data if data[:8] == b"\x89PNG\r\n\x1a\n" else None

    wanted = [clean_title(game.path.stem)]
    if arcade:
        wanted = [c for c in cands]
    for kind in kinds:
        for sysname in systems:
            # 1) recherche souple dans la liste des images de la console
            names = fuzzy_names(game, sysname, kind, wanted)
            if index(sysname, kind) is None:
                names = cands              # liste indisponible : on essaie les noms exacts
            for name in names:
                for host in HOSTS:
                    url = host.replace("Named_Boxarts", kind).format(
                        sys=urllib.parse.quote(sysname), repo=urllib.parse.quote(sysname.replace(" ", "_")),
                        name=urllib.parse.quote(name))
                    data = get(url)
                    if data:
                        dest.write_bytes(data)
                        return dest
    if not net_error:
        try:
            miss.touch()
        except OSError:
            pass
    return None


def forget_missing():
    """Permet de relancer la recherche des jaquettes manquantes."""
    for p in paths.COVERS.rglob("*.absent"):
        try:
            p.unlink()
        except OSError:
            pass
