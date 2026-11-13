"""Modelo interno de Open LVGL Studio.

Es la representación semántica central: el canvas la edita, los generadores la
leen y (a partir de la Fase 2) los parsers la producen. Se serializa a JSON.
"""
from __future__ import annotations

import copy
import re
from dataclasses import dataclass, field
from typing import Any, Iterator

FORMAT_NAME = "open-lvgl-studio"
SCHEMA_VERSION = 2

_ID_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_COLOR_RE = re.compile(r"^#[0-9A-Fa-f]{6}$")

# Palabras que no pueden usarse como id en ESPHome/C.
_RESERVED_IDS = {
    "lvgl", "image", "font", "display", "id", "auto", "break", "case", "char",
    "const", "continue", "default", "do", "double", "else", "enum", "extern",
    "float", "for", "goto", "if", "int", "long", "register", "return", "short",
    "signed", "sizeof", "static", "struct", "switch", "typedef", "union",
    "unsigned", "void", "volatile", "while", "true", "false", "null",
}


# --------------------------------------------------------------------------- utilidades
def is_valid_id(value: str) -> bool:
    return bool(value) and bool(_ID_RE.match(value)) and value.lower() not in _RESERVED_IDS


def sanitize_id(value: str, fallback: str = "obj") -> str:
    """Convierte un texto libre en un identificador C válido."""
    replacements = str.maketrans("áéíóúüñÁÉÍÓÚÜÑçÇ", "aeiouunAEIOUUNcC")
    s = (value or "").translate(replacements).strip().lower()
    s = re.sub(r"[^A-Za-z0-9_]+", "_", s).strip("_")
    if not s:
        s = fallback
    if s[0].isdigit():
        s = f"{fallback}_{s}"
    if s.lower() in _RESERVED_IDS:
        s = f"{s}_{fallback}"
    return s


def unique_id(base: str, existing: set[str] | frozenset[str]) -> str:
    base = sanitize_id(base)
    if base not in existing:
        return base
    m = re.match(r"^(.*?)(?:_(\d+))?$", base)
    stem = m.group(1) if m else base
    n = int(m.group(2)) + 1 if m and m.group(2) else 1
    while f"{stem}_{n}" in existing:
        n += 1
    return f"{stem}_{n}"


def is_valid_color(value: Any) -> bool:
    return isinstance(value, str) and bool(_COLOR_RE.match(value))


def normalize_color(value: Any) -> str:
    """Acepta '#rgb', '#rrggbb', '0xRRGGBB' o un entero y devuelve '#RRGGBB'."""
    if isinstance(value, int):
        return f"#{value & 0xFFFFFF:06X}"
    s = str(value).strip()
    if s.lower().startswith("0x"):
        return f"#{int(s, 16) & 0xFFFFFF:06X}"
    if s.startswith("#"):
        s = s[1:]
    if len(s) == 3:
        s = "".join(c * 2 for c in s)
    if len(s) != 6 or not re.fullmatch(r"[0-9A-Fa-f]{6}", s):
        raise ValueError(f"Color no válido: {value!r}")
    return f"#{s.upper()}"


def color_to_int(value: str) -> int:
    return int(normalize_color(value)[1:], 16)


# --------------------------------------------------------------------------- entidades
TOP_LAYER_ID = "top_layer"


@dataclass
class Action:
    kind: str
    params: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {"kind": self.kind, "params": copy.deepcopy(self.params)}

    @classmethod
    def from_dict(cls, d: dict) -> "Action":
        return cls(kind=str(d.get("kind", "logger")), params=copy.deepcopy(d.get("params", {})))


@dataclass
class EventHandler:
    trigger: str
    actions: list[Action] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {"trigger": self.trigger, "actions": [a.to_dict() for a in self.actions]}

    @classmethod
    def from_dict(cls, d: dict) -> "EventHandler":
        return cls(
            trigger=str(d.get("trigger", "on_click")),
            actions=[Action.from_dict(a) for a in d.get("actions", [])],
        )


# Geometría tal como se escribe en ESPHome: entero (px), "50%", "SIZE_CONTENT"
# o None (no indicada: LVGL usa su valor por defecto).
Geom = Any


