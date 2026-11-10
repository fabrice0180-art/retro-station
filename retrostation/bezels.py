"""Contours d'écran (« bezels ») originaux, dessinés à la résolution exacte de l'écran.

Chaque contour est une image transparente au centre (l'endroit où s'affiche le jeu)
que RetroArch superpose à l'image. On renvoie aussi la position exacte du trou pour
caler le jeu dedans au pixel près.
"""
from __future__ import annotations

import hashlib
import math
import random

from PIL import Image, ImageDraw, ImageFilter, ImageFont

from . import paths

STYLES = {
    "none": "Aucun contour",
    "handheld": "Console portable",
    "tv": "Télé rétro",
    "arcade": "Borne d'arcade",
    "neon": "Néon",
    "custom": "Mon image de contour (PNG)",
}
CUSTOM_DIR = paths.ROOT / "Contours"


def custom_file(cid):
    return CUSTOM_DIR / f"{cid}.png"


def import_custom(cid, src):
    """Copie une image de contour choisie par l'utilisateur. Elle doit avoir une zone transparente
    (l'écran). Renvoie un message d'erreur, ou "" si tout va bien."""
    try:
        img = Image.open(src).convert("RGBA")
    except Exception:
        return "Ce fichier n'est pas une image lisible."
    if not custom_hole_norm(img):
        return ("Cette image n'a pas de zone transparente pour l'écran.\n"
                "Il faut un PNG dont la partie « écran » est transparente.")
    CUSTOM_DIR.mkdir(parents=True, exist_ok=True)
    img.save(custom_file(cid))
    return ""


def custom_hole_norm(img):
    """Position de la zone transparente (proportions 0..1), ou None."""
    a = img.getchannel("A").point(lambda v: 255 if v < 24 else 0)
    bb = a.getbbox()
    if not bb:
        return None
    x0, y0, x1, y1 = bb
    W, H = img.size
    if (x1 - x0) < W * 0.15 or (y1 - y0) < H * 0.15:
        return None
    return x0 / W, y0 / H, (x1 - x0) / W, (y1 - y0) / H
COLORS = {
    "handheld": {"Gris clair": "#c8c8c2", "Noir": "#2c2c33", "Violet": "#6d52a8", "Jaune": "#e6c23c",
                 "Turquoise": "#27aeb0", "Rouge": "#c43a3f", "Blanc": "#ecebe6"},
    "tv": {"Bois": "#7b4a25", "Noir": "#232328", "Crème": "#ddd2b8", "Argent": "#9da2ab"},
    "arcade": {"Violet néon": "#8a3ffc", "Rouge": "#e0303a", "Bleu": "#2f6bff", "Vert": "#20b56b"},
    "neon": {"Rose": "#ff3fa8", "Bleu": "#2fd2ff", "Vert": "#3dff8a", "Orange": "#ff8a3d", "Violet": "#b05cff"},
}
# proportions de l'image de chaque console (largeur / hauteur)
ASPECT = {"gb": 10 / 9, "gbc": 10 / 9, "gg": 10 / 9, "gba": 3 / 2, "ngp": 20 / 19, "ngpc": 20 / 19, "psp": 480 / 272, "lynx": 160 / 102}

FONT_FILES = ["arialbd.ttf", "Arial Bold.ttf", "DejaVuSans-Bold.ttf", "Helvetica.ttc",
              "/System/Library/Fonts/Supplemental/Arial Bold.ttf", "/System/Library/Fonts/Helvetica.ttc",
              "C:/Windows/Fonts/arialbd.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"]


def _font(size):
    for f in FONT_FILES:
        try:
            return ImageFont.truetype(f, int(size))
        except OSError:
            continue
    try:
        return ImageFont.load_default(int(size))
    except TypeError:
        return ImageFont.load_default()


def _rgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def _shade(c, f):
    """f > 0 éclaircit, f < 0 assombrit."""
    if f >= 0:
        return tuple(min(255, int(v + (255 - v) * f)) for v in c)
    return tuple(max(0, int(v * (1 + f))) for v in c)


def _vgrad(size, top, bottom):
    w, h = size
    g = Image.new("RGBA", (1, h))
    for y in range(h):
        t = y / max(h - 1, 1)
        g.putpixel((0, y), tuple(int(top[i] + (bottom[i] - top[i]) * t) for i in range(3)) + (255,))
    return g.resize((w, h))


