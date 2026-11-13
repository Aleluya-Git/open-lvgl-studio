"""Dibujo de widgets LVGL con QPainter, compartido por el canvas y el simulador.

Dibuja a partir del *estilo efectivo* que calcula domain/layout.py (tema
aproximado de LVGL 9 + theme + style_definitions + propiedades propias).
La fidelidad exacta llegará en la Fase 6 (simulador con LVGL real).
"""
from __future__ import annotations

import os
from typing import Any, Callable

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import (QBrush, QColor, QFont, QFontDatabase, QFontMetricsF, QPainter,
                           QPainterPath, QPen, QPixmap, QTextOption)

from olvgl.i18n import tr
from olvgl.domain import catalog
from olvgl.domain.layout import Box, font_size, named_colors, resolve_color
from olvgl.domain.model import Project, Screen, Widget
from olvgl.domain.values import display_text, is_tagged, opa_to_float, strip_recolor

FONT_FAMILIES = ["Montserrat", "Segoe UI", "Arial"]

_pixmap_cache: dict[str, tuple[float, QPixmap]] = {}
_FONTS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "resources", "fonts")
_bundled_done = False
BUNDLED_FAMILIES: list[str] = []


def ensure_bundled_fonts() -> list[str]:
    """Registra Montserrat (la fuente por defecto de LVGL, licencia OFL) que va
    con la aplicación, para que el canvas no dependa de las fuentes del sistema."""
    global _bundled_done
    fams: list[str] = []
    if _bundled_done:
        return BUNDLED_FAMILIES
    from PySide6.QtGui import QGuiApplication
    if QGuiApplication.instance() is None:   # sin aplicación Qt no se pueden registrar
        return fams
    _bundled_done = True
    if os.path.isdir(_FONTS_DIR):
        for name in sorted(os.listdir(_FONTS_DIR)):
            if name.lower().endswith((".ttf", ".otf")):
                fams += _font_families_for_file(os.path.join(_FONTS_DIR, name))
    BUNDLED_FAMILIES[:] = list(dict.fromkeys(fams))
    return BUNDLED_FAMILIES
_font_files: dict[str, list[str]] = {}


# --------------------------------------------------------------------------- recursos
def load_pixmap(path: str) -> QPixmap | None:
    if not path or not os.path.exists(path):
        return None
    mtime = os.path.getmtime(path)
    cached = _pixmap_cache.get(path)
    if cached and cached[0] == mtime:
        return cached[1]
    pm = QPixmap(path)
    if pm.isNull():
        return None
    _pixmap_cache[path] = (mtime, pm)
    return pm


def image_size(path: str) -> tuple[int, int] | None:
    pm = load_pixmap(path)
    return (pm.width(), pm.height()) if pm else None


def _font_families_for_file(path: str) -> list[str]:
    if path in _font_files:
        return _font_files[path]
    fams: list[str] = []
    if os.path.exists(path):
        fid = QFontDatabase.addApplicationFont(path)
        if fid >= 0:
            fams = list(QFontDatabase.applicationFontFamilies(fid))
            from olvgl.presentation.fonts import invalidate
            invalidate()
    _font_files[path] = fams
    return fams


def qcolor(value: str, fallback: str = "#000000") -> QColor:
    c = QColor(str(value))
    return c if c.isValid() else QColor(fallback)


