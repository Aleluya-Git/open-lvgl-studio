"""Generador ESPHome: Modelo interno → AST YAML → texto.

Produce un *paquete* (`ui_lvgl.yaml`) con `color:`, `font:`, `image:` y `lvgl:`
que se incluye desde el YAML del dispositivo:

    packages:
      ui: !include ui_lvgl.yaml

Escribe todo lo que hay en el modelo (también lo importado y no editable aún),
de forma que importar y volver a generar no pierde información.
"""
from __future__ import annotations

import os
from typing import Any, Callable

from olvgl import __version__
from olvgl.domain import catalog
from olvgl.domain.model import Action, Project, Screen, Widget, color_to_int
from olvgl.domain.values import value_to_node
from olvgl.domain.yaml_ast import HEX, LITERAL, PLAIN, VERBATIM, YMap, YRaw, YScalar, YSeq
from olvgl.infrastructure.yaml_emitter import emit

HEADER = (
    "Generado por Open LVGL Studio {version}\n"
    "Proyecto: {name} ({w}x{h})\n"
    "No edites este fichero a mano: los cambios se perderán al regenerar.\n"
    "Inclúyelo desde el YAML de tu dispositivo con:\n"
    "  packages:\n"
    "    ui: !include ui_lvgl.yaml"
)

GEOMETRY = ("x", "y", "width", "height")
BUTTON_LABEL_PROPS = ("text", "text_color", "text_font")


def image_file_path(path: str) -> str:
    """Ruta con la que se referencia la imagen desde el YAML exportado."""
    return "images/" + os.path.basename(path.replace("\\", "/"))


def is_local_file(path: Any) -> bool:
    return (isinstance(path, str) and bool(path) and "://" not in path
            and not path.startswith(("mdi:", "gfonts:", "${")))


def font_file_path(path: str) -> str:
    return "fonts/" + os.path.basename(path.replace("\\", "/"))


# --------------------------------------------------------------------------- acciones
def action_node(a: Action):
    p = a.params
    if a.kind == "page_show":
        return YMap().set("lvgl.page.show", YScalar(p.get("page", "")))
    if a.kind == "page_next":
        return YMap().set("lvgl.page.next", YScalar(None))
    if a.kind == "page_prev":
        return YMap().set("lvgl.page.previous", YScalar(None))
    if a.kind == "ha_action":
        body = YMap().set("action", YScalar(p.get("action", "")))
        data = YMap()
        if p.get("entity_id"):
            data.set("entity_id", YScalar(p["entity_id"]))
        for k, v in (p.get("data") or {}).items():
            data.set(str(k), YScalar(v))
        if data.items:
            body.set("data", data)
        return YMap().set("homeassistant.action", body)
    if a.kind == "logger":
        return YMap().set("logger.log", YScalar(str(p.get("message", ""))))
    if a.kind == "widget_state":
        return YMap().set(f"lvgl.widget.{p.get('op', 'show')}", YScalar(p.get("id", "")))
    if a.kind == "widget_update":
        body = YMap().set("id", YScalar(p.get("id", "")))
        for k, v in (p.get("props") or {}).items():
            body.set(str(k), value_to_node(v, str(k)))
        return YMap().set(f"lvgl.{p.get('type') or 'widget'}.update", body)
    if a.kind == "delay":
        return YMap().set("delay", YScalar(p.get("duration", "1s")))
    if a.kind == "lambda":
        code = str(p.get("code", ""))
        return YMap().set("lambda", YScalar(code, LITERAL if "\n" in code else PLAIN))
    if a.kind == "call":
        return YMap().set(str(p.get("action", "")), YScalar(p.get("target")))
    if a.kind == "raw":
        return YRaw(p.get("yaml", "") or "")
    raise ValueError(f"Acción desconocida: {a.kind}")


def uses_ha_actions(project: Project) -> bool:
    return any(a.kind == "ha_action"
               for _, w in project.iter_widgets() for ev in w.events for a in ev.actions)


# --------------------------------------------------------------------------- widgets
def _events(m: YMap, w: Widget) -> None:
    for ev in w.events:
        if not ev.actions:
            continue
        m.set(ev.trigger, YSeq([action_node(a) for a in ev.actions]))


def widget_body(w: Widget) -> YMap:
    m = YMap()
    if not w.auto_id:
        m.set("id", w.id)
    for g in GEOMETRY:
        v = getattr(w, g)
        if v is not None:
            m.set(g, value_to_node(v, g))
    is_button_text = w.type == "button" and "text" in w.props
    for k, v in w.props.items():
        if is_button_text and k in BUTTON_LABEL_PROPS:
            continue
        m.set(k, value_to_node(v, k))
    children: list[YMap] = []
    if is_button_text:
        taken = {c.id for c in w.walk()}
        lid, n = f"{w.id}_label", 2
        while lid in taken:                      # ya hay un hijo con ese id
            lid, n = f"{w.id}_label_{n}", n + 1
        lbl = YMap().set("id", lid).set("align", YScalar("CENTER"))
        for k in BUTTON_LABEL_PROPS:
            if k in w.props:
                lbl.set(k, value_to_node(w.props[k], k))
        children.append(YMap().set("label", lbl))
    child_key, child_type = catalog.CHILD_LISTS.get(w.type, ("widgets", None))
    if child_type:
        tabs = YSeq([widget_body(c) for c in w.children])
        if tabs.items:
            m.set(child_key, tabs)
    else:
        children += [widget_node(c) for c in w.children
                     if not (c.type == "image" and not c.props.get("src"))]
        if children:
            m.set("widgets", YSeq(children))
    _events(m, w)
    return m


