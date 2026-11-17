"""Catálogo declarativo de widgets LVGL de ESPHome.

Cada widget se describe con un WidgetSpec: sus propiedades editables, sus
valores por defecto (los de LVGL/ESPHome: el generador no escribe una
propiedad que el usuario deja en su valor por defecto) y los eventos que
admite. Añadir un widget = registrar un WidgetSpec, su dibujo y (si hace
falta) su regla de generación. Es el punto de entrada del SDK de plugins
(Fase 7).

Las propiedades pueden tener nombre con puntos para valores anidados de
ESPHome: `state.checked` → `state: {checked: true}`, `indicator.bg_color` →
`indicator: {bg_color: …}`.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

# Tipos de propiedad que entiende el panel de propiedades
KIND_INT = "int"
KIND_STR = "str"
KIND_TEXT = "text"        # texto multilínea
KIND_COLOR = "color"
KIND_BOOL = "bool"
KIND_ENUM = "enum"
KIND_IMAGE = "image"      # referencia a ImageResource.id
KIND_LINES = "lines"      # lista de textos, uno por línea (opciones, puntos)
KIND_WIDGET = "widget"    # referencia al id de otro widget

FONTS = [f"montserrat_{n}" for n in range(8, 50, 2)]
DEFAULT_FONT = "montserrat_14"
TEXT_ALIGN = ["AUTO", "LEFT", "CENTER", "RIGHT"]
LONG_MODES = ["WRAP", "DOT", "SCROLL", "SCROLL_CIRCULAR", "CLIP"]
OPA_OPTIONS = ["COVER", "TRANSP"] + [f"{p}%" for p in range(10, 100, 10)]
DIRECTIONS = ["TOP", "BOTTOM", "LEFT", "RIGHT"]

# Estados y partes de LVGL tal como se escriben en ESPHome
STATES = ("pressed", "checked", "focused", "focus_key", "edited", "hovered", "scrolled",
          "disabled", "user_1", "user_2", "user_3", "user_4")
STATE_LABELS = {"": "Normal", "pressed": "Pulsado", "checked": "Activado", "focused": "Con foco",
                "disabled": "Desactivado", "edited": "Editando", "hovered": "Ratón encima",
                "focus_key": "Foco por teclado", "scrolled": "Desplazándose"}
PARTS = ("main", "scrollbar", "indicator", "knob", "selected", "items", "cursor",
         "textarea_placeholder", "ticks")
PART_LABELS = {"main": "Principal", "indicator": "Indicador", "knob": "Tirador",
               "selected": "Seleccionado", "items": "Elementos", "cursor": "Cursor",
               "scrollbar": "Barra de desplazamiento", "textarea_placeholder": "Texto de ejemplo",
               "ticks": "Marcas"}
GRAD_DIRS = ("NONE", "HOR", "VER")

# Colores aproximados del tema por defecto de LVGL 9 (modo claro)
LV_PRIMARY = "#2196F3"
LV_TEXT = "#212121"
LV_SCREEN_BG = "#FFFFFF"


@dataclass(frozen=True)
class PropSpec:
    name: str
    label: str
    kind: str
    default: Any
    options: tuple[str, ...] = ()
    minimum: int = 0
    maximum: int = 10000
    group: str = "Estilo"
    esphome_key: str | None = None   # None → igual que name

    @property
    def key(self) -> str:
        return self.esphome_key or self.name


@dataclass(frozen=True)
class WidgetSpec:
    type: str
    label: str
    default_size: tuple[int, int]
    props: tuple[PropSpec, ...]
    events: tuple[str, ...] = ()
    resizable: bool = True
    id_prefix: str = "obj"
    description: str = ""
    initial_props: tuple[tuple[str, Any], ...] = ()   # valores al crear un widget nuevo
    known: bool = True                               # False: tipo sin editor propio
    category: str = "Básicos"
    parts: tuple[str, ...] = ("main",)               # partes con estilo propio
    auto_size: bool = False                          # al crearlo, tamaño según contenido
    child_type: str | None = None                    # tabview → tab, tileview → tile
    initial_children: int = 0

    def prop(self, name: str) -> PropSpec | None:
        return next((p for p in self.props if p.name == name), None)

    def defaults(self) -> dict[str, Any]:
        return {p.name: p.default for p in self.props}


def P(name, label, kind, default, options=(), group="Estilo", minimum=0, maximum=10000):
    return PropSpec(name, label, kind, default, tuple(options), minimum, maximum, group)


HIDDEN = P("hidden", "Oculto", KIND_BOOL, False, group="Comportamiento")
COMMON_PROPS: tuple[PropSpec, ...] = (HIDDEN,)

# Grupos de propiedades de estilo reutilizables
BOX = (
    P("bg_color", "Color de fondo", KIND_COLOR, "#FFFFFF"),
    P("bg_opa", "Opacidad del fondo", KIND_ENUM, "COVER", OPA_OPTIONS),
    P("border_color", "Color del borde", KIND_COLOR, "#E0E0E0"),
    P("border_width", "Grosor del borde", KIND_INT, None, maximum=100),
    P("radius", "Radio de esquina", KIND_INT, None, maximum=1000),
    P("pad_all", "Margen interior", KIND_INT, None, maximum=500),
)
TEXT = (
    P("text_color", "Color del texto", KIND_COLOR, LV_TEXT),
    P("text_font", "Fuente", KIND_ENUM, DEFAULT_FONT, FONTS),
)
VALUE = (
    P("value", "Valor", KIND_INT, 0, group="Valor", minimum=-100000, maximum=100000),
    P("min_value", "Mínimo", KIND_INT, 0, group="Valor", minimum=-100000, maximum=100000),
    P("max_value", "Máximo", KIND_INT, 100, group="Valor", minimum=-100000, maximum=100000),
)
INDICATOR = (
    P("indicator.bg_color", "Color del indicador", KIND_COLOR, LV_PRIMARY),
)


def GRADIENT(prefix: str = "", group: str = "Degradado") -> tuple[PropSpec, ...]:
    """Degradado de fondo de LVGL (bg_grad_*) de la parte `prefix` ("" = principal, "indicator."…)."""
    return (
        P(prefix + "bg_grad_dir", "Dirección del degradado", KIND_ENUM, "NONE", GRAD_DIRS, group=group),
        P(prefix + "bg_grad_color", "Color final del degradado", KIND_COLOR, "#FFFFFF", group=group),
        P(prefix + "bg_main_stop", "Empieza en (0-255)", KIND_INT, 0, group=group, maximum=255),
        P(prefix + "bg_grad_stop", "Termina en (0-255)", KIND_INT, 255, group=group, maximum=255),
    )


CHECKED = P("state.checked", "Activado", KIND_BOOL, False, group="Valor")
SCROLLABLE = P("scrollable", "Desplazable", KIND_BOOL, True, group="Comportamiento")
CLICKABLE = P("clickable", "Responde al toque", KIND_BOOL, True, group="Comportamiento")

BUTTON_EVENTS = ("on_click", "on_short_click", "on_press", "on_release", "on_long_press")
GENERIC_EVENTS = BUTTON_EVENTS + ("on_value", "on_long_press_repeat", "on_focus", "on_defocus")
VALUE_EVENTS = ("on_value",) + BUTTON_EVENTS + ("on_focus", "on_defocus")
TEXT_EVENTS = ("on_value", "on_ready", "on_cancel", "on_focus", "on_defocus", "on_click")

EVENT_LABELS = {
    "on_click": "Al hacer clic",
    "on_short_click": "Clic corto",
    "on_press": "Al pulsar",
    "on_release": "Al soltar",
    "on_long_press": "Pulsación larga",
    "on_long_press_repeat": "Pulsación larga (repetida)",
    "on_value": "Al cambiar el valor",
    "on_focus": "Al recibir el foco",
    "on_defocus": "Al perder el foco",
    "on_ready": "Al confirmar (Intro)",
    "on_cancel": "Al cancelar",
    "on_load": "Al mostrar la página",
    "on_unload": "Al salir de la página",
    "on_double_click": "Doble clic",
    "on_press_lost": "Pulsación perdida (el dedo sale)",
    "on_gesture": "Gesto (cualquier dirección)",
    "on_swipe_left": "Deslizar a la izquierda",
    "on_swipe_right": "Deslizar a la derecha",
    "on_swipe_up": "Deslizar hacia arriba",
    "on_swipe_down": "Deslizar hacia abajo",
    "on_scroll_begin": "Empieza a desplazarse",
    "on_scroll": "Al desplazarse",
    "on_scroll_end": "Termina de desplazarse",
}

# --------------------------------------------------------------------------- widgets
LABEL = WidgetSpec(
    type="label", label="Etiqueta", default_size=(160, 32), id_prefix="lbl",
    description="Texto estático o dinámico", initial_props=(("text", "Etiqueta"),),
    events=GENERIC_EVENTS[:5],
    props=(
        P("text", "Texto", KIND_TEXT, "", group="Contenido"),
        *TEXT,
        P("text_align", "Alineación del texto", KIND_ENUM, "AUTO", TEXT_ALIGN),
        P("long_mode", "Texto largo", KIND_ENUM, "WRAP", LONG_MODES),
        P("recolor", "Colores en el texto (#RRGGBB …#)", KIND_BOOL, False, group="Contenido"),
        HIDDEN,
    ),
)

BUTTON = WidgetSpec(
    type="button", label="Botón", default_size=(140, 50), id_prefix="btn",
    description="Botón con texto, admite eventos", initial_props=(("text", "Botón"),),
    events=BUTTON_EVENTS,
    props=(
        P("text", "Texto", KIND_STR, "", group="Contenido"),
        P("bg_color", "Color de fondo", KIND_COLOR, LV_PRIMARY),
        P("text_color", "Color del texto", KIND_COLOR, "#FFFFFF"),
        P("text_font", "Fuente", KIND_ENUM, DEFAULT_FONT, FONTS),
        P("radius", "Radio de esquina", KIND_INT, 8, maximum=500),
        P("border_width", "Grosor del borde", KIND_INT, 0, maximum=50),
        P("border_color", "Color del borde", KIND_COLOR, LV_PRIMARY),
        *GRADIENT(),
        P("checkable", "Conmutable", KIND_BOOL, False, group="Comportamiento"),
        HIDDEN,
    ),
)

IMAGE = WidgetSpec(
    type="image", label="Imagen", default_size=(64, 64), id_prefix="image",
    description="Imagen de un recurso del proyecto", resizable=False, auto_size=True,
    events=BUTTON_EVENTS,
    props=(
        P("src", "Imagen", KIND_IMAGE, "", group="Contenido"),
        P("angle", "Giro (décimas de grado)", KIND_INT, None, group="Contenido", maximum=3600),
        P("image_recolor", "Teñir con color", KIND_COLOR, "#000000"),
        P("image_recolor_opa", "Intensidad del tinte", KIND_ENUM, "TRANSP", OPA_OPTIONS),
        HIDDEN,
    ),
)

OBJ = WidgetSpec(
    type="obj", label="Contenedor", default_size=(200, 150), id_prefix="obj",
    description="Caja para agrupar widgets (flex, grid…)", events=BUTTON_EVENTS,
    props=BOX + GRADIENT() + (SCROLLABLE, CLICKABLE, HIDDEN),
    parts=("main", "scrollbar"),
)

ARC = WidgetSpec(
    type="arc", label="Arco", default_size=(150, 150), id_prefix="arc",
    description="Indicador o control circular", category="Controles", events=VALUE_EVENTS,
    initial_props=(("value", 50), ("adjustable", True)),
    props=VALUE + (
        P("start_angle", "Ángulo inicial", KIND_INT, 135, group="Valor", maximum=360),
        P("end_angle", "Ángulo final", KIND_INT, 45, group="Valor", maximum=360),
        P("rotation", "Rotación", KIND_INT, 0, group="Valor", maximum=360),
        P("mode", "Modo", KIND_ENUM, "NORMAL", ("NORMAL", "REVERSE", "SYMMETRICAL"), group="Valor"),
        P("adjustable", "Se puede arrastrar", KIND_BOOL, False, group="Comportamiento"),
        P("arc_color", "Color del arco", KIND_COLOR, "#E0E0E0"),
        P("arc_width", "Grosor del arco", KIND_INT, None, maximum=200),
        P("indicator.arc_color", "Color del indicador", KIND_COLOR, LV_PRIMARY),
        P("indicator.arc_width", "Grosor del indicador", KIND_INT, None, maximum=200),
        P("arc_rounded", "Extremos redondeados", KIND_BOOL, True),
        P("bg_color", "Color de fondo (caja)", KIND_COLOR, "#FFFFFF", group="Degradado"),
        P("bg_opa", "Opacidad del fondo (caja)", KIND_ENUM, "TRANSP", OPA_OPTIONS, group="Degradado"),
        *GRADIENT(),
        P("knob.bg_color", "Color del tirador", KIND_COLOR, LV_PRIMARY, group="Degradado del tirador"),
        *GRADIENT("knob.", "Degradado del tirador"),
        HIDDEN,
    ),
    parts=("main", "indicator", "knob"),
)

BAR = WidgetSpec(
    type="bar", label="Barra", default_size=(200, 20), id_prefix="bar",
    description="Barra de progreso", category="Indicadores", events=("on_value",),
    initial_props=(("value", 50),),
    props=VALUE + (
        P("mode", "Modo", KIND_ENUM, "NORMAL", ("NORMAL", "SYMMETRICAL", "RANGE"), group="Valor"),
        P("start_value", "Valor inicial (modo RANGE)", KIND_INT, 0, group="Valor",
          minimum=-100000, maximum=100000),
        P("bg_color", "Color de fondo", KIND_COLOR, LV_PRIMARY),
        P("radius", "Radio de esquina", KIND_INT, None, maximum=1000),
        *INDICATOR, *GRADIENT("indicator.", "Degradado del indicador"), *GRADIENT(), HIDDEN,
    ),
    parts=("main", "indicator"),
)

SLIDER = WidgetSpec(
    type="slider", label="Deslizador", default_size=(200, 12), id_prefix="slider",
    description="Elegir un valor arrastrando", category="Controles", events=VALUE_EVENTS,
    initial_props=(("value", 50),),
    props=VALUE + (
        P("mode", "Modo", KIND_ENUM, "NORMAL", ("NORMAL", "SYMMETRICAL", "RANGE"), group="Valor"),
        P("bg_color", "Color de fondo", KIND_COLOR, LV_PRIMARY),
        *INDICATOR,
        P("knob.bg_color", "Color del tirador", KIND_COLOR, "#FFFFFF"),
        *GRADIENT("indicator.", "Degradado del indicador"), *GRADIENT(),
        *GRADIENT("knob.", "Degradado del tirador"),
        HIDDEN,
    ),
    parts=("main", "indicator", "knob"),
)

SWITCH = WidgetSpec(
    type="switch", label="Interruptor", default_size=(60, 32), id_prefix="sw",
    description="Encendido / apagado", category="Controles", events=VALUE_EVENTS,
    props=(CHECKED, P("bg_color", "Color apagado", KIND_COLOR, "#BDBDBD"),
           P("indicator.bg_color", "Color encendido", KIND_COLOR, LV_PRIMARY),
           P("knob.bg_color", "Color del tirador", KIND_COLOR, "#FFFFFF"), HIDDEN),
    parts=("main", "indicator", "knob"),
)

CHECKBOX = WidgetSpec(
    type="checkbox", label="Casilla", default_size=(150, 30), id_prefix="chk",
    description="Casilla de verificación con texto", category="Controles", events=VALUE_EVENTS,
    initial_props=(("text", "Casilla"),), auto_size=True,
    props=(P("text", "Texto", KIND_STR, "", group="Contenido"), CHECKED, *TEXT,
           P("indicator.bg_color", "Color de la casilla", KIND_COLOR, "#FFFFFF"), HIDDEN),
    parts=("main", "indicator"),
)

DROPDOWN = WidgetSpec(
    type="dropdown", label="Desplegable", default_size=(180, 44), id_prefix="dd",
    description="Lista desplegable de opciones", category="Controles", events=VALUE_EVENTS,
    initial_props=(("options", ["Opción 1", "Opción 2", "Opción 3"]),),
    props=(P("options", "Opciones (una por línea)", KIND_LINES, [], group="Contenido"),
           P("selected_index", "Opción elegida", KIND_INT, 0, group="Valor", maximum=1000),
           P("dir", "Dirección de la lista", KIND_ENUM, "BOTTOM", DIRECTIONS, group="Comportamiento"),
           *TEXT, *BOX[:2], HIDDEN),
    parts=("main", "indicator"),
)

ROLLER = WidgetSpec(
    type="roller", label="Rodillo", default_size=(120, 120), id_prefix="roller",
    description="Selector giratorio de opciones", category="Controles", events=VALUE_EVENTS,
    initial_props=(("options", ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes"]),),
    props=(P("options", "Opciones (una por línea)", KIND_LINES, [], group="Contenido"),
           P("selected_index", "Opción elegida", KIND_INT, 0, group="Valor", maximum=1000),
           P("mode", "Modo", KIND_ENUM, "NORMAL", ("NORMAL", "INFINITE"), group="Comportamiento"),
           P("visible_row_count", "Filas visibles", KIND_INT, None, group="Comportamiento", maximum=20),
           *TEXT, P("selected.bg_color", "Color de la selección", KIND_COLOR, LV_PRIMARY), HIDDEN),
    parts=("main", "selected"),
)

TEXTAREA = WidgetSpec(
    type="textarea", label="Área de texto", default_size=(240, 60), id_prefix="ta",
    description="Entrada de texto (con teclado)", category="Controles", events=TEXT_EVENTS,
    initial_props=(("placeholder_text", "Escribe aquí…"), ("one_line", True)),
    props=(P("text", "Texto", KIND_TEXT, "", group="Contenido"),
           P("placeholder_text", "Texto de ejemplo", KIND_STR, "", group="Contenido"),
           P("one_line", "Una sola línea", KIND_BOOL, False, group="Comportamiento"),
           P("password_mode", "Contraseña", KIND_BOOL, False, group="Comportamiento"),
           P("max_length", "Longitud máxima", KIND_INT, None, group="Comportamiento", maximum=10000),
           P("accepted_chars", "Caracteres permitidos", KIND_STR, "", group="Comportamiento"),
           *TEXT, HIDDEN),
    parts=("main", "cursor", "textarea_placeholder"),
)

SPINBOX = WidgetSpec(
    type="spinbox", label="Spinbox", default_size=(120, 44), id_prefix="spin",
    description="Número con dígitos ajustables", category="Controles", events=VALUE_EVENTS,
    props=(P("value", "Valor", KIND_INT, 0, group="Valor", minimum=-100000, maximum=100000),
           P("range_from", "Mínimo", KIND_INT, -100, group="Valor", minimum=-100000, maximum=100000),
           P("range_to", "Máximo", KIND_INT, 100, group="Valor", minimum=-100000, maximum=100000),
           P("digits", "Dígitos", KIND_INT, 4, group="Valor", maximum=10),
           P("decimal_places", "Decimales", KIND_INT, 0, group="Valor", maximum=9),
           P("rollover", "Vuelta al llegar al límite", KIND_BOOL, False, group="Comportamiento"),
           *TEXT, HIDDEN),
    parts=("main", "cursor"),
)

KEYBOARD = WidgetSpec(
    type="keyboard", label="Teclado", default_size=(600, 240), id_prefix="kb",
    description="Teclado en pantalla para un área de texto", category="Controles",
    events=("on_ready", "on_cancel", "on_value"),
    props=(P("mode", "Modo", KIND_ENUM, None, ("TEXT_LOWER", "TEXT_UPPER", "SPECIAL", "NUMBER"),
             group="Comportamiento"),
           P("textarea", "Área de texto asociada", KIND_WIDGET, "", group="Comportamiento"), HIDDEN),
    parts=("main", "items"),
)

BUTTONMATRIX = WidgetSpec(
    type="buttonmatrix", label="Matriz de botones", default_size=(300, 120), id_prefix="bm",
    description="Varios botones en filas", category="Controles", events=VALUE_EVENTS,
    initial_props=(("rows", [{"buttons": [{"text": "1"}, {"text": "2"}, {"text": "3"}]},
                             {"buttons": [{"text": "4"}, {"text": "5"}, {"text": "6"}]}]),),
    props=(HIDDEN,),
    parts=("main", "items"),
)

LED = WidgetSpec(
    type="led", label="LED", default_size=(30, 30), id_prefix="led",
    description="Luz indicadora", category="Indicadores",
    props=(P("color", "Color", KIND_COLOR, LV_PRIMARY),
           P("brightness", "Brillo", KIND_ENUM, "100%", [f"{p}%" for p in range(0, 101, 10)]), HIDDEN),
)

SPINNER = WidgetSpec(
    type="spinner", label="Spinner", default_size=(60, 60), id_prefix="spinner",
    description="Animación de espera", category="Indicadores",
    initial_props=(("spin_time", "2s"), ("arc_length", 60)),
    props=(P("spin_time", "Tiempo de vuelta", KIND_STR, "", group="Valor"),
           P("arc_length", "Longitud del arco (grados)", KIND_INT, None, group="Valor", maximum=360),
           P("arc_color", "Color de fondo", KIND_COLOR, "#E0E0E0"),
           P("indicator.arc_color", "Color del arco", KIND_COLOR, LV_PRIMARY), HIDDEN),
    parts=("main", "indicator"),
)

LINE = WidgetSpec(
    type="line", label="Línea", default_size=(100, 50), id_prefix="line",
    description="Línea por puntos", category="Indicadores", auto_size=True,
    initial_props=(("points", ["0,40", "50,0", "100,40"]), ("line_width", 4)),
    props=(P("points", "Puntos (x,y, uno por línea)", KIND_LINES, [], group="Contenido"),
           P("line_width", "Grosor", KIND_INT, None, maximum=100),
           P("line_color", "Color", KIND_COLOR, "#000000"),
           P("line_rounded", "Extremos redondeados", KIND_BOOL, False), HIDDEN),
)

QRCODE = WidgetSpec(
    type="qrcode", label="Código QR", default_size=(100, 100), id_prefix="qr",
    description="Código QR de un texto", category="Indicadores", auto_size=True,
    initial_props=(("text", "https://esphome.io"), ("size", 100)),
    props=(P("text", "Texto", KIND_STR, "", group="Contenido"),
           P("size", "Tamaño", KIND_INT, None, group="Contenido", maximum=1000),
           P("dark_color", "Color oscuro", KIND_COLOR, "#000000"),
           P("light_color", "Color claro", KIND_COLOR, "#FFFFFF"), HIDDEN),
)

METER = WidgetSpec(
    type="meter", label="Indicador de aguja", default_size=(200, 200), id_prefix="meter",
    description="Escalas, marcas, agujas y arcos", category="Indicadores",
    initial_props=(("scales", [{
        "range_from": 0, "range_to": 100, "angle_range": 270, "rotation": 135,
        "ticks": {"count": 21, "width": 2, "length": 10, "color": "#9E9E9E",
                  "major": {"stride": 5, "width": 4, "length": 16, "color": "#616161", "label_gap": 10}},
        "indicators": [
            {"arc": {"color": "#4CAF50", "width": 4, "start_value": 0, "end_value": 60}},
            {"arc": {"color": "#F44336", "width": 4, "start_value": 80, "end_value": 100}},
            {"line": {"color": "#2196F3", "width": 4, "r_mod": -10, "value": 60}},
        ]}]),),
    props=(*BOX[:2], *GRADIENT(), HIDDEN),
    parts=("main", "ticks", "indicator", "items"),
)

TABVIEW = WidgetSpec(
    type="tabview", label="Pestañas", default_size=(480, 300), id_prefix="tabview",
    description="Páginas con pestañas", category="Contenedores", events=("on_value",),
    child_type="tab", initial_children=2,
    props=(P("position", "Posición de las pestañas", KIND_ENUM, "TOP", DIRECTIONS, group="Contenido"),
           P("size", "Tamaño de la barra", KIND_STR, "", group="Contenido"),
           *BOX[:2], HIDDEN),
)

TAB = WidgetSpec(
    type="tab", label="Pestaña", default_size=(100, 100), id_prefix="tab",
    description="Una pestaña de un tabview", category="Contenedores", resizable=False,
    props=(P("name", "Nombre", KIND_STR, "", group="Contenido"), *BOX[:2], SCROLLABLE),
)

TILEVIEW = WidgetSpec(
    type="tileview", label="Mosaicos", default_size=(480, 300), id_prefix="tileview",
    description="Páginas que se deslizan", category="Contenedores", events=("on_value",),
    child_type="tile", initial_children=2,
    props=(*BOX[:2], HIDDEN),
)

TILE = WidgetSpec(
    type="tile", label="Mosaico", default_size=(100, 100), id_prefix="tile",
    description="Un mosaico de un tileview", category="Contenedores", resizable=False,
    props=(P("row", "Fila", KIND_INT, 0, group="Contenido", maximum=100),
           P("column", "Columna", KIND_INT, 0, group="Contenido", maximum=100),
           P("dir", "Direcciones de deslizamiento", KIND_STR, "", group="Contenido"),
           *BOX[:2]),
)

CANVAS = WidgetSpec(
    type="canvas", label="Lienzo", default_size=(200, 150), id_prefix="canvas",
    description="Superficie de dibujo libre", category="Media",
    props=(P("transparent", "Transparente", KIND_BOOL, False, group="Contenido"), HIDDEN),
)

ANIMIMG = WidgetSpec(
    type="animimg", label="Imagen animada", default_size=(64, 64), id_prefix="anim",
    description="Secuencia de imágenes", category="Media", resizable=False, auto_size=True,
    props=(P("duration", "Duración del ciclo", KIND_STR, "", group="Contenido"),
           P("repeat_count", "Repeticiones", KIND_STR, "", group="Contenido"), HIDDEN),
)

BUILTIN_SPECS = (LABEL, BUTTON, IMAGE, OBJ, SWITCH, CHECKBOX, SLIDER, ARC, DROPDOWN, ROLLER, SPINBOX,
                 TEXTAREA, KEYBOARD, BUTTONMATRIX, BAR, LED, SPINNER, LINE, QRCODE, METER,
                 TABVIEW, TAB, TILEVIEW, TILE, CANVAS, ANIMIMG)
BUILTIN_SPECS_TYPES = frozenset(s.type for s in BUILTIN_SPECS)
ALL_SPECS: list[WidgetSpec] = list(BUILTIN_SPECS)       # + los que registran los plugins
CATALOG: dict[str, WidgetSpec] = {s.type: s for s in ALL_SPECS}
PLUGIN_CATEGORY = "Plugins"
CATEGORIES: list[str] = ["Básicos", "Controles", "Indicadores", "Contenedores", "Media"]

WIDGET_LABELS = {s.type: s.label for s in ALL_SPECS}

# Widgets cuyos hijos van en una lista propia en lugar de `widgets:`
CHILD_LISTS = {"tabview": ("tabs", "tab"), "tileview": ("tiles", "tile")}
PSEUDO_TYPES = {"tab", "tile"}
CONTAINER_TYPES = {"obj", "button", "tab", "tile"}

_GENERIC: dict[str, WidgetSpec] = {}


def spec(widget_type: str) -> WidgetSpec:
    """Especificación del widget; los tipos desconocidos usan una genérica."""
    if widget_type in CATALOG:
        return CATALOG[widget_type]
    sp = _GENERIC.get(widget_type)
    if sp is None:
        sp = WidgetSpec(type=widget_type, label=widget_type, default_size=(100, 100),
                        props=COMMON_PROPS, events=GENERIC_EVENTS, id_prefix=widget_type, known=False)
        _GENERIC[widget_type] = sp
    return sp


def type_label(widget_type: str) -> str:
    return spec(widget_type).label


def register_spec(sp: WidgetSpec) -> None:
    """Añade (o sustituye) un tipo de widget de un plugin."""
    if sp.type in BUILTIN_SPECS_TYPES:
        raise ValueError(f"«{sp.type}» es un widget integrado y no se puede sustituir")
    unregister_spec(sp.type)
    ALL_SPECS.append(sp)
    CATALOG[sp.type] = sp
    WIDGET_LABELS[sp.type] = sp.label
    _GENERIC.pop(sp.type, None)
    if sp.category not in CATEGORIES:
        CATEGORIES.append(sp.category)


def unregister_spec(widget_type: str) -> None:
    if widget_type in BUILTIN_SPECS_TYPES:
        return
    old = CATALOG.pop(widget_type, None)
    if old is not None:
        ALL_SPECS[:] = [s for s in ALL_SPECS if s.type != widget_type]
        WIDGET_LABELS.pop(widget_type, None)
        builtin_cats = {b.category for b in BUILTIN_SPECS}
        used = {s.category for s in ALL_SPECS}
        CATEGORIES[:] = [c for c in CATEGORIES if c in builtin_cats or c in used]


def palette_specs() -> list[WidgetSpec]:
    """Widgets que se pueden añadir desde la paleta (sin las pestañas/mosaicos sueltos)."""
    return [s for s in ALL_SPECS if s.type not in PSEUDO_TYPES]


# --------------------------------------------------------------------------- valores anidados
_MISSING = object()


def get_path(props: dict, name: str, default: Any = None) -> Any:
    cur: Any = props
    for part in name.split("."):
        if not isinstance(cur, dict) or "__tag__" in cur or part not in cur:
            return default
        cur = cur[part]
    return cur


def set_path(props: dict, name: str, value: Any) -> dict:
    """Copia de `props` con `name` (con puntos) fijado; None lo quita y limpia mapas vacíos."""
    import copy
    out = copy.deepcopy(props)
    parts = name.split(".")
    stack = [out]
    cur = out
    for part in parts[:-1]:
        nxt = cur.get(part)
        if not isinstance(nxt, dict) or "__tag__" in nxt:
            if value is None:
                return out
            nxt = {}
            cur[part] = nxt
        cur = nxt
        stack.append(cur)
    if value is None:
        cur.pop(parts[-1], None)
        for i in range(len(parts) - 1, 0, -1):   # quita los mapas que se quedan vacíos
            parent = stack[i - 1]
            if not parent.get(parts[i - 1]):
                parent.pop(parts[i - 1], None)
    else:
        cur[parts[-1]] = value
    return out


def prop_value(widget, name: str) -> Any:
    """Valor efectivo de una propiedad (la fijada o la de por defecto)."""
    v = get_path(widget.props, name, _MISSING)
    if v is not _MISSING:
        return v
    p = spec(widget.type).prop(name)
    return p.default if p else None


# --------------------------------------------------------------------------- acciones
ACTION_KINDS = {
    "page_show": "Mostrar página",
    "page_next": "Página siguiente",
    "page_prev": "Página anterior",
    "widget_state": "Mostrar / ocultar / activar un widget",
    "widget_update": "Cambiar propiedades de un widget",
    "ha_action": "Acción de Home Assistant",
    "call": "Acción de un componente (light.toggle, script.execute…)",
    "delay": "Esperar",
    "logger": "Escribir en el log",
    "lambda": "Código C++ (lambda)",
    "raw": "YAML libre",
}

WIDGET_STATE_OPS = {"show": "Mostrar", "hide": "Ocultar", "enable": "Activar", "disable": "Desactivar"}


def default_action(kind: str) -> dict[str, Any]:
    return {
        "page_show": {"page": ""},
        "page_next": {},
        "page_prev": {},
        "widget_state": {"op": "hide", "id": ""},
        "widget_update": {"type": "label", "id": "", "props": {"text": "Nuevo texto"}},
        "ha_action": {"action": "light.toggle", "entity_id": "light.salon"},
        "call": {"action": "light.toggle", "target": ""},
        "delay": {"duration": "1s"},
        "logger": {"message": "Pulsado"},
        "lambda": {"code": "ESP_LOGI(\"ui\", \"pulsado\");"},
        "raw": {"yaml": "logger.log: \"hola\""},
    }.get(kind, {})


def describe_action(kind: str, params: dict) -> str:
    from olvgl.i18n import tr, trf
    if kind == "page_show":
        return trf("Mostrar página «{page}»", page=params.get("page", ""))
    if kind == "page_next":
        return tr("Página siguiente")
    if kind == "page_prev":
        return tr("Página anterior")
    if kind == "widget_state":
        op = params.get("op")
        return f"{tr(WIDGET_STATE_OPS.get(op, op or ''))} «{params.get('id', '')}»"
    if kind == "widget_update":
        keys = ", ".join(str(k) for k in (params.get("props") or {}))
        return trf("Cambiar {keys} de «{id}»", keys=keys or tr("propiedades"), id=params.get("id", ""))
    if kind == "ha_action":
        ent = params.get("entity_id", "")
        return f"HA: {params.get('action', '')}" + (f" → {ent}" if ent else "")
    if kind == "call":
        t = params.get("target")
        return f"{params.get('action', '')}" + (f": {t}" if t else "")
    if kind == "delay":
        return trf("Esperar {duration}", duration=params.get("duration", ""))
    if kind == "logger":
        return trf("Log: {message}", message=params.get("message", ""))
    if kind == "lambda":
        first = (params.get("code", "") or "").strip().splitlines()
        return f"λ {first[0] if first else ''}"
    if kind == "raw":
        first = (params.get("yaml", "") or "").strip().splitlines()
        return f"YAML: {first[0] if first else ''}"
    return kind


def STATE_KEY_COLORS(name: str) -> bool:  # noqa: N802 - utilidad de nombres
    """¿La última parte de un nombre con puntos es una propiedad de color?"""
    last = name.split(".")[-1]
    return last == "color" or last.endswith("_color")