def _paste_rounded(img, box, fill_img, radius):
    x0, y0, x1, y1 = map(int, box)
    w, h = x1 - x0, y1 - y0
    if w <= 0 or h <= 0:
        return
    m = Image.new("L", (w, h), 0)
    ImageDraw.Draw(m).rounded_rectangle([0, 0, w - 1, h - 1], int(radius), fill=255)
    img.paste(fill_img.resize((w, h)) if fill_img.size != (w, h) else fill_img, (x0, y0), m)


def _shadow(img, box, radius, blur, alpha=150, offset=(0, 0)):
    sh = Image.new("RGBA", img.size, (0, 0, 0, 0))
    x0, y0, x1, y1 = box
    ImageDraw.Draw(sh).rounded_rectangle([x0 + offset[0], y0 + offset[1], x1 + offset[0], y1 + offset[1]],
                                         int(radius), fill=(0, 0, 0, alpha))
    img.alpha_composite(sh.filter(ImageFilter.GaussianBlur(blur)))


def _text_center(d, cx, cy, text, font, fill):
    bb = d.textbbox((0, 0), text, font=font)
    d.text((cx - (bb[2] - bb[0]) / 2 - bb[0], cy - (bb[3] - bb[1]) / 2 - bb[1]), text, font=font, fill=fill)


# ------------------------------------------------------------------ styles
def _handheld(img, hole, base, H):
    W = img.width
    x, y, w, h = hole
    d = ImageDraw.Draw(img)
    img.alpha_composite(_vgrad(img.size, (24, 24, 32), (8, 8, 12)))
    side = max(H * 0.30, (W - w) * 0.36)
    body = [max(W * 0.03, x - side), max(H * 0.02, y - H * 0.08),
            min(W * 0.97, x + w + side), min(H * 0.98, y + h + H * 0.10)]
    r = H * 0.09
    _shadow(img, body, r, H * 0.02, 170, (0, int(H * 0.012)))
    _paste_rounded(img, body, _vgrad((10, 10), _shade(base, 0.18), _shade(base, -0.22)), r)
    d = ImageDraw.Draw(img)
    d.rounded_rectangle(body, int(r), outline=_shade(base, -0.35) + (255,), width=max(2, int(H * 0.004)))
    # cadre de l'écran
    pad = H * 0.045
    frame = [x - pad, y - pad, x + w + pad, y + h + pad * 1.6]
    _paste_rounded(img, frame, _vgrad((10, 10), (66, 68, 80), (40, 41, 50)), H * 0.03)
    d = ImageDraw.Draw(img)
    led = (frame[0] + pad * 0.55, y + h * 0.35)
    lr = H * 0.009
    glow = Image.new("RGBA", img.size, (0, 0, 0, 0))
    ImageDraw.Draw(glow).ellipse([led[0] - lr * 3, led[1] - lr * 3, led[0] + lr * 3, led[1] + lr * 3],
                                 fill=(255, 60, 60, 120))
    img.alpha_composite(glow.filter(ImageFilter.GaussianBlur(lr * 2)))
    d = ImageDraw.Draw(img)
    d.ellipse([led[0] - lr, led[1] - lr, led[0] + lr, led[1] + lr], fill=(255, 70, 70, 255))
    small = _font(H * 0.018)
    _text_center(d, led[0], led[1] + lr * 3.2, "ON", small, (170, 172, 185, 255))
    _text_center(d, x + w / 2, y + h + pad * 0.85, "RÉTRO STATION", _font(H * 0.026), (190, 192, 205, 255))
    # croix directionnelle (côté gauche)
    left_space = (x - pad) - body[0]
    if left_space > H * 0.14:
        cx, cy = body[0] + left_space / 2, y + h * 0.58
        a, t = min(left_space * 0.32, H * 0.085), H * 0.026
        dark = (38, 38, 44, 255)
        _shadow(img, [cx - a, cy - t, cx + a, cy + t], t * 0.3, H * 0.006, 120, (0, int(H * 0.006)))
        d = ImageDraw.Draw(img)
        d.rounded_rectangle([cx - a, cy - t, cx + a, cy + t], int(t * 0.3), fill=dark)
        d.rounded_rectangle([cx - t, cy - a, cx + t, cy + a], int(t * 0.3), fill=dark)
        d.ellipse([cx - t * 0.45, cy - t * 0.45, cx + t * 0.45, cy + t * 0.45], fill=(55, 55, 62, 255))
    # boutons ronds (côté droit)
    right_space = body[2] - (x + w + pad)
    if right_space > H * 0.14:
        cx = x + w + pad + right_space / 2
        br = min(right_space * 0.16, H * 0.042)
        accent = (150, 40, 90, 255) if sum(base) > 300 else (210, 60, 110, 255)
        for i, (dx, dy, lab) in enumerate(((br * 1.25, -br * 0.9, "A"), (-br * 1.25, br * 0.9, "B"))):
            bx, by = cx + dx, y + h * 0.55 + dy
            _shadow(img, [bx - br, by - br, bx + br, by + br], br, H * 0.006, 130, (0, int(H * 0.007)))
            d = ImageDraw.Draw(img)
            d.ellipse([bx - br, by - br, bx + br, by + br], fill=accent)
            d.ellipse([bx - br * 0.6, by - br * 0.75, bx + br * 0.2, by - br * 0.1], fill=(255, 255, 255, 50))
            _text_center(d, bx + br * 1.6 * (1 if i == 0 else -1), by + br * 1.3, lab, small,
                         _shade(base, -0.45) + (255,))
    # petits boutons en pilule
    pw, ph = H * 0.055, H * 0.016
    py = min(body[3] - H * 0.05, frame[3] + (body[3] - frame[3]) * 0.55)
    if py > frame[3] + ph * 2:
        for px in (x + w / 2 - pw * 1.2, x + w / 2 + pw * 1.2):
            d.rounded_rectangle([px - pw / 2, py - ph / 2, px + pw / 2, py + ph / 2], int(ph / 2),
                                fill=_shade(base, -0.45) + (255,))
    # grille de haut-parleur
    sx, sy = body[2] - H * 0.13, body[3] - H * 0.10
    for i in range(4):
        for j in range(5):
            cx_, cy_ = sx + j * H * 0.018, sy + i * H * 0.018
            if body[0] < cx_ < body[2] and cy_ < body[3] - H * 0.02:
                d.ellipse([cx_ - H * 0.004, cy_ - H * 0.004, cx_ + H * 0.004, cy_ + H * 0.004],
                          fill=_shade(base, -0.4) + (255,))
    return H * 0.012


