"""Mini-photos des consoles.

Photos libres de droits de Wikimedia Commons (photographe Evan-Amos et autres
contributeurs, domaine public ou CC BY-SA). Elles sont téléchargées une fois sur
l'ordinateur de l'utilisateur, puis gardées dans ~/RetroStation/Icones.
Clic droit sur une console pour mettre sa propre photo.
"""
import json
import urllib.parse
from pathlib import Path

from . import paths, engines

ICONS = paths.ROOT / "Icones"
FILEPATH = "https://commons.wikimedia.org/wiki/Special:FilePath/{name}?width=320"
SEARCH = ("https://commons.wikimedia.org/w/api.php?action=query&format=json&list=search"
          "&srnamespace=6&srlimit=8&srsearch={q}")

# Noms de fichiers Commons à essayer, puis une recherche de secours
PHOTOS = {
    "nes": (["NES-Console-Set.jpg", "NES-Console-Set.png"], "NES console set Evan-Amos"),
    "snes": (["SNES-Mod1-Console-Set.jpg", "SNES-Mod1-Console-Set.png"], "SNES console set Evan-Amos"),
    "gb": (["Game-Boy-FL.jpg", "Nintendo-Game-Boy-FL.jpg"], "Game Boy FL Evan-Amos"),
    "gbc": (["Nintendo-Game-Boy-Color-FL.jpg", "Game-Boy-Color-Purple.jpg"], "Game Boy Color FL Evan-Amos"),
    "gba": (["Nintendo-Game-Boy-Advance-Purple-FL.jpg", "Game-Boy-Advance-Purple-FL.jpg"],
            "Game Boy Advance FL Evan-Amos"),
    "n64": (["N64-Console-Set.jpg", "N64-Console-Set.png"], "Nintendo 64 console set Evan-Amos"),
    "gc": (["GameCube-Console-Set.jpg", "GameCube-Console-Set.png", "GameCube-Set.jpg"],
           "GameCube console set Evan-Amos"),
    "wii": (["Wii-console.jpg", "Wii-Console.jpg", "Nintendo-Wii-Console-FL.jpg"], "Wii console Evan-Amos"),
    "sms": (["Sega-Master-System-Set.jpg", "Sega-Master-System-Set.png"], "Sega Master System set Evan-Amos"),
    "md": (["Sega-Mega-Drive-EU-Mk1-wController-FL.jpg", "Sega-Genesis-Mod1-Set.jpg",
            "Sega-Genesis-NA-Mk2-Console-Set.png"], "Sega Mega Drive console Evan-Amos"),
    "gg": (["Game-Gear-Handheld.jpg", "Sega-Game-Gear-WB.jpg"], "Sega Game Gear Evan-Amos"),
    "segacd": (["Sega-CD-Model1-Set.jpg", "Sega-CD-Model2-Set.jpg"], "Sega CD model console Evan-Amos"),
    "32x": (["Sega-Genesis-Model2-32X.jpg", "Sega-32X-Console-Set.jpg"], "Sega 32X Evan-Amos"),
    "saturn": (["Sega-Saturn-Console-Set-Mk1.jpg", "Sega-Saturn-Console-Set-Mk1.png"],
               "Sega Saturn console set Evan-Amos"),
    "dreamcast": (["Dreamcast-Console-Set.jpg", "Dreamcast-Console-Set.png"], "Dreamcast console set Evan-Amos"),
    "neogeo": (["Neo-Geo-AES-Console-Set.jpg", "Neo-Geo-AES-Console-Set.png"], "Neo Geo AES console set"),
    "neocd": (["Neo-Geo-CD-Console-Set.jpg", "Neo-Geo-CD-Console-Set.png"], "Neo Geo CD console set"),
    "ngp": (["Neo-Geo-Pocket-Anthracite-Left.jpg", "Neo-Geo-Pocket-Anthracite.jpg"], "Neo Geo Pocket Evan-Amos"),
    "ngpc": (["Neo-Geo-Pocket-Color-Blue-Left.jpg", "Neo-Geo-Pocket-Color-Blue.jpg"],
             "Neo Geo Pocket Color Evan-Amos"),
    "psp": (["Psp-1000.jpg", "PSP-1000.jpg", "Sony-PSP-1000-Body.png"], "PlayStation Portable PSP-1000 Evan-Amos"),
    "a2600": (["Atari-2600-Wood-4Sw-Set.jpg", "Atari-2600-Wood-4Sw-Set.png"], "Atari 2600 console set Evan-Amos"),
    "a5200": (["Atari-5200-4-Port-wController-L.jpg", "Atari-5200-Console-Set.jpg"], "Atari 5200 console Evan-Amos"),
    "a7800": (["Atari-7800-Console-Set.jpg", "Atari-7800-Console-Set.png"], "Atari 7800 console set Evan-Amos"),
    "lynx": (["Atari-Lynx-I-Handheld.jpg", "Atari-Lynx-II-Handheld-Angled.jpg"], "Atari Lynx handheld Evan-Amos"),
    "jaguar": (["Atari-Jaguar-Console-Set.jpg", "Atari-Jaguar-Console-Set.png"], "Atari Jaguar console set Evan-Amos"),
    "atarist": (["Atari 1040STf.jpg", "Atari-1040STf.jpg"], "Atari 1040ST computer"),
    "amiga": (["Amiga500 system.jpg", "Amiga 500 system.jpg"], "Commodore Amiga 500 computer"),
    # bornes d'arcade : vraies photos de bornes (Commons, licence libre)
    "arcade": (["Japanese shmup arcade.jpg", "Sega Astro City.jpg"], "Sega Astro City arcade cabinet"),
    "mame": (["ArcadeGames.jpg", "Arcade games.jpg"], "upright arcade cabinets arcade"),
}

IMG_MAGIC = (b"\x89PNG", b"\xff\xd8\xff")


def custom(cid: str) -> Path:
    return ICONS / f"{cid}.perso.png"


def downloaded(cid: str) -> Path:
    return ICONS / f"{cid}.photo"


def best(cid: str):
    for p in (custom(cid), downloaded(cid)):
        if p.exists() and p.stat().st_size > 0:
            return p
    return None


def _get_image(name: str):
    url = FILEPATH.format(name=urllib.parse.quote(name.replace(" ", "_")))
    try:
        data = engines.fetch(url, timeout=20)
    except Exception:
        return None
    return data if data[:4].startswith(IMG_MAGIC[0]) or data[:3] == IMG_MAGIC[1] else None


def download(cid: str) -> bool:
    """Télécharge la photo d'une console (une seule fois)."""
    if best(cid):
        return True
    miss = ICONS / f"{cid}.absent"
    if miss.exists() or cid not in PHOTOS:
        return False
    ICONS.mkdir(parents=True, exist_ok=True)
    names, query = PHOTOS[cid]
    names = list(names)
    data = None
    for n in names:
        data = _get_image(n)
        if data:
            break
    if not data:  # recherche de secours sur Commons
        try:
            res = json.loads(engines.fetch(SEARCH.format(q=urllib.parse.quote(query)), timeout=20))
            for hit in res.get("query", {}).get("search", []):
                title = hit.get("title", "")
                if title.lower().endswith((".jpg", ".jpeg", ".png")):
                    data = _get_image(title.split(":", 1)[-1])
                    if data:
                        break
        except Exception:
            data = None
    if not data:
        miss.touch()
        return False
    downloaded(cid).write_bytes(data)
    return True


def forget_missing():
    for p in ICONS.glob("*.absent"):
        try:
            p.unlink()
        except OSError:
            pass