class RenderContext:
    """Todo lo que el dibujo necesita saber del proyecto (colores, fuentes, imágenes)."""

    def __init__(self, project: Project, resolve_path: Callable[[str], str] | None = None):
        ensure_bundled_fonts()
        self.project = project
        self.colors = named_colors(project)
        self.resolve_path = resolve_path or (lambda p: p)
        self._fonts: dict[str, QFont] = {}

    def color(self, value: Any, default: str = "#000000", opa: Any = None) -> QColor:
        c = QColor(resolve_color(value, self.colors, default))
        if opa is not None:
            c.setAlphaF(opa_to_float(opa))
        return c

    def font(self, name: Any) -> QFont:
        key = str(name or catalog.DEFAULT_FONT)
        f = self._fonts.get(key)
        if f is not None:
            return f
        f = QFont()
        families = list(FONT_FAMILIES)
        res = self.project.font(key)
        if res is not None:
            from olvgl.infrastructure import font_cache
            file = res.file
            cached = font_cache.cached_path(file)
            if cached:
                families = _font_families_for_file(cached) + families
            elif isinstance(file, str) and not file.startswith(("gfonts:", "mdi:")) and "://" not in file:
                families = _font_families_for_file(self.resolve_path(file)) + families
            elif isinstance(file, str) and file.startswith("gfonts://"):
                families = [file[len("gfonts://"):].split("@")[0]] + families
            elif isinstance(file, dict) and file.get("family"):
                families = [str(file["family"])] + families
            if font_cache.font_weight(file) >= 600:
                f.setBold(True)
        else:
            f.setWeight(QFont.Weight.Medium)   # las montserrat_N de LVGL son Montserrat Medium
        from olvgl.presentation.fonts import pick_family
        f.setFamily(pick_family(families))
        f.setPixelSize(max(4, font_size(self.project, key)))
        self._fonts[key] = f
        return f

    def image_path(self, image_id: Any) -> str | None:
        if not isinstance(image_id, str):
            return None
        img = self.project.image(image_id)
        return self.resolve_path(img.path) if img else None

    # medidas para el motor de disposición
    def measure_text(self, text: str, font: str, max_width: float | None = None) -> tuple[float, float]:
        fm = QFontMetricsF(self.font(font))
        line_h = fm.lineSpacing()
        lines = text.split("\n") if text else [""]
        width, n = 0.0, 0
        for line in lines:
            if max_width and max_width > 0:
                cur = ""
                for word in line.split(" "):
                    cand = f"{cur} {word}" if cur else word
                    if fm.horizontalAdvance(cand) > max_width and cur:
                        width = max(width, fm.horizontalAdvance(cur))
                        n += 1
                        cur = word
                    else:
                        cur = cand
                width = max(width, fm.horizontalAdvance(cur))
                n += 1
            else:
                width = max(width, fm.horizontalAdvance(line))
                n += 1
        if max_width and max_width > 0:
            width = min(width, max_width)
        return (float(int(width + 0.999)), float(int(n * line_h + 0.999)))

    def image_size_of(self, image_id: str) -> tuple[int, int] | None:
        path = self.image_path(image_id)
        return image_size(path) if path else None


# --------------------------------------------------------------------------- primitivas
def draw_text(p: QPainter, rect: QRectF, text: str, align, wrap: bool = False) -> None:
    """Dibuja texto con QTextOption (evita convertir flags de Qt a int)."""
    opt = QTextOption(align)
    opt.setWrapMode(QTextOption.WrapMode.WordWrap if wrap else QTextOption.WrapMode.NoWrap)
    p.drawText(rect, text, opt)


def _num(v: Any, default: float = 0.0) -> float:
    if isinstance(v, bool) or v is None or is_tagged(v):
        return default
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def _h_align(value: Any) -> Qt.AlignmentFlag:
    v = str(value or "").upper()
    if v == "CENTER":
        return Qt.AlignmentFlag.AlignHCenter
    if v == "RIGHT":
        return Qt.AlignmentFlag.AlignRight
    return Qt.AlignmentFlag.AlignLeft


def with_state(eff: dict, *states: str) -> dict:
    """Aplica los mapas de estado (pressed:, checked:…) sobre el estilo."""
    out = dict(eff)
    for st in states:
        sub = eff.get(st)
        if isinstance(sub, dict) and not is_tagged(sub):
            out.update({k: v for k, v in sub.items() if not isinstance(v, dict)})
    return out


def part(eff: dict, name: str) -> dict:
    sub = eff.get(name)
    return sub if isinstance(sub, dict) and not is_tagged(sub) else {}


def paint_box(p: QPainter, rect: QRectF, eff: dict, ctx: RenderContext) -> None:
    """Fondo, borde y radio según bg_color/bg_opa, border_*, radius."""
    radius = min(_num(eff.get("radius")), rect.width() / 2, rect.height() / 2)
    bg_opa = opa_to_float(eff.get("bg_opa"), 0.0 if "bg_color" not in eff else 1.0)
    bw = _num(eff.get("border_width"))
    p.save()
    p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    if bg_opa > 0 and "bg_color" in eff:
        c = ctx.color(eff.get("bg_color"), "#FFFFFF")
        c.setAlphaF(bg_opa)
        grad = eff.get("bg_grad_color")
        p.setPen(Qt.PenStyle.NoPen)
        if grad is not None and str(eff.get("bg_grad_dir", "NONE")).upper() in ("VER", "HOR"):
            from PySide6.QtGui import QLinearGradient
            vertical = str(eff.get("bg_grad_dir")).upper() == "VER"
            g = QLinearGradient(rect.topLeft(), rect.bottomLeft() if vertical else rect.topRight())
            g2 = ctx.color(grad, "#FFFFFF")
            g2.setAlphaF(bg_opa)
            g.setColorAt(0, c)
            g.setColorAt(1, g2)
            p.setBrush(QBrush(g))
        else:
            p.setBrush(QBrush(c))
        p.drawRoundedRect(rect, radius, radius)
    if bw > 0:
        bc = ctx.color(eff.get("border_color"), "#E0E0E0")
        bc.setAlphaF(opa_to_float(eff.get("border_opa"), 1.0) * bc.alphaF())
        p.setPen(QPen(bc, bw))
        p.setBrush(Qt.BrushStyle.NoBrush)
        inner = rect.adjusted(bw / 2, bw / 2, -bw / 2, -bw / 2)
        r2 = max(0.0, radius - bw / 2)
        p.drawRoundedRect(inner, r2, r2)
    p.restore()


