"""Refactorizaciones deterministas del proyecto (sin IA).

- `extract_styles`: propiedades de estilo repetidas en varios widgets se
  convierten en una definición de estilo (`style_definitions`) aplicada a
  todos ellos. El aspecto no cambia: un estilo tiene prioridad sobre el tema y
  las propiedades propias que no se mueven siguen mandando.
- `descriptive_ids`: ids automáticos (`btn_3`, `lbl_12`…) pasan a nombres
  según su texto o su contenido (`btn_salon`, `lbl_temperatura`), y se
  actualizan **todas** las referencias: acciones, `textarea`, `align_to` y
  `id(...)` dentro de lambdas y YAML libre.
- `rename_references`: la base de la anterior, reutilizable.

Todas devuelven un proyecto nuevo y un informe; el ViewModel lo aplica como un
único cambio que se puede deshacer.
"""
from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

from olvgl.domain.model import Project, StyleDef, Widget, is_valid_id, sanitize_id, unique_id

STYLE_KEYS = {
    "bg_color", "bg_opa", "bg_grad_color", "bg_grad_dir", "border_color", "border_width", "border_opa",
    "border_side", "radius", "pad_all", "pad_top", "pad_bottom", "pad_left", "pad_right", "pad_row",
    "pad_column", "text_color", "text_font", "text_align", "text_opa", "shadow_color", "shadow_width",
    "shadow_opa", "shadow_ofs_x", "shadow_ofs_y", "shadow_spread", "outline_color", "outline_width",
    "outline_pad", "opa",
}


@dataclass
class RefactorReport:
    changes: list[str] = field(default_factory=list)
    styles_created: list[str] = field(default_factory=list)
    renamed: dict[str, str] = field(default_factory=dict)

    @property
    def changed(self) -> bool:
        return bool(self.changes)


def _freeze(v: Any) -> Any:
    if isinstance(v, dict):
        return tuple(sorted((k, _freeze(x)) for k, x in v.items()))
    if isinstance(v, list):
        return tuple(_freeze(x) for x in v)
    return v


def _style_part(w: Widget) -> dict:
    """Las propiedades de estilo del widget que se pueden mover a un estilo compartido."""
    out = {}
    for k, v in w.props.items():
        # sólo valores simples: los estados (pressed:, checked:…) se quedan en el widget
        if k in STYLE_KEYS and not isinstance(v, (dict, list)):
            out[k] = v
    return out


COLOR_NAMES = {"FFFFFF": "blanco", "000000": "negro"}


def _style_name(wtype: str, props: dict) -> str:
    """Nombre legible: tipo + tamaño de letra + color principal (estilo_label_20_a8a8b8)."""
    parts = [f"estilo_{PREFIX.get(wtype, wtype)}"]
    m = re.match(r"montserrat_(\d+)$", str(props.get("text_font", "")))
    if m:
        parts.append(m.group(1))
    elif props.get("text_font"):
        parts.append(sanitize_id(str(props["text_font"]), "f")[:16])
    for key in ("bg_color", "text_color", "border_color"):
        v = props.get(key)
        if isinstance(v, str) and re.match(r"^(#|0x)[0-9A-Fa-f]{6}$", v):
            hexv = v[-6:].upper()
            parts.append(("fondo_" if key == "bg_color" else "") + COLOR_NAMES.get(hexv, hexv.lower()))
            break
        if isinstance(v, str) and is_valid_id(v):          # color con nombre (color: …)
            parts.append(("fondo_" if key == "bg_color" else "") + v[:16])
            break
    if "radius" in props and len(parts) < 3:
        parts.append(f"r{props['radius']}")
    return sanitize_id("_".join(str(p) for p in parts), "estilo")


def extract_styles(project: Project, min_widgets: int = 3, min_props: int = 2) -> tuple[Project, RefactorReport]:
    p = project.clone()
    rep = RefactorReport()
    groups: dict[tuple, list[Widget]] = defaultdict(list)
    for _s, w in p.iter_widgets():
        if w.props.get("styles"):
            continue                      # ya usa estilos: no se toca
        part = _style_part(w)
        if len(part) >= min_props:
            groups[(w.type, _freeze(part))].append(w)
    existing = p.all_ids() | {s.id for s in p.styles}
    for (wtype, _key), ws in sorted(groups.items(), key=lambda kv: -len(kv[1])):
        if len(ws) < min_widgets:
            continue
        props = _style_part(ws[0])
        sid = unique_id(_style_name(wtype, props), existing)
        existing.add(sid)
        p.styles.append(StyleDef(sid, dict(props)))
        for w in ws:
            for k in props:
                w.props.pop(k, None)
            w.props["styles"] = sid
        rep.styles_created.append(sid)
        rep.changes.append(f"{sid}: {len(props)} propiedades compartidas por {len(ws)} {wtype}")
    return p, rep


