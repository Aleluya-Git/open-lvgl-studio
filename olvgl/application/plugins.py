"""Gestor de plugins de Open LVGL Studio (Fase 7).

Un plugin es una carpeta con:

    plugin.json   {"id", "name", "version", "api": 1, "entry": "plugin.py",
                   "description", "author", "translations": {"en": {...}}}
    plugin.py     def register(ctx): ...

Se buscan en, por este orden:
1. `plugins/` junto a la aplicación (los de ejemplo);
2. la carpeta de plugins del usuario (`%APPDATA%/OpenLVGLStudio/plugins`);
3. las carpetas de la variable `OLVGL_PLUGINS` (separadas por `;` o `:`).

Si dos carpetas traen el mismo id, gana la última (el usuario puede
sustituir uno de ejemplo). Cada plugin se carga aislado: si falla, se anota
el error y el resto sigue funcionando.

**Seguridad**: un plugin es código Python con los mismos permisos que la
aplicación. Instala sólo plugins de quien te fíes.
"""
from __future__ import annotations

import importlib.util
import json
import os
import re
import sys
import traceback
from dataclasses import dataclass, field
from typing import Any, Callable

from olvgl.domain import catalog
from olvgl.domain.catalog import KIND_BOOL, KIND_COLOR, KIND_ENUM, KIND_INT, KIND_STR, KIND_TEXT, P, WidgetSpec
from olvgl.domain.extensions import API_VERSION, REGISTRY, Command, Exporter, Issue
from olvgl.domain.model import Action, EventHandler, Project, Widget

APP_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
BUILTIN_DIR = os.path.join(APP_ROOT, "plugins")
_ID_RE = re.compile(r"^[a-z][a-z0-9_]{1,40}$")


def user_plugins_dir() -> str:
    from olvgl.infrastructure.settings_db import app_data_dir
    path = os.path.join(app_data_dir(), "plugins")
    os.makedirs(path, exist_ok=True)
    return path


@dataclass
class PluginInfo:
    id: str
    name: str
    version: str = "0.0.0"
    api: int = API_VERSION
    description: str = ""
    author: str = ""
    path: str = ""
    entry: str = "plugin.py"
    source: str = ""                  # integrado | usuario | variable
    enabled: bool = True
    loaded: bool = False
    error: str = ""
    provides: list[str] = field(default_factory=list)
    translations: dict[str, dict[str, str]] = field(default_factory=dict)


class CommandContext:
    """Lo que recibe una orden de plugin al ejecutarse."""

    def __init__(self, vm, log: Callable[[str], None], window=None):
        self.vm = vm                      # ProjectViewModel: cambios con deshacer
        self.project: Project = vm.project
        self.selection: list[str] = list(getattr(vm, "selection", []))
        self.log = log
        self.window = window              # ventana principal (para diálogos), o None


class PluginContext:
    """API que recibe `register(ctx)`. Es la única superficie estable del SDK."""

    api_version = API_VERSION

    def __init__(self, info: PluginInfo, log: Callable[[str], None]):
        self.info = info
        self.id = info.id
        self.path = info.path
        self._log = log

    # ------------------------------------------------------------ utilidades
    def log(self, msg: str) -> None:
        self._log(f"[{self.id}] {msg}")

    def resource(self, *parts: str) -> str:
        return os.path.join(self.path, *parts)

    # atajos para declarar propiedades
    P = staticmethod(P)
    INT, STR, TEXT, COLOR, BOOL, ENUM = KIND_INT, KIND_STR, KIND_TEXT, KIND_COLOR, KIND_BOOL, KIND_ENUM
    Widget = Widget
    Action = Action
    EventHandler = EventHandler
    Issue = Issue

    # ------------------------------------------------------------ widgets
    def register_widget(self, type: str, label: str, *, props: tuple = (), default_size=(160, 100),
                        description: str = "", category: str = catalog.PLUGIN_CATEGORY,
                        events: tuple[str, ...] = ("on_click", "on_press", "on_release", "on_long_press"),
                        expand: Callable[[Widget], list[Widget]] | None = None,
                        paint: Callable[..., None] | None = None, icon: str | None = None,
                        initial_props: dict | None = None, id_prefix: str | None = None) -> WidgetSpec:
        """Widget compuesto: en el diseñador se dibuja con `paint` y al exportar se
        convierte con `expand` en widgets estándar de LVGL (obligatorio: ESPHome y
        LVGL no conocen tipos nuevos)."""
        if not _ID_RE.match(type):
            raise ValueError(f"tipo de widget no válido: «{type}» (minúsculas, números y _)")
        if expand is None:
            raise ValueError(f"«{type}» necesita una función expand(widget) → [widgets de LVGL]")
        sp = WidgetSpec(type=type, label=label, default_size=tuple(default_size), props=tuple(props) + (catalog.HIDDEN,),
                        events=tuple(events), id_prefix=id_prefix or type, description=description,
                        initial_props=tuple((initial_props or {}).items()), category=category)
        catalog.register_spec(sp)
        REGISTRY.widget_types[type] = self.id
        REGISTRY.expanders[type] = (self.id, expand)
        if paint is not None:
            try:
                from olvgl.presentation import render
                render.CUSTOM_PAINTERS[type] = paint
            except ImportError:            # sin Qt (CLI de validación): no se dibuja
                pass
        if icon:
            PLUGIN_ICONS[type] = self.resource(icon) if not os.path.isabs(icon) else icon
        self.info.provides.append(f"widget:{type}")
        return sp

    # ------------------------------------------------------------ exportadores
    def register_exporter(self, id: str, name: str, export: Callable[[Project, str], list[str]],
                          description: str = "") -> None:
        """`export(proyecto, carpeta)` escribe en la carpeta y devuelve los ficheros creados."""
        REGISTRY.exporters[f"{self.id}.{id}"] = Exporter(f"{self.id}.{id}", name, export, description, self.id)
        self.info.provides.append(f"exportador:{id}")

    # ------------------------------------------------------------ validadores
    def register_validator(self, fn: Callable[[Project], list[Issue]]) -> None:
        REGISTRY.validators.append((self.id, fn))
        self.info.provides.append("validador")

    # ------------------------------------------------------------ órdenes
    def register_command(self, id: str, label: str, run: Callable[[CommandContext], None],
                         description: str = "") -> None:
        REGISTRY.commands[f"{self.id}.{id}"] = Command(f"{self.id}.{id}", label, run, description, self.id)
        self.info.provides.append(f"orden:{id}")

    # ------------------------------------------------------------ traducciones
    def add_translations(self, code: str, mapping: dict[str, str]) -> None:
        from olvgl import i18n
        i18n.add_translations(code, mapping)


