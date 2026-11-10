"""Interface de Rétro Station (PySide6) — Windows et macOS."""
from __future__ import annotations

import json
import sys
import time
import traceback
from concurrent.futures import ThreadPoolExecutor
from functools import lru_cache
from pathlib import Path

from PySide6.QtCore import (Qt, QSize, QTimer, QObject, Signal, QRunnable, QThreadPool, QAbstractListModel,
                            QModelIndex,
                            QProcess, QUrl, QRectF, QEvent)
from PySide6.QtGui import (QIcon, QPixmap, QPainter, QColor, QLinearGradient, QPainterPath,
                           QFont, QKeyEvent, QDesktopServices, QPalette, QPen, QImage, QFontMetrics)
from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QListWidget, QListWidgetItem,
                               QListView, QAbstractItemView, QHBoxLayout, QVBoxLayout, QLabel,
                               QPushButton, QLineEdit, QStackedWidget, QFileDialog, QMessageBox,
                               QInputDialog, QProgressDialog, QDialog, QProgressBar, QCheckBox,
                               QMenu, QAbstractButton, QGridLayout, QComboBox, QFormLayout, QSlider,
                               QStyledItemDelegate, QStyle, QTreeWidget, QTreeWidgetItem)

from . import paths, engines, covers, launch, gamepad, photos
from .consoles import CONSOLES, BY_ID, FAMILIES
from .library import (Library, plan_import, execute_import, console_dir, analyze, preferred_only,
                      export_games, EXPORT_STYLES)

TW, TH = 140, 194          # taille d'une jaquette dans la grille (réglable)
MINI_W, MINI_H = 168, 232  # taille des jaquettes réduites gardées sur disque
TILE_SIZES = (104, 168)    # largeur mini / maxi du curseur


def set_tile_width(w):
    global TW, TH
    TW = int(max(TILE_SIZES[0], min(TILE_SIZES[1], w)))
    TH = int(round(TW * 232 / 168))
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
QPushButton#letter {{ background: transparent; border: none; border-radius: 6px; padding: 3px 6px;
    min-width: 18px; color: #9aa0b8; font-weight: 600; }}
QPushButton#letter:hover {{ background: #232636; color: white; }}
QPushButton#letter:checked {{ background: {ACCENT}; color: #1a0d07; }}
QPushButton#letter:disabled {{ color: #3a3e52; }}
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
DEFAULTS = {"fullscreen": True, "move_files": False, "dolphin_controls": "auto", "asked_engines": False,
            "confirm_quit": True, "all_versions": False, "tile_w": 140}


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


_card_images = {}      # cartes des consoles, préparées une fois (lisibles depuis les tâches de fond)
TILE_CACHE_MAX = 900


def prepare_cards():
    _card_images.clear()
    for c in CONSOLES:
        for w, h in ((136, 86), (52, 32)):
            _card_images[(c.id, w, h)] = console_card(c.id, w, h).toImage()


def _mini_cover_image(cover: Path) -> QImage:
    """Jaquette réduite, gardée sur disque : bien plus rapide à relire que l'image d'origine."""
    mini = cover.parent / ".mini" / (cover.stem + ".png")
    try:
        if mini.exists() and mini.stat().st_mtime >= cover.stat().st_mtime:
            img = QImage(str(mini))
            if not img.isNull():
                return img
    except OSError:
        pass
    img = QImage(str(cover))
    if img.isNull():
        return img
    img = img.scaled(MINI_W, MINI_H, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
    try:
        mini.parent.mkdir(parents=True, exist_ok=True)
        img.save(str(mini), "PNG")
    except OSError:
        pass
    return img


def build_tile(game, cover) -> QImage:
    """Dessine la vignette d'un jeu (appelé en tâche de fond)."""
    c = BY_ID[game.console]
    out = QImage(TW, TH, QImage.Format.Format_ARGB32_Premultiplied)
    out.fill(Qt.GlobalColor.transparent)
    p = QPainter(out)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
    clip = QPainterPath()
    clip.addRoundedRect(QRectF(0, 0, TW, TH), 14, 14)
    p.setClipPath(clip)
    img = _mini_cover_image(cover) if cover else QImage()
    if not img.isNull():
        p.fillRect(0, 0, TW, TH, QColor("#0d0e14"))
        # la jaquette remplit toute la vignette, centrée (les bords qui dépassent sont rognés)
        img = img.scaled(TW, TH, Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                         Qt.TransformationMode.SmoothTransformation)
        p.drawImage((TW - img.width()) // 2, (TH - img.height()) // 2, img)
    else:
        base = QColor(c.color)
        g = QLinearGradient(0, 0, TW, TH)
        g.setColorAt(0, base.lighter(135))
        g.setColorAt(1, base.darker(190))
        p.fillRect(0, 0, TW, TH, g)
        card = _card_images.get((c.id, 136, 86))
        k = TW / 168
        if card is not None:
            cw, ch = int(136 * k), int(86 * k)
            p.drawImage(QRectF((TW - cw) / 2, 34 * k, cw, ch), card)
        f = QFont()
        f.setPixelSize(max(11, int(15 * k)))
        f.setBold(True)
        p.setFont(f)
        p.setPen(QColor("white"))
        p.drawText(QRectF(10, 132 * k, TW - 20, TH - 140 * k),
                   int(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop) | int(Qt.TextFlag.TextWordWrap),
                   game.title)
    p.setClipping(False)
    badge = _card_images.get((c.id, 52, 32))
    if badge is not None:
        k = max(0.75, TW / 168)
        bw, bh = 52 * k, 32 * k
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(0, 0, 0, 120))
        p.drawRoundedRect(QRectF(TW - bw - 7, TH - bh - 7, bw + 4, bh + 4), 7, 7)
        p.drawImage(QRectF(TW - bw - 5, TH - bh - 5, bw, bh), badge)
    p.end()
    return out


@lru_cache(maxsize=None)
def first_letter(title: str) -> str:
    """Lettre de classement : « The Legend… » et « Le Roi… » sont rangés à L / R ; chiffres = « # »."""
    import unicodedata
    t = title.strip()
    for art in ("The ", "Le ", "La ", "Les ", "L'"):
        if t.startswith(art) and len(t) > len(art):
            t = t[len(art):]
            break
    for ch in t:
        if ch.isalnum():
            ch = unicodedata.normalize("NFKD", ch)[0].upper()
            return "#" if ch.isdigit() else (ch if "A" <= ch <= "Z" else "#")
    return "#"


class TileSignals(QObject):
    ready = Signal(str, QImage)


class TileJob(QRunnable):
    def __init__(self, key, game, cover, signals):
        super().__init__()
        self.key, self.game, self.cover, self.signals = key, game, cover, signals

    def run(self):
        try:
            img = build_tile(self.game, self.cover)
        except Exception:
            img = QImage()
        self.signals.ready.emit(self.key, img)


class GameModel(QAbstractListModel):
    """Liste des jeux affichés : filtrer = remplacer la liste, c'est instantané."""

    def __init__(self):
        super().__init__()
        self.games = []

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.games)

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid() or index.row() >= len(self.games):
            return None
        g = self.games[index.row()]
        if role == Qt.ItemDataRole.DisplayRole:
            return g.title
        if role == Qt.ItemDataRole.UserRole:
            return g
        if role == Qt.ItemDataRole.ToolTipRole:
            return f"{g.title}\n{BY_ID[g.console].name}" + (f" · {g.region}" if g.region else "") + f"\n{g.path.name}"
        return None

    def set_games(self, games):
        self.beginResetModel()
        self.games = list(games)
        self.endResetModel()

    def row_of(self, key):
        for i, g in enumerate(self.games):
            if g.key == key:
                return i
        return -1


