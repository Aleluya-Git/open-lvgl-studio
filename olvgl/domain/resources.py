"""Estimación de recursos de un proyecto en el dispositivo (perfilado).

Son **estimaciones** para un ESP32 (32 bits) con LVGL 9, pensadas para comparar
diseños y detectar problemas pronto (páginas con demasiados objetos, búferes
que no caben sin PSRAM, imágenes enormes…), no para sustituir a la medida
real con `lv_mem_monitor`. Las cifras se explican en docs/09_simulador.md.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Callable

from olvgl.domain import catalog
from olvgl.domain.model import Project, Widget

# bytes por objeto de LVGL (lv_obj_t + atributos especiales + clase), 32 bits
OBJ_BASE = 96
STYLE_PROP = 12        # cada propiedad de estilo local
STYLE_REF = 8          # cada estilo compartido aplicado
EVENT_DSC = 24         # cada manejador de evento
TYPE_EXTRA = {
    "label": 48, "button": 0, "image": 40, "obj": 0, "switch": 24, "checkbox": 48, "slider": 96,
    "arc": 64, "dropdown": 96, "roller": 96, "spinbox": 176, "textarea": 192, "keyboard": 1536,
    "buttonmatrix": 48, "bar": 80, "led": 16, "spinner": 96, "line": 24, "qrcode": 64, "meter": 256,
    "tabview": 96, "tab": 0, "tileview": 64, "tile": 0, "canvas": 64, "animimg": 64,
}
DEFAULT_GLYPHS = 95                    # ASCII imprimible, lo que ESPHome incluye por defecto
BUILTIN_GLYPHS = 96 + 60               # montserrat_N de LVGL: ASCII + símbolos
IMAGE_BPP = {"RGB565": 2.0, "RGB": 3.0, "RGB24": 3.0, "RGBA": 4.0, "GRAYSCALE": 1.0, "BINARY": 0.125,
             "ARGB8888": 4.0, "XRGB8888": 4.0}
PAGE_OBJECTS_WARN = 250
INTERNAL_RAM_BUDGET = 256 * 1024       # RAM interna disponible típica para LVGL sin PSRAM


@dataclass
class PageStats:
    id: str
    name: str
    objects: int = 0
    depth: int = 0
    events: int = 0
    heap: int = 0


@dataclass
class ResourceReport:
    display: tuple[int, int] = (0, 0)
    pages: list[PageStats] = field(default_factory=list)
    top_layer: PageStats | None = None
    heap_bytes: int = 0              # objetos de todas las páginas (ESPHome las crea todas al arrancar)
    draw_buffer_bytes: int = 0
    buffer_fraction: float = 1.0
    color_depth: int = 16
    images: list[tuple[str, int, int, int]] = field(default_factory=list)    # id, ancho, alto, bytes
    fonts: list[tuple[str, int, int, int, int]] = field(default_factory=list)  # id, tamaño, glifos, bpp, bytes
    warnings: list[str] = field(default_factory=list)

    @property
    def objects(self) -> int:
        return sum(p.objects for p in self.pages) + (self.top_layer.objects if self.top_layer else 0)

    @property
    def flash_bytes(self) -> int:
        return sum(i[3] for i in self.images) + sum(f[4] for f in self.fonts)

    @property
    def ram_bytes(self) -> int:
        return self.heap_bytes + self.draw_buffer_bytes

    def as_dict(self) -> dict:
        return {
            "display": list(self.display), "objects": self.objects, "heap_bytes": self.heap_bytes,
            "draw_buffer_bytes": self.draw_buffer_bytes, "ram_bytes": self.ram_bytes,
            "flash_bytes": self.flash_bytes,
            "pages": [vars(p) for p in self.pages],
            "top_layer": vars(self.top_layer) if self.top_layer else None,
            "images": [dict(zip(("id", "width", "height", "bytes"), i)) for i in self.images],
            "fonts": [dict(zip(("id", "size", "glyphs", "bpp", "bytes"), f)) for f in self.fonts],
            "warnings": self.warnings,
        }


def human(n: float) -> str:
    for unit in ("B", "KB", "MB"):
        if n < 1024 or unit == "MB":
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} MB"


def _text_len(v: Any) -> int:
    if isinstance(v, str):
        return len(v.encode("utf-8")) + 1
    if isinstance(v, list):
        return sum(_text_len(x) for x in v)
    return 16   # lambda / format: un búfer pequeño


def widget_heap(w: Widget) -> int:
    p = w.props
    n = OBJ_BASE + TYPE_EXTRA.get(w.type, 0)
    n += EVENT_DSC * len(w.events)
    styles = p.get("styles")
    n += STYLE_REF * (len(styles) if isinstance(styles, list) else 1 if styles else 0)

    def count_style(d: dict) -> int:
        c = 0
        for k, v in d.items():
            if isinstance(v, dict) and "__tag__" not in v:
                c += count_style(v)          # estados y partes
            elif k not in ("text", "options", "rows", "points", "widgets", "id", "styles"):
                c += 1
        return c
    n += STYLE_PROP * count_style(p)
    if w.type in ("label", "checkbox", "textarea"):
        n += _text_len(p.get("text", ""))
    if w.type in ("dropdown", "roller"):
        n += _text_len(p.get("options", []))
    if w.type == "buttonmatrix":
        rows = p.get("rows") if isinstance(p.get("rows"), list) else []
        buttons = sum(len(r.get("buttons", [])) for r in rows if isinstance(r, dict))
        n += 16 * buttons + 8 * len(rows)
    if w.type == "line":
        pts = p.get("points")
        n += 8 * (len(pts) if isinstance(pts, list) else 0)
    if w.type == "qrcode":
        size = int(p.get("size", 100) or 100)
        n += size * size // 8
    if w.type == "canvas":
        try:
            n += int(w.width or 0) * int(w.height or 0) * 2
        except (TypeError, ValueError):
            pass
    return n


def _walk_stats(widgets: list[Widget], depth: int, stats: PageStats) -> None:
    for w in widgets:
        stats.objects += 1
        stats.depth = max(stats.depth, depth)
        stats.events += len(w.events)
        stats.heap += widget_heap(w)
        if w.type == "tabview":
            stats.objects += 2 + len(w.children)       # barra de botones y contenedor
        _walk_stats(w.children, depth + 1, stats)


def _percent(v: Any, default: float) -> float:
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        return max(0.01, min(1.0, float(v) / 100.0 if v > 1 else float(v)))
    m = re.match(r"^\s*([\d.]+)\s*%\s*$", str(v or ""))
    return max(0.01, min(1.0, float(m.group(1)) / 100.0)) if m else default


def _glyph_count(data: dict) -> int:
    g = data.get("glyphs")
    if isinstance(g, str):
        return len(set(g)) or DEFAULT_GLYPHS
    if isinstance(g, list):
        return len({c for s in g if isinstance(s, str) for c in s}) or DEFAULT_GLYPHS
    return DEFAULT_GLYPHS


def font_bytes(size: int, glyphs: int, bpp: int) -> int:
    # mapa de bits medio de un glifo ≈ 55 % del cuadrado del tamaño, más su descriptor
    return int(glyphs * (size * size * 0.55 * bpp / 8 + 16))


def estimate_resources(project: Project,
                       image_size: Callable[[str], "tuple[int, int] | None"] | None = None) -> ResourceReport:
    from olvgl.domain.extensions import expand_project
    project = expand_project(project)     # lo que de verdad llega al dispositivo
    d = project.display
    rep = ResourceReport(display=(d.width, d.height))
    for s in project.screens:
        st = PageStats(s.id, s.name)
        st.objects = 1
        st.heap = OBJ_BASE
        _walk_stats(s.widgets, 1, st)
        rep.pages.append(st)
    if project.top_layer is not None:
        st = PageStats(project.top_layer.id, project.top_layer.name or "top_layer")
        _walk_stats(project.top_layer.widgets, 1, st)
        rep.top_layer = st
    rep.heap_bytes = sum(p.heap for p in rep.pages) + (rep.top_layer.heap if rep.top_layer else 0)

    extra = project.lvgl_extra
    rep.color_depth = int(extra.get("color_depth", 16) or 16)
    rep.buffer_fraction = _percent(extra.get("buffer_size"), 1.0)
    rep.draw_buffer_bytes = int(d.width * d.height * rep.color_depth / 8 * rep.buffer_fraction)

    # imágenes
    for img in project.images:
        size = None
        resize = img.extra.get("resize") if isinstance(img.extra, dict) else None
        if isinstance(resize, str) and "x" in resize.lower():
            try:
                size = tuple(int(v) for v in resize.lower().split("x"))
            except ValueError:
                size = None
        if size is None and image_size is not None:
            size = image_size(img.id)
        if not size:
            continue
        bpp = IMAGE_BPP.get(str(img.type or "RGB565").upper(), 2.0)
        if str(img.transparency or "").lower() == "alpha_channel" and bpp < 4:
            bpp += 1
        w, h = int(size[0]), int(size[1])
        rep.images.append((img.id, w, h, int(w * h * bpp)))
        if w * h > d.width * d.height:
            rep.warnings.append(f"La imagen «{img.id}» ({w}×{h}) es mayor que la pantalla: usa resize")

    # fuentes del proyecto y Montserrat integradas que se usan
    for f in project.fonts:
        bpp = int(f.data.get("bpp", 1) or 1)     # ESPHome: bpp 1 por defecto
        glyphs = _glyph_count(f.data)
        rep.fonts.append((f.id, f.size, glyphs, bpp, font_bytes(f.size, glyphs, bpp)))
    used = set()
    for _s, w in project.iter_widgets():
        tf = w.props.get("text_font")
        if isinstance(tf, str) and tf.startswith("montserrat_"):
            used.add(tf)
    dflt = extra.get("default_font")
    if isinstance(dflt, str) and dflt.startswith("montserrat_"):
        used.add(dflt)
    used.add(catalog.DEFAULT_FONT)
    for name in sorted(used, key=lambda n: int(n.split("_")[1]) if n.split("_")[1].isdigit() else 0):
        try:
            size = int(name.split("_")[1])
        except (IndexError, ValueError):
            continue
        rep.fonts.append((name, size, BUILTIN_GLYPHS, 4, font_bytes(size, BUILTIN_GLYPHS, 4)))

    # avisos
    for p in rep.pages:
        if p.objects > PAGE_OBJECTS_WARN:
            rep.warnings.append(f"La página «{p.id}» tiene {p.objects} objetos (más de "
                                f"{PAGE_OBJECTS_WARN}): tarda en crearse y consume RAM; divídela o reutiliza widgets")
        if p.depth > 8:
            rep.warnings.append(f"La página «{p.id}» anida {p.depth} niveles: cada nivel añade coste al redibujar")
    if rep.ram_bytes > INTERNAL_RAM_BUDGET:
        rep.warnings.append(f"RAM estimada {human(rep.ram_bytes)}: necesitas PSRAM (o reducir buffer_size, "
                            f"ahora {rep.buffer_fraction * 100:.0f} %)")
    if len(rep.fonts) > 16:
        rep.warnings.append(f"{len(rep.fonts)} fuentes/tamaños distintos: cada una ocupa flash")
    return rep