def content_rect(rect: QRectF, eff: dict) -> QRectF:
    base = _num(eff.get("pad_all"))
    bw = _num(eff.get("border_width"))
    return rect.adjusted(_num(eff.get("pad_left", base), base) + bw, _num(eff.get("pad_top", base), base) + bw,
                         -(_num(eff.get("pad_right", base), base) + bw),
                         -(_num(eff.get("pad_bottom", base), base) + bw))


def paint_text(p: QPainter, rect: QRectF, text: str, eff: dict, ctx: RenderContext,
               v_center: bool = False, default_color: str = catalog.LV_TEXT) -> None:
    p.save()
    p.setFont(ctx.font(eff.get("text_font")))
    color = ctx.color(eff.get("text_color"), default_color)
    color.setAlphaF(color.alphaF() * opa_to_float(eff.get("text_opa"), 1.0))
    p.setPen(color)
    p.setClipRect(rect.adjusted(-1, -1, 1, 1))
    mode = str(eff.get("long_mode", "WRAP")).upper()
    align = _h_align(eff.get("text_align"))
    valign = Qt.AlignmentFlag.AlignVCenter if v_center else Qt.AlignmentFlag.AlignTop
    if mode == "WRAP":
        draw_text(p, rect, text, align | valign, wrap=True)
    else:
        line = text.replace("\n", " ")
        if mode == "DOT":
            line = QFontMetricsF(p.font()).elidedText(line, Qt.TextElideMode.ElideRight, rect.width())
        draw_text(p, rect, line, align | valign)
    p.restore()


def _value_ratio(eff: dict, default_min: float = 0, default_max: float = 100) -> float:
    lo = _num(eff.get("min_value"), default_min)
    hi = _num(eff.get("max_value"), default_max)
    v = _num(eff.get("value"), lo)
    if hi <= lo:
        return 0.0
    return max(0.0, min(1.0, (v - lo) / (hi - lo)))


def _is_checked(w: Widget, eff: dict, checked: bool) -> bool:
    if checked:
        return True
    st = eff.get("state")
    return isinstance(st, dict) and bool(st.get("checked"))


# --------------------------------------------------------------------------- widgets
# tipo de widget de plugin → función (painter, rect, widget, props efectivas, RenderContext, estado)
CUSTOM_PAINTERS: dict[str, Callable[..., None]] = {}


