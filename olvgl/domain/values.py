"""Valores de propiedades: registro de propiedades LVGL y conversión AST ⇄ JSON.

En el modelo los valores se guardan como JSON:
- colores como "#RRGGBB" (en el YAML son 0xRRGGBB),
- valores con etiqueta (lambdas, !secret…) como {"__tag__": "!lambda", "value": …},
- mapas y listas tal cual (estados `pressed:`, partes `indicator:`, `format/args`…).
"""
from __future__ import annotations

import re
from typing import Any

from olvgl.domain.yaml_ast import HEX, LITERAL, YMap, YNode, YRaw, YScalar, YSeq

TAG_KEY = "__tag__"

# Tipos de propiedad del registro
COLOR = "color"
OPA = "opa"
INT = "int"
FONT = "font"
ENUM = "enum"
BOOL = "bool"
TEXT = "text"
ANY = "any"

ALIGNS = ["TOP_LEFT", "TOP_MID", "TOP_RIGHT", "LEFT_MID", "CENTER", "RIGHT_MID",
          "BOTTOM_LEFT", "BOTTOM_MID", "BOTTOM_RIGHT"]
OUT_ALIGNS = ["OUT_TOP_LEFT", "OUT_TOP_MID", "OUT_TOP_RIGHT", "OUT_BOTTOM_LEFT", "OUT_BOTTOM_MID",
              "OUT_BOTTOM_RIGHT", "OUT_LEFT_TOP", "OUT_LEFT_MID", "OUT_LEFT_BOTTOM",
              "OUT_RIGHT_TOP", "OUT_RIGHT_MID", "OUT_RIGHT_BOTTOM"]

# Registro de propiedades conocidas (subconjunto útil de la doc. de ESPHome LVGL)
REGISTRY: dict[str, tuple[str, tuple[str, ...]]] = {
    "align": (ENUM, tuple(ALIGNS)),
    "bg_color": (COLOR, ()), "bg_opa": (OPA, ()), "bg_grad_color": (COLOR, ()),
    "bg_grad_dir": (ENUM, ("NONE", "HOR", "VER")), "bg_main_stop": (INT, ()), "bg_grad_stop": (INT, ()),
    "color_start": (COLOR, ()), "color_end": (COLOR, ()),
    "bg_image_src": (ANY, ()), "bg_image_recolor": (COLOR, ()),
    "border_color": (COLOR, ()), "border_opa": (OPA, ()), "border_width": (INT, ()),
    "border_side": (ANY, ()), "border_post": (BOOL, ()),
    "outline_color": (COLOR, ()), "outline_opa": (OPA, ()), "outline_width": (INT, ()),
    "outline_pad": (INT, ()),
    "shadow_color": (COLOR, ()), "shadow_opa": (OPA, ()), "shadow_width": (INT, ()),
    "shadow_ofs_x": (INT, ()), "shadow_ofs_y": (INT, ()), "shadow_spread": (INT, ()),
    "radius": (INT, ()), "clip_corner": (BOOL, ()), "opa": (OPA, ()),
    "pad_all": (INT, ()), "pad_top": (INT, ()), "pad_bottom": (INT, ()), "pad_left": (INT, ()),
    "pad_right": (INT, ()), "pad_row": (INT, ()), "pad_column": (INT, ()),
    "text_color": (COLOR, ()), "text_opa": (OPA, ()), "text_font": (FONT, ()),
    "text_align": (ENUM, ("AUTO", "LEFT", "CENTER", "RIGHT")),
    "text_letter_space": (INT, ()), "text_line_space": (INT, ()),
    "text_decor": (ENUM, ("NONE", "UNDERLINE", "STRIKETHROUGH")),
    "line_color": (COLOR, ()), "line_width": (INT, ()), "line_rounded": (BOOL, ()),
    "arc_color": (COLOR, ()), "arc_opa": (OPA, ()), "arc_width": (INT, ()), "arc_rounded": (BOOL, ()),
    "image_recolor": (COLOR, ()), "image_recolor_opa": (OPA, ()),
    "min_width": (INT, ()), "max_width": (INT, ()), "min_height": (INT, ()), "max_height": (INT, ()),
    "transform_angle": (INT, ()), "transform_zoom": (ANY, ()), "transform_rotation": (INT, ()),
    "transform_scale": (ANY, ()),
    "hidden": (BOOL, ()), "clickable": (BOOL, ()), "checkable": (BOOL, ()), "scrollable": (BOOL, ()),
    "floating": (BOOL, ()), "ignore_layout": (BOOL, ()), "overflow_visible": (BOOL, ()),
    "scrollbar_mode": (ENUM, ("OFF", "ON", "ACTIVE", "AUTO")),
    "state": (ANY, ()), "styles": (ANY, ()), "group": (ANY, ()),
    "text": (TEXT, ()), "long_mode": (ENUM, ("WRAP", "DOT", "SCROLL", "SCROLL_CIRCULAR", "CLIP")),
    "src": (ANY, ()), "value": (ANY, ()), "min_value": (INT, ()), "max_value": (INT, ()),
    "start_angle": (INT, ()), "end_angle": (INT, ()), "rotation": (INT, ()),
    "bg_start_angle": (INT, ()), "bg_end_angle": (INT, ()), "adjustable": (BOOL, ()),
    "mode": (ANY, ()), "color": (COLOR, ()), "brightness": (ANY, ()),
    "options": (ANY, ()), "selected_index": (INT, ()), "placeholder_text": (TEXT, ()),
    "one_line": (BOOL, ()), "max_length": (INT, ()), "password_mode": (BOOL, ()),
    "layout": (ANY, ()), "flex_flow": (ANY, ()), "flex_grow": (INT, ()),
    "grid_cell_column_pos": (INT, ()), "grid_cell_row_pos": (INT, ()),
    "grid_cell_column_span": (INT, ()), "grid_cell_row_span": (INT, ()),
    "grid_cell_x_align": (ENUM, ("START", "END", "CENTER", "STRETCH")),
    "grid_cell_y_align": (ENUM, ("START", "END", "CENTER", "STRETCH")),
    "align_to": (ANY, ()), "position": (ANY, ()), "size": (ANY, ()),
}

