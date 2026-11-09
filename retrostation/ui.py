"""Interface de Rétro Station (PySide6) — Windows et macOS."""
from __future__ import annotations

import json
import sys
import time
import traceback
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from PySide6.QtCore import (Qt, QSize, QTimer, QObject, Signal, QRunnable, QThreadPool,
                            QProcess, QUrl, QRectF, QEvent)
from PySide6.QtGui import (QIcon, QPixmap, QPainter, QColor, QLinearGradient, QPainterPath,
                           QFont, QKeyEvent, QDesktopServices, QPalette, QPen)
from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QListWidget, QListWidgetItem,
                               QListView, QAbstractItemView, QHBoxLayout, QVBoxLayout, QLabel,
                               QPushButton, QLineEdit, QStackedWidget, QFileDialog, QMessageBox,
                               QInputDialog, QProgressDialog, QDialog, QProgressBar, QCheckBox,
                               QMenu, QAbstractButton, QGridLayout)

from . import paths, engines, covers, launch, gamepad, photos
from .consoles import CONSOLES, BY_ID, FAMILIES
from .library import Library, plan_import, execute_import, console_dir

TW, TH = 168, 232          # taille d'une jaquette dans la grille
ACCENT = "#ff7a45"

STYLE = f"""
* {{ font-size: 13px; color: #e8eaf2; }}
QMainWindow, QDialog {{ background: #12131a; }}
#side {{ background: #191b25; }}
#sidebar {{ background: #191b25; border: none; padding: 8px 6px; outline: 0; }}
#sidebar::item {{ padding: 6px 8px; border-radius: 9px; margin: 1px 4px; }}
#sidebar::item:selected {{ background: #2a2e40; color: white; }}
#sidebar::item:hover {{ background: #232636; }}
#grid {{ background: #12131a; border: none; outline: 0; padding: 14px; }}
#grid::item {{ border-radius: 14px; padding: 6px; color: #cfd3e3; }}
#grid::item:selected {{ background: #262a3b; color: white; }}
#grid::item:hover {{ background: #1c1f2c; }}
#title {{ font-size: 24px; font-weight: 700; color: white; }}
#subtitle {{ color: #8b90a7; }}
#brand {{ font-size: 18px; font-weight: 800; color: white; padding: 4px 8px; }}
#brandsub {{ color: #8b90a7; padding: 0 8px 10px 8px; font-size: 11px; }}
QLineEdit {{ background: #1c1f2c; border: 1px solid #2c3044; border-radius: 10px; padding: 8px 12px; }}
QLineEdit:focus {{ border-color: {ACCENT}; }}
QPushButton {{ background: #232636; border: 1px solid #30354b; border-radius: 10px; padding: 8px 14px; }}
QPushButton:hover {{ background: #2c3044; }}
QPushButton:focus {{ border-color: {ACCENT}; }}
QPushButton#primary {{ background: {ACCENT}; border: none; color: #1a0d07; font-weight: 700; padding: 10px 18px; }}
QPushButton#primary:hover {{ background: #ff8f61; }}
QPushButton#big {{ background: {ACCENT}; border: none; color: #1a0d07; font-size: 16px; font-weight: 800; padding: 16px 30px; border-radius: 14px; }}
QProgressBar {{ background: #1c1f2c; border: none; border-radius: 6px; height: 12px; text-align: center; }}
QProgressBar::chunk {{ background: {ACCENT}; border-radius: 6px; }}
QMenu {{ background: #1c1f2c; border: 1px solid #30354b; padding: 6px; }}
QMenu::item {{ padding: 6px 18px; border-radius: 6px; }}
QMenu::item:selected {{ background: #2c3044; }}
QCheckBox {{ spacing: 10px; }}
QScrollBar:vertical {{ background: transparent; width: 10px; }}
QScrollBar::handle:vertical {{ background: #2c3044; border-radius: 5px; min-height: 30px; }}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; }}
QMessageBox QLabel {{ color: #e8eaf2; }}
QComboBox {{ background: #1c1f2c; border: 1px solid #2c3044; border-radius: 8px; padding: 6px 10px; min-width: 260px; }}
QComboBox QAbstractItemView {{ background: #1c1f2c; selection-background-color: #2c3044; }}
QToolTip {{ background: #232636; color: #e8eaf2; border: 1px solid #30354b; padding: 6px; }}
"""


# ------------------------------------------------------------------ réglages
DEFAULTS = {"fullscreen": True, "move_files": False, "dolphin_controls": "auto", "asked_engines": False}


