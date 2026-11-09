"""Reconnaissance automatique de la console d'un fichier de jeu.

On regarde d'abord l'extension, puis, si elle est ambiguë (.bin, .iso, .cue,
.zip…), on lit l'en-tête du fichier : chaque console laisse une signature
reconnaissable au début de ses cartouches ou de ses disques.
"""
import re
import struct
import zipfile
from dataclasses import dataclass
from pathlib import Path

from .consoles import CONSOLES, BIOS_FILES

# Extensions de fichiers « annexes » à ignorer en silence (pistes, notices…)
SKIP_EXTS = {".txt", ".nfo", ".jpg", ".jpeg", ".png", ".pdf", ".dat", ".srm", ".sav",
             ".state", ".url", ".db", ".ini", ".xml", ".sfv", ".md5", ".ds_store"}


@dataclass
class Detection:
    kind: str                 # "game", "bios", "skip", "unknown"
    console: str = ""         # id console si reconnu
    candidates: tuple = ()    # consoles possibles si inconnu
    bios_target: str = ""     # chemin relatif dans BIOS/


def _ext_map():
    m = {}
    for c in CONSOLES:
        for e in c.exts:
            m.setdefault(e, []).append(c.id)
    return m


EXT_MAP = _ext_map()


def _read(path, off, n):
    try:
        with open(path, "rb") as f:
            f.seek(off)
            return f.read(n)
    except OSError:
        return b""


# ---------------------------------------------------------------- cartouches
def _snes_header_ok(data, base):
    if len(data) < base + 0x40:
        return False
    comp, chk = struct.unpack_from("<HH", data, base + 0x1C)
    if (comp ^ chk) != 0xFFFF:
        return False
    title = data[base:base + 21]
    return all(32 <= b < 127 for b in title)


def sniff_cart_bytes(h: bytes, size: int, read_at=None):
    """Identifie une cartouche à partir de ses premiers octets."""
    if h[:4] == b"NES\x1a" or h[:4] == b"FDS\x1a":
        return "nes"
    if h[:4] in (b"\x80\x37\x12\x40", b"\x37\x80\x40\x12", b"\x40\x12\x37\x80"):
        return "n64"
    if len(h) >= 0x110 and h[0x100:0x104] == b"SEGA":
        return "32x" if h[0x100:0x108] == b"SEGA 32X" else "md"
    if len(h) >= 0x150 and h[0x104:0x108] == b"\xCE\xED\x66\x66":
        return "gbc" if h[0x143] in (0x80, 0xC0) else "gb"
    if len(h) >= 0xC0 and h[0x04:0x08] == b"\x24\xFF\xAE\x51" and h[0xB2] == 0x96:
        return "gba"
    if read_at:
        for off in (0x7FF0, 0x3FF0, 0x1FF0):
            if size > off + 16:
                t = read_at(off, 16)
                if t[:8] == b"TMR SEGA":
                    region = t[15] >> 4
                    return "gg" if region in (5, 6, 7) else "sms"
        # Super Nintendo : en-tête interne LoROM / HiROM (avec ou sans en-tête copieur 512 o)
        for base in (0x7FC0, 0xFFC0, 0x81C0, 0x101C0):
            if size > base + 0x40:
                blk = read_at(base, 0x40)
                if _snes_header_ok(blk, 0):
                    return "snes"
    return None


def sniff_cart(path: Path):
    size = path.stat().st_size
    h = _read(path, 0, 0x200)
    return sniff_cart_bytes(h, size, lambda o, n: _read(path, o, n))


# ---------------------------------------------------------------- disques
SYNC = b"\x00" + b"\xff" * 10 + b"\x00"


def sniff_disc(path: Path):
    head = _read(path, 0, 0x40)
    data = _read(path, 0x10, 0x20) if head[:12] == SYNC else head[:0x20]
    if data.startswith(b"SEGADISCSYSTEM"):
        return "segacd"
    if data.startswith(b"SEGA SEGASATURN"):
        return "saturn"
    if data.startswith(b"SEGA SEGAKATANA"):
        return "dreamcast"
    if len(head) >= 0x20:
        if head[0x18:0x1C] == b"\x5D\x1C\x9E\xA3":
            return "wii"
        if head[0x1C:0x20] == b"\xC2\x33\x9F\x3D":
            return "gc"
    return None


def sniff_nintendo_container(path: Path, ext: str):
    if ext == ".wbfs":
        return "wii"
    if ext in (".rvz", ".wia"):
        h = _read(path, 0, 0x50)
        if h[:3] in (b"RVZ", b"WIA") and len(h) >= 0x4C:
            disc_type = struct.unpack_from(">I", h, 0x48)[0]
            return {1: "gc", 2: "wii"}.get(disc_type)
    if ext == ".ciso":
        h = _read(path, 0x8000, 0x20)
        if len(h) >= 0x20:
            if h[0x18:0x1C] == b"\x5D\x1C\x9E\xA3":
                return "wii"
            if h[0x1C:0x20] == b"\xC2\x33\x9F\x3D":
                return "gc"
    return None