PLUGIN_ICONS: dict[str, str] = {}


class PluginManager:
    def __init__(self, dirs: list[tuple[str, str]] | None = None, log: Callable[[str], None] | None = None):
        self.dirs = dirs if dirs is not None else self.default_dirs()
        self.log = log or (lambda m: None)
        self.plugins: dict[str, PluginInfo] = {}
        self.messages: list[str] = []

    @staticmethod
    def default_dirs() -> list[tuple[str, str]]:
        out = [(BUILTIN_DIR, "integrado")]
        try:
            out.append((user_plugins_dir(), "usuario"))
        except OSError:
            pass
        for d in re.split(r"[;" + (":" if os.name != "nt" else "") + "]", os.environ.get("OLVGL_PLUGINS", "")):
            if d.strip():
                out.append((d.strip(), "variable"))
        return out

    def _log(self, msg: str) -> None:
        self.messages.append(msg)
        self.log(msg)

    # ------------------------------------------------------------ descubrir
    def discover(self) -> dict[str, PluginInfo]:
        found: dict[str, PluginInfo] = {}
        for base, source in self.dirs:
            if not os.path.isdir(base):
                continue
            for name in sorted(os.listdir(base)):
                folder = os.path.join(base, name)
                manifest = os.path.join(folder, "plugin.json")
                if not os.path.isfile(manifest):
                    continue
                try:
                    with open(manifest, encoding="utf-8") as f:
                        m = json.load(f)
                    info = PluginInfo(id=str(m["id"]), name=str(m.get("name", m["id"])),
                                      version=str(m.get("version", "0.0.0")), api=int(m.get("api", 1)),
                                      description=str(m.get("description", "")), author=str(m.get("author", "")),
                                      path=folder, entry=str(m.get("entry", "plugin.py")), source=source,
                                      translations=m.get("translations") or {})
                    if not _ID_RE.match(info.id):
                        raise ValueError(f"id no válido «{info.id}»")
                except Exception as exc:
                    info = PluginInfo(id=name, name=name, path=folder, source=source,
                                      error=f"plugin.json no válido: {exc}")
                found[info.id] = info
        return found

    # ------------------------------------------------------------ cargar
    def load_all(self, disabled: set[str] | None = None) -> dict[str, PluginInfo]:
        disabled = disabled or set()
        for pid in list(self.plugins):
            self.unload(pid)
        self.plugins = self.discover()
        for info in self.plugins.values():
            info.enabled = info.id not in disabled
            if info.enabled and not info.error:
                self._load(info)
        return self.plugins

    def _load(self, info: PluginInfo) -> None:
        if info.api != API_VERSION:
            info.error = f"usa la API {info.api}; esta versión de Open LVGL Studio ofrece la {API_VERSION}"
            return
        entry = os.path.join(info.path, info.entry)
        if not os.path.isfile(entry):
            info.error = f"no existe {info.entry}"
            return
        modname = f"olvgl_plugin_{info.id}"
        try:
            spec = importlib.util.spec_from_file_location(modname, entry)
            module = importlib.util.module_from_spec(spec)
            sys.modules[modname] = module
            spec.loader.exec_module(module)
            if not hasattr(module, "register"):
                raise AttributeError("falta la función register(ctx)")
            ctx = PluginContext(info, self._log)
            for code, mapping in (info.translations or {}).items():
                if isinstance(mapping, dict):
                    ctx.add_translations(code, mapping)
            module.register(ctx)
            info.loaded = True
            info.error = ""
            self._log(f"plugin cargado: {info.name} {info.version}")
        except Exception as exc:
            self.unload(info.id)
            info.loaded = False
            info.provides = []
            info.error = f"{type(exc).__name__}: {exc}"
            self._log(f"plugin con errores: {info.name}: {info.error}\n"
                      + "".join(traceback.format_exc(limit=3)))
            sys.modules.pop(modname, None)

    def unload(self, plugin_id: str) -> None:
        types = [t for t, pid in REGISTRY.widget_types.items() if pid == plugin_id]
        REGISTRY.remove_plugin(plugin_id)
        try:
            from olvgl.presentation import render
            for t in types:
                render.CUSTOM_PAINTERS.pop(t, None)
        except ImportError:
            pass
        for t in types:
            PLUGIN_ICONS.pop(t, None)
        sys.modules.pop(f"olvgl_plugin_{plugin_id}", None)
        info = self.plugins.get(plugin_id)
        if info is not None:
            info.loaded = False
            info.provides = []

    # ------------------------------------------------------------ usar
    def run_command(self, command_id: str, vm, log: Callable[[str], None], window=None) -> bool:
        cmd = REGISTRY.commands.get(command_id)
        if cmd is None:
            return False
        try:
            cmd.run(CommandContext(vm, log, window))
            return True
        except Exception as exc:
            log(f"La orden «{cmd.label}» del plugin «{cmd.plugin}» falló: {exc}")
            return False

    def export(self, exporter_id: str, project: Project, folder: str) -> list[str]:
        ex = REGISTRY.exporters[exporter_id]
        os.makedirs(folder, exist_ok=True)
        return list(ex.export(project, folder) or [])