def _tv(img, hole, base, H):
    W = img.width
    x, y, w, h = hole
    rnd = random.Random(7)
    img.alpha_composite(_vgrad(img.size, (30, 24, 34), (12, 10, 14)))
    d = ImageDraw.Draw(img)
    knobs = H * 0.24
    body = [max(W * 0.02, x - H * 0.08), max(H * 0.02, y - H * 0.08),
            min(W * 0.98, x + w + H * 0.08 + knobs), min(H * 0.98, y + h + H * 0.09)]
    r = H * 0.04
    _shadow(img, body, r, H * 0.025, 190, (0, int(H * 0.015)))
    wood = _vgrad((int(body[2] - body[0]), int(body[3] - body[1])), _shade(base, 0.12), _shade(base, -0.25))
    wd = ImageDraw.Draw(wood)
    if base == _rgb(COLORS["tv"]["Bois"]):
        for _ in range(int(wood.height / 3)):
            yy = rnd.uniform(0, wood.height)
            amp = rnd.uniform(1, H * 0.006)
            col = _shade(base, rnd.uniform(-0.35, -0.05)) + (rnd.randint(40, 110),)
            pts = [(xx, yy + math.sin(xx / rnd.uniform(40, 120)) * amp) for xx in range(0, wood.width + 20, 20)]
            wd.line(pts, fill=col, width=1)
    _paste_rounded(img, body, wood, r)
    d = ImageDraw.Draw(img)
    # façade noire de l'écran
    pad = H * 0.04
    front = [x - pad, y - pad, x + w + pad, y + h + pad]
    _paste_rounded(img, front, _vgrad((10, 10), (34, 34, 38), (16, 16, 18)), H * 0.05)
    d = ImageDraw.Draw(img)
    # panneau de commandes à droite
    px0, px1 = x + w + pad + H * 0.03, body[2] - H * 0.035
    if px1 - px0 > H * 0.08:
        d.rounded_rectangle([px0, y, px1, y + h], int(H * 0.015), fill=(28, 28, 32, 255))
        kx = (px0 + px1) / 2
        kr = min((px1 - px0) * 0.32, H * 0.045)
        for k in range(2):
            ky = y + h * (0.18 + 0.24 * k)
            _shadow(img, [kx - kr, ky - kr, kx + kr, ky + kr], kr, H * 0.006, 160, (0, int(H * 0.006)))
            d = ImageDraw.Draw(img)
            d.ellipse([kx - kr, ky - kr, kx + kr, ky + kr], fill=(70, 70, 76, 255))
            d.ellipse([kx - kr * 0.7, ky - kr * 0.7, kx + kr * 0.7, ky + kr * 0.7], fill=(105, 105, 112, 255))
            ang = math.radians(-60 + 70 * k)
            d.line([kx, ky, kx + math.cos(ang) * kr * 0.65, ky + math.sin(ang) * kr * 0.65],
                   fill=(230, 230, 235, 255), width=max(2, int(H * 0.004)))
        for i in range(9):
            gy = y + h * 0.66 + i * H * 0.014
            if gy < y + h - H * 0.01:
                d.line([px0 + H * 0.02, gy, px1 - H * 0.02, gy], fill=(55, 55, 60, 255), width=max(2, int(H * 0.004)))
        d.ellipse([kx - H * 0.006, y + h * 0.05 - H * 0.006, kx + H * 0.006, y + h * 0.05 + H * 0.006],
                  fill=(255, 80, 60, 255))
    _text_center(d, x + w / 2, y + h + pad * 0.5, "RÉTRO STATION", _font(H * 0.02), (200, 200, 205, 255))
    return H * 0.045