class TileDelegate(QStyledItemDelegate):
    """Ne dessine que les vignettes visibles à l'écran."""

    def __init__(self, win):
        super().__init__(win)
        self.win = win
        self.font = QFont()
        self.font.setPixelSize(13)
        self.fm = QFontMetrics(self.font)
        self.elided = {}

    def sizeHint(self, option, index):
        return QSize(TW + 22, TH + 50)

    def paint(self, p, option, index):
        g = index.data(Qt.ItemDataRole.UserRole)
        if g is None:
            return
        r = option.rect
        p.save()
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        selected = bool(option.state & QStyle.StateFlag.State_Selected)
        hover = bool(option.state & QStyle.StateFlag.State_MouseOver)
        if selected or hover:
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor("#2b3046" if selected else "#1c1f2c"))
            p.drawRoundedRect(QRectF(r.adjusted(2, 2, -2, -2)), 14, 14)
        x, y = r.x() + (r.width() - TW) // 2, r.y() + 7
        pm = self.win.tile_for(g)
        if pm is not None:
            p.drawPixmap(x, y, pm)
        else:
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(BY_ID[g.console].color).darker(170))
            p.drawRoundedRect(QRectF(x, y, TW, TH), 14, 14)
        if selected:
            p.setPen(QPen(QColor(ACCENT), 2))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawRoundedRect(QRectF(x - 1, y - 1, TW + 2, TH + 2), 15, 15)
        p.setFont(self.font)
        p.setPen(QColor("white" if selected else "#cfd3e3"))
        text = self.elided.get(g.title)
        if text is None:
            text = self.elided[g.title] = self.fm.elidedText(g.title, Qt.TextElideMode.ElideRight,
                                                             (r.width() - 14) * 2 - 20)
        p.drawText(QRectF(r.x() + 7, y + TH + 5, r.width() - 14, 38),
                   int(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop) | int(Qt.TextFlag.TextWordWrap), text)
        p.restore()


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
        self.cq = QCheckBox("Demander confirmation pour quitter un jeu (Échap deux fois)")
        self.cq.setChecked(s.get("confirm_quit", True))
        for w in (self.fs, self.mv, self.dc, self.cq):
            lay.addWidget(w)

        grid = QGridLayout()
        buttons = [
            ("Ouvrir le dossier des jeux", lambda: self._open(paths.GAMES)),
            ("Ouvrir le dossier BIOS", lambda: self._open(paths.BIOS)),
            ("Installer / mettre à jour les moteurs", lambda: EngineDialog(self, force=True).exec()),
            ("Chercher jaquettes et photos manquantes", self._covers),
            ("État des BIOS", self._bios),
            ("Commandes clavier / manette", lambda: show_controls(self)),
            ("Affichage des jeux (taille, contours…)", lambda: DisplayDialog(self.win).exec()),
        ]
        for i, (label, fn) in enumerate(buttons):
            b = QPushButton(label)
            b.clicked.connect(lambda _=False, f=fn: f())
            grid.addWidget(b, i // 2, i % 2, 1, 2 if i == len(buttons) - 1 else 1)
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
        mv = engines.mame_version()
        lines.append(f"ℹ️  Arcade (MAME) — version de MAME : {mv or 'pas encore installé'} "
                     "(tes jeux MAME doivent correspondre à cette version)")
        QMessageBox.information(self, "État des BIOS",
                                "Les BIOS se copient depuis ta propre console.\n"
                                "Importe-les comme des jeux : ils sont rangés tout seuls.\n\n" + "\n".join(lines))

    def _save(self):
        s = self.win.settings
        s["fullscreen"] = self.fs.isChecked()
        s["move_files"] = self.mv.isChecked()
        s["dolphin_controls"] = "auto" if self.dc.isChecked() else "manuel"
        s["confirm_quit"] = self.cq.isChecked()
        save_settings(s)
        self.accept()


def show_controls(parent):
    QMessageBox.information(parent, "Commandes", """DANS LES MENUS DE RÉTRO STATION
• Souris : un clic sur un jeu le lance (clic droit = options)
• Clavier : flèches + Entrée, Échap pour revenir à la liste des consoles
• Manette (Windows) : croix / stick, A = jouer, B = retour, LB / RB = console précédente / suivante, Y = favori

DANS LES JEUX (NES, Super Nintendo, Game Boy, N64, Sega, Neo Geo)
• Menu du jeu : F1, ou Select + Start à la manette
• Régler les commandes en plein jeu : menu > Commandes > Port 1 > choisis un bouton et appuie sur la touche voulue.
  Tes réglages sont gardés automatiquement pour cette console.
• Clavier par défaut : flèches, X = A, Z = B, S = X, A = Y, Q / W = L / R, Entrée = Start, Maj droite = Select
• F2 = sauvegarde rapide, F4 = chargement rapide, Espace = accéléré
• Quitter : Échap deux fois (ou menu > Quitter)
• La partie reprend automatiquement là où tu l'avais laissée

WII / GAMECUBE
• Souris = pointeur de la Wiimote, clic gauche = A, clic droit = B
• Manette : stick droit = pointeur, gâchette droite = B, Start = +, Select = −
• Régler les manettes : clic droit sur Wii ou GameCube > « Régler les manettes »
• Quitter : Échap (confirmation demandée)""")


def show_remap_help(parent, cname):
    QMessageBox.information(parent, f"Commandes — {cname}", f"""Les commandes se règlent directement pendant le jeu :

1. Lance un jeu {cname}.
2. Ouvre le menu : F1 au clavier, ou Select + Start à la manette.
3. Va dans « Commandes », puis « Port 1 » (joueur 1).
4. Choisis un bouton et appuie sur la touche ou le bouton voulu.
5. Reviens au jeu : tes réglages sont enregistrés automatiquement pour la console.

Astuce : « Enregistrer le remappage du jeu » garde des commandes spéciales pour un seul jeu.""")


# ------------------------------------------------------------------ ménage de la bibliothèque
class CleanupDialog(QDialog):
    KIND = {"identique": "Copies identiques", "versions": "Plusieurs versions du même jeu",
            "douteuse": "ROMs douteuses"}

    def __init__(self, win):
        super().__init__(win)
        self.win = win
        self.setWindowTitle("Ménage : doublons et ROMs douteuses")
        self.resize(900, 640)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(22, 20, 22, 18)
        lay.addWidget(QLabel("Ménage de la bibliothèque", objectName="title"))
        self.info = QLabel("Analyse en cours…", objectName="subtitle")
        self.info.setWordWrap(True)
        lay.addWidget(self.info)
        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["Jeu / fichier", "Console", "Pourquoi"])
        self.tree.setColumnWidth(0, 470)
        self.tree.setColumnWidth(1, 150)
        self.tree.setStyleSheet("QTreeWidget { background:#191b25; border:none; border-radius:10px; }"
                                "QHeaderView::section { background:#232636; border:none; padding:6px; }")
        lay.addWidget(self.tree, 1)
        row = QHBoxLayout()
        self.count = QLabel("", objectName="subtitle")
        row.addWidget(self.count, 1)
        close = QPushButton("Fermer")
        close.clicked.connect(lambda: self.reject())
        self.go = QPushButton("Mettre à la corbeille les fichiers cochés", objectName="primary")
        self.go.setEnabled(False)
        self.go.clicked.connect(lambda: self._trash())
        row.addWidget(close)
        row.addWidget(self.go)
        lay.addLayout(row)
        self.tree.itemChanged.connect(lambda *_: self._update_count())
        self.task = Task(lambda sig: analyze(list(win.lib.games), lambda f: sig.progress.emit("", f)))
        self.task.signals.progress.connect(lambda _t, f: self.info.setText(f"Analyse en cours… {int(f * 100)} %"))
        self.task.signals.done.connect(self._show)
        QThreadPool.globalInstance().start(self.task)

    def _show(self, groups):
        if isinstance(groups, Exception):
            self.info.setText(f"Erreur pendant l'analyse : {groups}")
            return
        if not groups:
            self.info.setText("✅ Aucun doublon ni ROM douteuse : ta bibliothèque est propre.")
            return
        self.info.setText("Coche ce que tu veux retirer (les propositions sont déjà cochées). "
                          "Les fichiers vont dans la corbeille de ton ordinateur : tu peux les récupérer.")
        self.tree.blockSignals(True)
        for kind in ("identique", "versions", "douteuse"):
            sub = [g for g in groups if g["kind"] == kind]
            if not sub:
                continue
            top = QTreeWidgetItem([f"{self.KIND[kind]} ({len(sub) if kind != 'douteuse' else len(sub[0]['items'])})"])
            f = top.font(0)
            f.setBold(True)
            top.setFont(0, f)
            self.tree.addTopLevelItem(top)
            for grp in sub:
                parent = top
                if kind != "douteuse":
                    parent = QTreeWidgetItem([grp["title"], BY_ID[grp["console"]].name, ""])
                    top.addChild(parent)
                for game, why, remove in grp["items"]:
                    it = QTreeWidgetItem([game.path.name, BY_ID[game.console].name, why])
                    it.setData(0, Qt.ItemDataRole.UserRole, game)
                    it.setFlags(it.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                    it.setCheckState(0, Qt.CheckState.Checked if remove else Qt.CheckState.Unchecked)
                    parent.addChild(it)
                parent.setExpanded(True)
            top.setExpanded(True)
        self.tree.blockSignals(False)
        self._update_count()

    def _checked(self):
        out = []

        def walk(item):
            for i in range(item.childCount()):
                c = item.child(i)
                g = c.data(0, Qt.ItemDataRole.UserRole)
                if g is not None and c.checkState(0) == Qt.CheckState.Checked:
                    out.append(g)
                walk(c)
        walk(self.tree.invisibleRootItem())
        uniq = {g.key: g for g in out}
        return list(uniq.values())

    def _update_count(self):
        n = len(self._checked())
        self.count.setText(f"{n} fichier(s) coché(s)")
        self.go.setEnabled(n > 0)

    def _trash(self):
        games = self._checked()
        r = QMessageBox.question(self, "Ménage", f"Mettre {len(games)} jeu(x) à la corbeille ?\n"
                                 "(Tu pourras les récupérer depuis la corbeille.)")
        if r != QMessageBox.StandardButton.Yes:
            return
        from PySide6.QtCore import QFile
        from .detect import companions
        failed = 0
        for g in games:
            for f in [g.path] + companions(g.path):
                if f.exists() and not QFile.moveToTrash(str(f)):
                    failed += 1
            self.win.lib.meta.pop(g.key, None)
        self.win.lib.save()
        self.win.refresh()
        msg = f"{len(games)} jeu(x) mis à la corbeille."
        if failed:
            msg += f"\n{failed} fichier(s) n'ont pas pu être déplacés."
        QMessageBox.information(self, "Ménage", msg)
        self.accept()


# ------------------------------------------------------------------ export vers une autre machine
class ExportDialog(QDialog):
    def __init__(self, win, only=None):
        super().__init__(win)
        self.win = win
        self.setWindowTitle("Exporter les jeux")
        self.setMinimumWidth(620)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(22, 20, 22, 18)
        lay.setSpacing(10)
        lay.addWidget(QLabel("Exporter les jeux vers un autre appareil", objectName="title"))
        info = QLabel("Copie tes jeux, rangés par console, dans un dossier (disque externe, clé USB, carte SD…). "
                      "Rien n'est retiré de Rétro Station.", objectName="subtitle")
        info.setWordWrap(True)
        lay.addWidget(info)
        self.style = QComboBox()
        for k, v in EXPORT_STYLES.items():
            self.style.addItem(v, k)
        form = QFormLayout()
        form.addRow("Noms des dossiers", self.style)
        lay.addLayout(form)
        self.list = QListWidget()
        self.list.setStyleSheet("QListWidget { background:#191b25; border:none; border-radius:10px; padding:6px; }")
        self.list.setIconSize(QSize(40, 25))
        counts = {}
        for g in win.lib.games:
            counts[g.console] = counts.get(g.console, 0) + 1
        for c in CONSOLES:
            if not counts.get(c.id):
                continue
            it = QListWidgetItem(QIcon(console_card(c.id, 40, 25)), f"{c.name}   ({counts[c.id]})")
            it.setData(Qt.ItemDataRole.UserRole, c.id)
            it.setFlags(it.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            it.setCheckState(Qt.CheckState.Checked if (only is None or only == c.id) else Qt.CheckState.Unchecked)
            self.list.addItem(it)
        lay.addWidget(self.list, 1)
        self.one = QCheckBox("Une seule version de chaque jeu (sans les doublons de régions)")
        self.one.setChecked(not win.settings.get("all_versions"))
        self.bios = QCheckBox("Copier aussi les BIOS")
        self.bios.setChecked(True)
        lay.addWidget(self.one)
        lay.addWidget(self.bios)
        row = QHBoxLayout()
        self.dest_lab = QLabel("Aucun dossier choisi", objectName="subtitle")
        pick = QPushButton("📁  Choisir le dossier de destination…")
        pick.clicked.connect(lambda: self._pick())
        row.addWidget(pick)
        row.addWidget(self.dest_lab, 1)
        lay.addLayout(row)
        btns = QHBoxLayout()
        btns.addStretch(1)
        close = QPushButton("Fermer")
        close.clicked.connect(lambda: self.reject())
        self.go = QPushButton("📤  Exporter", objectName="primary")
        self.go.setEnabled(False)
        self.go.clicked.connect(lambda: self._export())
        btns.addWidget(close)
        btns.addWidget(self.go)
        lay.addLayout(btns)
        self.dest = None

    def _pick(self):
        d = QFileDialog.getExistingDirectory(self, "Dossier de destination", str(Path.home()))
        if d:
            self.dest = Path(d)
            self.dest_lab.setText(str(self.dest))
            self.go.setEnabled(True)

    def selected_games(self):
        chosen = {self.list.item(i).data(Qt.ItemDataRole.UserRole) for i in range(self.list.count())
                  if self.list.item(i).checkState() == Qt.CheckState.Checked}
        gs = [g for g in self.win.lib.games if g.console in chosen]
        return preferred_only(gs) if self.one.isChecked() else gs

    def _export(self):
        games = self.selected_games()
        if not games or not self.dest:
            return
        style, bios = self.style.currentData(), self.bios.isChecked()
        self.progress = QProgressDialog("Copie des jeux…", None, 0, 1000, self)
        self.progress.setWindowTitle("Export")
        self.progress.setWindowModality(Qt.WindowModality.WindowModal)
        self.progress.setMinimumDuration(0)
        self.progress.setMinimumWidth(460)
        dest = self.dest

        def work(sig):
            return export_games(games, dest, style, bios, lambda i, n, name: sig.progress.emit(name, i / max(n, 1)))
        self.task = Task(work)
        self.task.signals.progress.connect(lambda name, f: (self.progress.setValue(int(f * 1000)),
                                                            self.progress.setLabelText(f"Copie : {name}")))
        self.task.signals.done.connect(self._done)
        QThreadPool.globalInstance().start(self.task)

    def _done(self, res):
        self.progress.close()
        if isinstance(res, Exception):
            QMessageBox.warning(self, "Export", f"Erreur : {res}")
            return
        copied, skipped, errors = res
        msg = f"{copied} fichier(s) copié(s) dans :\n{self.dest}"
        if skipped:
            msg += f"\n{skipped} fichier(s) déjà présents, laissés tels quels."
        if errors:
            msg += "\n\nProblèmes :\n" + "\n".join(errors[:8])
        QMessageBox.information(self, "Export terminé", msg)
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.dest)))
        self.accept()