def paint_widget(p: QPainter, w: Widget, rect: QRectF, eff: dict, ctx: RenderContext,
                 box: Box | None = None, pressed: bool = False, checked: bool = False) -> None:
    """Dibuja un widget (sin sus hijos) en `rect`."""
    t = w.type
    custom = CUSTOM_PAINTERS.get(t)
    if custom is not None:
        p.save()
        try:
            custom(p, rect, w, eff, ctx, {"pressed": pressed, "checked": checked})
        except Exception as exc:     # un plugin roto se ve como un aviso, no cierra la app
            _placeholder(p, rect, f"{t}: {exc}"[:80])
        finally:
            p.restore()
        return
    is_checked = _is_checked(w, eff, checked)
    states = (("checked",) if is_checked else ()) + (("pressed",) if pressed else ())
    eff = with_state(eff, *states)
    opa = opa_to_float(eff.get("opa"), 1.0)
    p.save()
    if opa < 1.0:
        p.setOpacity(p.opacity() * opa)
    try:
        if t == "label":
            paint_box(p, rect, eff, ctx)
            text = display_text(eff.get("text", ""))
            if eff.get("recolor") is True:
                text = strip_recolor(text)
            paint_text(p, content_rect(rect, eff), text, eff, ctx)
        elif t == "button":
            if pressed or is_checked:
                c = ctx.color(eff.get("bg_color"), catalog.LV_PRIMARY)
                if pressed:
                    c = c.darker(120)
                if is_checked and "checked" not in eff:
                    c = c.darker(135)
                eff = dict(eff, bg_color=c.name(QColor.NameFormat.HexRgb))
            paint_box(p, rect, eff, ctx)
            if "text" in w.props:
                paint_text(p, content_rect(rect, eff), display_text(w.props.get("text")),
                           dict(eff, text_align="CENTER"), ctx, v_center=True, default_color="#FFFFFF")
        elif t == "image":
            path = ctx.image_path(w.props.get("src"))
            pm = load_pixmap(path) if path else None
            if pm is not None:
                p.drawPixmap(QRectF(rect.x(), rect.y(), pm.width(), pm.height()), pm,
                             QRectF(0, 0, pm.width(), pm.height()))
            else:
                _placeholder(p, rect, str(w.props.get("src") or "imagen"))
        elif t in ("slider", "bar"):
            _paint_slider(p, rect, w, eff, ctx, knob=(t == "slider"))
        elif t == "switch":
            _paint_switch(p, rect, eff, ctx, is_checked)
        elif t in ("arc", "spinner"):
            _paint_arc(p, rect, eff, ctx, spinner=(t == "spinner"))
        elif t == "checkbox":
            _paint_checkbox(p, rect, w, eff, ctx, is_checked)
        elif t == "led":
            c = ctx.color(eff.get("color"), catalog.LV_PRIMARY)
            c.setAlphaF(max(0.25, opa_to_float(eff.get("brightness"), 1.0)))
            p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(c)
            p.drawEllipse(rect)
        elif t == "dropdown":
            paint_box(p, rect, eff, ctx)
            opts = eff.get("options")
            first = opts[0] if isinstance(opts, list) and opts else str(opts or "").split("\n")[0]
            idx = int(_num(eff.get("selected_index"), 0))
            if isinstance(opts, list) and 0 <= idx < len(opts):
                first = opts[idx]
            cr = content_rect(rect, eff)
            paint_text(p, cr.adjusted(0, 0, -16, 0), display_text(first), dict(eff, long_mode="DOT"),
                       ctx, v_center=True)
            paint_text(p, cr, "▾", dict(eff, text_align="RIGHT", long_mode="CLIP"), ctx, v_center=True)
        elif t == "roller":
            paint_box(p, rect, eff, ctx)
            _paint_roller(p, rect, w, eff, ctx)
        elif t == "textarea":
            paint_box(p, rect, eff, ctx)
            text = display_text(eff.get("text", ""))
            if text:
                paint_text(p, content_rect(rect, eff), text, eff, ctx)
            else:
                paint_text(p, content_rect(rect, eff), display_text(eff.get("placeholder_text", "")),
                           dict(eff, text_color="#9E9E9E"), ctx)
        elif t == "tabview":
            paint_box(p, rect, eff, ctx)
            if box is not None:
                _paint_tab_bar(p, box, eff, ctx)
        elif t == "buttonmatrix":
            paint_box(p, rect, eff, ctx)
            _paint_button_matrix(p, content_rect(rect, eff), eff, ctx)
        elif t == "line":
            _paint_line(p, rect, w, eff, ctx)
        elif t == "spinbox":
            paint_box(p, rect, eff, ctx)
            paint_text(p, content_rect(rect, eff), spinbox_text(w), dict(eff, text_align="CENTER",
                                                                           long_mode="CLIP"), ctx, v_center=True)
        elif t == "keyboard":
            paint_box(p, rect, eff, ctx)
            _paint_keyboard(p, content_rect(rect, eff), w, eff, ctx)
        elif t == "qrcode":
            _paint_qrcode(p, rect, w, eff, ctx)
        elif t == "meter":
            paint_box(p, rect, eff, ctx)
            _paint_meter(p, rect, ctx)
        elif t == "animimg":
            srcs = w.props.get("src")
            path = ctx.image_path(srcs[0]) if isinstance(srcs, list) and srcs else None
            pm = load_pixmap(path) if path else None
            if pm is not None:
                p.drawPixmap(QRectF(rect.x(), rect.y(), pm.width(), pm.height()), pm,
                             QRectF(0, 0, pm.width(), pm.height()))
            else:
                _placeholder(p, rect, "animimg")
        elif t == "canvas":
            if not eff.get("transparent"):
                paint_box(p, rect, dict(eff, bg_color=eff.get("bg_color", "#FFFFFF"), bg_opa="COVER"), ctx)
            _type_hint(p, rect, catalog.type_label(t))
        elif t in ("obj", "tab", "tile", "tileview"):
            paint_box(p, rect, eff, ctx)
        else:
            _placeholder(p, rect, t)
    finally:
        p.restore()