def _arcade(img, hole, base, H):
    W = img.width
    x, y, w, h = hole
    img.alpha_composite(_vgrad(img.size, (14, 10, 26), (4, 4, 10)))
    d = ImageDraw.Draw(img)
    glowc = base + (255,)
    # rayures en diagonale sur les côtés
    stripes = Image.new("RGBA", img.size, (0, 0, 0, 0))
    sd = ImageDraw.Draw(stripes)
    step = H * 0.06
    for i in range(-20, int(W / step) + 20):
        x0 = i * step
        sd.polygon([(x0, H), (x0 + step * 0.45, H), (x0 + step * 0.45 + H * 0.6, 0), (x0 + H * 0.6, 0)],
                   fill=_shade(base, -0.55) + (90,))
    mask = Image.new("L", img.size, 255)
    ImageDraw.Draw(mask).rectangle([x - H * 0.06, 0, x + w + H * 0.06, H], fill=0)
    img.paste(Image.alpha_composite(img.copy(), stripes), (0, 0), mask)
    d = ImageDraw.Draw(img)
    # moulures lumineuses
    for side in (x - H * 0.05, x + w + H * 0.05):
        g = Image.new("RGBA", img.size, (0, 0, 0, 0))
        ImageDraw.Draw(g).line([side, 0, side, H], fill=glowc, width=int(H * 0.012))
        img.alpha_composite(g.filter(ImageFilter.GaussianBlur(H * 0.012)))
        d = ImageDraw.Draw(img)
        d.line([side, 0, side, H], fill=_shade(base, 0.5) + (255,), width=max(2, int(H * 0.004)))
    # cadre de l'écran
    d.rounded_rectangle([x - H * 0.03, y - H * 0.03, x + w + H * 0.03, y + h + H * 0.03], int(H * 0.02),
                        fill=(10, 10, 14, 255))
    # fronton
    if y > H * 0.06:
        mh = min(y - H * 0.04, H * 0.09)
        my = (y - H * 0.03) / 2
        _text_center(d, W / 2, my, "RÉTRO STATION", _font(mh * 0.7), _shade(base, 0.6) + (255,))
    return H * 0.012


def _neon(img, hole, base, H):
    W = img.width
    x, y, w, h = hole
    img.alpha_composite(_vgrad(img.size, (12, 8, 22), (4, 4, 8)))
    d = ImageDraw.Draw(img)
    gridc = _shade(base, -0.6) + (110,)
    for gx in range(0, W, int(H * 0.06)):
        d.line([gx, 0, gx, H], fill=gridc, width=1)
    for gy in range(0, H, int(H * 0.06)):
        d.line([0, gy, W, gy], fill=gridc, width=1)
    m = H * 0.02
    box = [x - m, y - m, x + w + m, y + h + m]
    for blur, width, alpha in ((H * 0.03, H * 0.02, 200), (H * 0.012, H * 0.01, 255)):
        g = Image.new("RGBA", img.size, (0, 0, 0, 0))
        ImageDraw.Draw(g).rounded_rectangle(box, int(H * 0.03), outline=base + (alpha,), width=int(width))
        img.alpha_composite(g.filter(ImageFilter.GaussianBlur(blur)))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle(box, int(H * 0.03), outline=_shade(base, 0.7) + (255,), width=max(2, int(H * 0.004)))
    return H * 0.02


DRAW = {"handheld": _handheld, "tv": _tv, "arcade": _arcade, "neon": _neon}


