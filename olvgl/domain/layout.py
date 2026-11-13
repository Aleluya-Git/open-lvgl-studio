"""Motor de disposición: calcula dónde dibuja LVGL cada widget.

Resuelve, en coordenadas absolutas de la pantalla:
- estilos efectivos: tema por defecto aproximado de LVGL 9 → `theme:` →
  `styles:` (style_definitions) → propiedades propias, con herencia de las
  propiedades de texto del padre, como hace LVGL;
- tamaños en px, porcentaje, SIZE_CONTENT o por defecto del tipo;
- `align` (9 posiciones), desplazamientos x/y (px o %) y `align_to`;
- disposiciones flex (ROW/COLUMN, WRAP, REVERSE, grow, alineaciones) y grid
  (px, FR(n), CONTENT, celdas con span y alineación; atajo `layout: 2x3`);
- pestañas (tabview/tab) y mosaicos (tileview/tile) mostrando el activo;
- `hidden`, `floating` e `ignore_layout`.

Es una aproximación fiel en geometría pero no idéntica píxel a píxel; el
simulador profesional de la Fase 6 usará LVGL real.
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from typing import Any, Callable

from olvgl.domain import catalog
from olvgl.domain.model import Project, Screen, Widget, normalize_color
from olvgl.domain.values import is_tagged

INHERITED = ("text_color", "text_font", "text_opa", "text_align", "text_letter_space",
             "text_line_space", "text_decor")

PRIMARY = catalog.LV_PRIMARY

# Aproximación del tema por defecto de LVGL 9 (modo claro)
BUILTIN_STYLES: dict[str, dict[str, Any]] = {
    "page": {"bg_color": "#FFFFFF", "bg_opa": "COVER", "text_color": catalog.LV_TEXT,
             "text_font": catalog.DEFAULT_FONT},
    "obj": {"bg_color": "#FFFFFF", "bg_opa": "COVER", "border_width": 2, "border_color": "#E0E0E0",
            "radius": 8, "pad_all": 16, "pad_row": 10, "pad_column": 10},
    "button": {"bg_color": PRIMARY, "bg_opa": "COVER", "radius": 8, "text_color": "#FFFFFF",
               "pad_left": 16, "pad_right": 16, "pad_top": 8, "pad_bottom": 8,
               "pad_row": 6, "pad_column": 6},
    "label": {"bg_opa": "TRANSP"},
    "image": {"bg_opa": "TRANSP"},
    "slider": {"bg_color": PRIMARY, "bg_opa": "30%", "radius": 1000},
    "bar": {"bg_color": PRIMARY, "bg_opa": "30%", "radius": 1000},
    "switch": {"bg_color": "#BDBDBD", "bg_opa": "COVER", "radius": 1000},
    "arc": {"arc_color": "#E0E0E0", "arc_width": 10},
    "spinner": {"arc_color": "#E0E0E0", "arc_width": 8},
    "checkbox": {"bg_opa": "TRANSP", "pad_column": 8},
    "led": {"color": PRIMARY},
    "dropdown": {"bg_color": "#FFFFFF", "bg_opa": "COVER", "border_width": 2, "border_color": "#E0E0E0",
                 "radius": 8, "pad_left": 12, "pad_right": 12, "pad_top": 8, "pad_bottom": 8},
    "roller": {"bg_color": "#FFFFFF", "bg_opa": "COVER", "border_width": 2, "border_color": "#E0E0E0",
               "radius": 8},
    "textarea": {"bg_color": "#FFFFFF", "bg_opa": "COVER", "border_width": 2, "border_color": "#E0E0E0",
                 "radius": 8, "pad_all": 12},
    "tabview": {"bg_color": "#FFFFFF", "bg_opa": "COVER"},
    "tab": {"bg_opa": "TRANSP", "pad_all": 16, "pad_row": 10, "pad_column": 10},
    "tileview": {"bg_opa": "TRANSP"},
    "tile": {"bg_opa": "TRANSP"},
    "buttonmatrix": {"bg_color": "#FFFFFF", "bg_opa": "COVER", "border_width": 2,
                     "border_color": "#E0E0E0", "radius": 8, "pad_all": 8},
    "keyboard": {"bg_color": "#EEEEEE", "bg_opa": "COVER", "pad_all": 4},
    "meter": {"bg_color": "#FFFFFF", "bg_opa": "COVER", "radius": 1000},
    "spinbox": {"bg_color": "#FFFFFF", "bg_opa": "COVER", "border_width": 2, "border_color": "#E0E0E0",
                "radius": 8, "pad_all": 8},
}

DEFAULT_SIZES: dict[str, tuple[Any, Any]] = {
    "obj": (100, 100), "label": ("SIZE_CONTENT", "SIZE_CONTENT"),
    "button": ("SIZE_CONTENT", "SIZE_CONTENT"), "image": ("SIZE_CONTENT", "SIZE_CONTENT"),
    "slider": (150, 10), "bar": (150, 10), "switch": (50, 26), "arc": (120, 120),
    "spinner": (80, 80), "checkbox": ("SIZE_CONTENT", "SIZE_CONTENT"), "led": (30, 30),
    "dropdown": (150, "SIZE_CONTENT"), "roller": (100, 120), "textarea": (200, 80),
    "tabview": ("100%", "100%"), "tileview": ("100%", "100%"), "keyboard": ("100%", "50%"),
    "buttonmatrix": ("100%", "50%"), "meter": (150, 150), "spinbox": (100, 40),
    "qrcode": ("SIZE_CONTENT", "SIZE_CONTENT"), "canvas": (100, 100), "line": ("SIZE_CONTENT", "SIZE_CONTENT"),
    "animimg": ("SIZE_CONTENT", "SIZE_CONTENT"),
}

ALIGN_FACTORS = {
    "TOP_LEFT": (0, 0), "TOP_MID": (0.5, 0), "TOP_RIGHT": (1, 0),
    "LEFT_MID": (0, 0.5), "CENTER": (0.5, 0.5), "RIGHT_MID": (1, 0.5),
    "BOTTOM_LEFT": (0, 1), "BOTTOM_MID": (0.5, 1), "BOTTOM_RIGHT": (1, 1),
}

MeasureText = Callable[[str, str, "float | None"], tuple[float, float]]


@dataclass
class Rect:
    x: float
    y: float
    w: float
    h: float

    @property
    def right(self) -> float:
        return self.x + self.w

    @property
    def bottom(self) -> float:
        return self.y + self.h


@dataclass
class Box:
    rect: Rect                 # coordenadas absolutas en la pantalla
    content: Rect              # área de contenido (sin padding ni borde)
    parent: str | None
    rel_x: float = 0           # desplazamiento x/y resuelto en px
    rel_y: float = 0
    managed: bool = False      # posición fijada por flex/grid
    shown: bool = True         # False: pestaña inactiva o dentro de ella
    hidden: bool = False       # flag `hidden`
    movable: bool = True
    resizable: bool = True
    props: dict[str, Any] = field(default_factory=dict)   # estilo efectivo
    extra: dict[str, Any] = field(default_factory=dict)   # barra de pestañas, etc.


@dataclass
class LayoutContext:
    project: Project
    measure_text: MeasureText | None = None
    image_size: Callable[[str], "tuple[int, int] | None"] | None = None
    active_tabs: dict[str, int] = field(default_factory=dict)


# --------------------------------------------------------------------------- utilidades
def font_size(project: Project, name: Any) -> int:
    s = str(name or "")
    m = re.match(r"^montserrat_(\d+)$", s)
    if m:
        return int(m.group(1))
    f = project.font(s)
    return f.size if f else 14


def line_points(value: Any) -> list[tuple[float, float]]:
    """Puntos de una línea ESPHome: ["x,y", …] o [{x: , y: }, …]."""
    out: list[tuple[float, float]] = []
    if not isinstance(value, list):
        return out
    for p in value:
        try:
            if isinstance(p, str) and "," in p:
                x, y = p.split(",", 1)
                out.append((float(x), float(y)))
            elif isinstance(p, dict) and "x" in p and "y" in p:
                out.append((float(p["x"]), float(p["y"])))
        except (TypeError, ValueError):
            continue
    return out


def approx_measure(project: Project) -> MeasureText:
    def measure(text: str, font: str, max_width: float | None = None) -> tuple[float, float]:
        size = font_size(project, font)
        lines = text.split("\n") or [""]
        char_w = size * 0.56
        width = max(len(line) for line in lines) * char_w
        n = 0
        for line in lines:
            lw = len(line) * char_w
            n += max(1, math.ceil(lw / max_width)) if max_width and max_width > 0 else 1
        if max_width and max_width > 0:
            width = min(width, max_width)
        return (math.ceil(width), math.ceil(n * size * 1.2))
    return measure


def named_colors(project: Project) -> dict[str, str]:
    out: dict[str, str] = {}
    entries = project.extra_sections.get("color")
    if not isinstance(entries, list):
        return out
    for e in entries:
        if not isinstance(e, dict) or "id" not in e:
            continue
        try:
            if "hex" in e:
                out[str(e["id"])] = normalize_color(str(e["hex"]))
                continue
            comps = []
            for c in ("red", "green", "blue"):
                if f"{c}_int" in e:
                    comps.append(int(e[f"{c}_int"]))
                else:
                    v = e.get(c, 0)
                    if isinstance(v, str) and v.endswith("%"):
                        v = float(v[:-1]) / 100
                    comps.append(int(round(float(v) * 255)))
            out[str(e["id"])] = "#{:02X}{:02X}{:02X}".format(*comps)
        except (TypeError, ValueError):
            continue
    return out


def resolve_color(value: Any, colors: dict[str, str], default: str = "#000000") -> str:
    if value is None or is_tagged(value):
        return default
    if isinstance(value, int) and not isinstance(value, bool):
        return f"#{value & 0xFFFFFF:06X}"
    s = str(value).strip()
    if s in colors:
        return colors[s]
    try:
        return normalize_color(s)
    except ValueError:
        return default


def _plain(d: dict | None) -> dict:
    """Propiedades de estilo simples (sin estados ni partes anidadas)."""
    if not isinstance(d, dict):
        return {}
    return {k: v for k, v in d.items() if not (isinstance(v, dict) and not is_tagged(v))
            or k in ("text", "layout", "align_to")}


def style_ids(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return [str(v) for v in value if isinstance(v, str)]
    return []


def effective_props(project: Project, widget: Widget, parent_eff: dict | None = None) -> dict:
    eff: dict[str, Any] = {}
    parent_eff = parent_eff or page_props(project, None)
    for k in INHERITED:
        if k in parent_eff:
            eff[k] = parent_eff[k]
    eff.update(BUILTIN_STYLES.get(widget.type, {}))
    theme = project.lvgl_extra.get("theme")
    if isinstance(theme, dict):
        eff.update(_plain(theme.get(widget.type)))
    for sid in style_ids(widget.props.get("styles")):
        st = project.style(sid)
        if st:
            eff.update(_plain(st.props))
    eff.update({k: v for k, v in widget.props.items() if k != "styles"})
    return eff


def page_props(project: Project, screen: Screen | None) -> dict:
    eff = dict(BUILTIN_STYLES["page"])
    extra = project.lvgl_extra
    eff.update({k: v for k, v in _plain(extra).items()
                if k not in ("pages", "top_layer", "theme", "style_definitions", "displays",
                             "touchscreens", "encoders", "keypads", "byte_order", "buffer_size",
                             "log_level", "color_depth", "default_font", "page_wrap", "full_refresh",
                             "on_idle", "on_pause", "on_resume", "on_draw_start", "on_draw_end")
                and not k.startswith("on_")})
    if "default_font" in extra and isinstance(extra["default_font"], str):
        eff["text_font"] = extra["default_font"]
    if isinstance(extra.get("theme"), dict):
        eff.update(_plain(extra["theme"].get("page")))
    for sid in style_ids(screen.props.get("styles") if screen else None):
        st = project.style(sid)
        if st:
            eff.update(_plain(st.props))
    if screen is not None:
        eff.update({k: v for k, v in screen.props.items() if k != "styles"})
        if screen.bg_color:
            eff["bg_color"] = screen.bg_color
    return eff


def _num(v: Any, default: float = 0.0) -> float:
    if isinstance(v, bool):
        return default
    if isinstance(v, (int, float)):
        return float(v)
    try:
        return float(str(v).strip().rstrip("px"))
    except ValueError:
        return default


def pads(eff: dict) -> tuple[float, float, float, float]:
    """(izquierda, arriba, derecha, abajo) incluyendo el grosor del borde."""
    base = _num(eff.get("pad_all", 0))
    border = _num(eff.get("border_width", 0))
    left = _num(eff.get("pad_left", base), base) + border
    top = _num(eff.get("pad_top", base), base) + border
    right = _num(eff.get("pad_right", base), base) + border
    bottom = _num(eff.get("pad_bottom", base), base) + border
    return left, top, right, bottom


def _upper(v: Any, default: str = "") -> str:
    return str(v).strip().upper() if v is not None and not is_tagged(v) else default


def _percent(v: Any) -> float | None:
    if isinstance(v, str) and v.strip().endswith("%"):
        try:
            return float(v.strip()[:-1]) / 100.0
        except ValueError:
            return None
    return None


def is_size_content(v: Any) -> bool:
    return isinstance(v, str) and v.strip().upper() == "SIZE_CONTENT"


# --------------------------------------------------------------------------- motor
class LayoutEngine:
    def __init__(self, ctx: LayoutContext):
        self.ctx = ctx
        self.project = ctx.project
        self.measure = ctx.measure_text or approx_measure(ctx.project)
        self.boxes: dict[str, Box] = {}

    # ----------------------------------------------------------------- tamaños
    def _content_size(self, w: Widget, eff: dict, avail: Rect, fixed_w: float | None) -> tuple[float, float]:
        pl, pt, pr, pb = pads(eff)
        font = eff.get("text_font", catalog.DEFAULT_FONT)
        if w.type == "label":
            from olvgl.domain.values import display_text
            text = display_text(w.props.get("text", eff.get("text", "")))
            if eff.get("recolor") is True:
                from olvgl.domain.values import strip_recolor
                text = strip_recolor(text)
            maxw = None
            if fixed_w is not None and _upper(eff.get("long_mode"), "WRAP") == "WRAP":
                maxw = max(1.0, fixed_w - pl - pr)
            tw, th = self.measure(text or " ", font, maxw)
            return tw + pl + pr, th + pt + pb
        if w.type == "animimg":
            srcs = w.props.get("src")
            first = srcs[0] if isinstance(srcs, list) and srcs else None
            size = self.ctx.image_size(first) if (self.ctx.image_size and isinstance(first, str)) else None
            return size or (64, 64)
        if w.type == "image":
            src = w.props.get("src")
            size = None
            img = self.project.image(src) if isinstance(src, str) else None
            resize = img.extra.get("resize") if img else None
            m = re.match(r"^\s*(\d+)\s*[xX]\s*(\d+)\s*$", str(resize)) if resize else None
            if m:  # ESPHome redimensiona la imagen a este tamaño
                size = (int(m.group(1)), int(m.group(2)))
            elif self.ctx.image_size and isinstance(src, str):
                size = self.ctx.image_size(src)
            return size or (64, 64)
        if w.type == "checkbox":
            from olvgl.domain.values import display_text
            text = display_text(w.props.get("text", ""))
            tw, th = self.measure(text, font, None) if text else (0, 0)
            box = font_size(self.project, font) + 6
            return box + (8 + tw if text else 0) + pl + pr, max(box, th) + pt + pb
        if w.type == "line":
            pts = line_points(w.props.get("points"))
            lw = _num(eff.get("line_width"), 1)
            if not pts:
                return (lw, lw)
            return (max(x for x, _ in pts) + lw, max(y for _, y in pts) + lw)
        if w.type == "qrcode":
            size = _num(w.props.get("size"), 100)
            return (size, size)
        if w.type == "dropdown":
            th = font_size(self.project, font) * 1.2
            return 150, th + pt + pb
        if w.type == "button" and "text" in w.props and not w.children:
            from olvgl.domain.values import display_text
            tw, th = self.measure(display_text(w.props.get("text")) or " ", font, None)
            return tw + pl + pr, th + pt + pb
        # contenedor: extensión de los hijos
        inner = Rect(0, 0, (fixed_w - pl - pr) if fixed_w is not None else avail.w, avail.h)
        probe = LayoutEngine(self.ctx)
        probe._layout_children(w.children, None, inner, eff, w.props, record=True)
        if not probe.boxes:
            return pl + pr, pt + pb
        right = max(b.rect.right for b in probe.boxes.values() if b.parent is None)
        bottom = max(b.rect.bottom for b in probe.boxes.values() if b.parent is None)
        return right + pl + pr, bottom + pt + pb

    def _size(self, w: Widget, eff: dict, avail: Rect) -> tuple[float, float]:
        dw, dh = DEFAULT_SIZES.get(w.type, (100, 100))
        wv = w.width if w.width is not None else dw
        hv = w.height if w.height is not None else dh

        def resolve(v: Any, total: float) -> float | None:
            if isinstance(v, (int, float)) and not isinstance(v, bool):
                return float(v)
            p = _percent(v)
            if p is not None:
                return total * p
            if is_size_content(v):
                return None
            return _num(v, 100.0)

        width = resolve(wv, avail.w)
        height = resolve(hv, avail.h)
        if width is None or height is None:
            cw, ch = self._content_size(w, eff, avail, width)
            width = cw if width is None else width
            height = ch if height is None else height
        for key, val in (("min_width", None), ("max_width", None)):
            if key in eff:
                lim = resolve(eff[key], avail.w)
                if lim is not None:
                    width = max(width, lim) if key == "min_width" else min(width, lim)
        for key in ("min_height", "max_height"):
            if key in eff:
                lim = resolve(eff[key], avail.h)
                if lim is not None:
                    height = max(height, lim) if key == "min_height" else min(height, lim)
        return max(0.0, width), max(0.0, height)

    # ----------------------------------------------------------------- disposición
    def _layout_kind(self, props: dict, eff: dict) -> tuple[str, dict] | None:
        lay = props.get("layout")
        if lay is None:
            return None
        if isinstance(lay, str):
            m = re.match(r"^\s*(\d+)\s*[xX]\s*(\d+)\s*$", lay)
            if m:
                rows, cols = int(m.group(1)), int(m.group(2))
                return "grid", {"grid_rows": ["FR(1)"] * rows, "grid_columns": ["FR(1)"] * cols,
                                "_auto": True}
            if lay.strip().lower() == "flex":
                return "flex", {}
            if lay.strip().lower() == "grid":
                return "grid", {}
            return None
        if isinstance(lay, dict):
            t = str(lay.get("type", "")).lower()
            if t in ("flex", "grid"):
                return t, lay
        return None

    def _gap(self, cfg: dict, eff: dict, key: str) -> float:
        if key in cfg:
            return _num(cfg[key])
        return _num(eff.get(key, 0))

    def _flex(self, items: list[tuple[Widget, dict, float, float]], content: Rect, cfg: dict,
              eff: dict) -> list[tuple[float, float, float, float]]:
        flow = _upper(cfg.get("flex_flow", eff.get("flex_flow")), "ROW")
        row = flow.startswith("ROW")
        wrap = "WRAP" in flow
        reverse = "REVERSE" in flow
        main_align = _upper(cfg.get("flex_align_main"), "START")
        cross_align = _upper(cfg.get("flex_align_cross"), "START")
        track_align = _upper(cfg.get("flex_align_track"), "START")
        gap_main = self._gap(cfg, eff, "pad_column" if row else "pad_row")
        gap_cross = self._gap(cfg, eff, "pad_row" if row else "pad_column")
        main_total = content.w if row else content.h
        cross_total = content.h if row else content.w

        sizes = [(iw, ih) if row else (ih, iw) for _, _, iw, ih in items]  # (main, cross)
        order = list(range(len(items)))
        if reverse:
            order.reverse()
        tracks: list[list[int]] = [[]]
        used = 0.0
        for i in order:
            m = sizes[i][0]
            if wrap and tracks[-1] and used + gap_main + m > main_total + 0.5:
                tracks.append([])
                used = 0.0
            used += (gap_main if tracks[-1] else 0) + m
            tracks[-1].append(i)

        result: dict[int, tuple[float, float, float, float]] = {}
        track_sizes = [max((sizes[i][1] for i in t), default=0) for t in tracks]
        total_cross = sum(track_sizes) + gap_cross * max(0, len(tracks) - 1)
        free_cross = cross_total - total_cross
        cross_pos = {"CENTER": free_cross / 2, "END": free_cross}.get(track_align, 0.0)
        for t, tsize in zip(tracks, track_sizes):
            mains = [sizes[i][0] for i in t]
            grows = [_num(items[i][1].get("flex_grow", 0)) for i in t]
            total_main = sum(mains) + gap_main * max(0, len(t) - 1)
            free = main_total - total_main
            if free > 0 and sum(grows) > 0:
                share = free / sum(grows)
                mains = [m + g * share for m, g in zip(mains, grows)]
                free = 0
            n = len(t)
            start, gap = 0.0, gap_main
            if main_align == "END":
                start = free
            elif main_align == "CENTER":
                start = free / 2
            elif main_align == "SPACE_BETWEEN" and n > 1:
                gap = gap_main + free / (n - 1)
            elif main_align == "SPACE_AROUND" and n > 0:
                gap = gap_main + free / n
                start = free / n / 2
            elif main_align == "SPACE_EVENLY" and n > 0:
                gap = gap_main + free / (n + 1)
                start = free / (n + 1)
            pos = start
            for idx, i in enumerate(t):
                m = mains[idx]
                c = sizes[i][1]
                off = {"CENTER": (tsize - c) / 2, "END": tsize - c}.get(cross_align, 0.0)
                if row:
                    result[i] = (content.x + pos, content.y + cross_pos + off, m, c)
                else:
                    result[i] = (content.x + cross_pos + off, content.y + pos, c, m)
                pos += m + gap
            cross_pos += tsize + gap_cross
        return [result[i] for i in range(len(items))]

    def _tracks(self, spec: Any, total: float, gap: float, content_sizes: dict[int, float]) -> list[tuple[float, float]]:
        values = spec if isinstance(spec, list) else []
        if not values:
            values = ["FR(1)"]
        fixed, frs = [], []
        for i, v in enumerate(values):
            s = str(v).strip().upper()
            m = re.match(r"^FR\((\d+(?:\.\d+)?)\)$", s)
            if m:
                fixed.append(None)
                frs.append(float(m.group(1)))
            elif s == "CONTENT":
                fixed.append(content_sizes.get(i, 0.0))
                frs.append(0.0)
            elif _percent(v) is not None:
                fixed.append(total * _percent(v))
                frs.append(0.0)
            else:
                fixed.append(_num(v))
                frs.append(0.0)
        free = total - sum(f for f in fixed if f is not None) - gap * max(0, len(values) - 1)
        fr_total = sum(frs) or 1.0
        out, pos = [], 0.0
        for f, fr in zip(fixed, frs):
            size = f if f is not None else max(0.0, free) * fr / fr_total
            out.append((pos, size))
            pos += size + gap
        return out

    def _grid(self, items: list[tuple[Widget, dict, float, float]], content: Rect, cfg: dict,
              eff: dict) -> list[tuple[float, float, float, float]]:
        cols_spec = cfg.get("grid_columns") or ["FR(1)"]
        rows_spec = cfg.get("grid_rows") or ["FR(1)"]
        ncols = len(cols_spec) if isinstance(cols_spec, list) else 1
        cells = []
        auto = 0
        for w, ieff, iw, ih in items:
            if "grid_cell_column_pos" in ieff or "grid_cell_row_pos" in ieff:
                c = int(_num(ieff.get("grid_cell_column_pos", 0)))
                r = int(_num(ieff.get("grid_cell_row_pos", 0)))
            else:
                c, r = auto % max(1, ncols), auto // max(1, ncols)
                auto += 1
            cs = max(1, int(_num(ieff.get("grid_cell_column_span", 1), 1)))
            rs = max(1, int(_num(ieff.get("grid_cell_row_span", 1), 1)))
            cells.append((c, r, cs, rs))
        col_content: dict[int, float] = {}
        row_content: dict[int, float] = {}
        for (c, r, cs, rs), (_, _, iw, ih) in zip(cells, items):
            if cs == 1:
                col_content[c] = max(col_content.get(c, 0.0), iw)
            if rs == 1:
                row_content[r] = max(row_content.get(r, 0.0), ih)
        gap_c = self._gap(cfg, eff, "pad_column")
        gap_r = self._gap(cfg, eff, "pad_row")
        cols = self._tracks(cols_spec, content.w, gap_c, col_content)
        rows = self._tracks(rows_spec, content.h, gap_r, row_content)
        out = []
        for (c, r, cs, rs), (_, ieff, iw, ih) in zip(cells, items):
            c = min(c, len(cols) - 1)
            r = min(r, len(rows) - 1)
            ce = min(c + cs, len(cols)) - 1
            re_ = min(r + rs, len(rows)) - 1
            cx = cols[c][0]
            cw = cols[ce][0] + cols[ce][1] - cx
            cy = rows[r][0]
            ch = rows[re_][0] + rows[re_][1] - cy
            xa = _upper(ieff.get("grid_cell_x_align"), "START")
            ya = _upper(ieff.get("grid_cell_y_align"), "START")
            w_, h_ = iw, ih
            if xa == "STRETCH":
                x, w_ = cx, cw
            else:
                x = cx + {"CENTER": (cw - iw) / 2, "END": cw - iw}.get(xa, 0.0)
            if ya == "STRETCH":
                y, h_ = cy, ch
            else:
                y = cy + {"CENTER": (ch - ih) / 2, "END": ch - ih}.get(ya, 0.0)
            out.append((content.x + x, content.y + y, w_, h_))
        return out

    def _aligned(self, w: Widget, eff: dict, content: Rect, iw: float, ih: float) -> tuple[float, float, float, float]:
        def off(v: Any, total: float) -> float:
            p = _percent(v)
            if p is not None:
                return total * p
            if isinstance(v, (int, float)) and not isinstance(v, bool):
                return float(v)
            return _num(v, 0.0) if v is not None and not is_tagged(v) else 0.0

        rx, ry = off(w.x, content.w), off(w.y, content.h)
        align_to = eff.get("align_to")
        if isinstance(align_to, dict) and str(align_to.get("id")) in self.boxes:
            target = self.boxes[str(align_to["id"])].rect
            a = _upper(align_to.get("align"), "OUT_BOTTOM_MID")
            bx, by = _align_to(a, target, iw, ih)
            rx = off(align_to.get("x", 0), content.w)
            ry = off(align_to.get("y", 0), content.h)
            return bx + rx, by + ry, rx, ry
        fx, fy = ALIGN_FACTORS.get(_upper(eff.get("align"), "TOP_LEFT"), (0, 0))
        bx = content.x + (content.w - iw) * fx
        by = content.y + (content.h - ih) * fy
        return bx + rx, by + ry, rx, ry

    def _layout_children(self, children: list[Widget], parent_id: str | None, content: Rect,
                         parent_eff: dict, parent_props: dict, shown: bool = True,
                         record: bool = True) -> None:
        kind = self._layout_kind(parent_props, parent_eff)
        prepared = []
        for w in children:
            eff = effective_props(self.project, w, parent_eff)
            iw, ih = self._size(w, eff, content)
            prepared.append((w, eff, iw, ih))
        managed_idx = []
        if kind:
            managed_idx = [i for i, (w, eff, _, _) in enumerate(prepared)
                           if not eff.get("hidden") and not eff.get("floating") and not eff.get("ignore_layout")]
        placed: dict[int, tuple[float, float, float, float]] = {}
        if managed_idx:
            items = [prepared[i] for i in managed_idx]
            rects = (self._flex if kind[0] == "flex" else self._grid)(items, content, kind[1], parent_eff)
            placed = dict(zip(managed_idx, rects))
        for i, (w, eff, iw, ih) in enumerate(prepared):
            if i in placed:
                x, y, iw, ih = placed[i]
                rx, ry = 0.0, 0.0
                managed = True
            else:
                x, y, rx, ry = self._aligned(w, eff, content, iw, ih)
                managed = False
            self._place(w, eff, Rect(x, y, iw, ih), parent_id, rx, ry, managed, shown)

    def _place(self, w: Widget, eff: dict, rect: Rect, parent_id: str | None, rx: float, ry: float,
               managed: bool, shown: bool) -> None:
        pl, pt, pr, pb = pads(eff)
        content = Rect(rect.x + pl, rect.y + pt, max(0.0, rect.w - pl - pr), max(0.0, rect.h - pt - pb))
        pseudo = w.type in catalog.PSEUDO_TYPES
        sp = catalog.spec(w.type)
        box = Box(rect=rect, content=content, parent=parent_id, rel_x=rx, rel_y=ry, managed=managed,
                  shown=shown, hidden=bool(eff.get("hidden")) if not is_tagged(eff.get("hidden")) else False,
                  movable=not managed and not pseudo
                  and not is_tagged(w.x) and not is_tagged(w.y) and "align_to" not in w.props,
                  resizable=not pseudo and sp.resizable and w.type != "image",
                  props=eff)
        self.boxes[w.id] = box
        if w.type in catalog.CHILD_LISTS:
            self._layout_tabs(w, eff, box, shown)
            return
        self._layout_children(w.children, w.id, content, eff, w.props, shown and not box.hidden)

    def _layout_tabs(self, w: Widget, eff: dict, box: Box, shown: bool) -> None:
        active = self.ctx.active_tabs.get(w.id, 0)
        if w.children:
            active = max(0, min(active, len(w.children) - 1))
        r = box.rect
        if w.type == "tabview":
            position = _upper(eff.get("position"), "TOP")
            size_v = eff.get("size", 50)
            vertical = position in ("LEFT", "RIGHT")
            total = r.w if vertical else r.h
            bar = total * _percent(size_v) if _percent(size_v) is not None else _num(size_v, 50)
            if position == "TOP":
                bar_r, cont = Rect(r.x, r.y, r.w, bar), Rect(r.x, r.y + bar, r.w, r.h - bar)
            elif position == "BOTTOM":
                bar_r, cont = Rect(r.x, r.bottom - bar, r.w, bar), Rect(r.x, r.y, r.w, r.h - bar)
            elif position == "LEFT":
                bar_r, cont = Rect(r.x, r.y, bar, r.h), Rect(r.x + bar, r.y, r.w - bar, r.h)
            else:
                bar_r, cont = Rect(r.right - bar, r.y, bar, r.h), Rect(r.x, r.y, r.w - bar, r.h)
            n = max(1, len(w.children))
            buttons = []
            for i, tab in enumerate(w.children):
                if vertical:
                    br = Rect(bar_r.x, bar_r.y + bar_r.h * i / n, bar_r.w, bar_r.h / n)
                else:
                    br = Rect(bar_r.x + bar_r.w * i / n, bar_r.y, bar_r.w / n, bar_r.h)
                buttons.append((br, str(tab.props.get("name", tab.id)), tab.id))
            box.extra.update({"tab_bar": bar_r, "tab_buttons": buttons, "active": active})
        else:
            cont = r
            box.extra.update({"active": active})
        for i, tab in enumerate(w.children):
            teff = effective_props(self.project, tab, eff)
            self._place(tab, teff, Rect(cont.x, cont.y, cont.w, cont.h), w.id, 0, 0, True,
                        shown and i == active)

    # ----------------------------------------------------------------- entrada
    def run(self, screen: Screen) -> dict[str, Box]:
        d = self.project.display
        eff = page_props(self.project, screen)
        pl, pt, pr, pb = pads(eff)
        content = Rect(pl, pt, d.width - pl - pr, d.height - pt - pb)
        self._layout_children(screen.widgets, None, content, eff, screen.props)
        return self.boxes


def _align_to(a: str, t: Rect, w: float, h: float) -> tuple[float, float]:
    table = {
        "OUT_TOP_LEFT": (t.x, t.y - h), "OUT_TOP_MID": (t.x + (t.w - w) / 2, t.y - h),
        "OUT_TOP_RIGHT": (t.right - w, t.y - h),
        "OUT_BOTTOM_LEFT": (t.x, t.bottom), "OUT_BOTTOM_MID": (t.x + (t.w - w) / 2, t.bottom),
        "OUT_BOTTOM_RIGHT": (t.right - w, t.bottom),
        "OUT_LEFT_TOP": (t.x - w, t.y), "OUT_LEFT_MID": (t.x - w, t.y + (t.h - h) / 2),
        "OUT_LEFT_BOTTOM": (t.x - w, t.bottom - h),
        "OUT_RIGHT_TOP": (t.right, t.y), "OUT_RIGHT_MID": (t.right, t.y + (t.h - h) / 2),
        "OUT_RIGHT_BOTTOM": (t.right, t.bottom - h),
    }
    if a in table:
        return table[a]
    fx, fy = ALIGN_FACTORS.get(a, (0, 0))
    return t.x + (t.w - w) * fx, t.y + (t.h - h) * fy


def compute_layout(project: Project, screen: Screen, ctx: LayoutContext | None = None) -> dict[str, Box]:
    ctx = ctx or LayoutContext(project)
    if ctx.project is not project:
        ctx = LayoutContext(project, ctx.measure_text, ctx.image_size, ctx.active_tabs)
    return LayoutEngine(ctx).run(screen)