def _paint_roller(p: QPainter, rect: QRectF, w: Widget, eff: dict, ctx: RenderContext) -> None:
    opts = eff.get("options")
    items = [display_text(i) for i in (opts if isinstance(opts, list) else str(opts or "").split("\n"))]
    if not items:
        return
    sel = int(_num(eff.get("selected_index"), 0)) % len(items)
    rows = int(_num(eff.get("visible_row_count"), 3)) or 3
    fm = QFontMetricsF(ctx.font(eff.get("text_font")))
    rh = max(fm.lineSpacing() + 6, rect.height() / max(1, rows))
    cy = rect.center().y()
    p.save()
    p.setClipRect(rect)
    sel_eff = part(eff, "selected")
    band = QRectF(rect.x(), cy - rh / 2, rect.width(), rh)
    paint_box(p, band, {"bg_color": sel_eff.get("bg_color", catalog.LV_PRIMARY),
                        "bg_opa": sel_eff.get("bg_opa", "COVER")}, ctx)
    half = rows // 2 + 1
    for off in range(-half, half + 1):
        i = sel + off
        if not 0 <= i < len(items):
            continue
        r = QRectF(rect.x(), cy - rh / 2 + off * rh, rect.width(), rh)
        te = dict(eff, text_align="CENTER", long_mode="CLIP")
        if off == 0:
            te["text_color"] = sel_eff.get("text_color", "#FFFFFF")
        paint_text(p, r, items[i], te, ctx, v_center=True)
    p.restore()


def spinbox_text(w: Widget) -> str:
    digits = int(_num(catalog.prop_value(w, "digits"), 4))
    dec = int(_num(catalog.prop_value(w, "decimal_places"), 0))
    v = int(_num(catalog.prop_value(w, "value"), 0))
    s = str(abs(v)).rjust(max(1, digits), "0")
    if 0 < dec < len(s):
        s = s[:-dec] + "." + s[-dec:]
    lo = _num(catalog.prop_value(w, "range_from"), -100)
    return ("-" if v < 0 else ("+" if lo < 0 else "")) + s


def _paint_line(p: QPainter, rect: QRectF, w: Widget, eff: dict, ctx: RenderContext) -> None:
    from olvgl.domain.layout import line_points
    from PySide6.QtGui import QPolygonF
    pts = line_points(w.props.get("points"))
    if len(pts) < 2:
        _placeholder(p, rect, tr("línea"))
        return
    width = _num(eff.get("line_width"), 1)
    cap = Qt.PenCapStyle.RoundCap if eff.get("line_rounded") else Qt.PenCapStyle.FlatCap
    color = ctx.color(eff.get("line_color"), "#000000")
    color.setAlphaF(color.alphaF() * opa_to_float(eff.get("line_opa"), 1.0))
    p.save()
    p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    p.setPen(QPen(color, max(1.0, width), Qt.PenStyle.SolidLine, cap, Qt.PenJoinStyle.RoundJoin))
    p.drawPolyline(QPolygonF([QPointF(rect.x() + x, rect.y() + y) for x, y in pts]))
    p.restore()


_KEY_ROWS = {
    "TEXT_LOWER": ["1#qwertyuiop", "ABCasdfghjklñ", "_-zxcvbnm.,:", "  ✓"],
    "TEXT_UPPER": ["1#QWERTYUIOP", "abcASDFGHJKLÑ", "_-ZXCVBNM.,:", "  ✓"],
    "SPECIAL": ["1#+&/*=%!?#<>", "abc\\@$()\"\":;", "_-[]{}'~^", "  ✓"],
    "NUMBER": ["123", "456", "789", "-0."],
}


def _paint_keyboard(p: QPainter, rect: QRectF, w: Widget, eff: dict, ctx: RenderContext) -> None:
    mode = str(w.props.get("mode") or "TEXT_LOWER").upper()
    rows = _KEY_ROWS.get(mode, _KEY_ROWS["TEXT_LOWER"])
    gap = 4.0
    rh = (rect.height() - gap * (len(rows) - 1)) / len(rows)
    for ri, row in enumerate(rows):
        keys = list(row) if row.strip() != "✓" else ["⌨", "␣", "✓"]
        if row.startswith("  "):
            keys = ["⌨", "␣", "✓"]
        kw = (rect.width() - gap * (len(keys) - 1)) / max(1, len(keys))
        for ki, k in enumerate(keys):
            r = QRectF(rect.x() + ki * (kw + gap), rect.y() + ri * (rh + gap), kw, rh)
            paint_box(p, r, {"bg_color": "#FFFFFF", "bg_opa": "COVER", "radius": 6}, ctx)
            paint_text(p, r, k, dict(eff, text_align="CENTER", long_mode="CLIP",
                                     text_font=eff.get("text_font", "montserrat_16")), ctx, v_center=True)


