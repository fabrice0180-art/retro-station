"""Noms complets des jeux d'arcade (FinalBurn Neo) : « sf2.zip » -> « Street Fighter II… ».

La liste officielle de FinalBurn Neo est téléchargée une fois sur l'ordinateur de
l'utilisateur, puis gardée dans Moteurs/arcade-noms.json.
"""
import json
import threading
import urllib.parse
import xml.etree.ElementTree as ET

from . import paths, engines

CACHE = paths.ENGINES / "arcade-noms.json"
API = "https://api.github.com/repos/libretro/FBNeo/contents/dats"
FALLBACK = ("https://raw.githubusercontent.com/libretro/FBNeo/master/dats/"
            + urllib.parse.quote("FinalBurn Neo (ClrMame Pro XML, Arcade only).dat"))

_db = None
_lock = threading.Lock()


def _load_cache():
    global _db
    if _db is None and CACHE.exists():
        try:
            _db = json.loads(CACHE.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            _db = None
    return _db


def ready():
    return _load_cache() is not None


def download():
    """Télécharge et convertit la liste (à lancer en tâche de fond). Renvoie True si disponible."""
    global _db
    with _lock:
        if _load_cache() is not None:
            return True
        url = None
        try:
            items = json.loads(engines.fetch(API, timeout=30))
            for it in items:
                n = it.get("name", "")
                if "arcade only" in n.lower() and n.lower().endswith(".dat"):
                    url = it.get("download_url")
                    break
        except Exception:
            url = None
        try:
            data = engines.fetch(url or FALLBACK, timeout=120)
        except Exception:
            return False
        db = {}
        try:
            root = ET.fromstring(data)
            for g in root.iter("game"):
                name = g.get("name")
                desc = g.findtext("description") or name
                if name:
                    db[name.lower()] = {"t": desc, "p": (g.get("cloneof") or "").lower(),
                                        "neo": (g.get("romof") or "").lower() == "neogeo"}
            # un clone d'un jeu Neo Geo est aussi Neo Geo
            for v in db.values():
                if not v["neo"] and v["p"] in db and db[v["p"]]["neo"]:
                    v["neo"] = True
        except ET.ParseError:
            return False
        if not db:
            return False
        CACHE.parent.mkdir(parents=True, exist_ok=True)
        CACHE.write_text(json.dumps(db, ensure_ascii=False), encoding="utf-8")
        _db = db
        return True


def info(set_name: str):
    db = _load_cache()
    return db.get(set_name.lower()) if db else None


def title(set_name: str):
    i = info(set_name)
    return i["t"] if i else None


def console_of(set_name: str):
    """'neogeo', 'arcade' ou None si le jeu n'est pas dans la liste."""
    i = info(set_name)
    if not i:
        return None
    return "neogeo" if i["neo"] else "arcade"