@dataclass
class Widget:
    id: str
    type: str
    x: Geom = 0
    y: Geom = 0
    width: Geom = 100
    height: Geom = 40
    props: dict[str, Any] = field(default_factory=dict)
    events: list[EventHandler] = field(default_factory=list)
    children: list["Widget"] = field(default_factory=list)
    auto_id: bool = False   # id inventado al importar: no se escribe en el YAML

    def walk(self) -> Iterator["Widget"]:
        yield self
        for c in self.children:
            yield from c.walk()

    def to_dict(self) -> dict:
        d = {
            "id": self.id,
            "type": self.type,
            "x": self.x,
            "y": self.y,
            "width": self.width,
            "height": self.height,
            "props": copy.deepcopy(self.props),
            "events": [e.to_dict() for e in self.events],
            "children": [c.to_dict() for c in self.children],
        }
        if self.auto_id:
            d["auto_id"] = True
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "Widget":
        return cls(
            id=str(d["id"]),
            type=str(d["type"]),
            x=d.get("x", 0),
            y=d.get("y", 0),
            width=d.get("width", 100),
            height=d.get("height", 40),
            props=copy.deepcopy(d.get("props", {})),
            events=[EventHandler.from_dict(e) for e in d.get("events", [])],
            children=[Widget.from_dict(c) for c in d.get("children", [])],
            auto_id=bool(d.get("auto_id", False)),
        )

    def clone(self) -> "Widget":
        return Widget.from_dict(self.to_dict())


@dataclass
class Screen:
    id: str
    name: str = ""
    bg_color: str | None = None
    widgets: list[Widget] = field(default_factory=list)
    props: dict[str, Any] = field(default_factory=dict)   # resto de claves de la página

    def walk(self) -> Iterator[Widget]:
        for w in self.widgets:
            yield from w.walk()

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "bg_color": self.bg_color,
            "props": copy.deepcopy(self.props),
            "widgets": [w.to_dict() for w in self.widgets],
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Screen":
        bg = d.get("bg_color")
        return cls(
            id=str(d["id"]),
            name=str(d.get("name") or d["id"]),
            bg_color=normalize_color(bg) if bg else None,
            widgets=[Widget.from_dict(w) for w in d.get("widgets", [])],
            props=copy.deepcopy(d.get("props", {})),
        )


@dataclass
class ImageResource:
    id: str
    path: str
    type: str | None = "RGB565"
    transparency: str | None = "alpha_channel"
    extra: dict[str, Any] = field(default_factory=dict)   # resize, byte_order…

    def to_dict(self) -> dict:
        return {"id": self.id, "path": self.path, "type": self.type,
                "transparency": self.transparency, "extra": copy.deepcopy(self.extra)}

    @classmethod
    def from_dict(cls, d: dict) -> "ImageResource":
        return cls(
            id=str(d["id"]),
            path=str(d.get("path", "")),
            type=d.get("type", "RGB565"),
            transparency=d.get("transparency", "alpha_channel"),
            extra=copy.deepcopy(d.get("extra", {})),
        )


@dataclass
class FontResource:
    """Fuente ESPHome (`font:`); `data` guarda la entrada completa salvo el id."""
    id: str
    data: dict[str, Any] = field(default_factory=dict)

    @property
    def size(self) -> int:
        try:
            return int(self.data.get("size", 20))
        except (TypeError, ValueError):
            return 20

    @property
    def file(self) -> Any:
        return self.data.get("file")

    def to_dict(self) -> dict:
        return {"id": self.id, "data": copy.deepcopy(self.data)}

    @classmethod
    def from_dict(cls, d: dict) -> "FontResource":
        return cls(id=str(d["id"]), data=copy.deepcopy(d.get("data", {})))


@dataclass
class StyleDef:
    """Estilo reutilizable (`lvgl: style_definitions:`)."""
    id: str
    props: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {"id": self.id, "props": copy.deepcopy(self.props)}

    @classmethod
    def from_dict(cls, d: dict) -> "StyleDef":
        return cls(id=str(d["id"]), props=copy.deepcopy(d.get("props", {})))


@dataclass
class DisplayProfile:
    name: str = "Personalizada"
    width: int = 800
    height: int = 480

    def to_dict(self) -> dict:
        return {"name": self.name, "width": self.width, "height": self.height}

    @classmethod
    def from_dict(cls, d: dict) -> "DisplayProfile":
        return cls(name=str(d.get("name", "Personalizada")), width=int(d.get("width", 800)),
                   height=int(d.get("height", 480)))


DISPLAY_PRESETS: list[DisplayProfile] = [
    DisplayProfile("Waveshare ESP32-S3-Touch-LCD-7B", 1024, 600),
    DisplayProfile("Waveshare ESP32-S3-Touch-LCD-7", 800, 480),
    DisplayProfile("Waveshare ESP32-S3-Touch-LCD-4.3", 800, 480),
    DisplayProfile("Sunton ESP32-8048S070 (7\")", 800, 480),
    DisplayProfile("Guition ESP32-S3-4848S040 (4\")", 480, 480),
    DisplayProfile("Sunton ESP32-4827S043 (4.3\")", 480, 272),
    DisplayProfile("ESP32-2432S028 CYD (2.8\")", 320, 240),
    DisplayProfile("LilyGO T-Display S3", 320, 170),
]


