"""Rétro Station — par Fabrice M. (point d'entrée)."""
import sys
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

try:
    from retrostation.ui import main
    main()
except SystemExit:
    raise
except Exception:
    err = traceback.format_exc()
    log = Path.home() / "RetroStation" / "Journaux" / "erreur_demarrage.txt"
    log.parent.mkdir(parents=True, exist_ok=True)
    log.write_text(err, encoding="utf-8")
    if sys.platform.startswith("win"):
        import ctypes
        ctypes.windll.user32.MessageBoxW(0, "Rétro Station n'a pas pu démarrer.\n\n" + err[-900:],
                                         "Rétro Station", 0x10)
    else:
        print(err)
    sys.exit(1)