def _paint_qrcode(p: QPainter, rect: QRectF, w: Widget, eff: dict, ctx: RenderContext) -> None:
    """Patrón con aspecto de QR (no es un código válido: se genera en el dispositivo)."""
    import hashlib
    dark = ctx.color(w.props.get("dark_color"), "#000000")
    light = ctx.color(w.props.get("light_color"), "#FFFFFF")
    n = 25
    size = min(rect.width(), rect.height())
    cell = size / n
    p.save()
    p.fillRect(QRectF(rect.x(), rect.y(), size, size), light)
    seed = hashlib.sha1(str(w.props.get("text", "")).encode("utf-8")).digest()
    bits = int.from_bytes(seed * 20, "big")
    for y in range(n):
        for x in range(n):
            finder = any(x0 <= x < x0 + 7 and y0 <= y < y0 + 7 for x0, y0 in ((0, 0), (n - 7, 0), (0, n - 7)))
            if finder:
                fx = x if x < 7 else x - (n - 7)
                fy = y if y < 7 else y - (n - 7)
                on = fx in (0, 6) or fy in (0, 6) or (2 <= fx <= 4 and 2 <= fy <= 4)
            else:
                on = (bits >> ((y * n + x) % 3000)) & 1
            if on:
                p.fillRect(QRectF(rect.x() + x * cell, rect.y() + y * cell, cell + 0.5, cell + 0.5), dark)
    p.restore()


