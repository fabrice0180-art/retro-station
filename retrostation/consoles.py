"""Liste des consoles prises en charge et de leur moteur d'émulation."""
from dataclasses import dataclass, field


@dataclass
class Console:
    id: str
    name: str            # nom affiché (et nom du dossier de jeux)
    family: str          # Nintendo / Sega / SNK
    short: str           # texte de l'icône
    color: str           # couleur principale de l'icône
    glyph: str           # cart / handheld / disc / arcade / home
    engine: str          # "retroarch" ou "dolphin"
    core: str = ""       # cœur libretro (si retroarch)
    exts: tuple = ()     # extensions reconnues
    primary: tuple = ()  # extensions affichées dans la bibliothèque (vide = exts)
    thumbs: str = ""     # nom du dépôt de jaquettes libretro
    bios_required: tuple = ()   # groupes de fichiers : ((fichierA, fichierB), ...) => au moins un par groupe
    bios_optional: tuple = ()
    bios_note: str = ""
    shown_exts: tuple = field(default=())

    def __post_init__(self):
        self.shown_exts = self.primary or self.exts


CONSOLES = [
    # ---------------- Nintendo ----------------
    Console("nes", "NES", "Nintendo", "NES", "#d4343c", "home", "retroarch", "mesen",
            (".nes", ".fds", ".unf", ".unif", ".zip"),
            thumbs="Nintendo - Nintendo Entertainment System",
            bios_optional=("disksys.rom",),
            bios_note="disksys.rom (facultatif, seulement pour les jeux Famicom Disk System)"),
    Console("snes", "Super Nintendo", "Nintendo", "SNES", "#6a4fb6", "home", "retroarch", "snes9x",
            (".sfc", ".smc", ".fig", ".swc", ".bs", ".zip"),
            thumbs="Nintendo - Super Nintendo Entertainment System"),
    Console("gb", "Game Boy", "Nintendo", "GB", "#7a9a3a", "handheld", "retroarch", "gambatte",
            (".gb", ".zip"), thumbs="Nintendo - Game Boy"),
    Console("gbc", "Game Boy Color", "Nintendo", "GBC", "#1f9bd1", "handheld", "retroarch", "gambatte",
            (".gbc", ".zip"), thumbs="Nintendo - Game Boy Color"),
    Console("gba", "Game Boy Advance", "Nintendo", "GBA", "#3c3fb0", "handheld", "retroarch", "mgba",
            (".gba", ".zip"), thumbs="Nintendo - Game Boy Advance",
            bios_optional=("gba_bios.bin",), bios_note="gba_bios.bin (facultatif)"),
    Console("n64", "Nintendo 64", "Nintendo", "N64", "#1e8a4c", "home", "retroarch", "mupen64plus_next",
            (".z64", ".n64", ".v64", ".zip"), thumbs="Nintendo - Nintendo 64"),
    Console("gc", "GameCube", "Nintendo", "GC", "#5b3d9e", "disc", "dolphin", "",
            (".iso", ".gcm", ".gcz", ".rvz", ".wia", ".ciso", ".dol", ".elf"),
            thumbs="Nintendo - GameCube"),
    Console("wii", "Wii", "Nintendo", "Wii", "#2aa7d8", "disc", "dolphin", "",
            (".wbfs", ".iso", ".rvz", ".wia", ".gcz", ".ciso", ".wad", ".dol", ".elf"),
            thumbs="Nintendo - Wii"),
    # ---------------- Sega ----------------
    Console("sms", "Master System", "Sega", "SMS", "#c62f2f", "home", "retroarch", "genesis_plus_gx",
            (".sms", ".sg", ".zip"), thumbs="Sega - Master System - Mark III"),
    Console("md", "Mega Drive", "Sega", "MD", "#1b1b1f", "home", "retroarch", "genesis_plus_gx",
            (".md", ".gen", ".smd", ".bin", ".zip"), thumbs="Sega - Mega Drive - Genesis"),
    Console("gg", "Game Gear", "Sega", "GG", "#28323c", "handheld", "retroarch", "genesis_plus_gx",
            (".gg", ".zip"), thumbs="Sega - Game Gear"),
    Console("segacd", "Mega-CD", "Sega", "MCD", "#3a4c8c", "disc", "retroarch", "genesis_plus_gx",
            (".cue", ".chd", ".iso", ".m3u", ".bin"), primary=(".cue", ".chd", ".iso", ".m3u"),
            thumbs="Sega - Mega-CD - Sega CD",
            bios_required=(("bios_CD_E.bin", "bios_CD_U.bin", "bios_CD_J.bin"),),
            bios_note="bios_CD_E.bin (Europe), bios_CD_U.bin (USA) ou bios_CD_J.bin (Japon)"),
    Console("32x", "32X", "Sega", "32X", "#b8862b", "cart", "retroarch", "picodrive",
            (".32x", ".bin", ".zip"), thumbs="Sega - 32X"),
    Console("saturn", "Saturn", "Sega", "SAT", "#4b5563", "disc", "retroarch", "mednafen_saturn",
            (".cue", ".chd", ".ccd", ".m3u", ".bin", ".iso"), primary=(".cue", ".chd", ".ccd", ".m3u", ".iso"),
            thumbs="Sega - Saturn",
            bios_required=(("mpr-17933.bin", "sega_101.bin"),),
            bios_note="mpr-17933.bin (Europe/USA) ou sega_101.bin (Japon)"),
    Console("dreamcast", "Dreamcast", "Sega", "DC", "#e2622a", "disc", "retroarch", "flycast",
            (".gdi", ".cdi", ".chd", ".m3u", ".bin", ".raw"), primary=(".gdi", ".cdi", ".chd", ".m3u"),
            thumbs="Sega - Dreamcast",
            bios_optional=("dc/dc_boot.bin", "dc/dc_flash.bin"),
            bios_note="dc/dc_boot.bin et dc/dc_flash.bin (recommandés)"),
    # ---------------- SNK ----------------
    Console("neogeo", "Neo Geo", "SNK", "NEO\nGEO", "#c9a227", "arcade", "retroarch", "fbneo",
            (".zip", ".7z"), thumbs="SNK - Neo Geo",
            bios_required=(("neogeo.zip",),),
            bios_note="neogeo.zip (indispensable : importe-le avec tes jeux, il sera rangé tout seul)"),
    Console("neocd", "Neo Geo CD", "SNK", "NGCD", "#a8842a", "disc", "retroarch", "neocd",
            (".cue", ".chd", ".bin", ".img"), primary=(".cue", ".chd"),
            thumbs="SNK - Neo Geo CD",
            bios_required=(("neocd/neocd_f.rom", "neocd/neocd_sf.rom", "neocd/neocd_t.rom",
                            "neocd/neocd_st.rom", "neocd/neocd_z.rom", "neocd/neocd_sz.rom",
                            "neocd/front-sp1.bin", "neocd/top-sp1.bin", "neocd/neocd.bin",
                            "neocd/uni-bioscd.rom"),
                           ("neocd/000-lo.lo", "neocd/ng-lo.rom")),
            bios_note="dans BIOS/neocd : un BIOS (neocd_f.rom, neocd_z.rom…) + 000-lo.lo"),
    Console("ngp", "Neo Geo Pocket", "SNK", "NGP", "#4a4a52", "handheld", "retroarch", "mednafen_ngp",
            (".ngp", ".zip"), thumbs="SNK - Neo Geo Pocket"),
    Console("ngpc", "Neo Geo Pocket Color", "SNK", "NGPC", "#2f7fb5", "handheld", "retroarch", "mednafen_ngp",
            (".ngc", ".zip"), thumbs="SNK - Neo Geo Pocket Color"),
]