@dataclass
class EsphomeSettings:
    device_name: str = "panel-lvgl"
    lvgl_version: int = 9

    def to_dict(self) -> dict:
        return {"device_name": self.device_name, "lvgl_version": self.lvgl_version}

    @classmethod
    def from_dict(cls, d: dict) -> "EsphomeSettings":
        return cls(device_name=str(d.get("device_name", "panel-lvgl")),
                   lvgl_version=int(d.get("lvgl_version", 9)))


@dataclass
class Location:
    screen: Screen
    parent: Widget | None
    container: list[Widget]
    index: int
    widget: Widget


@dataclass
class Project:
    name: str = "Nuevo proyecto"
    display: DisplayProfile = field(default_factory=DisplayProfile)
    screens: list[Screen] = field(default_factory=list)
    images: list[ImageResource] = field(default_factory=list)
    esphome: EsphomeSettings = field(default_factory=EsphomeSettings)
    fonts: list[FontResource] = field(default_factory=list)
    styles: list[StyleDef] = field(default_factory=list)
    top_layer: Screen | None = None
    lvgl_extra: dict[str, Any] = field(default_factory=dict)       # resto de claves de lvgl:
    extra_sections: dict[str, Any] = field(default_factory=dict)   # color:, etc.
    source: dict[str, Any] = field(default_factory=dict)           # origen de la importación

    # ---------------------------------------------------------------- consultas
    def all_screens(self) -> list[Screen]:
        return self.screens + ([self.top_layer] if self.top_layer is not None else [])

    def screen(self, screen_id: str) -> Screen | None:
        return next((s for s in self.all_screens() if s.id == screen_id), None)

    def image(self, image_id: str) -> ImageResource | None:
        return next((i for i in self.images if i.id == image_id), None)

    def font(self, font_id: str) -> FontResource | None:
        return next((f for f in self.fonts if f.id == font_id), None)

    def style(self, style_id: str) -> StyleDef | None:
        return next((s for s in self.styles if s.id == style_id), None)

    def iter_widgets(self) -> Iterator[tuple[Screen, Widget]]:
        for s in self.all_screens():
            for w in s.walk():
                yield s, w

    def locate(self, widget_id: str) -> Location | None:
        def search(screen: Screen, parent: Widget | None, lst: list[Widget]) -> Location | None:
            for i, w in enumerate(lst):
                if w.id == widget_id:
                    return Location(screen, parent, lst, i, w)
                found = search(screen, w, w.children)
                if found:
                    return found
            return None

        for s in self.all_screens():
            found = search(s, None, s.widgets)
            if found:
                return found
        return None

    def find_widget(self, widget_id: str) -> tuple[Screen, list[Widget], Widget] | None:
        loc = self.locate(widget_id)
        return (loc.screen, loc.container, loc.widget) if loc else None

    def widget(self, widget_id: str) -> Widget | None:
        loc = self.locate(widget_id)
        return loc.widget if loc else None

    def container(self, screen_id: str, parent_id: str | None) -> list[Widget]:
        if parent_id:
            w = self.widget(parent_id)
            if w is None:
                raise KeyError(parent_id)
            return w.children
        s = self.screen(screen_id)
        if s is None:
            raise KeyError(screen_id)
        return s.widgets

    def all_ids(self) -> set[str]:
        ids = {s.id for s in self.all_screens()}
        ids |= {i.id for i in self.images}
        ids |= {f.id for f in self.fonts}
        ids |= {s.id for s in self.styles}
        ids |= {w.id for _, w in self.iter_widgets()}
        # Los botones con texto generan un label hijo con id <id>_label
        ids |= {f"{w.id}_label" for _, w in self.iter_widgets() if w.type == "button" and "text" in w.props}
        return ids

    def validate(self) -> list[str]:
        """Lista de problemas encontrados (vacía si el proyecto es correcto)."""
        problems: list[str] = []
        seen: set[str] = set()

        def check(i: str, what: str, auto: bool = False) -> None:
            if not auto and not is_valid_id(i):
                problems.append(f"{what} '{i}': id no válido")
            if i in seen:
                problems.append(f"{what} '{i}': id duplicado")
            seen.add(i)

        for s in self.all_screens():
            check(s.id, "Pantalla")
        for img in self.images:
            check(img.id, "Imagen")
        for f in self.fonts:
            check(f.id, "Fuente")
        for st in self.styles:
            check(st.id, "Estilo")
        screen_ids = {s.id for s in self.screens}
        widget_ids = {w.id for _s, w in self.iter_widgets()}
        for _, w in self.iter_widgets():
            check(w.id, "Widget", w.auto_id)
            if w.type == "image":
                src = w.props.get("src")
                if isinstance(src, str) and src and not self.image(src):
                    problems.append(f"Widget '{w.id}': la imagen '{src}' no existe")
            lo, hi = w.props.get("min_value"), w.props.get("max_value")
            if isinstance(lo, (int, float)) and isinstance(hi, (int, float)) and lo >= hi:
                problems.append(f"Widget '{w.id}': el mínimo ({lo}) no es menor que el máximo ({hi})")
            triggers = [ev.trigger for ev in w.events]
            for t in sorted({t for t in triggers if triggers.count(t) > 1}):
                problems.append(f"Widget '{w.id}': el evento {t} está repetido (ESPHome no lo admite)")
            for ev in w.events:
                for a in ev.actions:
                    if a.kind == "page_show" and a.params.get("page") not in screen_ids:
                        problems.append(f"Widget '{w.id}': la página '{a.params.get('page')}' no existe")
                    if a.kind in ("widget_state", "widget_update") and a.params.get("id") not in widget_ids:
                        problems.append(f"Widget '{w.id}': {ev.trigger} usa el widget '{a.params.get('id')}', "
                                        "que no existe")
        if not self.screens:
            problems.append("El proyecto no tiene pantallas")
        return problems

    # ---------------------------------------------------------------- serialización
    def to_dict(self) -> dict:
        return {
            "format": FORMAT_NAME,
            "schema_version": SCHEMA_VERSION,
            "name": self.name,
            "display": self.display.to_dict(),
            "esphome": self.esphome.to_dict(),
            "source": copy.deepcopy(self.source),
            "images": [i.to_dict() for i in self.images],
            "fonts": [f.to_dict() for f in self.fonts],
            "styles": [s.to_dict() for s in self.styles],
            "lvgl_extra": copy.deepcopy(self.lvgl_extra),
            "extra_sections": copy.deepcopy(self.extra_sections),
            "top_layer": self.top_layer.to_dict() if self.top_layer else None,
            "screens": [s.to_dict() for s in self.screens],
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Project":
        d = migrate(d)
        top = d.get("top_layer")
        return cls(
            name=str(d.get("name", "Proyecto")),
            display=DisplayProfile.from_dict(d.get("display", {})),
            screens=[Screen.from_dict(s) for s in d.get("screens", [])],
            images=[ImageResource.from_dict(i) for i in d.get("images", [])],
            esphome=EsphomeSettings.from_dict(d.get("esphome", {})),
            fonts=[FontResource.from_dict(f) for f in d.get("fonts", [])],
            styles=[StyleDef.from_dict(s) for s in d.get("styles", [])],
            top_layer=Screen.from_dict(top) if top else None,
            lvgl_extra=copy.deepcopy(d.get("lvgl_extra", {})),
            extra_sections=copy.deepcopy(d.get("extra_sections", {})),
            source=copy.deepcopy(d.get("source", {})),
        )

    def clone(self) -> "Project":
        return Project.from_dict(self.to_dict())


_V1_TEXT_DEFAULTS = {"label": "Etiqueta", "button": "Botón"}


def migrate(d: dict) -> dict:
    """Migra un diccionario de proyecto a SCHEMA_VERSION."""
    d = copy.deepcopy(d)
    version = int(d.get("schema_version", 1))
    if version > SCHEMA_VERSION:
        raise ValueError(
            f"El proyecto usa el esquema {version}, más nuevo que el soportado ({SCHEMA_VERSION}). "
            "Actualiza Open LVGL Studio."
        )
    if version == 1:
        # v1 → v2: el texto por defecto pasa a guardarse explícitamente, el blanco
        # de página deja de ser explícito y las imágenes toman el tamaño del fichero.
        def fix(w: dict) -> None:
            if w.get("type") in _V1_TEXT_DEFAULTS:
                w.setdefault("props", {}).setdefault("text", _V1_TEXT_DEFAULTS[w["type"]])
            if w.get("type") == "image":
                w["width"] = None
                w["height"] = None
            for c in w.get("children", []):
                fix(c)
        for s in d.get("screens", []):
            if str(s.get("bg_color", "")).upper() == "#FFFFFF":
                s["bg_color"] = None
            for w in s.get("widgets", []):
                fix(w)
        version = 2
    d["schema_version"] = version
    return d


def new_project(name: str = "Nuevo proyecto", display: DisplayProfile | None = None) -> Project:
    p = Project(name=name, display=display or DisplayProfile("Waveshare ESP32-S3-Touch-LCD-7B", 1024, 600))
    p.esphome.device_name = sanitize_id(name, "panel").replace("_", "-")
    p.screens.append(Screen(id="main_page", name="Principal"))
    return p
