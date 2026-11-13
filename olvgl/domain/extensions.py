"""Puntos de extensión del núcleo (sin Qt): lo que registran los plugins.

- **expansores** de widgets: un widget de plugin se convierte, al exportar,
  en widgets estándar de LVGL (ESPHome y C sólo conocen esos);
- **exportadores**: nuevos formatos de salida (Archivo › Exportar y la CLI);
- **validadores**: reglas que revisan el proyecto (menú Plugins, CLI y VS Code);
- **órdenes**: acciones que modifican el proyecto desde el menú Plugins.

El registro guarda qué plugin aportó cada cosa para poder descargarlo.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from olvgl.domain import catalog
from olvgl.domain.model import Project, Screen, Widget

API_VERSION = 1


@dataclass
class Issue:
    """Resultado de un validador."""
    message: str
    severity: str = "warning"          # error | warning | info
    widget_id: str | None = None
    page_id: str | None = None
    plugin: str = ""


@dataclass
class Exporter:
    id: str
    name: str
    export: Callable[[Project, str], list[str]]   # (proyecto, carpeta) → ficheros escritos
    description: str = ""
    plugin: str = ""


@dataclass
class Command:
    id: str
    label: str
    run: Callable[[Any], None]                     # recibe un CommandContext
    description: str = ""
    plugin: str = ""


@dataclass
class Registry:
    expanders: dict[str, tuple[str, Callable[[Widget], list[Widget]]]] = field(default_factory=dict)
    exporters: dict[str, Exporter] = field(default_factory=dict)
    validators: list[tuple[str, Callable[[Project], list[Issue]]]] = field(default_factory=list)
    commands: dict[str, Command] = field(default_factory=dict)
    widget_types: dict[str, str] = field(default_factory=dict)       # tipo → plugin

    def remove_plugin(self, plugin_id: str) -> None:
        for t, pid in list(self.widget_types.items()):
            if pid == plugin_id:
                catalog.unregister_spec(t)
                del self.widget_types[t]
        self.expanders = {k: v for k, v in self.expanders.items() if v[0] != plugin_id}
        self.exporters = {k: v for k, v in self.exporters.items() if v.plugin != plugin_id}
        self.validators = [v for v in self.validators if v[0] != plugin_id]
        self.commands = {k: v for k, v in self.commands.items() if v.plugin != plugin_id}


REGISTRY = Registry()


# --------------------------------------------------------------------------- expansión
def _expand_list(widgets: list[Widget], warnings: list[str], depth: int = 0) -> list[Widget]:
    out: list[Widget] = []
    for w in widgets:
        entry = REGISTRY.expanders.get(w.type)
        if entry is not None and depth < 8:
            plugin, fn = entry
            try:
                produced = fn(w.clone())
            except Exception as exc:   # un plugin roto no rompe la exportación
                warnings.append(f"{w.id}: el plugin «{plugin}» falló al convertir «{w.type}»: {exc}")
                continue
            for p in produced or []:
                if not isinstance(p, Widget):
                    warnings.append(f"{w.id}: el plugin «{plugin}» devolvió algo que no es un Widget")
                    continue
                out += _expand_list([p], warnings, depth + 1)
            continue
        if w.type not in catalog.BUILTIN_SPECS_TYPES and w.type not in REGISTRY.expanders:
            if catalog.spec(w.type).known is False and w.type not in KNOWN_ESPHOME_TYPES:
                warnings.append(f"{w.id}: tipo «{w.type}» sin plugin que lo convierta a LVGL")
        if w.children:
            w = w.clone()
            w.children = _expand_list(w.children, warnings, depth)
        out.append(w)
    return out


# tipos de ESPHome que el editor conserva aunque no tengan editor propio
KNOWN_ESPHOME_TYPES = {"msgbox", "chart", "calendar", "list", "menu", "table", "win", "colorwheel",
                       "imagebutton", "span", "spangroup"}


def needs_expansion(project: Project) -> bool:
    if not REGISTRY.expanders:
        return False
    return any(w.type in REGISTRY.expanders for _s, w in project.iter_widgets())


def expand_project(project: Project, warnings: list[str] | None = None) -> Project:
    """Copia del proyecto con los widgets de plugins convertidos a widgets estándar."""
    if not needs_expansion(project):
        return project
    warnings = warnings if warnings is not None else []
    p = project.clone()
    for s in p.all_screens():
        s.widgets = _expand_list(s.widgets, warnings)
    return p


# --------------------------------------------------------------------------- validación
def validate(project: Project) -> list[Issue]:
    issues: list[Issue] = []
    for plugin, fn in list(REGISTRY.validators):
        try:
            for it in fn(project) or []:
                if isinstance(it, str):
                    it = Issue(it)
                it.plugin = it.plugin or plugin
                issues.append(it)
        except Exception as exc:
            issues.append(Issue(f"El validador del plugin «{plugin}» falló: {exc}", "error", plugin=plugin))
    return issues


def screen_of(project: Project, widget_id: str) -> Screen | None:
    loc = project.locate(widget_id)
    return loc.screen if loc else None