BY_ID = {c.id: c for c in CONSOLES}
FAMILIES = ["Nintendo", "Sega", "SNK"]

# Fichiers BIOS reconnus à l'import -> chemin dans le dossier BIOS
BIOS_FILES = {
    "neogeo.zip": "neogeo.zip",
    "disksys.rom": "disksys.rom",
    "gba_bios.bin": "gba_bios.bin",
    "bios_cd_e.bin": "bios_CD_E.bin",
    "bios_cd_u.bin": "bios_CD_U.bin",
    "bios_cd_j.bin": "bios_CD_J.bin",
    "mpr-17933.bin": "mpr-17933.bin",
    "sega_101.bin": "sega_101.bin",
    "dc_boot.bin": "dc/dc_boot.bin",
    "dc_flash.bin": "dc/dc_flash.bin",
    "neocd_f.rom": "neocd/neocd_f.rom",
    "neocd_sf.rom": "neocd/neocd_sf.rom",
    "neocd_t.rom": "neocd/neocd_t.rom",
    "neocd_st.rom": "neocd/neocd_st.rom",
    "neocd_z.rom": "neocd/neocd_z.rom",
    "neocd_sz.rom": "neocd/neocd_sz.rom",
    "front-sp1.bin": "neocd/front-sp1.bin",
    "top-sp1.bin": "neocd/top-sp1.bin",
    "neocd.bin": "neocd/neocd.bin",
    "uni-bioscd.rom": "neocd/uni-bioscd.rom",
    "000-lo.lo": "neocd/000-lo.lo",
    "ng-lo.rom": "neocd/ng-lo.rom",
}

RETROARCH_CORES = sorted({c.core for c in CONSOLES if c.engine == "retroarch"})
