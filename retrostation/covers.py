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
    dest.parent.mkdir(parents=True, exist_ok=True)
    for n, name in enumerate(_candidates(game)):
        for host in (HOSTS if n == 0 else HOSTS[:1]):   # site de secours seulement pour le nom exact
            url = host.format(sys=urllib.parse.quote(system),
                              repo=urllib.parse.quote(system.replace(" ", "_")),
                              name=urllib.parse.quote(name))
            try:
                data = engines.fetch(url, timeout=15)
            except Exception:
                continue
            if data[:8] == b"\x89PNG\r\n\x1a\n":
                dest.write_bytes(data)
                return dest
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