def widget_node(w: Widget) -> YMap:
    return YMap().set(w.type, widget_body(w))


def page_node(s: Screen) -> YMap:
    m = YMap()
    if s.id != "top_layer":
        m.set("id", s.id)
    if s.bg_color:
        m.set("bg_color", YScalar(color_to_int(s.bg_color), HEX))
    for k, v in s.props.items():
        m.set(k, value_to_node(v, k))
    widgets = YSeq()
    for w in s.widgets:
        if w.type == "image" and not w.props.get("src"):
            continue  # una imagen sin origen no compila en ESPHome
        widgets.append(widget_node(w))
    if widgets.items:
        m.set("widgets", widgets)
    return m


# --------------------------------------------------------------------------- documento
PathMap = Callable[[str], str]


def generate_ast(project: Project, image_path: PathMap = image_file_path,
                 font_path: PathMap = font_file_path) -> YMap:
    from olvgl.domain.extensions import expand_project
    project = expand_project(project)      # widgets de plugins → widgets estándar
    root = YMap()
    for sec, value in project.extra_sections.items():
        root.set(sec, value_to_node(value, sec))

    if project.fonts:
        seq = YSeq()
        from olvgl.domain.fonts import glyphs_for_export, is_icon_font, used_chars
        used = used_chars(project) if any(is_icon_font(f.data) for f in project.fonts) else {}
        for f in project.fonts:
            m = YMap()
            data = dict(f.data)
            glyphs = glyphs_for_export(project, f, used)  # los iconos que usa el proyecto, solos
            if glyphs is not None:
                data["glyphs"] = glyphs
            elif "glyphs" in data and data["glyphs"] in ([], ""):
                data.pop("glyphs")                       # fuente de iconos aún sin iconos
            if "file" in data:
                fv = data.pop("file")
                m.set("file", value_to_node(font_path(fv) if is_local_file(fv) else fv, "file"))
            m.set("id", f.id)
            for k, v in data.items():
                m.set(k, value_to_node(v, k))
            seq.append(m)
        root.set("font", seq)

    used_images = {str(v) for _, w in project.iter_widgets() if w.type == "image"
                   for v in [w.props.get("src")] if isinstance(v, str)}
    used_images |= {str(v) for _, w in project.iter_widgets() for k, v in w.props.items()
                    if k.endswith("src") and isinstance(v, str)}
    images = [i for i in project.images if i.id in used_images or project.source]
    if images:
        seq = YSeq()
        for img in images:
            m = YMap()
            if "file" in img.extra:
                m.set("file", value_to_node(img.extra["file"], "file"))
            elif img.path:
                m.set("file", YScalar(image_path(img.path) if is_local_file(img.path) else img.path))
            # sin file: p. ej. platform: online_image (usa url:)
            m.set("id", img.id)
            if img.type:
                m.set("type", img.type)
            if img.transparency:
                m.set("transparency", img.transparency)
            for k, v in img.extra.items():
                if k != "file":
                    m.set(k, value_to_node(v, k))
            seq.append(m)
        root.set("image", seq)

    lvgl = YMap()
    for k, v in project.lvgl_extra.items():
        lvgl.set(k, value_to_node(v, k))
    if project.styles:
        lvgl.set("style_definitions", YSeq([
            _style_node(s.id, s.props) for s in project.styles]))
    if project.top_layer is not None and (project.top_layer.widgets or project.top_layer.props):
        lvgl.set("top_layer", page_node(project.top_layer))
    pages = YSeq()
    for s in project.screens:
        pages.append(page_node(s))
    lvgl.set("pages", pages)
    root.set("lvgl", lvgl)
    return root


def _style_node(sid: str, props: dict) -> YMap:
    m = YMap().set("id", sid)
    for k, v in props.items():
        m.set(k, value_to_node(v, k))
    return m


def generate_yaml(project: Project, image_path: PathMap = image_file_path,
                  font_path: PathMap = font_file_path) -> str:
    header = HEADER.format(version=__version__, name=project.name,
                           w=project.display.width, h=project.display.height)
    return emit(generate_ast(project, image_path, font_path), header=header)


def generate_main_ast(project: Project) -> YMap:
    """Plantilla de YAML de dispositivo (sólo se escribe si no existe)."""
    root = YMap()
    root.set("esphome", YMap().set("name", project.esphome.device_name)
             .set("friendly_name", project.name))
    root.set("esp32", YMap().set("board", "esp32-s3-devkitc-1")
             .set("framework", YMap().set("type", "esp-idf")))
    root.set("logger", YScalar(None))
    root.set("api", YScalar(None))
    root.set("ota", YSeq([YMap().set("platform", "esphome")]))
    root.set("wifi", YMap()
             .set("ssid", YScalar("!secret wifi_ssid", VERBATIM))
             .set("password", YScalar("!secret wifi_password", VERBATIM)))
    root.set("packages", YMap().set("ui", YScalar("!include ui_lvgl.yaml", VERBATIM)),
             comment=(f"TODO: añade aquí display: y touchscreen: de tu placa "
                      f"({project.display.name}, {project.display.width}x{project.display.height}).\n"
                      "LVGL usa automáticamente el único display y touchscreen definidos."))
    return root


def generate_main_yaml(project: Project) -> str:
    header = (f"YAML de dispositivo para «{project.name}» — plantilla de Open LVGL Studio.\n"
              "Este fichero es tuyo: Open LVGL Studio no lo sobrescribe.")
    if uses_ha_actions(project):
        header += ("\nLos botones llaman a acciones de Home Assistant: en HA, abre la integración\n"
                   "ESPHome → Configurar y activa «Permitir que el dispositivo realice acciones».")
    return emit(generate_main_ast(project), header=header)
