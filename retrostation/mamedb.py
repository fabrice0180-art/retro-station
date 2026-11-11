"""Noms complets des jeux MAME : « daytona.zip » -> « Daytona USA (Japan, Revision A) ».

Une liste de jeux MAME (base libre libretro-database) est téléchargée une fois sur
l'ordinateur de l'utilisateur, réduite aux noms, puis gardée dans Moteurs/mame-noms.json.
"""
import html
import json
import re
import threading
import urllib.parse

from . import paths, engines

CACHE = paths.ENGINES / "mame-noms-2.json"
API = "https://api.github.com/repos/libretro/libretro-database/contents/{d}"
DIRS = ("metadat/mame", "metadat/mame-nonmerged", "metadat/mame-split", "metadat/mame-merged", "dat")
FALLBACKS = ("https://raw.githubusercontent.com/libretro/mame2003-plus-libretro/master/metadata/mame2003-plus.xml",)

_db = None
_lock = threading.Lock()
_log = []          # sources essayées (pour le diagnostic)


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


def _version(name: str):
    m = re.search(r"(\d+)\.(\d+)", name)
    return (int(m.group(1)), int(m.group(2))) if m else (0, 0)


def _sources():
    """Listes MAME disponibles, la plus récente d'abord."""
    found = []
    for d in DIRS:
        try:
            items = json.loads(engines.fetch(API.format(d=urllib.parse.quote(d)), timeout=30))
        except Exception:
            continue
        if not isinstance(items, list):
            continue
        for it in items:
            n = it.get("name", "")
            low = n.lower()
            if it.get("type") == "file" and "mame" in low and low.endswith((".dat", ".xml")) \
                    and it.get("download_url"):
                found.append((_version(n), it.get("size", 0), it["download_url"]))
    found.sort(reverse=True)
    return [u for _v, _s, u in found] + list(FALLBACKS)


_XML_START = re.compile(rb'<(?:game|machine)\s+name="([^"]+)"([^>]*)>')
_XML_CLONE = re.compile(rb'cloneof="([^"]+)"')
_CMP_GAME = re.compile(rb'(?:^|\n)\s*(?:game|machine|resource)\s*\(\s*\n', re.I)


def parse(data: bytes) -> dict:
    """Lit une liste au format XML (MAME / Logiqx) ou ClrMamePro. Renvoie {nom: {"t", "p"}}."""
    db = {}
    starts = list(_XML_START.finditer(data))
    if starts:
        for i, m in enumerate(starts):
            end = starts[i + 1].start() if i + 1 < len(starts) else len(data)
            a = data.find(b"<description>", m.end(), end)
            if a < 0:
                continue
            b = data.find(b"</description>", a, end)
            desc = html.unescape(data[a + 13:b].decode("utf-8", "replace")).strip()
            c = _XML_CLONE.search(m.group(2))
            name = m.group(1).decode("utf-8", "replace").lower()
            db[name] = {"t": desc or name, "p": c.group(1).decode().lower() if c else ""}
            if b'isbios="yes"' in m.group(2) or b'isdevice="yes"' in m.group(2):
                db[name]["b"] = 1
        return db
    blocks = _CMP_GAME.split(data)
    for blk in blocks[1:]:
        n = re.search(rb'^\s*name\s+"?([^"\n]+?)"?\s*$', blk, re.M)
        d = re.search(rb'^\s*description\s+"(.*)"\s*$', blk, re.M)
        p = re.search(rb'^\s*cloneof\s+"?([^"\n]+?)"?\s*$', blk, re.M)
        if n:
            name = n.group(1).decode("utf-8", "replace").lower()
            db[name] = {"t": d.group(1).decode("utf-8", "replace") if d else name,
                        "p": p.group(1).decode().lower() if p else ""}
    return db


def download():
    """Télécharge et réduit la liste (à lancer en tâche de fond). Renvoie True si disponible."""
    global _db
    from . import romcheck
    with _lock:
        if _load_cache() is not None and romcheck.ready("mame"):
            return True
        for url in _sources():
            try:
                data = engines.fetch(url, timeout=300)
            except Exception as e:
                _log.append(f"{url} : {e}")
                continue
            db = parse(data)
            _log.append(f"{url} : {len(db)} jeux")
            if len(db) > 1000 and "mame2003" not in url:
                try:
                    romcheck.save("mame", romcheck.parse_crcs(data))
                except Exception:
                    pass
            if len(db) > 1000:
                CACHE.parent.mkdir(parents=True, exist_ok=True)
                CACHE.write_text(json.dumps(db, ensure_ascii=False), encoding="utf-8")
                _db = db
                return True
        return False


def info(set_name: str):
    db = _load_cache()
    return db.get(set_name.lower()) if db else None


def is_support(set_name: str) -> bool:
    """BIOS ou puce partagée (pas un jeu)."""
    i = info(set_name)
    return bool(i and i.get("b"))


def title(set_name: str):
    i = info(set_name)
    return i["t"] if i else None