# ------------------------------------------------------------------ affichage par console
class DisplayDialog(QDialog):
    """Taille de l'écran, netteté, effets et contour, console par console."""

    def __init__(self, win, cid=None):
        super().__init__(win)
        from . import bezels
        self.bz = bezels
        self.win = win
        self.setWindowTitle("Affichage des jeux")
        self.setMinimumWidth(760)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(22, 20, 22, 20)
        lay.setSpacing(22)
        left = QVBoxLayout()
        t = QLabel("Affichage des jeux", objectName="title")
        left.addWidget(t)
        form = QFormLayout()
        form.setSpacing(10)
        self.console = QComboBox()
        for c in CONSOLES:
            self.console.addItem(QIcon(console_card(c.id, 40, 25)), c.name, c.id)
        form.addRow("Console", self.console)
        self.bezel = QComboBox()
        for k, v in bezels.STYLES.items():
            self.bezel.addItem(v, k)
        form.addRow("Contour", self.bezel)
        self.color = QComboBox()
        form.addRow("Couleur du contour", self.color)
        self.pick = QPushButton("Choisir mon image de contour (PNG)…")
        self.pick.clicked.connect(lambda: self._pick_custom())
        form.addRow("", self.pick)
        self.size = QSlider(Qt.Orientation.Horizontal)
        self.size.setRange(55, 95)
        self.size_lab = QLabel()
        row = QHBoxLayout()
        row.addWidget(self.size, 1)
        row.addWidget(self.size_lab)
        form.addRow("Taille de l'écran", row)
        self.size_row = row
        self.ssize = QSlider(Qt.Orientation.Horizontal)
        self.ssize.setRange(60, 100)
        self.ssize_lab = QLabel()
        srow = QHBoxLayout()
        srow.addWidget(self.ssize, 1)
        srow.addWidget(self.ssize_lab)
        form.addRow("Taille de l'écran de jeu", srow)
        self.ssize_row = srow
        self.scale = QComboBox()
        self.scale.addItem("Remplir l'écran (proportions respectées)", "fit")
        self.scale.addItem("Pixels parfaits (tous identiques, bords noirs)", "integer")
        form.addRow("Taille de l'image", self.scale)
        self.smooth = QComboBox()
        self.smooth.addItem("Pixels nets", False)
        self.smooth.addItem("Lissé (plus doux)", True)
        form.addRow("Netteté", self.smooth)
        self.effect = QComboBox()
        for k, v in launch.EFFECTS.items():
            self.effect.addItem(v, k)
        form.addRow("Effet d'écran", self.effect)
        self.mode = QComboBox()
        self.mode.addItem("Plein écran", True)
        self.mode.addItem("Fenêtre", False)
        form.addRow("Affichage", self.mode)
        self.window = QComboBox()
        for k in (2, 3, 4, 5, 6):
            self.window.addItem(f"× {k}", k)
        form.addRow("Taille de la fenêtre", self.window)
        self.res = QComboBox()
        for k, lab in ((1, "× 1 (d'origine, flou)"), (2, "× 2"), (3, "× 3 (Full HD)"), (4, "× 4 (conseillé)"),
                       (6, "× 6 (4K)")):
            self.res.addItem(lab, k)
        form.addRow("Résolution 3D", self.res)
        self.form = form
        left.addLayout(form)
        self.hint = QLabel("", objectName="subtitle")
        self.hint.setWordWrap(True)
        left.addWidget(self.hint)
        left.addStretch(1)
        btns = QHBoxLayout()
        reset = QPushButton("Valeurs par défaut")
        reset.clicked.connect(lambda: self._reset())
        save = QPushButton("Enregistrer", objectName="primary")
        save.clicked.connect(lambda: self._save())
        btns.addWidget(reset)
        btns.addStretch(1)
        btns.addWidget(save)
        left.addLayout(btns)
        lay.addLayout(left, 3)
        right = QVBoxLayout()
        right.addWidget(QLabel("Aperçu", objectName="subtitle"))
        self.preview = QLabel(alignment=Qt.AlignmentFlag.AlignCenter)
        self.preview.setFixedSize(400, 225)
        self.preview.setStyleSheet("background:#000; border-radius: 10px;")
        right.addWidget(self.preview)
        right.addStretch(1)
        lay.addLayout(right, 2)

        self.edits = {}
        self.console.currentIndexChanged.connect(lambda _i: self._load())
        for w in (self.bezel, self.color, self.scale, self.smooth, self.effect, self.mode, self.window, self.res):
            w.currentIndexChanged.connect(lambda _i: self._changed())
        self.size.valueChanged.connect(lambda _v: self._changed())
        self.ssize.valueChanged.connect(lambda _v: self._changed())
        start = cid if cid in BY_ID else (win.filter if win.filter in BY_ID else "gb")
        self.console.setCurrentIndex(self.console.findData(start))
        self._load()

    def _cid(self):
        return self.console.currentData()

    def _set(self, combo, value):
        i = combo.findData(value)
        combo.setCurrentIndex(max(i, 0))

    def _load(self):
        cid = self._cid()
        d = self.edits.get(cid) or launch.display_for(self.win.settings, cid)
        self._loading = True
        self._set(self.bezel, d["bezel"])
        self._fill_colors(d["bezel"], d.get("bezel_color", ""))
        self.size.setValue(int(d.get("bezel_size", 82)))
        self.ssize.setValue(int(d.get("screen_size", 100)))
        self._set(self.scale, d["scale"])
        self._set(self.smooth, bool(d["smooth"]))
        self._set(self.effect, d["effect"])
        self._set(self.mode, bool(d["fullscreen"]))
        self._set(self.window, int(d.get("window", 4)))
        self._set(self.res, int(d.get("dolphin_res", 3)))
        self._loading = False
        self._refresh()

    def _fill_colors(self, style, current):
        self.color.blockSignals(True)
        self.color.clear()
        for name in self.bz.COLORS.get(style, {}):
            self.color.addItem(name, name)
        if current:
            self._set(self.color, current)
        self.color.blockSignals(False)

    def _current(self):
        return {"bezel": self.bezel.currentData(), "bezel_color": self.color.currentData() or "",
                "bezel_size": self.size.value(), "screen_size": self.ssize.value(),
                "scale": self.scale.currentData(),
                "smooth": bool(self.smooth.currentData()), "effect": self.effect.currentData(),
                "fullscreen": bool(self.mode.currentData()), "window": self.window.currentData(),
                "dolphin_res": self.res.currentData()}

    def _changed(self):
        if getattr(self, "_loading", False):
            return
        style = self.bezel.currentData()
        if self.color.count() == 0 or self.color.itemData(0) not in self.bz.COLORS.get(style, {}):
            self._fill_colors(style, "")
        self.edits[self._cid()] = self._current()
        self._refresh()

    def _refresh(self):
        cid = self._cid()
        dolphin = BY_ID[cid].engine == "dolphin"
        style = self.bezel.currentData()
        has_bezel = style != "none" and not dolphin
        custom = style == "custom"
        vis = {self.bezel: not dolphin, self.color: has_bezel and not custom, self.size: has_bezel and not custom,
               self.pick: has_bezel and custom, self.scale: not has_bezel and not dolphin,
               self.smooth: not dolphin, self.effect: not dolphin, self.mode: not has_bezel,
               self.window: not has_bezel and not dolphin and not self.mode.currentData(),
               self.res: dolphin or cid in launch.CONSOLES_3D,
               self.ssize: not has_bezel and not dolphin and bool(self.mode.currentData())}
        for w, on in vis.items():
            row = self.size_row if w is self.size else (self.ssize_row if w is self.ssize else w)
            self.form.setRowVisible(row, on)
        self.size_lab.setText(f"{self.size.value()} %")
        self.ssize_lab.setText(f"{self.ssize.value()} %")
        self.hint.setText("Wii / GameCube : le contour n'est pas disponible ; la résolution 3D rend l'image "
                          "plus fine (× 3 ou × 4 conseillé sur ton PC)." if dolphin else
                          "Résolution 3D : plus elle est haute, plus l'image est fine (× 4 conseillé). "
                          "Effet « Télé cathodique » ou « Lissage » : moins de gros pixels. "
                          "Taille de l'écran : rétrécit l'image, avec un cadre noir autour." if cid in launch.CONSOLES_3D
                          else
                          "Gros pixels ? Choisis l'effet « Télé cathodique » ou « Lissage intelligent », "
                          "et réduis la taille de l'écran de jeu. "
                          "Avec un contour, le jeu s'affiche toujours en plein écran. Ton image de contour : "
                          "un PNG (idéalement 1920 × 1080) dont la zone de l'écran est transparente. "
                          "« Pixels parfaits » évite les pixels de tailles inégales.")
        try:
            img = self.bz.preview(cid, style if not dolphin else "none", self.color.currentData() or "",
                                  self.size.value() if has_bezel else self.ssize.value(), 400, 225)
            import io
            buf = io.BytesIO()
            img.save(buf, "PNG")
            pm = QPixmap()
            pm.loadFromData(buf.getvalue())
            self.preview.setPixmap(pm)
        except Exception:
            self.preview.setText("Aperçu indisponible")

    def _pick_custom(self):
        cid = self._cid()
        f, _ = QFileDialog.getOpenFileName(self, f"Image de contour pour {BY_ID[cid].name}", str(Path.home()),
                                           "Images PNG (*.png)")
        if not f:
            return
        err = self.bz.import_custom(cid, f)
        if err:
            QMessageBox.warning(self, "Contour", err)
            return
        self._changed()

    def _reset(self):
        cid = self._cid()
        self.edits.pop(cid, None)
        self.win.settings.setdefault("display", {}).pop(cid, None)
        self._load()

    def _save(self):
        disp = self.win.settings.setdefault("display", {})
        for cid, d in self.edits.items():
            disp[cid] = d
        save_settings(self.win.settings)
        self.accept()