def _paint_meter(p: QPainter, rect: QRectF, ctx: RenderContext) -> None:
    import math
    size = min(rect.width(), rect.height())
    c = QPointF(rect.center().x(), rect.center().y())
    r = size / 2 - 10
    p.save()
    p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    p.setPen(QPen(QColor("#9E9E9E"), 2))
    for i in range(21):
        a = math.radians(135 + 270 * i / 20)
        r1 = r - (10 if i % 5 == 0 else 5)
        p.drawLine(QPointF(c.x() + r * math.cos(a), c.y() + r * math.sin(a)),
                   QPointF(c.x() + r1 * math.cos(a), c.y() + r1 * math.sin(a)))
    a = math.radians(135 + 270 * 0.6)
    p.setPen(QPen(QColor(catalog.LV_PRIMARY), 4, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
    p.drawLine(c, QPointF(c.x() + (r - 15) * math.cos(a), c.y() + (r - 15) * math.sin(a)))
    p.restore()


def _placeholder(p: QPainter, rect: QRectF, text: str) -> None:
    p.save()
    p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    p.setPen(QPen(QColor("#9E9E9E"), 1, Qt.PenStyle.DashLine))
    p.setBrush(QColor(158, 158, 158, 40))
    p.drawRect(rect.adjusted(0.5, 0.5, -0.5, -0.5))
    p.drawLine(rect.topLeft(), rect.bottomRight())
    p.drawLine(rect.topRight(), rect.bottomLeft())
    from olvgl.presentation.fonts import pick_family
    f = QFont(pick_family(FONT_FAMILIES))
    f.setPixelSize(10)
    p.setFont(f)
    p.setPen(QColor("#616161"))
    draw_text(p, rect, text, Qt.AlignmentFlag.AlignCenter, wrap=True)
    p.restore()


def _type_hint(p: QPainter, rect: QRectF, text: str) -> None:
    p.save()
    from olvgl.presentation.fonts import pick_family
    f = QFont(pick_family(FONT_FAMILIES))
    f.setPixelSize(11)
    p.setFont(f)
    p.setPen(QColor(128, 128, 128, 200))
    draw_text(p, rect, text, Qt.AlignmentFlag.AlignCenter)
    p.restore()


def _paint_slider(p: QPainter, rect: QRectF, w: Widget, eff: dict, ctx: RenderContext, knob: bool) -> None:
    vertical = rect.height() > rect.width()
    paint_box(p, rect, dict(eff, radius=eff.get("radius", 1000)), ctx)
    ind = with_state(part(eff, "indicator"), *())
    ratio = _value_ratio(eff)
    if vertical:
        ir = QRectF(rect.x(), rect.bottom() - rect.height() * ratio, rect.width(), rect.height() * ratio)
    else:
        ir = QRectF(rect.x(), rect.y(), rect.width() * ratio, rect.height())
    ieff = {"bg_color": ind.get("bg_color", catalog.LV_PRIMARY), "bg_opa": ind.get("bg_opa", "COVER"),
            "radius": ind.get("radius", eff.get("radius", 1000))}
    if ratio > 0:
        paint_box(p, ir, ieff, ctx)
    if knob:
        k = part(eff, "knob")
        d = min(rect.width(), rect.height()) + 10
        cx = ir.right() if not vertical else rect.center().x()
        cy = rect.center().y() if not vertical else ir.top()
        kr = QRectF(cx - d / 2, cy - d / 2, d, d)
        paint_box(p, kr, {"bg_color": k.get("bg_color", "#FFFFFF"), "bg_opa": "COVER", "radius": 1000,
                          "border_width": k.get("border_width", 2),
                          "border_color": k.get("border_color", catalog.LV_PRIMARY)}, ctx)


def _paint_switch(p: QPainter, rect: QRectF, eff: dict, ctx: RenderContext, checked: bool) -> None:
    ind = part(eff, "indicator")
    track = dict(eff, radius=1000)
    if checked:
        track["bg_color"] = ind.get("bg_color", catalog.LV_PRIMARY)
        track["bg_opa"] = "COVER"
    paint_box(p, rect, track, ctx)
    pad = 3
    d = rect.height() - 2 * pad
    x = rect.right() - pad - d if checked else rect.x() + pad
    knob = part(eff, "knob")
    paint_box(p, QRectF(x, rect.y() + pad, d, d),
              {"bg_color": knob.get("bg_color", "#FFFFFF"), "bg_opa": "COVER", "radius": 1000}, ctx)


def _arc_path(rect: QRectF, start: float, end: float) -> tuple[float, float]:
    """Ángulos LVGL (horario desde las 3) → ángulos de Qt (antihorario)."""
    span = (end - start) % 360 or (360 if end != start else 0)
    return -start, -span


def _paint_arc(p: QPainter, rect: QRectF, eff: dict, ctx: RenderContext, spinner: bool) -> None:
    width = _num(eff.get("arc_width"), 10)
    size = min(rect.width(), rect.height())
    sq = QRectF(rect.center().x() - size / 2, rect.center().y() - size / 2, size, size)
    ar = sq.adjusted(width / 2, width / 2, -width / 2, -width / 2)
    rot = _num(eff.get("rotation"), 0)
    p.save()
    p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    cap = Qt.PenCapStyle.RoundCap

    def arc(color: QColor, a0: float, a1: float) -> None:
        start, span = _arc_path(ar, a0 + rot, a1 + rot)
        if span == 0:
            return
        path = QPainterPath()
        path.arcMoveTo(ar, start)
        path.arcTo(ar, start, span)
        p.setPen(QPen(color, width, Qt.PenStyle.SolidLine, cap))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawPath(path)

    bg0 = _num(eff.get("bg_start_angle"), 0 if spinner else 135)
    bg1 = _num(eff.get("bg_end_angle"), 360 if spinner else 45)
    arc(ctx.color(eff.get("arc_color"), "#E0E0E0"), bg0, bg1)
    ind = part(eff, "indicator")
    icolor = ctx.color(ind.get("arc_color"), catalog.LV_PRIMARY)
    if spinner:
        arc(icolor, 270, 330)
    else:
        span = (bg1 - bg0) % 360 or 360
        arc(icolor, bg0, bg0 + span * _value_ratio(eff))
        k = part(eff, "knob")
        if k or eff.get("adjustable", True):
            import math
            ang = math.radians(bg0 + rot + span * _value_ratio(eff))
            cx = ar.center().x() + ar.width() / 2 * math.cos(ang)
            cy = ar.center().y() + ar.height() / 2 * math.sin(ang)
            d = width + 6
            paint_box(p, QRectF(cx - d / 2, cy - d / 2, d, d),
                      {"bg_color": k.get("bg_color", catalog.LV_PRIMARY), "bg_opa": "COVER",
                       "radius": 1000}, ctx)
    p.restore()


def _paint_checkbox(p: QPainter, rect: QRectF, w: Widget, eff: dict, ctx: RenderContext, checked: bool) -> None:
    font = ctx.font(eff.get("text_font"))
    s = QFontMetricsF(font).height()
    br = QRectF(rect.x(), rect.y() + (rect.height() - s) / 2, s, s)
    ind = part(eff, "indicator")
    beff = {"bg_color": ind.get("bg_color", catalog.LV_PRIMARY if checked else "#FFFFFF"), "bg_opa": "COVER",
            "border_width": 2, "border_color": ind.get("border_color", catalog.LV_PRIMARY), "radius": 4}
    paint_box(p, br, beff, ctx)
    if checked:
        p.save()
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        p.setPen(QPen(QColor("#FFFFFF"), max(2.0, s / 8)))
        from PySide6.QtGui import QPolygonF
        p.drawPolyline(QPolygonF([QPointF(br.x() + s * 0.22, br.y() + s * 0.52),
                                  QPointF(br.x() + s * 0.42, br.y() + s * 0.72),
                                  QPointF(br.x() + s * 0.78, br.y() + s * 0.3)]))
        p.restore()
    text = display_text(w.props.get("text", ""))
    if text:
        gap = _num(eff.get("pad_column"), 8)
        paint_text(p, QRectF(br.right() + gap, rect.y(), rect.width() - s - gap, rect.height()), text,
                   dict(eff, long_mode="CLIP"), ctx, v_center=True)


def _paint_tab_bar(p: QPainter, box: Box, eff: dict, ctx: RenderContext) -> None:
    bar = box.extra.get("tab_bar")
    if bar is None:
        return
    br = QRectF(bar.x, bar.y, bar.w, bar.h)
    tb = part(eff, "tab_style") or {}
    paint_box(p, br, {"bg_color": tb.get("bg_color", "#F5F5F5"), "bg_opa": "COVER"}, ctx)
    active = box.extra.get("active", 0)
    for i, (r, name, _tid) in enumerate(box.extra.get("tab_buttons", [])):
        rr = QRectF(r.x, r.y, r.w, r.h)
        teff = dict(eff, text_align="CENTER", long_mode="DOT")
        if i == active:
            p.save()
            p.fillRect(QRectF(rr.x(), rr.bottom() - 3, rr.width(), 3), QColor(catalog.LV_PRIMARY))
            p.restore()
            teff["text_color"] = catalog.LV_PRIMARY
        paint_text(p, rr.adjusted(4, 0, -4, 0), name, teff, ctx, v_center=True)


def _paint_button_matrix(p: QPainter, rect: QRectF, eff: dict, ctx: RenderContext) -> None:
    rows = eff.get("rows")
    if not isinstance(rows, list) or not rows:
        _type_hint(p, rect, tr("Matriz de botones"))
        return
    gap = 6.0
    rh = (rect.height() - gap * (len(rows) - 1)) / len(rows)
    for ri, row in enumerate(rows):
        buttons = row.get("buttons", []) if isinstance(row, dict) else []
        if not buttons:
            continue
        bw = (rect.width() - gap * (len(buttons) - 1)) / len(buttons)
        for bi, b in enumerate(buttons):
            r = QRectF(rect.x() + bi * (bw + gap), rect.y() + ri * (rh + gap), bw, rh)
            paint_box(p, r, {"bg_color": "#FFFFFF", "bg_opa": "COVER", "radius": 6,
                             "border_width": 1, "border_color": "#E0E0E0"}, ctx)
            text = display_text(b.get("text", "")) if isinstance(b, dict) else ""
            paint_text(p, r, text, dict(eff, text_align="CENTER", long_mode="DOT"), ctx, v_center=True)


# --------------------------------------------------------------------------- árbol
def page_background(project: Project, screen: Screen | None, ctx: RenderContext) -> QColor:
    from olvgl.domain.layout import page_props
    eff = page_props(project, screen)
    return ctx.color(eff.get("bg_color"), "#FFFFFF")


def paint_tree(p: QPainter, widgets: list[Widget], boxes: dict[str, Box], ctx: RenderContext,
               pressed: str | None = None, checked: set[str] | frozenset = frozenset(),
               skip_hidden: bool = True) -> None:
    """Dibuja widgets y sus hijos con el recorte de LVGL (cada hijo dentro de su padre)."""
    for w in widgets:
        b = boxes.get(w.id)
        if b is None or not b.shown or (skip_hidden and b.hidden):
            continue
        r = QRectF(b.rect.x, b.rect.y, b.rect.w, b.rect.h)
        paint_widget(p, w, r, b.props, ctx, b, pressed=(w.id == pressed), checked=(w.id in checked))
        if w.children:
            p.save()
            if not b.props.get("overflow_visible"):
                p.setClipRect(r, Qt.ClipOperation.IntersectClip)
            paint_tree(p, w.children, boxes, ctx, pressed, checked, skip_hidden)
            p.restore()


def widget_icon_color(widget_type: str) -> str:
    return {"label": "#26A69A", "button": "#42A5F5", "image": "#AB47BC"}.get(widget_type, "#9E9E9E")
