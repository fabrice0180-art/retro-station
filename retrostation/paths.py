"""Emplacements des fichiers de Rétro Station (Windows et macOS)."""
import os
import sys
import platform
from pathlib import Path

APP_NAME = "Rétro Station"
VERSION = "1.10.1"
PUBLISHER = "Fabrice M."

IS_WINDOWS = sys.platform.startswith("win")
IS_MAC = sys.platform == "darwin"

# Dossier racine : volontairement HORS de Documents pour ne pas envoyer
# des Go de jeux sur OneDrive / iCloud.
ROOT = Path(os.environ.get("RETROSTATION_HOME", str(Path.home() / "RetroStation")))

GAMES = ROOT / "Jeux"
BIOS = ROOT / "BIOS"
SAVES = ROOT / "Sauvegardes"
COVERS = ROOT / "Jaquettes"
ENGINES = ROOT / "Moteurs"
LOGS = ROOT / "Journaux"
LIBRARY_FILE = ROOT / "bibliotheque.json"
SETTINGS_FILE = ROOT / "parametres.json"

APP_DIR = Path(__file__).resolve().parent.parent
FROZEN = getattr(sys, "frozen", False)          # True dans l'appli installée (setup / DMG)
ASSETS = Path(getattr(sys, "_MEIPASS", APP_DIR)) / "assets"


def mac_arch() -> str:
    m = platform.machine().lower()
    return "arm64" if m in ("arm64", "aarch64") else "x86_64"


def ensure_dirs():
    for d in (GAMES, BIOS, BIOS / "dc", BIOS / "neocd", SAVES / "parties",
              SAVES / "etats", SAVES / "Dolphin", COVERS, ENGINES, LOGS):
        d.mkdir(parents=True, exist_ok=True)
