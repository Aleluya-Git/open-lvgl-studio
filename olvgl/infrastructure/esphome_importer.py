"""Importador ESPHome: YAML → AST → modelo interno (ingeniería inversa).

Objetivo: no perder nada. Lo que el editor entiende se convierte a su forma
semántica (páginas, widgets anidados, eventos conocidos, imágenes, fuentes,
estilos, capa superior); el resto se guarda tal cual (propiedades genéricas,
acciones en YAML libre, claves de `lvgl:` y secciones como `color:`) y el
generador lo vuelve a escribir.
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from typing import Any

from olvgl.domain import catalog
from olvgl.domain.model import (TOP_LAYER_ID, Action, DisplayProfile, EventHandler, FontResource,
                                ImageResource, Project, Screen, StyleDef, Widget, parse_rotation)
from olvgl.domain.values import node_to_value
from olvgl.domain.yaml_ast import YMap, YNode, YRaw, YScalar, YSeq
from olvgl.infrastructure.yaml_parser import IncludeLog, load_esphome, parse

GEOMETRY = ("x", "y", "width", "height")
PASSTHROUGH_SECTIONS = ("color",)


@dataclass
class ImportReport:
    path: str = ""
    pages: int = 0
    widgets: int = 0
    images: int = 0
    fonts: int = 0
    styles: int = 0
    top_layer: int = 0
    included: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    generic_types: dict[str, int] = field(default_factory=dict)
    raw_actions: int = 0

    def summary(self) -> str:
        lines = [f"{self.pages} página(s), {self.widgets} widget(s)"
                 + (f", {self.top_layer} en la capa superior" if self.top_layer else ""),
                 f"{self.images} imagen(es), {self.fonts} fuente(s), {self.styles} estilo(s)"]
        if self.generic_types:
            types = ", ".join(f"{t} ×{n}" for t, n in sorted(self.generic_types.items()))
            lines.append(f"Widgets sin editor propio (se conservan y se dibujan de forma básica): {types}")
        if self.raw_actions:
            lines.append(f"{self.raw_actions} acción(es) conservadas como YAML libre")
        if self.included:
            lines.append("Ficheros incluidos: " + ", ".join(os.path.basename(p) for p in self.included))
        return "\n".join(lines)


class ImportError_(Exception):
    pass


class EsphomeImporter:
    def __init__(self, base_dir: str = "", display: DisplayProfile | None = None):
        self.base_dir = base_dir
        self.display = display
        self.report = ImportReport()
        self.ids: set[str] = set()
        self._auto_counter: dict[str, int] = {}

    # ----------------------------------------------------------------- utilidades
    def _new_auto_id(self, wtype: str) -> str:
        base = re.sub(r"[^A-Za-z0-9_]+", "_", wtype).strip("_") or "obj"
        n = self._auto_counter.get(base, 0)
        while True:
            n += 1
            cand = f"_{base}_{n}"
            if cand not in self.ids:
                break
        self._auto_counter[base] = n
        return cand

    @staticmethod
    def _scalar(node: YNode | None) -> Any:
        return node.value if isinstance(node, YScalar) else None

    def _abs_path(self, path: str) -> str:
        if not path or os.path.isabs(path) or "://" in path or path.startswith(("mdi:", "gfonts:", "${")):
            return path
        return os.path.normpath(os.path.join(self.base_dir, path)) if self.base_dir else path

    # ----------------------------------------------------------------- acciones
    def _action(self, node: YNode) -> Action:
        if isinstance(node, YMap) and len(node.items) == 1 and not node.tag:
            key, val = node.items[0].key, node.items[0].value
            if key == "lvgl.page.show" and isinstance(val, YScalar) and not val.tag \
                    and isinstance(val.value, str):
                return Action("page_show", {"page": val.value})
            if key in ("lvgl.page.next", "lvgl.page.previous") and isinstance(val, YScalar) \
                    and val.value is None and not val.tag:
                return Action("page_next" if key.endswith("next") else "page_prev", {})
            if key == "logger.log" and isinstance(val, YScalar) and not val.tag \
                    and isinstance(val.value, str):
                return Action("logger", {"message": val.value})
            if key == "homeassistant.action" and isinstance(val, YMap) and not val.tag:
                keys = set(val.keys())
                action = val.get("action")
                data = val.get("data")
                ok = keys <= {"action", "data"} and isinstance(action, YScalar) \
                    and isinstance(action.value, str) and not action.tag
                if ok and data is not None:
                    ok = isinstance(data, YMap) and not data.tag and all(
                        isinstance(p.value, YScalar) and not p.value.tag
                        and isinstance(p.value.value, (str, int, float, bool)) for p in data.items)
                if ok:
                    params: dict[str, Any] = {"action": action.value}
                    extra = {}
                    if isinstance(data, YMap):
                        for p in data.items:
                            if p.key == "entity_id" and isinstance(p.value.value, str):
                                params["entity_id"] = p.value.value
                            else:
                                extra[p.key] = p.value.value
                    if extra:
                        params["data"] = extra
                    return Action("ha_action", params)
            special = self._lvgl_action(key, val)
            if special is not None:
                return special
        self.report.raw_actions += 1
        return Action("raw", {"yaml": emit_fragment(node)})

    @staticmethod
    def _plain_str(v: YNode) -> bool:
        return isinstance(v, YScalar) and not v.tag and isinstance(v.value, str)

    def _lvgl_action(self, key: str, val: YNode) -> Action | None:
        """Acciones de la Fase 4 (sólo sus formas simples; el resto queda como YAML libre)."""
        m = re.fullmatch(r"lvgl\.widget\.(show|hide|enable|disable)", key)
        if m and self._plain_str(val):
            return Action("widget_state", {"op": m.group(1), "id": val.value})
        m = re.fullmatch(r"lvgl\.([a-z_]+)\.update", key)
        if m and m.group(1) not in ("page",) and isinstance(val, YMap) and not val.tag:
            idn = val.get("id")
            if self._plain_str(idn) and len(val.items) > 1:
                props = {p.key: node_to_value(p.value, p.key) for p in val.items if p.key != "id"}
                return Action("widget_update", {"type": m.group(1), "id": idn.value, "props": props})
        if key == "delay" and isinstance(val, YScalar) and not val.tag and isinstance(val.value, (str, int)):
            return Action("delay", {"duration": val.value})
        if key == "lambda" and self._plain_str(val):
            return Action("lambda", {"code": val.value})
        if re.fullmatch(r"[a-z_][a-z0-9_]*(\.[a-z_][a-z0-9_]*)+", key) and not key.startswith(
                ("homeassistant.", "logger.")) and isinstance(val, YScalar) and not val.tag \
                and (val.value is None or isinstance(val.value, str)):
            return Action("call", {"action": key, "target": val.value})
        return None

    def _event(self, trigger: str, node: YNode) -> EventHandler | None:
        """Devuelve el manejador o None si el disparador debe guardarse tal cual."""
        if isinstance(node, YSeq) and not node.tag:
            return EventHandler(trigger, [self._action(a) for a in node.items])
        if isinstance(node, YMap) and not node.tag:
            if node.keys() == ["then"] and isinstance(node.get("then"), YSeq):
                return EventHandler(trigger, [self._action(a) for a in node.get("then").items])
            if "then" in node:
                return None  # disparador con opciones (p. ej. tiempos): se conserva tal cual
            return EventHandler(trigger, [self._action(node)])
        return None

    # ----------------------------------------------------------------- widgets
    def _widget(self, item: YNode, path: str) -> Widget | None:
        if not isinstance(item, YMap) or len(item.items) != 1:
            self.report.warnings.append(f"{path}: entrada de widget no reconocida, se ignora")
            return None
        wtype = item.items[0].key
        body = item.items[0].value
        if isinstance(body, YScalar) and body.value is None:
            body = YMap()
        if not isinstance(body, YMap):
            self.report.warnings.append(f"{path}: '{wtype}' sin propiedades válidas, se ignora")
            return None
        id_node = body.get("id")
        wid = self._scalar(id_node)
        auto = not isinstance(wid, str) or not wid
        if auto:
            wid = self._new_auto_id(wtype)
        elif wid in self.ids:
            self.report.warnings.append(f"{path}: id '{wid}' repetido; se renombra")
            wid = self._new_auto_id(wid)
            auto = True
        self.ids.add(wid)
        w = Widget(id=wid, type=wtype, x=None, y=None, width=None, height=None, auto_id=auto)
        child_key, child_type = catalog.CHILD_LISTS.get(wtype, ("widgets", None))
        for p in body.items:
            k, v = p.key, p.value
            if k == "id":
                continue
            if k in GEOMETRY:
                setattr(w, k, node_to_value(v, k))
            elif k == child_key and isinstance(v, YSeq):
                for i, ch in enumerate(v.items):
                    if child_type:
                        c = self._pseudo_child(child_type, ch, f"{path}/{wid}/{i}")
                    else:
                        c = self._widget(ch, f"{path}/{wid}/{i}")
                    if c:
                        w.children.append(c)
            elif k.startswith("on_"):
                ev = self._event(k, v)
                if ev is None:
                    w.props[k] = node_to_value(v, k)
                else:
                    w.events.append(ev)
            else:
                w.props[k] = node_to_value(v, k)
        if wtype not in catalog.CATALOG:
            self.report.generic_types[wtype] = self.report.generic_types.get(wtype, 0) + 1
        if wtype == "button":
            self._collapse_button_label(w)
        self.report.widgets += 1
        return w

    def _pseudo_child(self, ptype: str, node: YNode, path: str) -> Widget | None:
        if not isinstance(node, YMap):
            self.report.warnings.append(f"{path}: {ptype} no válido, se ignora")
            return None
        wrapped = YMap().set(ptype, node)
        return self._widget(wrapped, path)

    @staticmethod
    def _collapse_button_label(w: Widget) -> None:
        """Un botón con un único label centrado se edita como 'botón con texto'."""
        if "text" in w.props or len(w.children) != 1:
            return
        lbl = w.children[0]
        allowed = {"text", "text_color", "text_font", "align"}
        if lbl.type != "label" or lbl.children or lbl.events or not set(lbl.props) <= allowed:
            return
        if any(getattr(lbl, g) is not None for g in GEOMETRY):
            return
        if str(lbl.props.get("align", "")).upper() != "CENTER":
            return
        if not isinstance(lbl.props.get("text"), str):
            return
        if not (lbl.auto_id or lbl.id == f"{w.id}_label"):
            return
        for k in ("text", "text_color", "text_font"):
            if k in lbl.props:
                w.props[k] = lbl.props[k]
        w.children = []

    def _screen(self, node: YNode, index: int, sid_default: str) -> Screen | None:
        if not isinstance(node, YMap):
            self.report.warnings.append(f"pages[{index}]: página no válida, se ignora")
            return None
        sid = self._scalar(node.get("id"))
        if not isinstance(sid, str) or not sid:
            sid = sid_default
            n = 1
            while sid in self.ids:
                n += 1
                sid = f"{sid_default}_{n}"
        self.ids.add(sid)
        s = Screen(id=sid, name=sid)
        for p in node.items:
            if p.key == "id":
                continue
            if p.key == "widgets" and isinstance(p.value, YSeq):
                for i, item in enumerate(p.value.items):
                    w = self._widget(item, f"{sid}[{i}]")
                    if w:
                        s.widgets.append(w)
            elif p.key == "bg_color":
                v = node_to_value(p.value, "bg_color")
                if isinstance(v, str) and v.startswith("#"):
                    s.bg_color = v
                else:
                    s.props["bg_color"] = v
            else:
                s.props[p.key] = node_to_value(p.value, p.key)
        return s

    # ----------------------------------------------------------------- recursos
    def _images(self, node: YNode, project: Project) -> None:
        entries: list[tuple[YMap, str | None]] = []
        if isinstance(node, YSeq):
            entries = [(e, None) for e in node.items if isinstance(e, YMap)]
        elif isinstance(node, YMap):  # agrupadas por tipo: image: rgb565: [...]
            for p in node.items:
                if isinstance(p.value, YSeq):
                    entries += [(e, p.key.upper()) for e in p.value.items if isinstance(e, YMap)]
        for e, group_type in entries:
            iid = self._scalar(e.get("id"))
            if not isinstance(iid, str):
                self.report.warnings.append("image: entrada sin id, se ignora")
                continue
            file_v = node_to_value(e.get("file"), "file") if e.get("file") is not None else ""
            path = self._abs_path(file_v) if isinstance(file_v, str) else ""
            img = ImageResource(id=iid, path=path, type=None, transparency=None)
            if not isinstance(file_v, str):
                img.extra["file"] = file_v
            for p in e.items:
                if p.key in ("id", "file"):
                    continue
                if p.key == "type":
                    img.type = str(self._scalar(p.value))
                elif p.key == "transparency":
                    img.transparency = str(self._scalar(p.value))
                else:
                    img.extra[p.key] = node_to_value(p.value, p.key)
            if group_type and not img.type:
                img.type = group_type
            if isinstance(file_v, str) and path and not os.path.exists(path) and "://" not in file_v:
                self.report.warnings.append(f"Imagen '{iid}': no se encuentra {file_v}")
            self.ids.add(iid)
            project.images.append(img)
            self.report.images += 1

    def _fonts(self, node: YNode, project: Project) -> None:
        if not isinstance(node, YSeq):
            return
        for e in node.items:
            if not isinstance(e, YMap):
                continue
            fid = self._scalar(e.get("id"))
            if not isinstance(fid, str):
                self.report.warnings.append("font: entrada sin id, se ignora")
                continue
            data = {p.key: node_to_value(p.value, p.key) for p in e.items if p.key != "id"}
            f = data.get("file")
            if isinstance(f, str) and "://" not in f and not f.startswith(("gfonts:", "mdi:")):
                data["file"] = self._abs_path(f)
            project.fonts.append(FontResource(fid, data))
            self.ids.add(fid)
            self.report.fonts += 1

    # ----------------------------------------------------------------- documento
    def import_root(self, root: YMap, name: str = "Importado") -> Project:
        lvgl = root.get("lvgl")
        if not isinstance(lvgl, YMap):
            raise ImportError_("El fichero no contiene una sección 'lvgl:'")
        project = Project(name=name)
        if self.display:
            project.display = self.display
        esph = root.get("esphome")
        if isinstance(esph, YMap) and isinstance(self._scalar(esph.get("name")), str):
            project.esphome.device_name = self._scalar(esph.get("name"))
            fname = self._scalar(esph.get("friendly_name"))
            if isinstance(fname, str):
                project.name = fname
        if root.get("image") is not None:
            self._images(root.get("image"), project)
        if root.get("font") is not None:
            self._fonts(root.get("font"), project)
        for sec in PASSTHROUGH_SECTIONS:
            if root.get(sec) is not None:
                project.extra_sections[sec] = node_to_value(root.get(sec), sec)
                if isinstance(root.get(sec), YSeq):
                    for e in root.get(sec).items:
                        if isinstance(e, YMap) and isinstance(self._scalar(e.get("id")), str):
                            self.ids.add(self._scalar(e.get("id")))

        for p in lvgl.items:
            if p.key == "style_definitions" and isinstance(p.value, YSeq):
                for e in p.value.items:
                    if isinstance(e, YMap) and isinstance(self._scalar(e.get("id")), str):
                        sid = self._scalar(e.get("id"))
                        project.styles.append(StyleDef(sid, {q.key: node_to_value(q.value, q.key)
                                                             for q in e.items if q.key != "id"}))
                        self.ids.add(sid)
                        self.report.styles += 1

        for p in lvgl.items:
            if p.key == "pages" and isinstance(p.value, YSeq):
                for i, pn in enumerate(p.value.items):
                    s = self._screen(pn, i, f"page_{i + 1}")
                    if s:
                        project.screens.append(s)
            elif p.key == "top_layer" and isinstance(p.value, YMap):
                tl = self._screen(YMap([q for q in p.value.items if q.key != "id"]), 0, TOP_LAYER_ID)
                if tl:
                    tl.id = TOP_LAYER_ID
                    tl.name = "Capa superior"
                    project.top_layer = tl
                    self.report.top_layer = sum(1 for _ in tl.walk())
            elif p.key == "widgets" and isinstance(p.value, YSeq):
                # lvgl: widgets: sin páginas → una página implícita
                s = self._screen(YMap().set("widgets", p.value), 0, "main_page")
                if s:
                    project.screens.insert(0, s)
                    project.source["implicit_page"] = True
            elif p.key in ("style_definitions", "pages"):
                continue                     # pages vacío o no válido: se regenera
            else:
                project.lvgl_extra[p.key] = node_to_value(p.value, p.key)
        if not project.screens:
            project.screens.append(Screen(id="main_page", name="Principal"))
            self.report.warnings.append("No había páginas: se crea una vacía")
        self.report.pages = len(project.screens)
        return project


def emit_fragment(node: YNode) -> str:
    """YAML de un nodo suelto (para acciones en YAML libre)."""
    if isinstance(node, YRaw):
        return node.text
    from olvgl.infrastructure.yaml_emitter import _emit_map, _emit_seq
    if isinstance(node, YMap) and not node.tag:
        return "\n".join(_emit_map(node, 0))
    lines = _emit_seq(YSeq([node]), 0)
    return "\n".join([lines[0][2:]] + [ln[2:] if ln.startswith("  ") else ln for ln in lines[1:]])


def guess_display(root: YMap) -> DisplayProfile | None:
    """Intenta deducir la resolución de la sección display:."""
    disp = root.get("display")
    entries = disp.items if isinstance(disp, YSeq) else [disp] if isinstance(disp, YMap) else []
    for d in entries:
        if not isinstance(d, YMap):
            continue
        dims = d.get("dimensions")
        w = h = None
        if isinstance(dims, YMap):
            w, h = (dims.get("width"), dims.get("height"))
            w = w.value if isinstance(w, YScalar) else None
            h = h.value if isinstance(h, YScalar) else None
        elif isinstance(dims, YScalar) and isinstance(dims.value, str) and "x" in dims.value.lower():
            try:
                w, h = (int(v) for v in dims.value.lower().split("x"))
            except ValueError:
                pass
        if isinstance(w, int) and isinstance(h, int):
            rot = d.get("rotation")
            rv = rot.value if isinstance(rot, YScalar) else 0
            if isinstance(rv, int) and rv in (90, 270):
                w, h = h, w
            lv = root.get("lvgl")                    # lvgl: rotation: (ESPHome 2026.4+)
            lrot = lv.get("rotation") if isinstance(lv, YMap) else None
            if isinstance(lrot, YScalar) and parse_rotation(lrot.value) in (90, 270):
                w, h = h, w
            model = d.get("model")
            name = model.value if isinstance(model, YScalar) and isinstance(model.value, str) else "Importada"
            return DisplayProfile(str(name), w, h)
    return None


_HEADER_RE = re.compile(r"^# Proyecto: (?P<name>.*) \((?P<w>\d+)x(?P<h>\d+)\)\s*$", re.M)


def header_info(text: str) -> tuple[str, DisplayProfile] | None:
    """Nombre y resolución de un fichero generado por Open LVGL Studio (están en la cabecera)."""
    head = text[:600]
    if "Generado por Open LVGL Studio" not in head:
        return None
    m = _HEADER_RE.search(head)
    if not m:
        return None
    return m.group("name"), DisplayProfile("Importada", int(m.group("w")), int(m.group("h")))


def import_esphome_file(path: str, display: DisplayProfile | None = None) -> tuple[Project, ImportReport]:
    root, log = load_esphome(path)
    from olvgl.infrastructure.yaml_parser import read_text
    head = read_text(path)[:600]
    project, report = _import(root, log, path, display, header_info(head))
    if log.from_html:
        project.source["from_html"] = True       # no se vincula: el fichero es una página web
    return project, report


def import_esphome_text(text: str, path: str = "", display: DisplayProfile | None = None) -> tuple[Project, ImportReport]:
    root = parse(text, path)
    if not isinstance(root, YMap):
        raise ImportError_("El documento no es un mapa YAML")
    return _import(root, IncludeLog(), path, display, header_info(text))


def _import(root: YMap, log: IncludeLog, path: str, display: DisplayProfile | None,
            header: tuple[str, DisplayProfile] | None = None) -> tuple[Project, ImportReport]:
    base = os.path.dirname(os.path.abspath(path)) if path else ""
    display = display or guess_display(root) or (header[1] if header else None)
    imp = EsphomeImporter(base, display)
    name = os.path.splitext(os.path.basename(path))[0] if path else "Importado"
    project = imp.import_root(root, name)
    if header and root.get("esphome") is None:
        project.name = header[0]
    if display is None:
        imp.report.warnings.append(
            f"No se pudo deducir la resolución de la pantalla; se usa "
            f"{project.display.width}×{project.display.height} (cámbiala en Propiedades del proyecto)")
    project.source.update({"path": os.path.abspath(path) if path else "", "kind": "esphome-yaml"})
    imp.report.path = path
    imp.report.included = log.included
    imp.report.warnings = log.warnings + imp.report.warnings
    return project, imp.report
