"""Test automatique de l'interface (sans écran) : erreurs + vitesse, avec beaucoup de jeux."""
import os
import sys
import tempfile
import time
import traceback
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["RETROSTATION_HOME"] = tempfile.mkdtemp()
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def notice(msg):
    print(f"::notice::{msg}", flush=True)


def main():
    from PySide6.QtWidgets import QApplication
    from retrostation import paths, covers, photos, ui
    from retrostation.library import console_dir

    paths.ensure_dirs()
    n_nes, n_gb = 2000, 1000
    for cid, n, ext, head in (("nes", n_nes, ".nes", b"NES\x1a"), ("gb", n_gb, ".gb", b"")):
        d = console_dir(cid)
        d.mkdir(parents=True, exist_ok=True)
        for i in range(n):
            name = f"Jeu Test {i:04d}" + (" Zelda" if i % 100 == 0 else "") + " (Europe)"
            (d / (name + ext)).write_bytes(head + bytes(64))
    covers.download_cover = lambda g: None
    photos.download = lambda cid: False
    ui.MainWindow._first_run = lambda self: None

    app = QApplication([])
    ui.QMessageBox.information = staticmethod(lambda *a, **k: None)
    t = time.perf_counter()
    w = ui.MainWindow()
    w.resize(1400, 900)
    w.show()
    notice(f"Ouverture de la fenêtre avec {n_nes + n_gb} jeux : {time.perf_counter() - t:.2f} s")

    def pump(sec):
        end = time.perf_counter() + sec
        while time.perf_counter() < end:
            app.processEvents()
            time.sleep(0.005)

    pump(1.5)
    assert w.model.rowCount() == n_nes + n_gb, w.model.rowCount()
    assert w.tile_cache, "aucune vignette dessinée"

    t = time.perf_counter()
    w._select_filter("gb")
    notice(f"Filtre par console : {(time.perf_counter() - t) * 1000:.0f} ms")
    assert w.model.rowCount() == n_gb and all(g.console == "gb" for g in w.model.games)

    w._select_filter("fam:Nintendo")
    assert w.model.rowCount() == n_nes + n_gb
    w._select_filter("all")

    t = time.perf_counter()
    w.search.setText("zelda")
    w.populate()
    notice(f"Recherche : {(time.perf_counter() - t) * 1000:.0f} ms ({w.model.rowCount()} résultats)")
    assert w.model.rowCount() == (n_nes + n_gb) // 100
    w.search.setText("")
    w.populate()

    t = time.perf_counter()
    for _ in range(40):
        w.grid.verticalScrollBar().setValue(w.grid.verticalScrollBar().value() + 400)
        pump(0.02)
    notice(f"Défilement (40 pas) : {time.perf_counter() - t:.2f} s, vignettes en mémoire : {len(w.tile_cache)}")

    # fenêtres secondaires
    dd = ui.DisplayDialog(w, "gb")
    dd._set(dd.bezel, "tv")
    dd._changed()
    dd._set(dd.bezel, "none")
    dd._changed()
    dd.close()
    ui.SettingsDialog(w).close()
    t = time.perf_counter()
    cd = ui.CleanupDialog(w)
    while cd.tree.topLevelItemCount() == 0 and time.perf_counter() - t < 30:
        pump(0.1)
    assert cd.tree.topLevelItemCount() > 0, cd.info.text()
    notice(f"Analyse des doublons ({n_nes + n_gb} jeux) : {time.perf_counter() - t:.2f} s, "
           f"{len(cd._checked())} fichiers proposés")
    cd.close()
    w.hide_var.setChecked(True)
    assert w.model.rowCount() >= 1
    w.hide_var.setChecked(False)
    w._select_filter("all")
    w._pad_poll()
    w._cycle_console(1)
    w._select_filter("all")
    g = w.current_game()
    assert g is not None
    w._cover_ready(g.key)
    pump(0.3)
    w.close()
    notice("Test de l'interface : OK")


try:
    main()
except Exception:
    tb = traceback.format_exc()
    print(tb)
    print("::error::" + tb.replace("\n", "%0A"))
    sys.exit(1)