# ---------------------------------------------------------------- fichiers liés
def cue_files(cue: Path):
    """Pistes référencées par un .cue."""
    out = []
    try:
        for line in cue.read_text(errors="ignore").splitlines():
            m = re.match(r'\s*FILE\s+"?(.+?)"?\s+\w+\s*$', line, re.I)
            if m:
                out.append(cue.parent / m.group(1))
    except OSError:
        pass
    return out


def gdi_files(gdi: Path):
    out = []
    try:
        for line in gdi.read_text(errors="ignore").splitlines()[1:]:
            m = re.match(r'\s*\d+\s+\d+\s+\d+\s+\d+\s+("([^"]+)"|(\S+))', line)
            if m:
                out.append(gdi.parent / (m.group(2) or m.group(3)))
    except OSError:
        pass
    return out


def m3u_files(m3u: Path):
    out = []
    try:
        for line in m3u.read_text(errors="ignore").splitlines():
            line = line.strip()
            if line and not line.startswith("#"):
                out.append(m3u.parent / line)
    except OSError:
        pass
    return out


def companions(path: Path):
    """Tous les fichiers à copier avec ce jeu (pistes .bin, disques d'un .m3u…)."""
    ext = path.suffix.lower()
    files = []
    if ext == ".cue":
        files = cue_files(path)
    elif ext == ".gdi":
        files = gdi_files(path)
    elif ext == ".m3u":
        for f in m3u_files(path):
            files.append(f)
            files.extend(companions(f))
    return [f for f in files if f.exists()]


# ---------------------------------------------------------------- zip
NEOGEO_PART = re.compile(r"(^|[-_.])(p\d|c\d|m\d|s\d|v\d\d?)(\.|$)|\d{3}-[pcmsv]\d", re.I)


def sniff_zip(path: Path):
    try:
        with zipfile.ZipFile(path) as z:
            names = [n for n in z.namelist() if not n.endswith("/")]
            for n in names:
                e = Path(n).suffix.lower()
                ids = [i for i in EXT_MAP.get(e, []) if i not in ("neogeo",)]
                if len(ids) == 1:
                    return ids[0], ()
                if e == ".bin":
                    with z.open(n) as f:
                        h = f.read(0x8000)
                    c = sniff_cart_bytes(h[:0x200], len(h), lambda o, k: h[o:o + k])
                    if c:
                        return c, ()
            if any(NEOGEO_PART.search(Path(n).name) for n in names):
                return "neogeo", ()
    except (zipfile.BadZipFile, OSError):
        pass
    return None, ("neogeo",)


# ---------------------------------------------------------------- principal
def detect(path: Path) -> Detection:
    path = Path(path)
    name = path.name.lower()
    ext = path.suffix.lower()

    if name in BIOS_FILES:
        return Detection("bios", bios_target=BIOS_FILES[name])
    if ext in SKIP_EXTS or name.startswith("."):
        return Detection("skip")

    ids = EXT_MAP.get(ext, [])
    if not ids:
        return Detection("unknown")

    if ext == ".zip":
        c, cand = sniff_zip(path)
        return Detection("game", c) if c else Detection("unknown", candidates=cand)
    if ext == ".7z":
        return Detection("unknown", candidates=("neogeo",))

    if len(ids) == 1:
        return Detection("game", ids[0])

    # Extension partagée par plusieurs consoles : on lit le contenu
    c = None
    if ext in (".rvz", ".wia", ".ciso", ".wbfs"):
        c = sniff_nintendo_container(path, ext)
    elif ext == ".iso":
        c = sniff_disc(path)
    elif ext == ".bin":
        c = sniff_cart(path) or sniff_disc(path)
    elif ext == ".cue":
        tracks = cue_files(path)
        if tracks and tracks[0].exists():
            c = sniff_disc(tracks[0])
    elif ext == ".m3u":
        first = m3u_files(path)
        if first and first[0].exists():
            sub = detect(first[0])
            c = sub.console or None
            if not c:
                return Detection("unknown", candidates=sub.candidates or tuple(ids))
    if c and (c in ids or ext in (".bin", ".iso")):
        return Detection("game", c)
    if ext == ".gcz" and not c:
        ids = ["gc", "wii"]
    return Detection("unknown", candidates=tuple(ids))


# ---------------------------------------------------------------- titres
def clean_title(stem: str) -> str:
    t = re.sub(r"\s*[\(\[][^\)\]]*[\)\]]", "", stem).replace("_", " ").strip()
    return t or stem


REGIONS = {"europe": "EU", "france": "FR", "usa": "US", "japan": "JP", "world": "Monde"}


def region_of(stem: str) -> str:
    for grp in re.findall(r"\(([^)]*)\)", stem):
        for word in re.split(r"[,\s]+", grp.lower()):
            if word in REGIONS:
                return REGIONS[word]
    return ""