def load_settings():
    try:
        s = json.loads(paths.SETTINGS_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        s = {}
    return {**DEFAULTS, **s}


def save_settings(s):
    paths.SETTINGS_FILE.write_text(json.dumps(s, indent=1), encoding="utf-8")


# ------------------------------------------------------------------ tâches de fond
class Signals(QObject):
    progress = Signal(str, float)
    done = Signal(object)
    cover = Signal(str)


class Task(QRunnable):
    def __init__(self, fn, *args):
        super().__init__()
        self.fn, self.args = fn, args
        self.signals = Signals()
        self.setAutoDelete(False)

    def run(self):
        try:
            res = self.fn(self.signals, *self.args)
        except Exception as e:  # remonté à l'interface
            traceback.print_exc()
            res = e
        self.signals.done.emit(res)


# ------------------------------------------------------------------ icônes
_icon_cache = {}


def console_pixmap(cid: str, size: int) -> QPixmap:
    key = (cid, size)
    if key in _icon_cache:
        return _icon_cache[key]
    f = paths.ASSETS / "consoles" / f"{cid}.png"
    pm = QPixmap(str(f)) if f.exists() else QPixmap()
    if pm.isNull():
        pm = QPixmap(size, size)
        pm.fill(QColor(BY_ID[cid].color))
    pm = pm.scaled(size, size, Qt.AspectRatioMode.KeepAspectRatio,
                   Qt.TransformationMode.SmoothTransformation)
    _icon_cache[key] = pm
    return pm


def console_card(cid: str, w: int, h: int) -> QPixmap:
    """Mini-photo de la console sur une carte claire arrondie (ou l'icône d'origine)."""
    key = ("card", cid, w, h)
    if key in _icon_cache:
        return _icon_cache[key]
    src = photos.best(cid)
    img = QPixmap(str(src)) if src else QPixmap()
    pm = QPixmap(w, h)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
    rad = max(4, min(w, h) * 0.18)
    if img.isNull():
        ic = console_pixmap(cid, min(w, h))
        p.drawPixmap((w - ic.width()) // 2, (h - ic.height()) // 2, ic)
    else:
        clip = QPainterPath()
        clip.addRoundedRect(QRectF(0, 0, w, h), rad, rad)
        p.setClipPath(clip)
        g = QLinearGradient(0, 0, 0, h)
        g.setColorAt(0, QColor("#f7f8fc"))
        g.setColorAt(1, QColor("#d8dbe8"))
        p.fillRect(0, 0, w, h, g)
        pad = max(2, int(min(w, h) * 0.08))
        s = img.scaled(w - 2 * pad, h - 2 * pad, Qt.AspectRatioMode.KeepAspectRatio,
                       Qt.TransformationMode.SmoothTransformation)
        p.drawPixmap((w - s.width()) // 2, (h - s.height()) // 2, s)
        p.setClipping(False)
        p.setPen(QPen(QColor(BY_ID[cid].color), max(1.5, h * 0.05)))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRoundedRect(QRectF(0.5, 0.5, w - 1, h - 1), rad, rad)
    p.end()
    _icon_cache[key] = pm
    return pm


def make_tile(game, cover: Path | None) -> QPixmap:
    c = BY_ID[game.console]
    pm = QPixmap(TW, TH)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
    clip = QPainterPath()
    clip.addRoundedRect(QRectF(0, 0, TW, TH), 14, 14)
    p.setClipPath(clip)
    img = QPixmap(str(cover)) if cover else QPixmap()
    if not img.isNull():
        p.fillRect(0, 0, TW, TH, QColor("#0d0e14"))
        s = img.scaled(TW, TH, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
        p.drawPixmap((TW - s.width()) // 2, (TH - s.height()) // 2, s)
    else:
        base = QColor(c.color)
        g = QLinearGradient(0, 0, TW, TH)
        g.setColorAt(0, base.lighter(135))
        g.setColorAt(1, base.darker(190))
        p.fillRect(0, 0, TW, TH, g)
        ic = console_card(c.id, 136, 86)
        p.drawPixmap((TW - ic.width()) // 2, 34, ic)
        f = QFont()
        f.setPixelSize(15)
        f.setBold(True)
        p.setFont(f)
        p.setPen(QColor("white"))
        p.drawText(QRectF(12, 132, TW - 24, TH - 150),
                   int(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop) | int(Qt.TextFlag.TextWordWrap),
                   game.title)
    # mini-photo de la console en bas à droite
    p.setClipping(False)
    badge = console_card(c.id, 52, 32)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor(0, 0, 0, 120))
    p.drawRoundedRect(QRectF(TW - 59, TH - 39, 56, 36), 8, 8)
    p.drawPixmap(TW - 57, TH - 37, badge)
    p.end()
    return pm


# ------------------------------------------------------------------ installation des moteurs
class EngineDialog(QDialog):
    def __init__(self, parent, force=False):
        super().__init__(parent)
        self.setWindowTitle("Installation des moteurs d'émulation")
        self.setMinimumWidth(520)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(26, 24, 26, 24)
        lay.setSpacing(14)
        t = QLabel("Téléchargement des moteurs")
        t.setObjectName("title")
        lay.addWidget(t)
        self.info = QLabel("RetroArch, ses cœurs d'émulation et Dolphin (environ 300 Mo). "
                           "À faire une seule fois.")
        self.info.setWordWrap(True)
        self.info.setObjectName("subtitle")
        lay.addWidget(self.info)
        self.step = QLabel("Préparation…")
        lay.addWidget(self.step)
        self.bar = QProgressBar()
        self.bar.setRange(0, 1000)
        lay.addWidget(self.bar)
        self.close_btn = QPushButton("Patiente…")
        self.close_btn.setEnabled(False)
        self.close_btn.clicked.connect(self.accept)
        lay.addWidget(self.close_btn, alignment=Qt.AlignmentFlag.AlignRight)
        self.task = Task(lambda sig: engines.install_all(lambda t, f: sig.progress.emit(t, f), force))
        self.task.signals.progress.connect(self._progress)
        self.task.signals.done.connect(self._done)
        QThreadPool.globalInstance().start(self.task)

    def _progress(self, text, frac):
        self.step.setText(text)
        self.bar.setValue(int(frac * 1000))

    def _done(self, errors):
        self.bar.setValue(1000)
        self.close_btn.setEnabled(True)
        self.close_btn.setText("Fermer")
        self.close_btn.setObjectName("primary")
        self.close_btn.setStyleSheet("")
        if isinstance(errors, Exception):
            errors = [str(errors)]
        if not errors:
            self.step.setText("✅ Tout est installé. Bon jeu !")
            return
        self.step.setText("⚠️ Certains éléments n'ont pas pu être installés :")
        msg = "\n".join("• " + e for e in errors)
        if paths.IS_MAC:
            msg += ("\n\nSur Mac, tu peux aussi installer RetroArch et Dolphin à la main "
                    "(glisse-les dans Applications) : Rétro Station les trouvera tout seul.")
        self.info.setText(msg)
        row = QHBoxLayout()
        for label, url in (("Site RetroArch", engines.RETROARCH_PAGE), ("Site Dolphin", engines.DOLPHIN_PAGE)):
            b = QPushButton(label)
            b.clicked.connect(lambda _=False, u=url: QDesktopServices.openUrl(QUrl(u)))
            row.addWidget(b)
        self.layout().insertLayout(4, row)

    def reject(self):
        if self.close_btn.isEnabled():
            super().reject()


# ------------------------------------------------------------------ réglages
class SettingsDialog(QDialog):
    def __init__(self, win):
        super().__init__(win)
        self.win = win
        s = win.settings
        self.setWindowTitle("Paramètres")
        self.setMinimumWidth(560)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(26, 24, 26, 24)
        lay.setSpacing(12)
        t = QLabel("Paramètres")
        t.setObjectName("title")
        lay.addWidget(t)

        self.fs = QCheckBox("Lancer les jeux en plein écran")
        self.fs.setChecked(s["fullscreen"])
        self.mv = QCheckBox("À l'import, déplacer les fichiers au lieu de les copier (plus rapide)")
        self.mv.setChecked(s["move_files"])
        self.dc = QCheckBox("Régler tout seul les commandes Wii / GameCube (manette si branchée, sinon clavier + souris)")
        self.dc.setChecked(s["dolphin_controls"] == "auto")
        self.dc.setVisible(paths.IS_WINDOWS)
        for w in (self.fs, self.mv, self.dc):
            lay.addWidget(w)

        grid = QGridLayout()
        buttons = [
            ("Ouvrir le dossier des jeux", lambda: self._open(paths.GAMES)),
            ("Ouvrir le dossier BIOS", lambda: self._open(paths.BIOS)),
            ("Installer / mettre à jour les moteurs", lambda: EngineDialog(self, force=True).exec()),
            ("Chercher jaquettes et photos manquantes", self._covers),
            ("État des BIOS", self._bios),
            ("Commandes clavier / manette", lambda: show_controls(self)),
        ]
        for i, (label, fn) in enumerate(buttons):
            b = QPushButton(label)
            b.clicked.connect(lambda _=False, f=fn: f())
            grid.addWidget(b, i // 2, i % 2)
        lay.addLayout(grid)

        foot = QLabel(f"{paths.APP_NAME} {paths.VERSION} — par {paths.PUBLISHER}\nDossier : {paths.ROOT}\n"
                      "Photos des consoles : Evan-Amos et contributeurs de Wikimedia Commons "
                      "(domaine public / CC BY-SA). Jaquettes : libretro-thumbnails.")
        foot.setWordWrap(True)
        foot.setObjectName("subtitle")
        lay.addWidget(foot)
        ok = QPushButton("Enregistrer")
        ok.setObjectName("primary")
        ok.clicked.connect(lambda: self._save())
        lay.addWidget(ok, alignment=Qt.AlignmentFlag.AlignRight)

    def _open(self, p):
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(p)))

    def _covers(self):
        covers.forget_missing()
        photos.forget_missing()
        self.win.fetch_covers()
        self.win.fetch_photos()
        QMessageBox.information(self, "Jaquettes", "Recherche des jaquettes et des photos de consoles relancée.")

    def _bios(self):
        lines = []
        for c in CONSOLES:
            if not (c.bios_required or c.bios_optional):
                continue
            miss = launch.missing_bios(c.id)
            ok = "✅" if not miss else "❌"
            if not c.bios_required:
                ok = "➖"
            lines.append(f"{ok}  {c.name} — {c.bios_note}")
        QMessageBox.information(self, "État des BIOS",
                                "Les BIOS se copient depuis ta propre console.\n"
                                "Importe-les comme des jeux : ils sont rangés tout seuls.\n\n" + "\n".join(lines))

    def _save(self):
        s = self.win.settings
        s["fullscreen"] = self.fs.isChecked()
        s["move_files"] = self.mv.isChecked()
        s["dolphin_controls"] = "auto" if self.dc.isChecked() else "manuel"
        save_settings(s)
        self.accept()


def show_controls(parent):
    quit_hint = ("Maintenir Select + Start (manette)" if paths.IS_WINDOWS else "Select + Start (manette)")
    QMessageBox.information(parent, "Commandes", f"""DANS LES MENUS
• Souris : un clic sur un jeu le lance (clic droit = options)
• Clavier : flèches + Entrée, Échap pour revenir à la liste des consoles
• Manette (Windows) : croix / stick, A = jouer, B = retour, LB / RB = console précédente / suivante, Y = favori

DANS LES JEUX (NES, Super Nintendo, Game Boy, N64, Sega, Neo Geo)
• Manette : reconnue automatiquement
• Clavier : flèches, X = A, Z = B, S = X, A = Y, Q / W = L / R, Entrée = Start, Maj droite = Select
• F1 = menu, F2 = sauvegarde rapide, F4 = chargement rapide, Espace = accéléré
• Quitter : Échap, ou {quit_hint}. Menu à la manette : L3 + R3
• La partie reprend automatiquement là où tu l'avais laissée

WII / GAMECUBE
• Souris = pointeur de la Wiimote, clic gauche = A, clic droit = B
• Manette : stick droit = pointeur, gâchette droite = B, Start = +, Select = −
• Quitter : Échap""")


# ------------------------------------------------------------------ fenêtre principale
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.settings = load_settings()
        self.lib = Library()
        self.filter = "all"
        self.proc = None
        self.running_game = None
        self.started = 0.0
        self.hold_since = None
        self.tasks = []
        self.items = {}
        self.cover_pool = ThreadPoolExecutor(4)
        self.cover_pending = set()
        self.cover_signals = Signals()
        self.cover_signals.cover.connect(self._cover_ready)
        self.photo_signals = Signals()
        self.photo_signals.done.connect(self._photos_ready)

        self.setWindowTitle(f"{paths.APP_NAME} — par {paths.PUBLISHER}")
        ico = paths.ASSETS / "icon.png"
        if ico.exists():
            self.setWindowIcon(QIcon(str(ico)))
        self.resize(1280, 800)
        self.setAcceptDrops(True)
        self._build()
        self.refresh()

        self.pad_prev = 0
        self.pad_next_repeat = 0.0
        self.pad_timer = QTimer(self, interval=16, timeout=self._pad_poll)
        self.pad_timer.start()
        QTimer.singleShot(400, self._first_run)
        QTimer.singleShot(200, self.fetch_photos)

    # ---------------- construction
    def _build(self):
        root = QWidget()
        h = QHBoxLayout(root)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(0)

        side = QWidget()
        side.setFixedWidth(250)
        side.setObjectName("side")
        side.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        sv = QVBoxLayout(side)
        sv.setContentsMargins(8, 16, 8, 12)
        brand_row = QHBoxLayout()
        logo = QLabel()
        lp = paths.ASSETS / "icon.png"
        if lp.exists():
            logo.setPixmap(QPixmap(str(lp)).scaled(40, 40, Qt.AspectRatioMode.KeepAspectRatio,
                                                   Qt.TransformationMode.SmoothTransformation))
        brand_row.addWidget(logo)
        bl = QVBoxLayout()
        b1 = QLabel(paths.APP_NAME)
        b1.setObjectName("brand")
        b2 = QLabel(f"par {paths.PUBLISHER}")
        b2.setObjectName("brandsub")
        bl.addWidget(b1)
        bl.addWidget(b2)
        brand_row.addLayout(bl, 1)
        sv.addLayout(brand_row)
        self.sidebar = QListWidget(objectName="sidebar")
        self.sidebar.setIconSize(QSize(54, 33))
        self.sidebar.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.sidebar.customContextMenuRequested.connect(self._side_menu)
        self.sidebar.currentItemChanged.connect(self._side_changed)
        self.sidebar.installEventFilter(self)
        sv.addWidget(self.sidebar, 1)
        gear = QPushButton("⚙  Paramètres")
        gear.clicked.connect(lambda: SettingsDialog(self).exec())
        sv.addWidget(gear)
        h.addWidget(side)

        main = QWidget()
        mv = QVBoxLayout(main)
        mv.setContentsMargins(26, 20, 20, 8)
        top = QHBoxLayout()
        tl = QVBoxLayout()
        self.title = QLabel("Tous les jeux", objectName="title")
        self.subtitle = QLabel("", objectName="subtitle")
        tl.addWidget(self.title)
        tl.addWidget(self.subtitle)
        top.addLayout(tl, 1)
        self.search = QLineEdit(placeholderText="🔍  Rechercher un jeu…")
        self.search.setFixedWidth(260)
        self.search.textChanged.connect(lambda _t: self.populate())
        top.addWidget(self.search)
        imp = QPushButton("＋  Importer des jeux", objectName="primary")
        imp.setToolTip("Sélectionne tous tes jeux d'un coup : ils sont rangés tout seuls par console")
        imp.clicked.connect(lambda: self.import_files())
        top.addWidget(imp)
        imp_dir = QPushButton("📁  Un dossier entier")
        imp_dir.clicked.connect(lambda: self.import_folder())
        top.addWidget(imp_dir)
        mv.addLayout(top)

        self.stack = QStackedWidget()
        self.grid = QListWidget(objectName="grid")
        g = self.grid
        g.setViewMode(QListView.ViewMode.IconMode)
        g.setResizeMode(QListView.ResizeMode.Adjust)
        g.setMovement(QListView.Movement.Static)
        g.setIconSize(QSize(TW, TH))
        g.setGridSize(QSize(TW + 30, TH + 58))
        g.setWordWrap(True)
        g.setUniformItemSizes(True)
        g.setSpacing(6)
        g.setDragDropMode(QAbstractItemView.DragDropMode.NoDragDrop)
        g.setAcceptDrops(False)
        g.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        g.itemClicked.connect(self._play_item)
        g.itemActivated.connect(self._play_item)
        g.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        g.customContextMenuRequested.connect(self._context_menu)
        g.installEventFilter(self)
        self.stack.addWidget(self.grid)

        empty = QWidget()
        ev = QVBoxLayout(empty)
        ev.addStretch(1)
        big_logo = QLabel(alignment=Qt.AlignmentFlag.AlignCenter)
        if lp.exists():
            big_logo.setPixmap(QPixmap(str(lp)).scaled(140, 140, Qt.AspectRatioMode.KeepAspectRatio,
                                                       Qt.TransformationMode.SmoothTransformation))
        ev.addWidget(big_logo)
        t = QLabel("Ta ludothèque est vide", objectName="title", alignment=Qt.AlignmentFlag.AlignCenter)
        ev.addWidget(t)
        st = QLabel("Sélectionne tous tes jeux d'un coup (ou glisse-les sur cette fenêtre) :\n"
                    "ils seront rangés tout seuls par console, avec leur jaquette.",
                    objectName="subtitle", alignment=Qt.AlignmentFlag.AlignCenter)
        ev.addWidget(st)
        bb = QPushButton("＋  Importer des jeux", objectName="big")
        bb.clicked.connect(lambda: self.import_files())
        ev.addWidget(bb, alignment=Qt.AlignmentFlag.AlignCenter)
        ev.addStretch(2)
        self.stack.addWidget(empty)
        self.empty_page = empty
        mv.addWidget(self.stack, 1)

        self.status = QLabel("", objectName="subtitle")
        mv.addWidget(self.status)
        h.addWidget(main, 1)
        self.setCentralWidget(root)

    # ---------------- données
    def refresh(self):
        self.lib.scan()
        counts = self.lib.counts()
        keep = self.filter
        self.sidebar.blockSignals(True)
        self.sidebar.clear()

        def add(text, key, icon=None, header=False):
            it = QListWidgetItem(text)
            if icon:
                it.setIcon(QIcon(icon))
            if header:
                it.setFlags(Qt.ItemFlag.NoItemFlags)
                f = QFont()
                f.setPixelSize(11)
                f.setBold(True)
                it.setFont(f)
                it.setForeground(QColor("#6f7491"))
            else:
                it.setData(Qt.ItemDataRole.UserRole, key)
            self.sidebar.addItem(it)
            return it

        total = len(self.lib.games)
        add(f"🎮  Tous les jeux   {total}", "all")
        add("⭐  Favoris", "fav")
        add("🕘  Récents", "recent")
        for fam in FAMILIES:
            cons = [c for c in CONSOLES if c.family == fam and counts[c.id]]
            if not cons:
                continue
            add(fam.upper(), None, header=True)
            for c in cons:
                add(f"{c.name}   {counts[c.id]}", c.id, console_card(c.id, 54, 33))
        self.sidebar.blockSignals(False)
        self._select_filter(keep if keep in ("all", "fav", "recent") or counts.get(keep) else "all")
        self.fetch_covers()

    def _select_filter(self, key):
        for i in range(self.sidebar.count()):
            if self.sidebar.item(i).data(Qt.ItemDataRole.UserRole) == key:
                self.sidebar.setCurrentRow(i)
                break
        self.filter = key
        self.populate()

    def _side_changed(self, cur, _prev):
        if cur and cur.data(Qt.ItemDataRole.UserRole):
            self.filter = cur.data(Qt.ItemDataRole.UserRole)
            self.populate()

    def visible_games(self):
        q = self.search.text().strip().lower()
        gs = self.lib.games
        if self.filter == "fav":
            gs = [g for g in gs if self.lib.meta.get(g.key, {}).get("fav")]
        elif self.filter == "recent":
            gs = [g for g in gs if self.lib.meta.get(g.key, {}).get("last")]
            gs.sort(key=lambda g: -self.lib.meta[g.key]["last"])
            gs = gs[:30]
        elif self.filter in BY_ID:
            gs = [g for g in gs if g.console == self.filter]
        if q:
            gs = [g for g in gs if q in g.title.lower()]
        return gs

    def populate(self):
        names = {"all": "Tous les jeux", "fav": "Favoris", "recent": "Joués récemment"}
        self.title.setText(names.get(self.filter) or BY_ID[self.filter].name)
        gs = self.visible_games()
        n = len(gs)
        self.subtitle.setText(f"{n} jeu" + ("x" if n > 1 else ""))
        self.grid.clear()
        self.items = {}
        for g in gs:
            it = QListWidgetItem(QIcon(make_tile(g, covers.best_cover(g))), g.title)
            it.setData(Qt.ItemDataRole.UserRole, g)
            tip = f"{g.title}\n{BY_ID[g.console].name}" + (f" · {g.region}" if g.region else "")
            it.setToolTip(tip + f"\n{g.path.name}")
            it.setSizeHint(QSize(TW + 26, TH + 52))
            self.grid.addItem(it)
            self.items[g.key] = it
        self.stack.setCurrentWidget(self.empty_page if not self.lib.games else self.grid)
        if self.grid.count():
            self.grid.setCurrentRow(0)

    # ---------------- jaquettes
    def fetch_covers(self):
        todo = [g for g in self.lib.games if g.key not in self.cover_pending
                and not covers.best_cover(g) and not covers.cover_file(g).with_suffix(".absent").exists()]
        self.cover_pending.update(g.key for g in todo)
        sig = self.cover_signals

        def job(g):
            if covers.download_cover(g):
                sig.cover.emit(g.key)
        for g in todo:
            self.cover_pool.submit(job, g)

    def fetch_photos(self):
        todo = [c.id for c in CONSOLES if not photos.best(c.id)]
        if not todo:
            return
        sig = self.photo_signals

        def job():
            got = sum(1 for cid in todo if photos.download(cid))
            sig.done.emit(got)
        self.cover_pool.submit(job)

    def _photos_ready(self, got):
        if got:
            _icon_cache.clear()
            self.refresh()

    def _side_menu(self, pos):
        it = self.sidebar.itemAt(pos)
        cid = it.data(Qt.ItemDataRole.UserRole) if it else None
        if cid not in BY_ID:
            return
        m = QMenu(self)
        m.addAction("📷  Mettre ma propre photo de la console…", lambda: self._set_console_photo(cid))
        if photos.custom(cid).exists():
            m.addAction("↺  Remettre la photo d'origine", lambda: self._reset_console_photo(cid))
        m.exec(self.sidebar.viewport().mapToGlobal(pos))

    def _set_console_photo(self, cid):
        f, _ = QFileDialog.getOpenFileName(self, f"Photo pour {BY_ID[cid].name}", str(Path.home()),
                                           "Images (*.png *.jpg *.jpeg *.webp)")
        if f and not QPixmap(f).isNull():
            photos.ICONS.mkdir(parents=True, exist_ok=True)
            QPixmap(f).scaled(640, 640, Qt.AspectRatioMode.KeepAspectRatio,
                              Qt.TransformationMode.SmoothTransformation).save(str(photos.custom(cid)), "PNG")
            _icon_cache.clear()
            self.refresh()

    def _reset_console_photo(self, cid):
        try:
            photos.custom(cid).unlink()
        except OSError:
            pass
        _icon_cache.clear()
        self.refresh()

    def _cover_ready(self, key):
        it = self.items.get(key)
        if it:
            g = it.data(Qt.ItemDataRole.UserRole)
            it.setIcon(QIcon(make_tile(g, covers.best_cover(g))))

    # ---------------- import
    def import_files(self):
        files, _ = QFileDialog.getOpenFileNames(self, "Sélectionne tes jeux (Ctrl+A pour tout prendre)",
                                                str(Path.home()), "Tous les fichiers (*)")
        if files:
            self.start_import(files)

    def import_folder(self):
        d = QFileDialog.getExistingDirectory(self, "Choisis le dossier qui contient tes jeux", str(Path.home()))
        if d:
            self.start_import([d])

    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()

    def dropEvent(self, e):
        files = [u.toLocalFile() for u in e.mimeData().urls() if u.isLocalFile()]
        if files:
            self.start_import(files)

    def start_import(self, selection):
        self.status.setText("Analyse des fichiers…")
        t = Task(lambda sig: plan_import(selection))
        t.signals.done.connect(self._plan_ready)
        self._run(t)

    def _plan_ready(self, plan):
        self.status.setText("")
        if isinstance(plan, Exception):
            QMessageBox.warning(self, "Import", f"Erreur pendant l'analyse : {plan}")
            return
        # fichiers dont la console n'a pas pu être devinée : une question par type de fichier
        for ext, grp in plan.unknown.items():
            cands = [BY_ID[c].name for c in grp["candidates"]]
            others = [c.name for c in CONSOLES if c.name not in cands]
            choices = cands + others + ["— Ignorer ces fichiers —"]
            n = len(grp["files"])
            ex = ", ".join(f.name for f in grp["files"][:3]) + ("…" if n > 3 else "")
            choice, ok = QInputDialog.getItem(
                self, "Console à préciser",
                f"{n} fichier(s) {ext} n'ont pas pu être reconnus :\n{ex}\n\nÀ quelle console appartiennent-ils ?",
                choices, 0, False)
            if ok and not choice.startswith("—"):
                cid = next(c.id for c in CONSOLES if c.name == choice)
                plan.games += [(f, cid) for f in grp["files"]]
        if not plan.games and not plan.bios:
            QMessageBox.information(self, "Import", "Aucun jeu reconnu dans cette sélection.")
            return
        self.progress = QProgressDialog("Rangement des jeux…", None, 0, 1000, self)
        self.progress.setWindowTitle("Import")
        self.progress.setWindowModality(Qt.WindowModality.WindowModal)
        self.progress.setMinimumDuration(0)
        self.progress.setMinimumWidth(460)
        move = self.settings["move_files"]

        def work(sig):
            return execute_import(plan, move,
                                  lambda i, n, name: sig.progress.emit(name, i / max(n, 1)))
        t = Task(work)
        t.signals.progress.connect(lambda name, f: (self.progress.setValue(int(f * 1000)),
                                                    self.progress.setLabelText(f"Rangement : {name}")))
        t.signals.done.connect(lambda res, p=plan: self._import_done(res, p))
        self._run(t)

    def _import_done(self, res, plan):
        self.progress.close()
        if isinstance(res, Exception):
            QMessageBox.warning(self, "Import", f"Erreur : {res}")
            return
        added, errors = res
        per = {}
        for _, cid in plan.games:
            per[BY_ID[cid].name] = per.get(BY_ID[cid].name, 0) + 1
        lines = [f"• {name} : {n}" for name, n in sorted(per.items())]
        msg = f"{added} jeu(x) ajouté(s).\n\n" + "\n".join(lines)
        if plan.bios:
            msg += "\n\nBIOS rangés : " + ", ".join(Path(t).name for _, t in plan.bios)
        if errors:
            msg += "\n\nProblèmes :\n" + "\n".join(errors[:8])
        self.refresh()
        QMessageBox.information(self, "Import terminé", msg)

    def _run(self, task):
        self.tasks.append(task)
        task.signals.done.connect(lambda _r, t=task: self.tasks.remove(t) if t in self.tasks else None)
        QThreadPool.globalInstance().start(task)

    # ---------------- lancement
    def _first_run(self):
        if not engines.everything_installed() and not self.settings.get("asked_engines"):
            self.settings["asked_engines"] = True
            save_settings(self.settings)
            r = QMessageBox.question(self, "Bienvenue !",
                                     "Pour jouer, Rétro Station doit télécharger ses moteurs d'émulation "
                                     "(environ 300 Mo, une seule fois).\n\nLe faire maintenant ?")
            if r == QMessageBox.StandardButton.Yes:
                EngineDialog(self).exec()

    def _play_item(self, item):
        if item and self.proc is None:
            self.play(item.data(Qt.ItemDataRole.UserRole))

    def play(self, game):
        c = BY_ID[game.console]
        miss = launch.missing_bios(game.console)
        if miss:
            box = QMessageBox(self)
            box.setWindowTitle("BIOS manquant")
            box.setText(f"{c.name} a besoin de son BIOS pour démarrer :\n{c.bios_note}\n\n"
                        "Copie-le depuis ta console, puis importe-le comme un jeu.")
            open_b = box.addButton("Ouvrir le dossier BIOS", QMessageBox.ButtonRole.ActionRole)
            go = box.addButton("Lancer quand même", QMessageBox.ButtonRole.AcceptRole)
            box.addButton("Annuler", QMessageBox.ButtonRole.RejectRole)
            box.exec()
            if box.clickedButton() == open_b:
                QDesktopServices.openUrl(QUrl.fromLocalFile(str(paths.BIOS)))
                return
            if box.clickedButton() != go:
                return
        try:
            exe, args, cwd = launch.build_command(game, self.settings)
        except launch.LaunchError as e:
            r = QMessageBox.question(self, "Moteur manquant", f"{e}\n\nL'installer maintenant ?")
            if r == QMessageBox.StandardButton.Yes:
                EngineDialog(self).exec()
            return
        self.proc = QProcess(self)
        self.proc.setProgram(exe)
        self.proc.setArguments(args)
        self.proc.setWorkingDirectory(cwd)
        self.proc.finished.connect(self._game_finished)
        self.proc.errorOccurred.connect(self._game_error)
        self.running_game = game
        self.started = time.time()
        self.was_maximized = self.isMaximized() or self.isFullScreen()
        self.status.setText(f"▶  {game.title} en cours…")
        self.proc.start()
        QTimer.singleShot(700, lambda: self.proc is not None and self.showMinimized())

    def stop_game(self):
        if self.proc is not None and self.proc.state() != QProcess.ProcessState.NotRunning:
            self.proc.terminate()
            p = self.proc
            QTimer.singleShot(4000, lambda: p.state() != QProcess.ProcessState.NotRunning and p.kill())

    def _game_error(self, err):
        if err == QProcess.ProcessError.FailedToStart:
            QMessageBox.warning(self, "Lancement", "Le moteur d'émulation n'a pas pu démarrer.\n"
                                "Réinstalle les moteurs depuis les Paramètres.")
            self._game_finished(-1, None)

    def _game_finished(self, code, _status):
        if not self.running_game:
            return
        game, elapsed = self.running_game, time.time() - self.started
        self.running_game = None
        self.proc = None
        self.hold_since = None
        self.status.setText("")
        self.showMaximized() if self.was_maximized else self.showNormal()
        self.raise_()
        self.activateWindow()
        if elapsed > 5:
            self.lib.record_play(game, elapsed)
        elif code not in (0, None):
            QMessageBox.warning(self, "Le jeu s'est arrêté",
                                "Le jeu s'est fermé tout de suite. Le fichier est peut-être abîmé, "
                                "incomplet, ou il manque un BIOS.\n\nDétails techniques : dossier Journaux.")

    # ---------------- clic droit
    def _context_menu(self, pos):
        it = self.grid.itemAt(pos)
        if not it:
            return
        g = it.data(Qt.ItemDataRole.UserRole)
        fav = self.lib.meta.get(g.key, {}).get("fav")
        m = QMenu(self)
        m.addAction("▶  Jouer", lambda: self.play(g))
        m.addAction("☆  Retirer des favoris" if fav else "⭐  Ajouter aux favoris", lambda: self._fav(g))
        m.addAction("🖼  Choisir une jaquette…", lambda: self._pick_cover(g))
        m.addAction("📂  Afficher le fichier", lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(g.path.parent))))
        m.addSeparator()
        m.addAction("🗑  Supprimer de la bibliothèque", lambda: self._delete(g))
        m.exec(self.grid.viewport().mapToGlobal(pos))

    def _fav(self, g):
        self.lib.toggle_favorite(g)
        if self.filter == "fav":
            self.populate()

    def _pick_cover(self, g):
        f, _ = QFileDialog.getOpenFileName(self, "Choisir une image", str(Path.home()),
                                           "Images (*.png *.jpg *.jpeg *.webp)")
        if f:
            pm = QPixmap(f)
            if not pm.isNull():
                dest = covers.custom_cover(g)
                dest.parent.mkdir(parents=True, exist_ok=True)
                pm.save(str(dest), "PNG")
                self._cover_ready(g.key)

    def _delete(self, g):
        r = QMessageBox.question(self, "Supprimer",
                                 f"Supprimer « {g.title} » ?\nLe fichier du jeu sera effacé de "
                                 f"{console_dir(g.console)}.\n(Tes sauvegardes sont conservées.)")
        if r == QMessageBox.StandardButton.Yes:
            self.lib.remove(g, delete_file=True)
            self.refresh()

    # ---------------- clavier
    def eventFilter(self, obj, ev):
        if ev.type() == QEvent.Type.KeyPress:
            if obj is self.grid and ev.key() == Qt.Key.Key_Escape:
                self.sidebar.setFocus()
                return True
            if obj is self.sidebar and ev.key() in (Qt.Key.Key_Right, Qt.Key.Key_Return, Qt.Key.Key_Enter):
                self.grid.setFocus()
                return True
        return super().eventFilter(obj, ev)

    def keyPressEvent(self, e):
        if e.key() == Qt.Key.Key_F11:
            self.showNormal() if self.isFullScreen() else self.showFullScreen()
        else:
            super().keyPressEvent(e)

    # ---------------- manette (Windows)
    def _pad_poll(self):
        if not gamepad.AVAILABLE:
            return
        b = gamepad.read() or 0
        now = time.time()
        if self.proc is not None:
            # pendant le jeu : maintenir Select + Start 1,5 s (ou Échap sous Dolphin) = quitter
            combo = (b & gamepad.BACK) and (b & gamepad.START)
            if combo:
                self.hold_since = self.hold_since or now
                if now - self.hold_since > 1.5:
                    self.hold_since = None
                    self.stop_game()
            else:
                self.hold_since = None
            if (self.running_game and BY_ID[self.running_game.console].engine == "dolphin"
                    and gamepad.escape_pressed()):
                self.stop_game()
            self.pad_prev = b
            return
        if not QApplication.activeWindow():
            self.pad_prev = b
            return
        pressed = b & ~self.pad_prev
        dirs = b & (gamepad.UP | gamepad.DOWN | gamepad.LEFT | gamepad.RIGHT)
        if dirs and (dirs & pressed or now >= self.pad_next_repeat):
            delay = 0.35 if dirs & pressed else 0.08
            self.pad_next_repeat = now + delay
            self._pad_direction(dirs)
        if pressed & gamepad.A:
            self._pad_accept()
        if pressed & gamepad.B:
            self._key(Qt.Key.Key_Escape)
        if pressed & gamepad.Y and QApplication.activeWindow() is self:
            it = self.grid.currentItem()
            if it:
                self._fav(it.data(Qt.ItemDataRole.UserRole))
        if pressed & (gamepad.LB | gamepad.RB) and QApplication.activeWindow() is self:
            self._cycle_console(-1 if pressed & gamepad.LB else 1)
        self.pad_prev = b

    def _key(self, key):
        w = QApplication.focusWidget() or QApplication.activeWindow()
        if w:
            QApplication.postEvent(w, QKeyEvent(QEvent.Type.KeyPress, key, Qt.KeyboardModifier.NoModifier))
            QApplication.postEvent(w, QKeyEvent(QEvent.Type.KeyRelease, key, Qt.KeyboardModifier.NoModifier))

    def _pad_direction(self, dirs):
        w = QApplication.focusWidget()
        if isinstance(w, QAbstractButton):          # dans les fenêtres de dialogue
            self._key(Qt.Key.Key_Backtab if dirs & (gamepad.LEFT | gamepad.UP) else Qt.Key.Key_Tab)
            return
        if w is self.sidebar and dirs & gamepad.RIGHT:
            self.grid.setFocus()
            return
        if w is self.grid and dirs & gamepad.LEFT and self.grid.currentRow() >= 0:
            # bord gauche de la grille -> retour à la liste des consoles
            r = self.grid.visualItemRect(self.grid.currentItem())
            if r.left() < TW // 2:
                self.sidebar.setFocus()
                return
        for flag, key in ((gamepad.UP, Qt.Key.Key_Up), (gamepad.DOWN, Qt.Key.Key_Down),
                          (gamepad.LEFT, Qt.Key.Key_Left), (gamepad.RIGHT, Qt.Key.Key_Right)):
            if dirs & flag:
                self._key(key)
                break

    def _pad_accept(self):
        w = QApplication.focusWidget()
        if w is self.grid:
            self._play_item(self.grid.currentItem())
        elif w is self.sidebar:
            self.grid.setFocus()
        elif isinstance(w, QAbstractButton):
            w.click()
        else:
            self._key(Qt.Key.Key_Return)

    def _cycle_console(self, step):
        rows = [i for i in range(self.sidebar.count())
                if self.sidebar.item(i).data(Qt.ItemDataRole.UserRole)]
        cur = self.sidebar.currentRow()
        idx = rows.index(cur) if cur in rows else 0
        self.sidebar.setCurrentRow(rows[(idx + step) % len(rows)])

    def closeEvent(self, e):
        self.cover_pool.shutdown(wait=False, cancel_futures=True)
        super().closeEvent(e)


def main():
    app = QApplication(sys.argv)
    app.setApplicationName(paths.APP_NAME)
    app.setOrganizationName(paths.PUBLISHER)
    app.setStyle("Fusion")
    pal = QPalette()
    R = QPalette.ColorRole
    for role, col in ((R.Window, "#12131a"), (R.WindowText, "#e8eaf2"), (R.Base, "#1c1f2c"),
                      (R.AlternateBase, "#232636"), (R.Text, "#e8eaf2"), (R.Button, "#232636"),
                      (R.ButtonText, "#e8eaf2"), (R.Highlight, ACCENT), (R.HighlightedText, "#1a0d07"),
                      (R.ToolTipBase, "#232636"), (R.ToolTipText, "#e8eaf2"), (R.PlaceholderText, "#8b90a7")):
        pal.setColor(role, QColor(col))
    app.setPalette(pal)
    app.setStyleSheet(STYLE)
    ico = paths.ASSETS / "icon.png"
    if ico.exists():
        app.setWindowIcon(QIcon(str(ico)))
    w = MainWindow()
    w.show()
    sys.exit(app.exec())