def hole_rect(cid, size_pct, W, H, style):
    asp = ASPECT.get(cid, 4 / 3)
    h = H * size_pct / 100
    w = h * asp
    room = 0.62 if style == "handheld" else (0.80 if style == "tv" else 0.92)
    if w > W * room:
        w = W * room
        h = w / asp
    x = (W - w) / 2 - (H * 0.12 if style == "tv" else 0)
    y = (H - h) / 2 - (H * 0.02 if style in ("handheld", "tv") else 0)
    return int(round(x)), int(round(y)), int(round(w)), int(round(h))


def _render_custom(cid, W, H):
    f = custom_file(cid)
    if not f.exists():
        return None
    src = Image.open(f).convert("RGBA")
    norm = custom_hole_norm(src)
    if not norm:
        return None
    img = src.resize((W, H), Image.LANCZOS)
    nx, ny, nw, nh = norm
    return img, (int(nx * W), int(ny * H), max(1, int(nw * W)), max(1, int(nh * H)))


def render_image(cid, style, color, size_pct, W, H):
    """Renvoie (image RGBA, trou (x, y, w, h))."""
    if style == "custom":
        res = _render_custom(cid, W, H)
        if res:
            return res
        style = "handheld"
    style = style if style in DRAW else "handheld"
    base = _rgb(COLORS[style].get(color) or next(iter(COLORS[style].values())))
    hole = hole_rect(cid, size_pct, W, H, style)
    img = Image.new("RGBA", (W, H), (0, 0, 0, 255))
    radius = DRAW[style](img, hole, base, H)
    x, y, w, h = hole
    m = Image.new("L", (W, H), 255)
    ImageDraw.Draw(m).rounded_rectangle([x, y, x + w - 1, y + h - 1], int(radius), fill=0)
    img.putalpha(Image.composite(img.getchannel("A"), Image.new("L", (W, H), 0), m))
    return img, hole


def render_overlay(cid, style, color, size_pct, W, H):
    """Crée (ou réutilise) le contour pour cet écran. Renvoie (fichier .cfg, trou)."""
    stamp = custom_file(cid).stat().st_mtime if style == "custom" and custom_file(cid).exists() else 0
    key = hashlib.md5(f"v1|{cid}|{style}|{color}|{size_pct}|{W}x{H}|{stamp}".encode()).hexdigest()[:12]
    out = paths.ENGINES / "contours"
    out.mkdir(parents=True, exist_ok=True)
    png, cfg = out / f"{key}.png", out / f"{key}.cfg"
    hole = hole_rect(cid, size_pct, W, H, style)
    if style == "custom" or not (png.exists() and cfg.exists()):
        img, hole = render_image(cid, style, color, size_pct, W, H)
        img.save(png)
        cfg.write_text(
            "overlays = 1\n"
            f'overlay0_overlay = "{png.name}"\n'
            "overlay0_full_screen = true\n"
            "overlay0_normalized = true\n"
            "overlay0_range_mod = 1.0\n"
            "overlay0_alpha_mod = 1.0\n"
            "overlay0_descs = 0\n", encoding="utf-8")
    return cfg, hole


def preview(cid, style, color, size_pct, W=640, H=360):
    """Aperçu : le contour avec une fausse image de jeu dans le trou."""
    if style == "none":
        img = Image.new("RGBA", (W, H), (0, 0, 0, 255))
        asp = ASPECT.get(cid, 4 / 3)
        h = int(H * min(100, size_pct) / 100)
        w = min(W, int(h * asp))
        h = int(w / asp)
        hole = ((W - w) // 2, (H - h) // 2, w, h)
        img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        m = Image.new("L", (W, H), 255)
        ImageDraw.Draw(m).rectangle([hole[0], hole[1], hole[0] + w - 1, hole[1] + h - 1], fill=0)
        img.putalpha(m)
    else:
        img, hole = render_image(cid, style, color, size_pct, W, H)
    x, y, w, h = hole
    fake = _vgrad((max(w, 1), max(h, 1)), (120, 190, 255), (90, 200, 120))
    fd = ImageDraw.Draw(fake)
    for i in range(0, w, max(4, w // 20)):
        fd.rectangle([i, int(h * 0.75), i + max(2, w // 40), h], fill=(70, 140, 70, 255))
    _text_center(fd, w / 2, h / 2, "ÉCRAN DU JEU", _font(max(10, h * 0.09)), (255, 255, 255, 230))
    bg = Image.new("RGBA", (W, H), (0, 0, 0, 255))
    bg.paste(fake, (x, y))
    bg.alpha_composite(img)
    return bg