_manager: PluginManager | None = None


def manager() -> PluginManager:
    global _manager
    if _manager is None:
        _manager = PluginManager()
    return _manager


def load_plugins(disabled: set[str] | None = None, force: bool = False) -> PluginManager:
    """Carga los plugins una sola vez por proceso (o de nuevo con force=True)."""
    m = manager()
    if force or not m.plugins:
        m.load_all(disabled)
    return m


# --------------------------------------------------------------------------- plantilla
TEMPLATE_MANIFEST = {"id": "", "name": "", "version": "0.1.0", "api": API_VERSION, "entry": "plugin.py",
                     "description": "", "author": ""}

TEMPLATE_CODE = '''"""Plugin «{name}» para Open LVGL Studio.

Documentación del SDK: docs/10_plugins.md
"""


def register(ctx):
    P = ctx.P

    def expand(w):
        # Convierte el widget en widgets estándar de LVGL (los que entiende ESPHome).
        card = ctx.Widget(w.id, "obj", w.x, w.y, w.width, w.height,
                          props={{"bg_color": w.props.get("color", "#2D2D3A"), "radius": 12,
                                  "border_width": 0}}, events=w.events)
        card.children.append(ctx.Widget(f"{{w.id}}_text", "label", None, None, None, None,
                                        props={{"text": w.props.get("text", ""), "align": "CENTER",
                                                "text_color": "#FFFFFF"}}))
        return [card]

    def paint(p, rect, w, props, rctx, state):
        from olvgl.presentation import render
        render.paint_box(p, rect, {{"bg_color": props.get("color", "#2D2D3A"), "radius": 12}}, rctx)
        render.paint_text(p, rect, str(props.get("text", "")), {{"text_color": "#FFFFFF",
                          "text_align": "CENTER"}}, rctx, v_center=True)

    ctx.register_widget(
        "{id}_widget", "{name}", description="Widget de ejemplo del plugin",
        props=(P("text", "Texto", ctx.STR, "Hola", group="Contenido"),
               P("color", "Color", ctx.COLOR, "#2D2D3A")),
        initial_props={{"text": "Hola"}}, expand=expand, paint=paint)

    def check(project):
        return []          # devuelve ctx.Issue("mensaje", "warning", widget_id) por cada problema

    ctx.register_validator(check)
'''


def create_plugin(folder: str, plugin_id: str, name: str = "", author: str = "") -> str:
    """Crea la plantilla de un plugin nuevo y devuelve su carpeta."""
    if not _ID_RE.match(plugin_id):
        raise ValueError("el id debe ir en minúsculas, con letras, números y _ (p. ej. mi_plugin)")
    path = os.path.join(folder, plugin_id)
    if os.path.exists(path):
        raise FileExistsError(path)
    os.makedirs(path)
    manifest = dict(TEMPLATE_MANIFEST, id=plugin_id, name=name or plugin_id, author=author,
                    description=f"Plugin {name or plugin_id}")
    with open(os.path.join(path, "plugin.json"), "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)
    with open(os.path.join(path, "plugin.py"), "w", encoding="utf-8") as f:
        f.write(TEMPLATE_CODE.format(id=plugin_id, name=name or plugin_id))
    return path


def describe(info: PluginInfo) -> dict[str, Any]:
    return {"id": info.id, "name": info.name, "version": info.version, "source": info.source,
            "enabled": info.enabled, "loaded": info.loaded, "error": info.error, "provides": info.provides,
            "path": info.path, "description": info.description, "author": info.author}
