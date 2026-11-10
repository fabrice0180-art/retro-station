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
    # ---------------- Sony ----------------
    Console("psp", "PSP", "Sony", "PSP", "#1f2a44", "handheld", "retroarch", "ppsspp",
            (".iso", ".cso", ".pbp", ".chd"), thumbs="Sony - PlayStation Portable"),
    # ---------------- Atari ----------------
    Console("a2600", "Atari 2600", "Atari", "2600", "#8a5a2b", "home", "retroarch", "stella",
            (".a26", ".bin", ".zip"), thumbs="Atari - 2600"),
    Console("a5200", "Atari 5200", "Atari", "5200", "#3b3b44", "home", "retroarch", "a5200",
            (".a52", ".bin", ".zip"), thumbs="Atari - 5200",
            bios_required=(("5200.rom",),), bios_note="5200.rom (indispensable)"),
    Console("a7800", "Atari 7800", "Atari", "7800", "#b0252f", "home", "retroarch", "prosystem",
            (".a78", ".bin", ".zip"), thumbs="Atari - 7800",
            bios_optional=("7800 BIOS (U).rom", "7800 BIOS (E).rom"), bios_note="7800 BIOS (U).rom (facultatif)"),
    Console("lynx", "Atari Lynx", "Atari", "LYNX", "#d0612a", "handheld", "retroarch", "handy",
            (".lnx", ".o", ".zip"), thumbs="Atari - Lynx",
            bios_required=(("lynxboot.img",),), bios_note="lynxboot.img (indispensable)"),
    Console("jaguar", "Atari Jaguar", "Atari", "JAG", "#1d1d22", "home", "retroarch", "virtualjaguar",
            (".j64", ".jag", ".abs", ".cof", ".zip"), thumbs="Atari - Jaguar"),
    Console("atarist", "Atari ST", "Atari", "ST", "#7d8794", "computer", "retroarch", "hatari",
            (".st", ".msa", ".stx", ".dim", ".ipf", ".zip"), thumbs="Atari - ST",
            bios_required=(("tos.img",),), bios_note="tos.img (le TOS de ton Atari ST, indispensable)"),
    # ---------------- Commodore ----------------
    Console("amiga", "Amiga", "Commodore", "AMIGA", "#c8432f", "computer", "retroarch", "puae",
            (".adf", ".adz", ".dms", ".fdi", ".ipf", ".hdf", ".hdz", ".lha", ".uae", ".m3u", ".zip"),
            thumbs="Commodore - Amiga",
            bios_optional=("kick34005.A500", "kick40068.A1200", "amiga-os-130.rom", "amiga-os-310-a1200.rom"),
            bios_note="Kickstart 1.3 (kick34005.A500 ou amiga-os-130.rom) et 3.1 (kick40068.A1200 ou "
                      "amiga-os-310-a1200.rom, + rom.key pour Amiga Forever) conseillés ; sans eux, "
                      "un Kickstart libre intégré est utilisé (moins compatible)"),
    # ---------------- Arcade ----------------
    Console("arcade", "Arcade (Capcom, Konami…)", "Arcade", "ARC", "#6b2fbf", "arcade", "retroarch", "fbneo",
            (".zip", ".7z"), thumbs="FBNeo - Arcade Games",
            bios_note="Capcom CPS1 / CPS2 / CPS3 et des centaines d'autres bornes (jeux au format FinalBurn Neo)"),
    Console("mame", "Arcade (MAME)", "Arcade", "MAME", "#2f3a8f", "arcade", "retroarch", "mame",
            (".zip", ".7z"), thumbs="MAME",
            bios_note="jeux au format de la version de MAME indiquée dans Paramètres > État des BIOS"),
    # ---------------- SNK ----------------
    Console("neogeo", "Neo Geo", "SNK", "NEO\nGEO", "#c9a227", "arcade", "retroarch", "fbneo",
            (".zip", ".7z"), thumbs="FBNeo - Arcade Games",
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
FAMILIES = ["Nintendo", "Sega", "Sony", "Atari", "Commodore", "SNK", "Arcade"]

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
    "5200.rom": "5200.rom",
    "7800 bios (u).rom": "7800 BIOS (U).rom",
    "7800 bios (e).rom": "7800 BIOS (E).rom",
    "lynxboot.img": "lynxboot.img",
    "tos.img": "tos.img",
    "kick34005.a500": "kick34005.A500",
    "kick37175.a500": "kick37175.A500",
    "kick40063.a600": "kick40063.A600",
    "kick40068.a1200": "kick40068.A1200",
    "kick40068.a4000": "kick40068.A4000",
    # Kickstart au format Amiga Forever (acceptés tels quels par l'émulateur Amiga)
    "amiga-os-120.rom": "amiga-os-120.rom",
    "amiga-os-130.rom": "amiga-os-130.rom",
    "amiga-os-204.rom": "amiga-os-204.rom",
    "amiga-os-205.rom": "amiga-os-205.rom",
    "amiga-os-310-a600.rom": "amiga-os-310-a600.rom",
    "amiga-os-310-a1200.rom": "amiga-os-310-a1200.rom",
    "amiga-os-310-a4000.rom": "amiga-os-310-a4000.rom",
    "amiga-os-310-cd32.rom": "amiga-os-310-cd32.rom",
    "amiga-ext-310-cd32.rom": "amiga-ext-310-cd32.rom",
    "rom.key": "rom.key",
    "capsimg.dll": "capsimg.dll",          # lecture des disquettes .ipf (Amiga, Atari ST)
    "capsimg.so": "capsimg.so",
    "000-lo.lo": "neocd/000-lo.lo",
    "ng-lo.rom": "neocd/ng-lo.rom",
}

RETROARCH_CORES = sorted({c.core for c in CONSOLES if c.engine == "retroarch"})