# --------------------------------------------------------------------------- referencias
def _replace_in_code(text: str, mapping: dict[str, str]) -> str:
    """`id(x)` en lambdas y, en YAML libre (acciones `raw`), `id: x`,
    `textarea: x` y `lvgl.widget.hide: x` / `lvgl.widget.show: [x, y]`."""
    if not mapping or not any(k in text for k in mapping):
        return text
    names = "|".join(re.escape(k) for k in sorted(mapping, key=len, reverse=True))
    text = re.sub(r"\bid\(\s*(" + names + r")\s*\)", lambda m: f"id({mapping[m.group(1)]})", text)
    if "\n" in text or re.match(r"^\s*[\w.]+\s*:", text):
        text = re.sub(r"(?m)((?:^|[\s{,\[-])(?:id|textarea|tile_id|lvgl\.[\w.]+)\s*:\s*\[?\s*)(" + names + r")\b(?![\w(])",
                      lambda m: m.group(1) + mapping[m.group(2)], text)
        text = re.sub(r"(\[[^\]\n]*?)\b(" + names + r")\b(?=[^\]\n]*\])",
                      lambda m: m.group(1) + mapping[m.group(2)], text) if "[" in text else text
    return text


def _rewrite(value: Any, mapping: dict[str, str]) -> Any:
    """Recorre un valor (props, YAML libre) cambiando ids: claves `id`, `textarea`,
    `align_to.id` y `id(...)` en el código."""
    if isinstance(value, dict):
        out = {}
        for k, v in value.items():
            if k in ("id", "textarea", "tile_id") and isinstance(v, str) and v in mapping:
                out[k] = mapping[v]
            elif (k == "target" and isinstance(v, str) and v in mapping
                  and str(value.get("action", "")).startswith("lvgl.")):
                out[k] = mapping[v]             # acción `call` (lvgl.widget.redraw: x…)
            else:
                out[k] = _rewrite(v, mapping)
        return out
    if isinstance(value, list):
        return [_rewrite(v, mapping) for v in value]
    if isinstance(value, str):
        return _replace_in_code(value, mapping)
    return value


def rename_references(project: Project, mapping: dict[str, str]) -> Project:
    """Renombra widgets según `mapping` (viejo → nuevo) y actualiza las referencias."""
    p = project.clone()
    if not mapping:
        return p
    for _s, w in p.iter_widgets():
        if w.id in mapping:
            w.id = mapping[w.id]
            w.auto_id = False
        w.props = _rewrite(w.props, mapping)
        for ev in w.events:
            for a in ev.actions:
                a.params = _rewrite(a.params, mapping)
    for s in p.all_screens():
        s.props = _rewrite(s.props, mapping)
    p.lvgl_extra = _rewrite(p.lvgl_extra, mapping)
    p.extra_sections = _rewrite(p.extra_sections, mapping)
    return p


_AUTO_RE = re.compile(r"^([a-z]+)_\d+$")
PREFIX = {"button": "btn", "label": "lbl", "switch": "sw", "slider": "sl", "arc": "arc", "checkbox": "chk",
          "dropdown": "dd", "roller": "rol", "bar": "bar", "image": "img", "obj": "panel", "led": "led",
          "textarea": "ta", "spinbox": "spin", "tabview": "tabs", "tab": "tab", "tileview": "tiles", "tile": "tile"}


def _label_text(w: Widget) -> str:
    t = w.props.get("text")
    if isinstance(t, str) and t.strip():
        return t
    for c in w.children:
        t = c.props.get("text")
        if c.type == "label" and isinstance(t, str) and t.strip():
            return t
    name = w.props.get("name")
    return name if isinstance(name, str) else ""


def descriptive_ids(project: Project, only_generic: bool = True) -> tuple[Project, RefactorReport]:
    rep = RefactorReport()
    existing = set(project.all_ids())
    mapping: dict[str, str] = {}
    for _s, w in project.iter_widgets():
        generic = w.auto_id or bool(_AUTO_RE.match(w.id))
        if only_generic and not generic:
            continue
        text = _label_text(w)
        if not text:
            continue
        slug = sanitize_id(text, "x")[:24].strip("_")
        if not slug or slug == "x":
            continue
        base = f"{PREFIX.get(w.type, w.type)}_{slug}"
        if not is_valid_id(base):
            continue
        new = unique_id(base, existing - {w.id})
        if new != w.id:
            existing.discard(w.id)
            existing.add(new)
            mapping[w.id] = new
    p = rename_references(project, mapping)
    rep.renamed = mapping
    rep.changes = [f"{a} → {b}" for a, b in mapping.items()]
    return p, rep