_HEX_COLOR = re.compile(r"^(?:0x|#)([0-9A-Fa-f]{6})$")


def kind_of(key: str) -> str:
    if key in REGISTRY:
        return REGISTRY[key][0]
    if key == "color" or key.endswith("_color") or key.endswith("_recolor"):
        return COLOR
    if key.endswith("_opa"):
        return OPA
    return ANY


def is_tagged(value: Any) -> bool:
    return isinstance(value, dict) and TAG_KEY in value


def tagged(tag: str, value: Any) -> dict:
    return {TAG_KEY: tag, "value": value}


# --------------------------------------------------------------------------- AST → JSON
def node_to_value(node: YNode, key: str = "") -> Any:
    if isinstance(node, YScalar):
        if node.tag:
            return tagged(node.tag, node.value)
        v = node.value
        if kind_of(key) == COLOR:
            if isinstance(v, int) and not isinstance(v, bool):
                return f"#{v & 0xFFFFFF:06X}"
            if isinstance(v, str):
                m = _HEX_COLOR.match(v.strip())
                if m:
                    return f"#{m.group(1).upper()}"
        return v
    if isinstance(node, YRaw):
        return tagged("!raw", node.text)
    if isinstance(node, YSeq):
        value = [node_to_value(i, key) for i in node.items]
        return tagged(node.tag, value) if node.tag else value
    if isinstance(node, YMap):
        value = {p.key: node_to_value(p.value, p.key) for p in node.items}
        return tagged(node.tag, value) if node.tag else value
    raise TypeError(type(node))


# --------------------------------------------------------------------------- JSON → AST
def value_to_node(value: Any, key: str = "") -> YNode:
    if is_tagged(value):
        tag, inner = value[TAG_KEY], value.get("value")
        if tag == "!raw":
            return YRaw(str(inner))
        node = value_to_node(inner, key)
        if isinstance(node, YScalar):
            node.tag = tag
            if isinstance(inner, str) and ("\n" in inner or tag == "!lambda"):
                node.style = LITERAL
        elif isinstance(node, (YMap, YSeq)):
            node.tag = tag
        return node
    if isinstance(value, dict):
        m = YMap()
        for k, v in value.items():
            m.items.append(_pair(k, v))
        return m
    if isinstance(value, list):
        return YSeq([value_to_node(v, key) for v in value])
    if kind_of(key) == COLOR and isinstance(value, str):
        m = _HEX_COLOR.match(value.strip())
        if m:
            return YScalar(int(m.group(1), 16), HEX)
    if isinstance(value, str) and "\n" in value:
        return YScalar(value, LITERAL)
    return YScalar(value)


def _pair(k: str, v: Any):
    from olvgl.domain.yaml_ast import YPair
    return YPair(str(k), value_to_node(v, str(k)))


# --------------------------------------------------------------------------- utilidades
def opa_to_float(value: Any, default: float = 1.0) -> float:
    """TRANSP/COVER, '50%', 0..1 o 0..255 → 0..1."""
    if value is None:
        return default
    if isinstance(value, bool):
        return 1.0 if value else 0.0
    if isinstance(value, (int, float)):
        v = float(value)
        return max(0.0, min(1.0, v if v <= 1.0 else v / 255.0))
    s = str(value).strip().upper()
    if s == "TRANSP":
        return 0.0
    if s == "COVER":
        return 1.0
    if s.endswith("%"):
        try:
            return max(0.0, min(1.0, float(s[:-1]) / 100.0))
        except ValueError:
            return default
    return default


def display_text(value: Any) -> str:
    """Texto a mostrar en el canvas para un valor de `text:`."""
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if is_tagged(value):
        tag = value[TAG_KEY]
        if tag == "!lambda":
            return "λ"
        return f"{tag} {value.get('value')}"
    if isinstance(value, dict):
        fmt = value.get("format")
        if isinstance(fmt, str):
            return fmt
        if "time_format" in value:
            return str(value["time_format"])
    return str(value)


_RECOLOR = re.compile(r"#[0-9A-Fa-f]{6} (.*?)#", re.S)


def strip_recolor(text: str) -> str:
    """Quita el marcado de color de LVGL (`#FF0000 texto#`) cuando `recolor: true`."""
    return _RECOLOR.sub(r"\1", text)