# ------------------------------------------------------------------ fenêtre principale
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.settings = load_settings()
        set_tile_width(self.settings.get("tile_w", 140))
        self.lib = Library()
        self.filter = "all"
        self.proc = None
        self.running_game = None
        self.started = 0.0
        self.hold_since = None
        self.tasks = []
        self.cover_pool = ThreadPoolExecutor(3)
        self.tile_pool = QThreadPool()
        self.tile_pool.setMaxThreadCount(3)
        self.tile_signals = TileSignals()
        self.tile_signals.ready.connect(self._tile_ready)
        self.tile_cache = {}          # clé -> QPixmap
        self.tile_pending = set()
        self.cover_of = {}            # jeu -> (jaquette, date)
        self.repaint_timer = QTimer(self, singleShot=True, interval=40,
                                    timeout=lambda: self.grid.viewport().update())
        prepare_cards()
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
        for eff in ("lcd", "crt", "smooth"):      # prépare les effets d'écran : lancement plus rapide
            self.cover_pool.submit(launch.find_shader, eff)
        QTimer.singleShot(300, self.fetch_arcade_names)

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
        self.sidebar.itemClicked.connect(lambda it: self._side_changed(it, None))
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
        self.search_timer = QTimer(self, singleShot=True, interval=220, timeout=self.apply_search)
        self.search.textChanged.connect(lambda _t: self.search_timer.start())
        top.addWidget(self.search)
        size_box = QHBoxLayout()
        size_box.setSpacing(4)
        small = QLabel("▫")
        big = QLabel("◻")
        self.size_slider = QSlider(Qt.Orientation.Horizontal)
        self.size_slider.setRange(*TILE_SIZES)
        self.size_slider.setFixedWidth(110)
        self.size_slider.setToolTip("Taille des jaquettes")
        self.size_slider.setValue(TW)
        self.size_slider.valueChanged.connect(lambda v: self.size_timer.start())
        self.size_timer = QTimer(self, singleShot=True, interval=120, timeout=self._apply_tile_size)
        size_box.addWidget(small)
        size_box.addWidget(self.size_slider)
        size_box.addWidget(big)
        top.addLayout(size_box)
        imp = QPushButton("＋  Importer des jeux", objectName="primary")
        imp.setToolTip("Sélectionne tous tes jeux d'un coup : ils sont rangés tout seuls par console")
        imp.clicked.connect(lambda: self.import_files())
        top.addWidget(imp)
        imp_dir = QPushButton("📁  Un dossier entier")
        imp_dir.clicked.connect(lambda: self.import_folder())
        top.addWidget(imp_dir)
        export = QPushButton("📤  Exporter")
        export.setToolTip("Copier tes jeux dans un dossier pour une autre machine")
        export.clicked.connect(lambda: ExportDialog(self).exec())
        top.addWidget(export)
        clean = QPushButton("🧹  Ménage")
        clean.setToolTip("Trouver les doublons et les ROMs abîmées")
        clean.clicked.connect(lambda: CleanupDialog(self).exec())
        top.addWidget(clean)
        mv.addLayout(top)
        self.hide_var = QCheckBox("Afficher toutes les versions d'un même jeu (régions, révisions, copies)")
        self.hide_var.setChecked(self.settings.get("all_versions", False))
        self.hide_var.toggled.connect(self._toggle_variants)
        mv.addWidget(self.hide_var)
        # barre de lettres : Tous, 0-9, A…Z
        abc = QHBoxLayout()
        abc.setSpacing(2)
        self.letter = ""
        self.letter_btns = {}
        for key, label in [("", "Tous"), ("#", "0-9")] + [(ch, ch) for ch in "ABCDEFGHIJKLMNOPQRSTUVWXYZ"]:
            b = QPushButton(label, objectName="letter")
            b.setCheckable(True)
            b.setChecked(key == "")
            b.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.clicked.connect(lambda _=False, k=key: self.set_letter(k))
            abc.addWidget(b)
            self.letter_btns[key] = b
        abc.addStretch(1)
        mv.addLayout(abc)

        self.stack = QStackedWidget()
        self.grid = QListView(objectName="grid")
        g = self.grid
        self.model = GameModel()
        g.setModel(self.model)
        g.setItemDelegate(TileDelegate(self))
        g.setViewMode(QListView.ViewMode.IconMode)
        g.setResizeMode(QListView.ResizeMode.Adjust)
        g.setMovement(QListView.Movement.Static)
        g.setGridSize(QSize(TW + 26, TH + 54))
        g.setUniformItemSizes(True)
        g.setMouseTracking(True)
        g.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        g.setDragDropMode(QAbstractItemView.DragDropMode.NoDragDrop)
        g.setAcceptDrops(False)
        g.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        g.verticalScrollBar().setSingleStep(40)
        g.clicked.connect(self._play_index)
        g.activated.connect(self._play_index)
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
        shown = self.lib.games if self.settings.get("all_versions") else preferred_only(self.lib.games)
        counts = {c.id: 0 for c in CONSOLES}
        for g in shown:
            counts[g.console] += 1
        keep = self.filter
        self.sidebar.blockSignals(True)
        self.sidebar.clear()

        def add(text, key, icon=None, header=False):
            it = QListWidgetItem(text)
            if icon:
                it.setIcon(QIcon(icon))
            if header:
                it.setData(Qt.ItemDataRole.UserRole, key)
                f = QFont()
                f.setPixelSize(11)
                f.setBold(True)
                it.setFont(f)
                it.setForeground(QColor("#6f7491"))
            else:
                it.setData(Qt.ItemDataRole.UserRole, key)
            self.sidebar.addItem(it)
            return it

        total = len(shown)
        add(f"🎮  Tous les jeux   {total}", "all")
        add("⭐  Favoris", "fav")
        add("🕘  Récents", "recent")
        for fam in FAMILIES:
            cons = [c for c in CONSOLES if c.family == fam and counts[c.id]]
            if not cons:
                continue
            add(f"{fam.upper()}   {sum(counts[c.id] for c in cons)}", f"fam:{fam}", header=True)
            for c in cons:
                add(f"{c.name}   {counts[c.id]}", c.id, console_card(c.id, 54, 33))
        self.sidebar.blockSignals(False)
        keep_ok = keep in ("all", "fav", "recent") or counts.get(keep) or (
            keep.startswith("fam:") and any(counts[c.id] for c in CONSOLES if c.family == keep[4:]))
        self._select_filter(keep if keep_ok else "all")
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

    def _toggle_variants(self, on):
        self.settings["all_versions"] = bool(on)
        save_settings(self.settings)
        self.refresh()

    def _apply_tile_size(self):
        set_tile_width(self.size_slider.value())
        self.settings["tile_w"] = TW
        save_settings(self.settings)
        self.grid.setGridSize(QSize(TW + 26, TH + 54))
        self._forget_tiles()
        self.grid.doItemsLayout()

    def visible_games(self):
        gs = self.lib.games
        if not self.settings.get("all_versions"):
            gs = preferred_only(gs)          # un seul exemplaire de chaque jeu par console
        if self.filter == "fav":
            gs = [g for g in gs if self.lib.meta.get(g.key, {}).get("fav")]
        elif self.filter == "recent":
            gs = [g for g in gs if self.lib.meta.get(g.key, {}).get("last")]
            gs.sort(key=lambda g: -self.lib.meta[g.key]["last"])
            gs = gs[:30]
        elif self.filter.startswith("fam:"):
            fam = self.filter[4:]
            gs = [g for g in gs if BY_ID[g.console].family == fam]
        elif self.filter in BY_ID:
            gs = [g for g in gs if g.console == self.filter]
        return gs

    def populate(self):
        names = {"all": "Tous les jeux", "fav": "Favoris", "recent": "Joués récemment"}
        self.title.setText(names.get(self.filter) or (f"Toutes les consoles {self.filter[4:]}"
                           if self.filter.startswith("fam:") else BY_ID[self.filter].name))
        gs = self.visible_games()
        q = self.search.text().strip().lower()
        if q:
            gs = [g for g in gs if q in g.title.lower()]
        present = {first_letter(g.title) for g in gs}
        for k, b in self.letter_btns.items():
            b.setEnabled(k == "" or k in present or k == self.letter)
            b.setChecked(k == self.letter)
        if self.letter:
            gs = [g for g in gs if first_letter(g.title) == self.letter]
        self.model.set_games(gs)
        n = len(gs)
        self.subtitle.setText(f"{n} jeu" + ("x" if n > 1 else ""))
        self.stack.setCurrentWidget(self.empty_page if not self.lib.games else self.grid)
        if n:
            self.grid.setCurrentIndex(self.model.index(0))
            self.grid.scrollToTop()

    def apply_search(self):
        self.populate()

    def set_letter(self, key):
        self.letter = key
        self.populate()

    # ---------------- vignettes : préparées en tâche de fond, seulement pour ce qui est à l'écran
    def _cover_info(self, g):
        info = self.cover_of.get(g.key)
        if info is None:
            cover = covers.best_cover(g)
            try:
                stamp = cover.stat().st_mtime if cover else 0
            except OSError:
                stamp = 0
            info = self.cover_of[g.key] = (cover, stamp)
        return info

    def tile_for(self, g):
        cover, stamp = self._cover_info(g)
        key = f"{g.key}|{cover}|{stamp}"
        pm = self.tile_cache.get(key)
        if pm is not None:
            return pm
        if key not in self.tile_pending:
            self.tile_pending.add(key)
            self.tile_pool.start(TileJob(key, g, cover, self.tile_signals))
        return None

    def _tile_ready(self, key, img):
        self.tile_pending.discard(key)
        if img.isNull():
            return
        if len(self.tile_cache) > TILE_CACHE_MAX:
            for k in list(self.tile_cache)[: TILE_CACHE_MAX // 3]:
                del self.tile_cache[k]
        self.tile_cache[key] = QPixmap.fromImage(img)
        if not self.repaint_timer.isActive():
            self.repaint_timer.start()

    def _forget_tiles(self, key=None):
        if key is None:
            self.tile_cache.clear()
            self.cover_of.clear()
        else:
            self.cover_of.pop(key, None)
            for k in [k for k in self.tile_cache if k.startswith(key + "|")]:
                del self.tile_cache[k]
        self.grid.viewport().update()

    def current_game(self):
        idx = self.grid.currentIndex()
        return idx.data(Qt.ItemDataRole.UserRole) if idx.isValid() else None

    # ---------------- jaquettes
    def fetch_covers(self):
        games = [g for g in self.lib.games if g.key not in self.cover_pending]
        self.cover_pending.update(g.key for g in games)
        sig = self.cover_signals

        def job(g):
            if covers.best_cover(g) or covers.cover_file(g).with_suffix(".absent").exists():
                return
            if covers.download_cover(g):
                sig.cover.emit(g.key)
        for g in games:
            self.cover_pool.submit(job, g)

    def fetch_arcade_names(self):
        from . import arcadedb
        if arcadedb.ready():
            return
        sig = self.arcade_signals = Signals()
        sig.done.connect(lambda ok: ok and self._arcade_ready())

        def job():
            sig.done.emit(arcadedb.download())
        self.cover_pool.submit(job)

    def _arcade_ready(self):
        if any(g.console in ("arcade", "neogeo") for g in self.lib.games):
            for g in self.lib.games:
                if g.console in ("arcade", "neogeo"):
                    try:
                        covers.cover_file(g).with_suffix(".absent").unlink()
                    except OSError:
                        pass
            self.cover_pending.clear()
            self._forget_tiles()
            self.refresh()

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
            prepare_cards()
            self._forget_tiles()
            self.refresh()

    def _side_menu(self, pos):
        it = self.sidebar.itemAt(pos)
        cid = it.data(Qt.ItemDataRole.UserRole) if it else None
        if cid not in BY_ID:
            return
        m = QMenu(self)
        m.addAction("🖥  Affichage et contour d'écran…", lambda: DisplayDialog(self, cid).exec())
        m.addAction("🎮  Régler les manettes…" if BY_ID[cid].engine == "dolphin" else "🎮  Régler les commandes…",
                    lambda: self._controls_for(cid))
        m.addAction("📤  Exporter les jeux de cette console…", lambda: ExportDialog(self, cid).exec())
        m.addAction("📷  Mettre ma propre photo de la console…", lambda: self._set_console_photo(cid))
        if photos.custom(cid).exists():
            m.addAction("↺  Remettre la photo d'origine", lambda: self._reset_console_photo(cid))
        m.exec(self.sidebar.viewport().mapToGlobal(pos))

    def _controls_for(self, cid):
        c = BY_ID[cid]
        if c.engine != "dolphin":
            show_remap_help(self, c.name)
            return
        try:
            exe, args, cwd = launch.dolphin_setup_command()
        except launch.LaunchError as e:
            QMessageBox.warning(self, "Manettes", str(e))
            return
        r = QMessageBox.question(self, "Manettes Wii / GameCube",
                                 "Dolphin va s'ouvrir. Clique sur l'icône « Manettes » (ou menu Options > "
                                 "Configuration des manettes), règle tes boutons, puis ferme Dolphin.\n\n"
                                 "Rétro Station gardera ensuite tes réglages au lieu des siens. Continuer ?")
        if r != QMessageBox.StandardButton.Yes:
            return
        self.settings["dolphin_controls"] = "manuel"
        save_settings(self.settings)
        QProcess.startDetached(exe, args, cwd)

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
        prepare_cards()
        self._forget_tiles()
        self.refresh()

    def _cover_ready(self, key):
        self._forget_tiles(key)

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

    def _play_index(self, index):
        g = index.data(Qt.ItemDataRole.UserRole) if index.isValid() else None
        if g and self.proc is None:
            self.play(g)

    def play(self, game, use_shader=True):
        c = BY_ID[game.console]
        if launch.needs_capsimg(game):
            lib = "capsimg.dll" if paths.IS_WINDOWS else "capsimg.so"
            box = QMessageBox(self)
            box.setWindowTitle("Disquette .ipf")
            box.setText(f"Ce jeu est une copie de disquette au format .ipf. Pour la lire, l'émulateur a besoin "
                        f"du fichier « {lib} » (gratuit, fourni par la Software Preservation Society).\n\n"
                        "1. Télécharge-le sur la page qui va s'ouvrir"
                        + (" (paquet Windows, version 64 bits : fichier CAPSImg.dll du dossier x64)."
                           if paths.IS_WINDOWS else " (greffon CAPSImg pour macOS).")
                        + "\n2. Importe-le dans Rétro Station comme un jeu : il est rangé tout seul.\n\n"
                        "Astuce : la version .adf du même jeu fonctionne sans ce fichier.")
            web = box.addButton("Ouvrir la page de téléchargement", QMessageBox.ButtonRole.ActionRole)
            imp = box.addButton("Importer le fichier…", QMessageBox.ButtonRole.ActionRole)
            go = box.addButton("Lancer quand même", QMessageBox.ButtonRole.AcceptRole)
            box.addButton("Annuler", QMessageBox.ButtonRole.RejectRole)
            box.exec()
            clicked = box.clickedButton()
            if clicked == web:
                QDesktopServices.openUrl(QUrl(launch.IPF_PAGE_WIN if paths.IS_WINDOWS else launch.IPF_PAGE_MAC))
                return
            if clicked == imp:
                f, _ = QFileDialog.getOpenFileName(self, f"Choisir {lib}", str(Path.home() / "Downloads"),
                                                   f"Bibliothèque ({lib} CAPSImg.dll capsimg*)")
                if f:
                    import shutil
                    paths.BIOS.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(f, paths.BIOS / lib)
                    QMessageBox.information(self, "Disquette .ipf", f"{lib} est en place. Relance le jeu.")
                return
            if clicked != go:
                return
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
            scr = QApplication.primaryScreen()
            ratio = scr.devicePixelRatio() if scr else 1.0
            size = (round(scr.size().width() * ratio), round(scr.size().height() * ratio)) if scr else (1920, 1080)
            exe, args, cwd, self.shader_used = launch.build_command(game, self.settings, use_shader, size)
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
        # demande polie de fermeture : le moteur affiche sa confirmation et sauvegarde
        if self.proc is not None and self.proc.state() != QProcess.ProcessState.NotRunning:
            self.proc.terminate()

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
        elif code not in (0, None) and getattr(self, "shader_used", False):
            self.shader_used = False
            self.status.setText("Relance sans effet d'écran…")
            QTimer.singleShot(300, lambda g=game: self.play(g, use_shader=False))
        elif code not in (0, None):
            QMessageBox.warning(self, "Le jeu s'est arrêté",
                                "Le jeu s'est fermé tout de suite. Le fichier est peut-être abîmé, "
                                "incomplet, ou il manque un BIOS.\n\nDétails techniques : dossier Journaux.")

    # ---------------- clic droit
    def _context_menu(self, pos):
        idx = self.grid.indexAt(pos)
        if not idx.isValid():
            return
        g = idx.data(Qt.ItemDataRole.UserRole)
        fav = self.lib.meta.get(g.key, {}).get("fav")
        m = QMenu(self)
        m.addAction("▶  Jouer", lambda: self.play(g))
        m.addAction("☆  Retirer des favoris" if fav else "⭐  Ajouter aux favoris", lambda: self._fav(g))
        m.addAction("🖼  Choisir une jaquette…", lambda: self._pick_cover(g))
        m.addAction(f"🖥  Affichage {BY_ID[g.console].name} (taille, contour…)",
                    lambda: DisplayDialog(self, g.console).exec())
        m.addAction("🎮  Régler les commandes…", lambda: self._controls_for(g.console))
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
            # Wii / GameCube : maintenir Select + Start 1,5 s, ou Échap = quitter (Dolphin demande confirmation).
            # Les autres consoles gèrent elles-mêmes Échap et Select + Start (menu).
            dolphin = self.running_game and BY_ID[self.running_game.console].engine == "dolphin"
            if dolphin:
                if (b & gamepad.BACK) and (b & gamepad.START):
                    self.hold_since = self.hold_since or now
                    if now - self.hold_since > 1.5:
                        self.hold_since = now + 3   # pas de répétition immédiate
                        self.stop_game()
                else:
                    self.hold_since = None
                esc = gamepad.escape_pressed()
                if esc and not getattr(self, "esc_prev", False) and now > getattr(self, "esc_next", 0):
                    self.esc_next = now + 2
                    self.stop_game()
                self.esc_prev = esc
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
            g = self.current_game()
            if g:
                self._fav(g)
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
        if w is self.grid and dirs & gamepad.LEFT and self.grid.currentIndex().isValid():
            # bord gauche de la grille -> retour à la liste des consoles
            r = self.grid.visualRect(self.grid.currentIndex())
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
            self._play_index(self.grid.currentIndex())
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
