"""Generador de código C para LVGL 9 (ui.h / ui.c).

Traduce el modelo a llamadas de la API de LVGL 9.x (la misma versión que usa
ESPHome): pantallas, capa superior, todos los widgets, posición/tamaño/
alineación, estilos por parte y estado, definiciones de estilo y tema
(`lv_style_t`), layouts flex y grid, fuentes, imágenes y eventos.

Lo que sólo existe en ESPHome (acciones de Home Assistant, scripts, lambdas,
textos con `format`) no se puede traducir: se deja comentado y los eventos
llaman a `ui_action_handler`, una función que el programa principal puede
asignar para hacer el trabajo.
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from typing import Any

from olvgl import __version__
from olvgl.domain import catalog
from olvgl.domain.layout import named_colors, resolve_color
from olvgl.domain.model import TOP_LAYER_ID, Action, Project, Screen, Widget
from olvgl.domain.values import display_text, is_tagged

# --------------------------------------------------------------------------- tablas
PART_C = {"main": "LV_PART_MAIN", "scrollbar": "LV_PART_SCROLLBAR", "indicator": "LV_PART_INDICATOR",
          "knob": "LV_PART_KNOB", "selected": "LV_PART_SELECTED", "items": "LV_PART_ITEMS",
          "cursor": "LV_PART_CURSOR", "textarea_placeholder": "LV_PART_TEXTAREA_PLACEHOLDER",
          "ticks": "LV_PART_INDICATOR"}   # meter → lv_scale: las marcas principales y sus números
STATE_C = {s: f"LV_STATE_{s.upper()}" for s in catalog.STATES}

EVENT_C = {
    "on_click": "LV_EVENT_CLICKED", "on_short_click": "LV_EVENT_SHORT_CLICKED",
    "on_press": "LV_EVENT_PRESSED", "on_release": "LV_EVENT_RELEASED",
    "on_long_press": "LV_EVENT_LONG_PRESSED", "on_long_press_repeat": "LV_EVENT_LONG_PRESSED_REPEAT",
    "on_value": "LV_EVENT_VALUE_CHANGED", "on_change": "LV_EVENT_VALUE_CHANGED",
    "on_focus": "LV_EVENT_FOCUSED", "on_defocus": "LV_EVENT_DEFOCUSED",
    "on_ready": "LV_EVENT_READY", "on_cancel": "LV_EVENT_CANCEL",
    "on_scroll": "LV_EVENT_SCROLL", "on_scroll_begin": "LV_EVENT_SCROLL_BEGIN",
    "on_scroll_end": "LV_EVENT_SCROLL_END",
    "on_load": "LV_EVENT_SCREEN_LOADED", "on_unload": "LV_EVENT_SCREEN_UNLOADED",
    "on_press_lost": "LV_EVENT_PRESS_LOST", "on_single_click": "LV_EVENT_SINGLE_CLICKED",
    "on_double_click": "LV_EVENT_DOUBLE_CLICKED", "on_triple_click": "LV_EVENT_TRIPLE_CLICKED",
    "on_gesture": "LV_EVENT_GESTURE", "on_swipe_left": "LV_EVENT_GESTURE",
    "on_swipe_right": "LV_EVENT_GESTURE", "on_swipe_up": "LV_EVENT_GESTURE", "on_swipe_top": "LV_EVENT_GESTURE",
    "on_swipe_down": "LV_EVENT_GESTURE", "on_swipe_bottom": "LV_EVENT_GESTURE",
}
# los on_swipe_* de ESPHome son LV_EVENT_GESTURE con una dirección concreta
TILE_DIRS = ("LEFT", "RIGHT", "TOP", "BOTTOM", "HOR", "VER", "ALL", "NONE")
SIDE_DIRS = ("LEFT", "RIGHT", "TOP", "BOTTOM")
SWIPE_DIR = {"on_swipe_left": "LV_DIR_LEFT", "on_swipe_right": "LV_DIR_RIGHT", "on_swipe_up": "LV_DIR_TOP",
             "on_swipe_top": "LV_DIR_TOP", "on_swipe_down": "LV_DIR_BOTTOM", "on_swipe_bottom": "LV_DIR_BOTTOM"}

# propiedad ESPHome → (setter de estilo LVGL, tipo)
STYLE = {
    "bg_color": ("bg_color", "color"), "bg_opa": ("bg_opa", "opa"),
    "bg_grad_color": ("bg_grad_color", "color"), "bg_grad_dir": ("bg_grad_dir", "grad_dir"),
    "bg_main_stop": ("bg_main_stop", "int"), "bg_grad_stop": ("bg_grad_stop", "int"),
    "bg_image_src": ("bg_image_src", "image"), "bg_image_opa": ("bg_image_opa", "opa"),
    "bg_image_recolor": ("bg_image_recolor", "color"), "bg_image_recolor_opa": ("bg_image_recolor_opa", "opa"),
    "border_color": ("border_color", "color"), "border_opa": ("border_opa", "opa"),
    "border_width": ("border_width", "int"), "border_side": ("border_side", "border_side"),
    "border_post": ("border_post", "bool"),
    "outline_color": ("outline_color", "color"), "outline_opa": ("outline_opa", "opa"),
    "outline_width": ("outline_width", "int"), "outline_pad": ("outline_pad", "int"),
    "shadow_color": ("shadow_color", "color"), "shadow_opa": ("shadow_opa", "opa"),
    "shadow_width": ("shadow_width", "int"), "shadow_ofs_x": ("shadow_offset_x", "int"),
    "shadow_ofs_y": ("shadow_offset_y", "int"), "shadow_offset_x": ("shadow_offset_x", "int"),
    "shadow_offset_y": ("shadow_offset_y", "int"), "shadow_spread": ("shadow_spread", "int"),
    "radius": ("radius", "int"), "clip_corner": ("clip_corner", "bool"), "opa": ("opa", "opa"),
    "opa_layered": ("opa_layered", "opa"),
    "pad_all": ("pad_all", "int"), "pad_top": ("pad_top", "int"), "pad_bottom": ("pad_bottom", "int"),
    "pad_left": ("pad_left", "int"), "pad_right": ("pad_right", "int"), "pad_row": ("pad_row", "int"),
    "pad_column": ("pad_column", "int"),
    "text_color": ("text_color", "color"), "text_opa": ("text_opa", "opa"), "text_font": ("text_font", "font"),
    "text_align": ("text_align", "text_align"), "text_letter_space": ("text_letter_space", "int"),
    "text_line_space": ("text_line_space", "int"), "text_decor": ("text_decor", "text_decor"),
    "line_color": ("line_color", "color"), "line_opa": ("line_opa", "opa"), "line_width": ("line_width", "int"),
    "line_rounded": ("line_rounded", "bool"), "line_dash_width": ("line_dash_width", "int"),
    "line_dash_gap": ("line_dash_gap", "int"),
    "arc_color": ("arc_color", "color"), "arc_opa": ("arc_opa", "opa"), "arc_width": ("arc_width", "int"),
    "arc_rounded": ("arc_rounded", "bool"),
    "image_recolor": ("image_recolor", "color"), "image_recolor_opa": ("image_recolor_opa", "opa"),
    "image_opa": ("image_opa", "opa"),
    "min_width": ("min_width", "coord"), "max_width": ("max_width", "coord"),
    "min_height": ("min_height", "coord"), "max_height": ("max_height", "coord"),
    "transform_angle": ("transform_rotation", "int"), "transform_rotation": ("transform_rotation", "int"),
    "transform_zoom": ("transform_scale", "scale"), "transform_scale": ("transform_scale", "scale"),
    "transform_pivot_x": ("transform_pivot_x", "coord"), "transform_pivot_y": ("transform_pivot_y", "coord"),
    "translate_x": ("translate_x", "coord"), "translate_y": ("translate_y", "coord"),
}
FLAGS = {"hidden": "LV_OBJ_FLAG_HIDDEN", "clickable": "LV_OBJ_FLAG_CLICKABLE",
         "scrollable": "LV_OBJ_FLAG_SCROLLABLE", "checkable": "LV_OBJ_FLAG_CHECKABLE",
         "floating": "LV_OBJ_FLAG_FLOATING", "ignore_layout": "LV_OBJ_FLAG_IGNORE_LAYOUT",
         "overflow_visible": "LV_OBJ_FLAG_OVERFLOW_VISIBLE", "press_lock": "LV_OBJ_FLAG_PRESS_LOCK",
         "event_bubble": "LV_OBJ_FLAG_EVENT_BUBBLE", "gesture_bubble": "LV_OBJ_FLAG_GESTURE_BUBBLE",
         "snappable": "LV_OBJ_FLAG_SNAPPABLE", "scroll_elastic": "LV_OBJ_FLAG_SCROLL_ELASTIC",
         "scroll_momentum": "LV_OBJ_FLAG_SCROLL_MOMENTUM", "scroll_on_focus": "LV_OBJ_FLAG_SCROLL_ON_FOCUS",
         "click_focusable": "LV_OBJ_FLAG_CLICK_FOCUSABLE", "adv_hittest": "LV_OBJ_FLAG_ADV_HITTEST"}
FLAG_SETTERS = [(f[len("LV_OBJ_FLAG_"):].lower(), f) for f in dict.fromkeys(FLAGS.values())]
LONG_MODE_C = {"WRAP": "WRAP", "DOT": "DOTS", "DOTS": "DOTS", "SCROLL": "SCROLL",
               "SCROLL_CIRCULAR": "SCROLL_CIRCULAR", "CLIP": "CLIP"}
CREATE = {"obj": "lv_obj_create", "label": "lv_label_create", "button": "lv_button_create",
          "image": "lv_image_create", "arc": "lv_arc_create", "bar": "lv_bar_create",
          "slider": "lv_slider_create", "switch": "lv_switch_create", "checkbox": "lv_checkbox_create",
          "dropdown": "lv_dropdown_create", "roller": "lv_roller_create", "textarea": "lv_textarea_create",
          "spinbox": "lv_spinbox_create", "led": "lv_led_create", "spinner": "lv_spinner_create",
          "line": "lv_line_create", "qrcode": "lv_qrcode_create", "keyboard": "lv_keyboard_create",
          "buttonmatrix": "lv_buttonmatrix_create", "tabview": "lv_tabview_create",
          "tileview": "lv_tileview_create", "canvas": "lv_canvas_create", "animimg": "lv_animimg_create",
          "meter": "lv_scale_create"}
# propiedades que cada tipo trata aparte (no son estilos ni flags)
HANDLED = {"text", "long_mode", "recolor", "src", "angle", "zoom", "value", "min_value", "max_value",
           "start_angle", "end_angle", "rotation", "mode", "adjustable", "change_rate", "start_value",
           "animated", "options", "selected_index", "dir", "symbol", "visible_row_count",
           "placeholder_text", "one_line", "password_mode", "max_length", "accepted_chars",
           "range_from", "range_to", "digits", "decimal_places", "step", "rollover", "selected_digit",
           "color", "brightness", "spin_time", "arc_length", "points", "size", "dark_color",
           "light_color", "textarea", "rows", "position", "name", "row", "column", "duration",
           "repeat_count", "auto_start", "transparent", "styles", "state", "layout", "align", "align_to",
           "flex_grow", "grid_cell_column_pos", "grid_cell_row_pos", "grid_cell_column_span",
           "grid_cell_row_span", "grid_cell_x_align", "grid_cell_y_align", "scrollbar_mode", "group",
           "scales", "pivot_x", "pivot_y", "offset_x", "offset_y", "antialias"}


V93 = "#if LVGL_VERSION_MAJOR > 9 || (LVGL_VERSION_MAJOR == 9 && LVGL_VERSION_MINOR >= 3)"


def c_str(s: Any) -> str:
    s = str(s)
    out = (s.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n").replace("\r", "\\r")
           .replace("\t", "\\t").replace("??", "?\\?"))
    return f'"{out}"'


def c_comment(s: Any) -> str:
    return str(s).replace("*/", "* /").replace("\n", " ")


def _num(v: Any) -> float | None:
    if isinstance(v, bool) or v is None or is_tagged(v):
        return None
    if isinstance(v, (int, float)):
        return float(v)
    try:
        return float(str(v).strip())
    except ValueError:
        return None


def _ms(v: Any, default: int) -> int:
    """'1s', '500ms', 1000 → milisegundos."""
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        return int(v)
    m = re.fullmatch(r"\s*([\d.]+)\s*(ms|s|min)?\s*", str(v or ""))
    if not m:
        return default
    n = float(m.group(1))
    unit = m.group(2) or "ms"
    return int(n * {"ms": 1, "s": 1000, "min": 60000}[unit])


@dataclass
class Out:
    header: str
    source: str
    warnings: list[str] = field(default_factory=list)
    fonts: list[str] = field(default_factory=list)      # fuentes Montserrat que hay que activar
    custom_fonts: list[str] = field(default_factory=list)
    images: list[str] = field(default_factory=list)


class CGenerator:
    def __init__(self, project: Project):
        self.p = project
        self.colors = named_colors(project)
        self.globals: list[str] = []        # declaraciones a nivel de fichero
        self.public: list[str] = []         # objetos con id (también en ui.h)
        self.statics: list[str] = []        # arrays estáticos (puntos, mapas…)
        self.styles: list[str] = []         # cuerpo de ui_styles_init()
        self.events: list[str] = []         # funciones de evento
        self.body: list[str] = []           # creación de pantallas
        self.deferred: list[str] = []       # lo que necesita que existan otros objetos
        self.warnings: list[str] = []
        self.fonts: set[int] = set()
        self.custom_fonts: set[str] = set()
        self.images: set[str] = set()
        self.theme_styles: dict[str, list[tuple[str, str]]] = {}   # tipo → [(var estilo, selector)]
        self.style_defs: dict[str, list[tuple[str, str]]] = {}     # id → [(var estilo, selector)]
        self.var_of: dict[str, str] = {}
        self._n = 0

    # ----------------------------------------------------------------- nombres
    def var(self, w: Widget) -> str:
        v = self.var_of.get(w.id)
        if v is None:
            v = "ui_" + re.sub(r"[^A-Za-z0-9_]", "_", w.id)
            self.var_of[w.id] = v
        return v

    def screen_var(self, s: Screen) -> str:
        return "lv_layer_top()" if s.id == TOP_LAYER_ID else "ui_" + re.sub(r"[^A-Za-z0-9_]", "_", s.id)

    def uniq(self, base: str) -> str:
        self._n += 1
        return f"{base}_{self._n}"

    # ----------------------------------------------------------------- valores
    def color(self, v: Any) -> str | None:
        if v is None or is_tagged(v):
            return None
        hexv = resolve_color(v, self.colors, "")
        if not hexv:
            return None
        return f"lv_color_hex(0x{hexv[1:]})"

    @staticmethod
    def opa(v: Any) -> str | None:
        if v is None or is_tagged(v):
            return None
        if isinstance(v, bool):
            return "LV_OPA_COVER" if v else "LV_OPA_TRANSP"
        if isinstance(v, (int, float)):
            f = float(v)
            return str(int(round(f * 255 if f <= 1.0 else f)))
        s = str(v).strip().upper()
        if s in ("COVER", "TRANSP"):
            return f"LV_OPA_{s}"
        if s.endswith("%"):
            try:
                pct = float(s[:-1])
            except ValueError:
                return None
            return f"LV_OPA_{int(pct)}" if pct in range(0, 101, 10) else str(int(round(pct * 2.55)))
        return None

    @staticmethod
    def coord(v: Any) -> str | None:
        if v is None or is_tagged(v):
            return None
        if isinstance(v, bool):
            return None
        if isinstance(v, (int, float)):
            return str(int(v))
        s = str(v).strip()
        if s.upper() == "SIZE_CONTENT":
            return "LV_SIZE_CONTENT"
        if s.endswith("%"):
            try:
                return f"lv_pct({int(float(s[:-1]))})"
            except ValueError:
                return None
        try:
            return str(int(float(s.rstrip("px"))))
        except ValueError:
            return None

    def font(self, v: Any) -> str | None:
        if not isinstance(v, str):
            return None
        m = re.fullmatch(r"montserrat_(\d+)", v)
        if m:
            self.fonts.add(int(m.group(1)))
            return f"&lv_font_montserrat_{m.group(1)}"
        if self.p.font(v) is not None:
            name = "font_" + re.sub(r"[^A-Za-z0-9_]", "_", v)
            self.custom_fonts.add(name)
            return f"&{name}"
        return None

    def image(self, v: Any) -> str | None:
        if not isinstance(v, str):
            return None
        img = self.p.image(v)
        if img is None:
            return None
        if not img.path or "file" in img.extra:
            return None   # online_image u otra fuente sólo de ESPHome
        name = re.sub(r"[^A-Za-z0-9_]", "_", v)
        self.images.add(name)
        return f"&{name}"

    @staticmethod
    def enum(prefix: str, v: Any) -> str | None:
        if not isinstance(v, str) or is_tagged(v):
            return None
        return f"{prefix}{v.strip().upper()}"

    def value_c(self, kind: str, v: Any) -> str | None:
        if kind == "color":
            return self.color(v)
        if kind == "opa":
            return self.opa(v)
        if kind == "int":
            n = _num(v)
            return None if n is None else str(int(n))
        if kind == "bool":
            return ("true" if v else "false") if isinstance(v, bool) else None
        if kind == "font":
            return self.font(v)
        if kind == "coord":
            return self.coord(v)
        if kind == "image":
            return self.image(v)
        if kind == "scale":
            n = _num(v)
            return None if n is None else str(int(round(n * 256 if n <= 16 else n)))
        if kind == "text_align":
            return self.enum("LV_TEXT_ALIGN_", v)
        if kind == "text_decor":
            return self.enum("LV_TEXT_DECOR_", v)
        if kind == "grad_dir":
            return self.enum("LV_GRAD_DIR_", v)
        if kind == "border_side":
            sides = v if isinstance(v, list) else [v]
            parts = [f"LV_BORDER_SIDE_{str(s).strip().upper()}" for s in sides if isinstance(s, str)]
            return " | ".join(parts) if parts else None
        return None

    # ----------------------------------------------------------------- estilos
    def style_calls(self, target: str, props: dict, selector: str, out: list[str], is_style: bool,
                    skip: set[str] | frozenset = frozenset(), where: str = "") -> None:
        """Emite los setters de estilo de `props` (y de sus estados/partes anidados)."""
        for k, v in props.items():
            if k in skip:
                continue
            if k in STYLE:
                name, kind = STYLE[k]
                cv = self.value_c(kind, v)
                if cv is None:
                    out.append(f"    /* {k}: {c_comment(v)} — no traducible a C */")
                    continue
                if is_style:
                    out.append(f"    lv_style_set_{name}(&{target}, {cv});")
                else:
                    out.append(f"    lv_obj_set_style_{name}({target}, {cv}, {selector});")
            elif isinstance(v, dict) and not is_tagged(v) and (k in catalog.STATES or k in PART_C):
                if is_style:
                    continue   # los estilos con estados se tratan en build_style()
                sub_sel = self.combine(selector, k)
                self.style_calls(target, v, sub_sel, out, is_style, skip=frozenset(), where=where)

    @staticmethod
    def combine(selector: str, key: str) -> str:
        part, state = "LV_PART_MAIN", "LV_STATE_DEFAULT"
        for tok in selector.split("|"):
            tok = tok.strip()
            if tok.startswith("LV_PART_"):
                part = tok
            elif tok.startswith("LV_STATE_"):
                state = tok
        if key in PART_C:
            part = PART_C[key]
        elif key in STATE_C:
            state = STATE_C[key]
        return f"{part} | {state}"

    def build_style(self, base: str, props: dict, registry: list[tuple[str, str]]) -> None:
        """Un lv_style_t por cada combinación parte/estado de `props`."""
        def walk(d: dict, selector: str, suffix: str) -> None:
            plain = {k: v for k, v in d.items()
                     if not (isinstance(v, dict) and not is_tagged(v) and (k in catalog.STATES or k in PART_C))}
            if plain:
                var = f"{base}{suffix}"
                self.globals.append(f"static lv_style_t {var};")
                self.styles.append(f"    lv_style_init(&{var});")
                self.style_calls(var, plain, selector, self.styles, is_style=True)
                registry.append((var, selector))
            for k, v in d.items():
                if isinstance(v, dict) and not is_tagged(v) and (k in catalog.STATES or k in PART_C):
                    walk(v, self.combine(selector, k), f"{suffix}_{k}")
        walk(props, "LV_PART_MAIN | LV_STATE_DEFAULT", "")

    # ----------------------------------------------------------------- widgets
    def geometry(self, w: Widget, o: str, out: list[str]) -> None:
        if w.type in catalog.PSEUDO_TYPES:
            return
        wv, hv = self.coord(w.width), self.coord(w.height)
        if wv is not None and hv is not None:
            out.append(f"    lv_obj_set_size({o}, {wv}, {hv});")
        else:
            if wv is not None:
                out.append(f"    lv_obj_set_width({o}, {wv});")
            if hv is not None:
                out.append(f"    lv_obj_set_height({o}, {hv});")
        for g in ("x", "y", "width", "height"):
            if is_tagged(getattr(w, g)):
                out.append(f"    /* {g}: lambda de ESPHome — no traducible a C */")
        xv, yv = self.coord(w.x), self.coord(w.y)
        align = w.props.get("align")
        if isinstance(align, str):
            out.append(f"    lv_obj_align({o}, LV_ALIGN_{align.upper()}, {xv or 0}, {yv or 0});")
        elif xv is not None and yv is not None:
            out.append(f"    lv_obj_set_pos({o}, {xv}, {yv});")
        else:
            if xv is not None:
                out.append(f"    lv_obj_set_x({o}, {xv});")
            if yv is not None:
                out.append(f"    lv_obj_set_y({o}, {yv});")
        at = w.props.get("align_to")
        if isinstance(at, dict) and isinstance(at.get("id"), str):
            target = self.p.widget(at["id"])
            if target is not None:
                a = str(at.get("align", "OUT_BOTTOM_MID")).upper()
                self.deferred.append(f"    lv_obj_align_to({o}, {self.var(target)}, LV_ALIGN_{a}, "
                                     f"{self.coord(at.get('x', 0)) or 0}, {self.coord(at.get('y', 0)) or 0});")

    def flags_and_state(self, w: Widget, o: str, out: list[str]) -> None:
        for k, flag in FLAGS.items():
            v = w.props.get(k)
            if v is True:
                out.append(f"    ui_set_flag({o}, {flag}, true);")
            elif v is False:
                out.append(f"    ui_set_flag({o}, {flag}, false);")
        sm = w.props.get("scrollbar_mode")
        if isinstance(sm, str):
            out.append(f"    lv_obj_set_scrollbar_mode({o}, LV_SCROLLBAR_MODE_{sm.upper()});")
        st = w.props.get("state")
        if isinstance(st, dict):
            for k, v in st.items():
                if k in STATE_C and v is True:
                    out.append(f"    lv_obj_add_state({o}, {STATE_C[k]});")

    def layout(self, w: Widget | Screen, o: str, out: list[str]) -> None:
        lay = w.props.get("layout")
        if lay is None:
            return
        if isinstance(lay, str):
            m = re.fullmatch(r"\s*(\d+)\s*[xX]\s*(\d+)\s*", lay)
            if m:
                rows, cols = int(m.group(1)), int(m.group(2))
                lay = {"type": "grid", "grid_rows": ["FR(1)"] * rows, "grid_columns": ["FR(1)"] * cols,
                       "_auto": True}
            elif lay.strip().lower() in ("flex", "grid"):
                lay = {"type": lay.strip().lower()}
            else:
                return
        if not isinstance(lay, dict):
            return
        t = str(lay.get("type", "")).lower()
        if t == "flex":
            out.append(f"    lv_obj_set_layout({o}, LV_LAYOUT_FLEX);")
            flow = str(lay.get("flex_flow", "ROW")).upper()
            out.append(f"    lv_obj_set_flex_flow({o}, LV_FLEX_FLOW_{flow});")
            if any(k in lay for k in ("flex_align_main", "flex_align_cross", "flex_align_track")):
                a = [str(lay.get(k, "START")).upper() for k in
                     ("flex_align_main", "flex_align_cross", "flex_align_track")]
                out.append(f"    lv_obj_set_flex_align({o}, LV_FLEX_ALIGN_{a[0]}, LV_FLEX_ALIGN_{a[1]}, "
                           f"LV_FLEX_ALIGN_{a[2]});")
        elif t == "grid":
            def track(v: Any) -> str:
                s = str(v).strip().upper()
                m2 = re.fullmatch(r"FR\((\d+)\)", s)
                if m2:
                    return f"LV_GRID_FR({m2.group(1)})"
                if s == "CONTENT":
                    return "LV_GRID_CONTENT"
                return self.coord(v) or "LV_GRID_FR(1)"
            cols = [track(v) for v in (lay.get("grid_columns") or ["FR(1)"])]
            rows = [track(v) for v in (lay.get("grid_rows") or ["FR(1)"])]
            cname, rname = f"{o}_cols", f"{o}_rows"
            self.statics.append(f"static const int32_t {cname}[] = {{{', '.join(cols)}, LV_GRID_TEMPLATE_LAST}};")
            self.statics.append(f"static const int32_t {rname}[] = {{{', '.join(rows)}, LV_GRID_TEMPLATE_LAST}};")
            out.append(f"    lv_obj_set_grid_dsc_array({o}, {cname}, {rname});")
            out.append(f"    lv_obj_set_layout({o}, LV_LAYOUT_GRID);")
            if isinstance(w, Widget):
                ncols = len(cols)
                auto = 0
                for c in w.children:
                    if c.props.get("floating") or c.props.get("ignore_layout") or c.props.get("hidden") is True:
                        continue
                    if "grid_cell_column_pos" in c.props or "grid_cell_row_pos" in c.props:
                        col = int(_num(c.props.get("grid_cell_column_pos")) or 0)
                        row = int(_num(c.props.get("grid_cell_row_pos")) or 0)
                    else:
                        col, row = auto % ncols, auto // ncols
                        auto += 1
                    cs = int(_num(c.props.get("grid_cell_column_span")) or 1)
                    rs = int(_num(c.props.get("grid_cell_row_span")) or 1)
                    xa = str(c.props.get("grid_cell_x_align", "START")).upper()
                    ya = str(c.props.get("grid_cell_y_align", "START")).upper()
                    self.deferred.append(f"    lv_obj_set_grid_cell({self.var(c)}, LV_GRID_ALIGN_{xa}, {col}, {cs}, "
                                         f"LV_GRID_ALIGN_{ya}, {row}, {rs});")
        for k in ("pad_row", "pad_column"):
            if k in lay:
                n = _num(lay[k])
                if n is not None:
                    out.append(f"    lv_obj_set_style_{k}({o}, {int(n)}, 0);")

    def specific(self, w: Widget, o: str, out: list[str]) -> None:
        pr = w.props
        t = w.type

        def num(k: str, default: Any = None) -> int | None:
            n = _num(pr.get(k, default))
            return None if n is None else int(n)

        def text_of(k: str) -> str | None:
            v = pr.get(k)
            if v is None:
                return None
            if is_tagged(v):
                out.append(f"    /* {k}: {c_comment(v.get('value'))} — lambda de ESPHome */")
                return None
            if isinstance(v, dict):
                out.append(f"    /* {k}: format {c_comment(v)} — ESPHome lo rellena en tiempo real */")
                return display_text(v)
            return str(v)

        if t == "label":
            s = text_of("text")
            if s is not None:
                out.append(f"    lv_label_set_text({o}, {c_str(s)});")
            lm = pr.get("long_mode")
            if isinstance(lm, str) and lm.upper() in LONG_MODE_C:
                out.append(f"    lv_label_set_long_mode({o}, LV_LABEL_LONG_MODE_{LONG_MODE_C[lm.upper()]});")
            if pr.get("recolor") is True:
                out.append(f"    lv_label_set_recolor({o}, true);")
        elif t == "button" and "text" in pr:
            lbl = f"{o}_label"
            self.globals.append(f"static lv_obj_t * {lbl};")
            out.append(f"    {lbl} = lv_label_create({o});")
            out.append(f"    lv_obj_center({lbl});")
            s = text_of("text")
            if s is not None:
                out.append(f"    lv_label_set_text({lbl}, {c_str(s)});")
            self.style_calls(lbl, {k: pr[k] for k in ("text_color", "text_font") if k in pr},
                             "LV_PART_MAIN | LV_STATE_DEFAULT", out, is_style=False)
        elif t == "image":
            src = self.image(pr.get("src"))
            if src:
                out.append(f"    lv_image_set_src({o}, {src});")
            elif pr.get("src"):
                out.append(f"    /* src: {c_comment(pr.get('src'))} — imagen en línea/ESPHome: asígnala en tu código */")
            if num("angle") is not None:
                out.append(f"    lv_image_set_rotation({o}, {num('angle')});")
            z = _num(pr.get("zoom"))
            if z is not None:
                out.append(f"    lv_image_set_scale({o}, {int(round(z * 256))});")
        elif t in ("arc", "bar", "slider"):
            if "min_value" in pr or "max_value" in pr:
                out.append(f"    lv_{t}_set_range({o}, {num('min_value', 0)}, {num('max_value', 100)});")
            anim = "" if t == "arc" else ", LV_ANIM_OFF"
            if num("value") is not None:
                out.append(f"    lv_{t}_set_value({o}, {num('value')}{anim});")
            if isinstance(pr.get("mode"), str):
                out.append(f"    lv_{t}_set_mode({o}, LV_{t.upper()}_MODE_{pr['mode'].upper()});")
            if t == "arc":
                if "start_angle" in pr or "end_angle" in pr:
                    out.append(f"    lv_arc_set_bg_angles({o}, {num('start_angle', 135)}, {num('end_angle', 45)});")
                if num("rotation") is not None:
                    out.append(f"    lv_arc_set_rotation({o}, {num('rotation')});")
                if not pr.get("adjustable", False):
                    out.append(f"    lv_obj_remove_style({o}, NULL, LV_PART_KNOB);   /* adjustable: false */")
                    out.append(f"    ui_set_flag({o}, LV_OBJ_FLAG_CLICKABLE, false);")
            elif t == "bar" and num("start_value") is not None:
                out.append(f"    lv_bar_set_start_value({o}, {num('start_value')}, LV_ANIM_OFF);")
        elif t == "checkbox":
            s = text_of("text")
            if s is not None:
                out.append(f"    lv_checkbox_set_text({o}, {c_str(s)});")
        elif t in ("dropdown", "roller"):
            opts = pr.get("options")
            items = opts if isinstance(opts, list) else ([opts] if isinstance(opts, str) else [])
            joined = c_str("\n".join(display_text(i) for i in items))
            if t == "dropdown":
                if items:
                    out.append(f"    lv_dropdown_set_options({o}, {joined});")
                if num("selected_index") is not None:
                    out.append(f"    lv_dropdown_set_selected({o}, {num('selected_index')});")
                if isinstance(pr.get("dir"), str):
                    out.append(f"    lv_dropdown_set_dir({o}, {self.dirs(w, pr['dir'], SIDE_DIRS, 'BOTTOM')});")
            else:
                mode = str(pr.get("mode", "NORMAL")).upper()
                if items:
                    out.append(f"    lv_roller_set_options({o}, {joined}, LV_ROLLER_MODE_{mode});")
                if num("selected_index") is not None:
                    out.append(f"    lv_roller_set_selected({o}, {num('selected_index')}, LV_ANIM_OFF);")
                if num("visible_row_count") is not None:
                    out.append(f"    lv_roller_set_visible_row_count({o}, {num('visible_row_count')});")
        elif t == "textarea":
            for k, fn in (("text", "lv_textarea_set_text"), ("placeholder_text", "lv_textarea_set_placeholder_text"),
                          ("accepted_chars", "lv_textarea_set_accepted_chars")):
                s = text_of(k)
                if s is not None:
                    out.append(f"    {fn}({o}, {c_str(s)});")
            for k in ("one_line", "password_mode"):
                if isinstance(pr.get(k), bool):
                    out.append(f"    lv_textarea_set_{k}({o}, {'true' if pr[k] else 'false'});")
            if num("max_length") is not None:
                out.append(f"    lv_textarea_set_max_length({o}, {num('max_length')});")
        elif t == "spinbox":
            digits = num("digits", 4) or 4
            dec = num("decimal_places", 0) or 0
            out.append(f"    lv_spinbox_set_range({o}, {num('range_from', -100)}, {num('range_to', 100)});")
            out.append(f"    lv_spinbox_set_digit_format({o}, {digits}, {digits - dec if dec else 0});")
            if num("step") is not None:
                out.append(f"    lv_spinbox_set_step({o}, {num('step')});")
            if num("value") is not None:
                out.append(f"    lv_spinbox_set_value({o}, {num('value')});")
            if isinstance(pr.get("rollover"), bool):
                out.append(f"    lv_spinbox_set_rollover({o}, {'true' if pr['rollover'] else 'false'});")
        elif t == "led":
            c = self.color(pr.get("color"))
            if c:
                out.append(f"    lv_led_set_color({o}, {c});")
            b = pr.get("brightness")
            if b is not None:
                pct = _num(str(b).rstrip("%"))
                if pct is not None:
                    out.append(f"    lv_led_set_brightness({o}, {int(round(pct * 2.55 if pct <= 100 else pct))});")
        elif t == "spinner":
            if "spin_time" in pr or "arc_length" in pr:
                out.append(f"    lv_spinner_set_anim_params({o}, {_ms(pr.get('spin_time'), 1000)}, "
                           f"{num('arc_length', 200)});")
        elif t == "line":
            from olvgl.domain.layout import line_points
            pts = line_points(pr.get("points"))
            if pts:
                arr = f"{o}_points"
                self.statics.append(f"static const lv_point_precise_t {arr}[] = {{"
                                    + ", ".join(f"{{{int(x)}, {int(y)}}}" for x, y in pts) + "};")
                out.append(f"    lv_line_set_points({o}, {arr}, {len(pts)});")
        elif t == "qrcode":
            if num("size") is not None:
                out.append(f"    lv_qrcode_set_size({o}, {num('size')});")
            for k in ("dark_color", "light_color"):
                c = self.color(pr.get(k))
                if c:
                    out.append(f"    lv_qrcode_set_{k}({o}, {c});")
            s = text_of("text")
            if s is not None:
                out.append(f"    lv_qrcode_update({o}, {c_str(s)}, {len(s.encode('utf-8'))});")
        elif t == "keyboard":
            if isinstance(pr.get("mode"), str):
                out.append(f"    lv_keyboard_set_mode({o}, LV_KEYBOARD_MODE_{pr['mode'].upper()});")
            ta = self.p.widget(pr.get("textarea")) if isinstance(pr.get("textarea"), str) else None
            if ta is not None:
                self.deferred.append(f"    lv_keyboard_set_textarea({o}, {self.var(ta)});")
        elif t == "buttonmatrix":
            rows = pr.get("rows")
            if isinstance(rows, list):
                cells: list[str] = []
                for i, row in enumerate(rows):
                    for b in (row.get("buttons", []) if isinstance(row, dict) else []):
                        txt = b.get("text", "") if isinstance(b, dict) else ""
                        cells.append(c_str(display_text(txt)))
                    if i < len(rows) - 1:
                        cells.append('"\\n"')
                arr = f"{o}_map"
                self.statics.append(f"static const char * {arr}[] = {{{', '.join(cells + [chr(34) * 2])}}};")
                out.append(f"    lv_buttonmatrix_set_map({o}, {arr});")
        elif t == "tabview":
            if isinstance(pr.get("position"), str):
                out.append(f"    lv_tabview_set_tab_bar_position({o}, {self.dirs(w, pr['position'], SIDE_DIRS, 'TOP')});")
            if pr.get("size") not in (None, ""):
                sz = self.coord(pr.get("size"))
                if sz:
                    out.append(f"    lv_tabview_set_tab_bar_size({o}, {sz});")
        elif t == "canvas":
            out.append(f"    /* lienzo: asigna un búfer con lv_canvas_set_buffer({o}, …) en tu código */")
        elif t == "animimg":
            srcs = [self.image(s) for s in (pr.get("src") or []) if isinstance(s, str)]
            srcs = [s for s in srcs if s]
            if srcs:
                arr = f"{o}_frames"
                self.statics.append(f"static const void * {arr}[] = {{{', '.join(srcs)}}};")
                out.append(f"    lv_animimg_set_src({o}, {arr}, {len(srcs)});")
            out.append(f"    lv_animimg_set_duration({o}, {_ms(pr.get('duration'), 1000)});")
            rc = pr.get("repeat_count")
            out.append(f"    lv_animimg_set_repeat_count({o}, "
                       f"{int(rc) if isinstance(rc, int) else 'LV_ANIM_REPEAT_INFINITE'});")
            if pr.get("auto_start", True) is not False:
                out.append(f"    lv_animimg_start({o});")
        elif t == "meter":
            self.meter(w, o, out)

    def meter(self, w: Widget, o: str, out: list[str]) -> None:
        """meter de ESPHome → lv_scale redonda de LVGL 9 (marcas, números, agujas y arcos como secciones)."""
        from olvgl.domain import meter as mt
        scales = mt.scales_of(w.props)
        out.append("    /* meter → lv_scale (LVGL 9). Las escalas adicionales se crean encima, transparentes */")
        for si, sc in enumerate(scales):
            s = o
            if si > 0:
                s = f"{o}_scale{si + 1}"
                self.globals.append(f"static lv_obj_t * {s};")
                out.append(f"    {s} = lv_scale_create({o});")
                out.append(f"    lv_obj_set_size({s}, lv_pct(100), lv_pct(100));")
                out.append(f"    lv_obj_center({s});")
                out.append(f"    lv_obj_set_style_bg_opa({s}, LV_OPA_TRANSP, LV_PART_MAIN);")
            g = mt.scale_geo(sc)
            ticks, major = mt.ticks_of(sc)
            out.append(f"    lv_scale_set_mode({s}, LV_SCALE_MODE_ROUND_INNER);")
            out.append(f"    lv_scale_set_range({s}, {int(g.range_from)}, {int(g.range_to)});")
            out.append(f"    lv_scale_set_angle_range({s}, {int(g.angle_range)});")
            out.append(f"    lv_scale_set_rotation({s}, {int(g.rotation)});")
            out.append(f"    lv_scale_set_total_tick_count({s}, {int(mt.num(ticks.get('count'), 12))});")
            out.append(f"    lv_scale_set_major_tick_every({s}, {int(mt.num(major.get('stride'), 3)) if major else 0});")
            out.append(f"    lv_scale_set_label_show({s}, {'true' if major else 'false'});")
            out.append(f"    lv_obj_set_style_arc_width({s}, 0, LV_PART_MAIN);   /* el meter no dibuja el arco de la escala */")
            for spec_, part in ((ticks, "LV_PART_ITEMS"), (major, "LV_PART_INDICATOR")):
                if not spec_:
                    continue
                ln = spec_.get("length")
                if isinstance(ln, str) and ln.strip().endswith("%"):
                    out.append(f"    lv_obj_set_style_length({s}, {self.coord(ln)}, {part});")
                elif mt.num(ln, -1) >= 0:
                    out.append(f"    lv_obj_set_style_length({s}, {int(mt.num(ln))}, {part});")
                out.append(f"    lv_obj_set_style_line_width({s}, {int(mt.num(spec_.get('width'), 2))}, {part});")
                c = self.color(spec_.get("color"))
                if c:
                    out.append(f"    lv_obj_set_style_line_color({s}, {c}, {part});")
                if mt.num(spec_.get("radial_offset"), 0):
                    out.append(V93)
                    out.append(f"    lv_obj_set_style_radial_offset({s}, {int(mt.num(spec_['radial_offset']))}, {part});")
                    out.append("#endif")
            if major and mt.num(major.get("label_gap"), 0):
                out.append(V93)
                out.append(f"    lv_obj_set_style_pad_radial({s}, {-int(mt.num(major['label_gap']))}, LV_PART_INDICATOR);")
                out.append("#endif")
            need_layout = True
            for ii, it in enumerate(sc.get("indicators") or []):
                k = mt.indicator_kind(it)
                if k is None:
                    continue
                kind, d = k
                name = d.get("id") if isinstance(d.get("id"), str) else None
                var = "ui_" + re.sub(r"[^A-Za-z0-9_]", "_", name) if name else f"{o}_{kind}{si + 1}_{ii + 1}"
                if name:
                    self.public.append(var)
                if kind in ("line", "image"):
                    if need_layout:
                        out.append(f"    lv_obj_update_layout({s});")
                        need_layout = False
                    value = int(mt.num(d.get("value"), g.range_from))
                    if kind == "line":
                        if not name:
                            self.globals.append(f"static lv_obj_t * {var};")
                        out.append(f"    {var} = lv_line_create({s});")
                        out.append(f"    lv_obj_set_style_line_width({var}, {int(mt.num(d.get('width'), 4))}, 0);")
                        c = self.color(d.get("color"))
                        if c:
                            out.append(f"    lv_obj_set_style_line_color({var}, {c}, 0);")
                        out.append(f"    lv_obj_set_style_line_rounded({var}, true, 0);")
                        op = self.opa(d.get("opa"))
                        if op:
                            out.append(f"    lv_obj_set_style_line_opa({var}, {op}, 0);")
                        rmod = int(mt.num(d.get("r_mod"), 0))
                        out.append(f"    lv_scale_set_line_needle_value({s}, {var}, "
                                   f"lv_obj_get_width({s}) / 2 + ({rmod}), {value});")
                    else:
                        if not name:
                            self.globals.append(f"static lv_obj_t * {var};")
                        out.append(f"    {var} = lv_image_create({s});")
                        src = self.image(d.get("src"))
                        if src:
                            out.append(f"    lv_image_set_src({var}, {src});")
                        out.append(f"    lv_image_set_pivot({var}, {int(mt.num(d.get('pivot_x'), 0))}, "
                                   f"{int(mt.num(d.get('pivot_y'), 0))});")
                        out.append(f"    lv_scale_set_image_needle_value({s}, {var}, {value});")
                else:
                    st = f"{var}_style"
                    sec = f"{var}_section"
                    self.globals.append(f"static lv_style_t {st};")
                    self.globals.append(f"static lv_scale_section_t * {sec};")
                    out.append(f"    lv_style_init(&{st});")
                    if kind == "arc":
                        c = self.color(d.get("color"))
                        if c:
                            out.append(f"    lv_style_set_arc_color(&{st}, {c});")
                        out.append(f"    lv_style_set_arc_width(&{st}, {int(mt.num(d.get('width'), 4))});")
                        op = self.opa(d.get("opa"))
                        if op:
                            out.append(f"    lv_style_set_arc_opa(&{st}, {op});")
                        part = "LV_PART_MAIN"
                        out.append(f"    lv_obj_set_style_arc_width({s}, 1, LV_PART_MAIN);   /* para que se vean las secciones */")
                        out.append(f"    lv_obj_set_style_arc_opa({s}, LV_OPA_TRANSP, LV_PART_MAIN);")
                    else:
                        c = self.color(d.get("color_start"))
                        if c:
                            out.append(f"    lv_style_set_line_color(&{st}, {c});")
                        if "width" in d:
                            out.append(f"    lv_style_set_line_width(&{st}, {int(mt.num(d.get('width'), 2))});")
                        part = "LV_PART_ITEMS"
                        if d.get("color_end") not in (None, d.get("color_start")):
                            self.warnings.append(f"{w.id}: el degradado de color de las marcas (color_start → color_end) "
                                                 "no existe en lv_scale; se usa color_start")
                    out.append(f"    {sec} = lv_scale_add_section({s});")
                    out.append(f"    lv_scale_section_set_range({sec}, {int(mt.num(d.get('start_value'), g.range_from))}, "
                               f"{int(mt.num(d.get('end_value'), g.range_to))});")
                    out.append(f"    lv_scale_section_set_style({sec}, {part}, &{st});")
                    if kind == "tick_style":
                        out.append(f"    lv_scale_section_set_style({sec}, LV_PART_INDICATOR, &{st});")

    def widget(self, w: Widget, parent: str, out: list[str], parent_widget: Widget | None = None,
               index: int = 0) -> None:
        o = self.var(w)
        if w.auto_id:
            self.globals.append(f"static lv_obj_t * {o};")
        else:
            self.public.append(o)
        label = catalog.type_label(w.type)
        out.append(f"    /* {label}: {w.id if not w.auto_id else '(sin id)'} */")
        if w.type == "tab" and parent_widget is not None:
            out.append(f"    {o} = lv_tabview_add_tab({parent}, {c_str(w.props.get('name', w.id))});")
        elif w.type == "tile" and parent_widget is not None:
            dc = self.dirs(w, w.props.get("dir"), TILE_DIRS, "ALL")
            out.append(f"    {o} = lv_tileview_add_tile({parent}, {int(_num(w.props.get('column')) or 0)}, "
                       f"{int(_num(w.props.get('row')) or 0)}, {dc});")
        else:
            fn = CREATE.get(w.type)
            if fn is None:
                fn = "lv_obj_create"
                self.warnings.append(f"{w.id}: el tipo «{w.type}» no existe en LVGL 9; se crea un lv_obj")
            out.append(f"    {o} = {fn}({parent});")
        self.geometry(w, o, out)
        self.specific(w, o, out)
        skip = set(HANDLED) | set(FLAGS)
        if w.type == "button" and "text" in w.props:
            skip |= {"text_color", "text_font"}
        for var, sel in self.theme_styles.get(w.type, []):
            out.append(f"    lv_obj_add_style({o}, &{var}, {sel});")
        for sid in (w.props.get("styles") if isinstance(w.props.get("styles"), list)
                    else [w.props.get("styles")] if isinstance(w.props.get("styles"), str) else []):
            for var, sel in self.style_defs.get(sid, []):
                out.append(f"    lv_obj_add_style({o}, &{var}, {sel});")
        self.style_calls(o, w.props, "LV_PART_MAIN | LV_STATE_DEFAULT", out, is_style=False, skip=skip)
        for k, v in w.props.items():
            if k in skip or k in STYLE or (isinstance(v, dict) and (k in catalog.STATES or k in PART_C)):
                continue
            if k.startswith("on_"):
                self.warnings.append(f"{w.id}: el evento {k} con opciones de ESPHome no se traduce")
                out.append(f"    /* {k}: evento con opciones de ESPHome — no traducido */")
                continue
            out.append(f"    /* {k}: {c_comment(v)[:160]} — no traducido */")
        self.flags_and_state(w, o, out)
        self.layout(w, o, out)
        if w.props.get("flex_grow") is not None and _num(w.props.get("flex_grow")) is not None:
            out.append(f"    lv_obj_set_flex_grow({o}, {int(_num(w.props['flex_grow']))});")
        merged: dict[str, list[Action]] = {}
        for ev in w.events:                      # mismo disparador dos veces → una sola función
            merged.setdefault(ev.trigger, []).extend(ev.actions)
        for trigger, actions in merged.items():
            self.event(w.id, o, trigger, actions, out)
        for i, c in enumerate(w.children):
            self.widget(c, o, out, w, i)

    def dirs(self, w: Widget, value: Any, valid: tuple[str, ...], default: str) -> str:
        """Direcciones de LVGL a partir de texto libre («LEFT | RIGHT», [TOP, BOTTOM]…)."""
        items = value if isinstance(value, list) else re.split(r"[|,\s]+", str(value or ""))
        names = [str(x).strip().upper() for x in items if str(x).strip()]
        good = [n for n in names if n in valid]
        bad = [n for n in names if n not in valid]
        if bad:
            self.warnings.append(f"{w.id}: dirección no válida {', '.join(bad)} (se usa {', '.join(good) or default})")
        return " | ".join(f"LV_DIR_{n}" for n in (good or [default]))

    # ----------------------------------------------------------------- eventos
    def event(self, wid: str, o: str, trigger: str, actions: list[Action], out: list[str]) -> None:
        code = EVENT_C.get(trigger)
        if code is None:
            out.append(f"    /* {trigger}: evento sin equivalente en LVGL */")
            return
        fn = f"ui_ev_{re.sub(r'[^A-Za-z0-9_]', '_', wid)}_{trigger}"
        lines = [f"static void {fn}(lv_event_t * e)", "{", "    LV_UNUSED(e);"]
        if trigger in SWIPE_DIR:
            lines.append(f"    if(lv_indev_get_gesture_dir(lv_indev_active()) != {SWIPE_DIR[trigger]}) return;")
        for i, a in enumerate(actions):
            lines += self.action(wid, trigger, i, a)
        lines.append("}")
        self.events.append("\n".join(lines))
        out.append(f"    lv_obj_add_event_cb({o}, {fn}, {code}, NULL);")

    def action(self, wid: str, trigger: str, index: int, a: Action) -> list[str]:
        p = a.params
        desc = c_comment(catalog.describe_action(a.kind, p))
        if a.kind == "page_show":
            s = self.p.screen(str(p.get("page")))
            if s is not None and s.id != TOP_LAYER_ID:
                return [f"    lv_screen_load({self.screen_var(s)});"]
        if a.kind in ("page_next", "page_prev"):
            return [f"    ui_page_step({1 if a.kind == 'page_next' else -1});"]
        if a.kind == "widget_state":
            target = self.p.widget(str(p.get("id")))
            if target is not None:
                t = self.var(target)
                return {"show": [f"    ui_set_flag({t}, LV_OBJ_FLAG_HIDDEN, false);"],
                        "hide": [f"    ui_set_flag({t}, LV_OBJ_FLAG_HIDDEN, true);"],
                        "enable": [f"    lv_obj_remove_state({t}, LV_STATE_DISABLED);"],
                        "disable": [f"    lv_obj_add_state({t}, LV_STATE_DISABLED);"]}.get(
                            str(p.get("op")), [f"    /* {desc} */"])
        if a.kind == "widget_update":
            target = self.p.widget(str(p.get("id")))
            if target is not None:
                t = self.var(target)
                lines: list[str] = []
                props = dict(p.get("props") or {})
                if "text" in props and target.type in ("label", "checkbox", "textarea"):
                    txt = props.pop("text")
                    fn = {"label": "lv_label_set_text", "checkbox": "lv_checkbox_set_text",
                          "textarea": "lv_textarea_set_text"}[target.type]
                    if isinstance(txt, str):
                        lines.append(f"    {fn}({t}, {c_str(txt)});")
                    else:
                        lines.append(f"    /* text: {c_comment(txt)} — ESPHome */")
                if "value" in props and target.type in ("arc", "bar", "slider", "spinbox"):
                    n = _num(props.pop("value"))
                    if n is not None:
                        anim = ", LV_ANIM_OFF" if target.type in ("bar", "slider") else ""
                        lines.append(f"    lv_{target.type}_set_value({t}, {int(n)}{anim});")
                if "hidden" in props:
                    hv = props.pop("hidden")
                    if isinstance(hv, bool):
                        lines.append(f"    ui_set_flag({t}, LV_OBJ_FLAG_HIDDEN, {'true' if hv else 'false'});")
                self.style_calls(t, props, "LV_PART_MAIN | LV_STATE_DEFAULT", lines, is_style=False)
                return lines
        # lo demás sólo existe en ESPHome: se delega en el programa principal
        return [f"    /* {desc} */",
                f"    if(ui_action_handler) ui_action_handler({c_str(wid)}, {c_str(trigger)}, {index}, {c_str(desc)});"]

    # ----------------------------------------------------------------- pantallas
    def screen(self, s: Screen) -> None:
        top = s.id == TOP_LAYER_ID
        sv = self.screen_var(s)
        fn = "ui_top_layer_create" if top else f"ui_{re.sub(r'[^A-Za-z0-9_]', '_', s.id)}_create"
        out: list[str] = [f"static void {fn}(void)", "{"]
        if not top:
            self.public.append(sv)
            out.append(f"    {sv} = lv_obj_create(NULL);")
            base = {k: v for k, v in self.p.lvgl_extra.items() if k in STYLE}
            if isinstance(self.p.lvgl_extra.get("default_font"), str):
                base["text_font"] = self.p.lvgl_extra["default_font"]
            theme = self.p.lvgl_extra.get("theme")
            if isinstance(theme, dict) and isinstance(theme.get("page"), dict):
                base.update({k: v for k, v in theme["page"].items() if k in STYLE})
            if s.bg_color:
                base["bg_color"] = s.bg_color
            base.update({k: v for k, v in s.props.items() if k in STYLE or
                         (isinstance(v, dict) and (k in catalog.STATES or k in PART_C))})
            self.style_calls(sv, base, "LV_PART_MAIN | LV_STATE_DEFAULT", out, is_style=False)
            for sid in (s.props.get("styles") if isinstance(s.props.get("styles"), list)
                        else [s.props.get("styles")] if isinstance(s.props.get("styles"), str) else []):
                for var, sel in self.style_defs.get(sid, []):
                    out.append(f"    lv_obj_add_style({sv}, &{var}, {sel});")
            if s.props.get("scrollable") is False:
                out.append(f"    ui_set_flag({sv}, LV_OBJ_FLAG_SCROLLABLE, false);")
            self.layout(s, sv, out)
            for k in ("on_load", "on_unload"):
                v = s.props.get(k)
                if isinstance(v, list):
                    acts = [Action("logger", {"message": c_comment(x)}) for x in v]
                    out.append(f"    /* {k}: acciones de ESPHome */")
                    self.event(s.id, sv, k, acts, out)
        for w in s.widgets:
            self.widget(w, sv, out)
        out.append("}")
        self.body.append("\n".join(out))

    # ----------------------------------------------------------------- documento
    def generate(self) -> Out:
        theme = self.p.lvgl_extra.get("theme")
        if isinstance(theme, dict):
            for wtype, props in theme.items():
                if isinstance(props, dict) and wtype != "page":
                    reg: list[tuple[str, str]] = []
                    self.build_style(f"ui_theme_{re.sub(r'[^A-Za-z0-9_]', '_', wtype)}", props, reg)
                    self.theme_styles[wtype] = reg
        for st in self.p.styles:
            reg = []
            self.build_style(f"ui_style_{re.sub(r'[^A-Za-z0-9_]', '_', st.id)}", st.props, reg)
            self.style_defs[st.id] = reg
        for s in self.p.screens:
            self.screen(s)
        has_top = self.p.top_layer is not None and self.p.top_layer.widgets
        if has_top:
            self.screen(self.p.top_layer)
        screens = [self.screen_var(s) for s in self.p.screens]
        guard = "OLVGL_UI_H"
        name = self.p.name
        hdr = [f"/* Generado por Open LVGL Studio {__version__} — proyecto «{c_comment(name)}» "
               f"({self.p.display.width}x{self.p.display.height}). */",
               f"#ifndef {guard}", f"#define {guard}", "", "#include \"lvgl.h\"", "",
               "#ifdef __cplusplus", "extern \"C\" {", "#endif", "",
               "/* Acciones que sólo existen en ESPHome (Home Assistant, scripts, lambdas…):",
               " * asigna esta función para atenderlas desde tu programa. */",
               "typedef void (*ui_action_cb_t)(const char * widget, const char * event, int index,",
               "                               const char * description);",
               "extern ui_action_cb_t ui_action_handler;", "",
               "/* Crea todas las pantallas y carga la primera. */",
               "void ui_init(void);", ""]
        hdr += [f"extern lv_obj_t * {v};" for v in self.public]
        hdr += ["", "#ifdef __cplusplus", "}", "#endif", "", f"#endif /* {guard} */", ""]

        src = [f"/* Generado por Open LVGL Studio {__version__}. No lo edites a mano: se regenera. */",
               "#include \"ui.h\"", ""]
        if self.fonts:
            src.append("/* Activa en lv_conf.h: " + ", ".join(f"LV_FONT_MONTSERRAT_{n}" for n in sorted(self.fonts))
                       + " */")
        if self.custom_fonts:
            src.append("/* Fuentes propias: conviértelas con lv_font_conv (https://lvgl.io/tools/fontconverter) */")
            src += [f"extern const lv_font_t {f};" for f in sorted(self.custom_fonts)]
        if self.images:
            src.append("/* Imágenes: conviértelas con https://lvgl.io/tools/imageconverter */")
            src += [f"LV_IMAGE_DECLARE({i});" for i in sorted(self.images)]
        src += ["", "#if LVGL_VERSION_MAJOR != 9 || LVGL_VERSION_MINOR < 5",
                "#error \"ui.c necesita LVGL 9.5 o superior (la versión de ESPHome)\"",
                "#endif", "",
                "ui_action_cb_t ui_action_handler = NULL;", "",
                "/* LVGL 9.6 cambió las funciones de flags por un setter por flag. */",
                "static void ui_set_flag(lv_obj_t * o, lv_obj_flag_t f, bool on)", "{",
                "#if LVGL_VERSION_MINOR >= 6",
                "    switch(f) {"]
        src += [f"        case {flag}: lv_obj_set_{name}(o, on); break;" for name, flag in FLAG_SETTERS]
        src += ["        default: break;",
                "    }",
                "#else",
                "    if(on) lv_obj_add_flag(o, f);",
                "    else lv_obj_remove_flag(o, f);",
                "#endif",
                "}", ""]
        src += [f"lv_obj_t * {v};" for v in self.public]
        src += self.globals + [""] + self.statics + [""]
        src += [f"static lv_obj_t ** const ui_screens[] = {{{', '.join('&' + s for s in screens)}}};",
                f"static const uint32_t ui_screen_count = {len(screens)};", "",
                "static void ui_page_step(int delta)", "{",
                "    lv_obj_t * cur = lv_screen_active();",
                "    for(uint32_t i = 0; i < ui_screen_count; i++) {",
                "        if(*ui_screens[i] == cur) {",
                "            uint32_t n = (uint32_t)((int)i + delta + (int)ui_screen_count) % ui_screen_count;",
                "            lv_screen_load(*ui_screens[n]);",
                "            return;",
                "        }",
                "    }",
                "}", ""]
        src += self.events + [""] if self.events else []
        src += ["static void ui_styles_init(void)", "{"] + (self.styles or ["    /* sin estilos */"]) + ["}", ""]
        src += self.body + [""]
        src += ["void ui_init(void)", "{", "    ui_styles_init();"]
        src += [f"    ui_{re.sub(r'[^A-Za-z0-9_]', '_', s.id)}_create();" for s in self.p.screens]
        if has_top:
            src.append("    ui_top_layer_create();")
        src += self.deferred
        if screens:
            src.append(f"    lv_screen_load({screens[0]});")
        src += ["}", ""]
        return Out("\n".join(hdr), "\n".join(src), self.warnings,
                   [f"LV_FONT_MONTSERRAT_{n}" for n in sorted(self.fonts)],
                   sorted(self.custom_fonts), sorted(self.images))


def generate_c(project: Project) -> Out:
    from olvgl.domain.extensions import expand_project
    warnings: list[str] = []
    out = CGenerator(expand_project(project, warnings)).generate()
    out.warnings[:0] = warnings
    return out


def export_c(project: Project, out_dir: str) -> tuple[list[str], Out]:
    from olvgl.infrastructure.json_store import atomic_write_text
    res = generate_c(project)
    os.makedirs(out_dir, exist_ok=True)
    written = []
    for name, text in (("ui.h", res.header), ("ui.c", res.source)):
        path = os.path.join(out_dir, name)
        atomic_write_text(path, text)
        written.append(path)
    return written, res
