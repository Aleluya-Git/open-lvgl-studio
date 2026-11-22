"""ProjectViewModel: el ViewModel de MVVM. Python puro, sin Qt.

Las vistas Qt sólo llaman a estos métodos y escuchan sus señales; nunca tocan
el modelo directamente. Así toda la lógica de edición es testeable.

Desde la Fase 2 las operaciones geométricas trabajan sobre la disposición
calculada (domain/layout.py): mover = desplazar x/y relativos al padre,
respetando align, porcentajes y contenedores con flex/grid.
"""
from __future__ import annotations

import copy
import dataclasses
import os
from typing import Any, Callable, Iterable

from olvgl.application import commands as cmd
from olvgl.application.history import Command, CompositeCommand, History
from olvgl.application.observable import Signal
from olvgl.domain import catalog
from olvgl.domain.layout import Box, LayoutContext, compute_layout
from olvgl.domain.model import (TOP_LAYER_ID, DisplayProfile, EventHandler, Project, Screen,
                                Widget, is_valid_id, new_project, normalize_color, sanitize_id,
                                unique_id)

ALIGN_MODES = ("left", "hcenter", "right", "top", "vcenter", "bottom")
GEOMETRY_KEYS = {"x", "y", "width", "height"}


def _file_hash(path: str) -> str:
    import hashlib
    with open(path, "rb") as f:
        return hashlib.sha1(f.read()).hexdigest()


@dataclasses.dataclass
class ChangeInfo:
    """Último cambio del proyecto: kind = geometry | widgets | structure.
    `ids` = widgets tocados (None: puede ser cualquiera)."""
    kind: str = "structure"
    ids: set | None = None
    keys: set = dataclasses.field(default_factory=set)


class SetTopLayer(Command):
    def __init__(self, label: str, before: dict | None, after: dict | None):
        self.label = label
        self.before, self.after = copy.deepcopy(before), copy.deepcopy(after)

    def do(self, project: Project) -> None:
        project.top_layer = Screen.from_dict(self.after) if self.after else None

    def undo(self, project: Project) -> None:
        project.top_layer = Screen.from_dict(self.before) if self.before else None


class ReplaceProjectData(Command):
    """Sustituye el contenido del proyecto (cambios externos del YAML), deshacible."""

    def __init__(self, label: str, before: dict, after: dict):
        self.label = label
        self.before, self.after = copy.deepcopy(before), copy.deepcopy(after)

    @staticmethod
    def _apply(project: Project, d: dict) -> None:
        new = Project.from_dict(d)
        for f in dataclasses.fields(Project):
            setattr(project, f.name, getattr(new, f.name))

    def do(self, project: Project) -> None:
        self._apply(project, self.after)

    def undo(self, project: Project) -> None:
        self._apply(project, self.before)


def _style_list(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return [str(v) for v in value if isinstance(v, str)]
    return []


def _style_value(ids: list[str]) -> Any:
    """ESPHome admite `styles: id` o `styles: [a, b]`."""
    if not ids:
        return None
    return ids[0] if len(ids) == 1 else list(ids)


class SetStylesTheme(Command):
    """Cambia las definiciones de estilo y el tema del proyecto."""

    def __init__(self, label: str, before: dict, after: dict):
        self.label = label
        self.before, self.after = copy.deepcopy(before), copy.deepcopy(after)

    @staticmethod
    def _apply(project: Project, d: dict) -> None:
        from olvgl.domain.model import StyleDef
        project.styles = [StyleDef.from_dict(st) for st in d["styles"]]
        if d.get("theme"):
            project.lvgl_extra["theme"] = copy.deepcopy(d["theme"])
        else:
            project.lvgl_extra.pop("theme", None)

    def do(self, project: Project) -> None:
        self._apply(project, self.after)

    def undo(self, project: Project) -> None:
        self._apply(project, self.before)


class ProjectViewModel:
    def __init__(self, project: Project | None = None, *,
                 generator: Callable[[Project], str] | None = None,
                 saver: Callable[[Project, str], None] | None = None,
                 loader: Callable[[str], Project] | None = None,
                 importer: Callable[..., tuple[Project, Any]] | None = None,
                 sync_factory: Callable[[str], Any] | None = None):
        self._generator = generator
        self._sync_factory = sync_factory
        self.sync = None                    # SyncSession con el YAML vinculado (Fase 3)
        self.sync_error: str | None = None
        self._saver = saver
        self._loader = loader
        self._importer = importer

        self.project_changed = Signal()     # cualquier cambio del modelo
        self.project_replaced = Signal()    # nuevo/abrir/importar
        self.selection_changed = Signal()   # (lista de ids)
        self.screen_changed = Signal()      # (id de pantalla)
        self.dirty_changed = Signal()       # (bool)
        self.history_changed = Signal()
        self.path_changed = Signal()        # (ruta o None)
        self.layout_changed = Signal()      # cambia la vista sin cambiar el modelo (pestaña activa)
        self.sync_changed = Signal()        # vínculo/estado de la sincronización con el YAML
        self.sync_message = Signal()        # (texto) avisos de sincronización para la interfaz

        self.history = History()
        self.project: Project = project or new_project()
        self.path: str | None = None
        self.selection: list[str] = []
        self.current_screen_id: str = self.project.screens[0].id if self.project.screens else ""
        self.last_change = ChangeInfo()
        self.last_merge = None                       # resultado de la última fusión al guardar
        self._disk_hash: str | None = None
        self._disk_base: dict | None = None
        self.clipboard: list[dict] = []
        self.grid_size = 10
        self.snap = True
        self._last_dirty = False

        # Disposición: la capa de presentación puede aportar medidas reales
        self.measure_text: Callable | None = None
        self.image_size: Callable[[str], "tuple[int, int] | None"] | None = None
        self.active_tabs: dict[str, int] = {}
        self._version = 0
        self._layout_cache: dict[str, tuple[int, dict[str, Box]]] = {}

    # ================================================================ proyecto
    @staticmethod
    def repair_duplicate_auto_ids(project: Project) -> int:
        """Da un id nuevo a los widgets sin id propio que comparten id automático con otro
        (proyectos guardados con el fallo de copiar y pegar de la 0.10.0b1)."""
        seen: set[str] = set()
        dups = []
        for _s, w in project.iter_widgets():
            if w.id in seen and w.auto_id:
                dups.append(w)
            seen.add(w.id)
        for w in dups:
            taken = seen | {i[1:] for i in seen if i.startswith("_")}
            w.id = "_" + unique_id(w.id.lstrip("_"), taken)
            seen.add(w.id)
        return len(dups)

    def replace_project(self, project: Project, path: str | None = None) -> None:
        self.repair_duplicate_auto_ids(project)
        self.project = project
        self.path = path
        self.history.clear()
        self.selection = []
        self.active_tabs = {}
        self._bump()
        self.last_change = ChangeInfo()
        self._disk_hash, self._disk_base = None, None
        self.current_screen_id = project.screens[0].id if project.screens else ""
        self.project_replaced.emit()
        self.project_changed.emit()
        self.selection_changed.emit([])
        self.screen_changed.emit(self.current_screen_id)
        self.history_changed.emit()
        self.path_changed.emit(path)
        self._emit_dirty(force=True)

    def new(self, name: str = "Nuevo proyecto", display: DisplayProfile | None = None, rotation: int = 0) -> None:
        self.unlink_source()
        self.replace_project(new_project(name, display, rotation))

    def set_orientation(self, rotation: int) -> bool:
        """Gira la pantalla (0/90/180/270): intercambia ancho y alto si hace falta y escribe
        `lvgl: rotation:` (ESPHome 2026.4+ gira también el táctil). Un solo paso de deshacer."""
        from olvgl.domain.model import parse_rotation, rotate_display
        new = parse_rotation(rotation)
        old = self.project.rotation
        if new == old:
            return False
        p = self.project.clone()
        p.display = rotate_display(p.display, old, new)
        if new:
            p.lvgl_extra["rotation"] = new
        else:
            p.lvgl_extra.pop("rotation", None)
        return self.apply_project("Orientación de la pantalla", p, self.current_screen_id, keep_selection=True)

    def set_display_keep_orientation(self, display: DisplayProfile) -> None:
        """Cambia de placa (tamaño natural, apaisado) manteniendo la orientación elegida."""
        from olvgl.domain.model import rotate_display
        self.set_project_meta(display=rotate_display(display, 0, self.project.rotation))

    def open(self, path: str) -> None:
        """Abre un .olvgl. Si estaba vinculado a un YAML que existe, se revincula
        (sin escribir); la interfaz decide qué hacer si difieren."""
        if not self._loader:
            raise RuntimeError("No hay cargador configurado")
        project = self._loader(path)
        self.unlink_source()
        self.replace_project(project, path)
        self._remember_disk(path)
        src = project.source.get("path") if project.source else None
        if src and project.source.get("linked") and os.path.exists(src):
            self.link_source(src, write_now=False)

    def import_yaml(self, path: str, display: DisplayProfile | None = None, link: bool = True):
        """Importa un YAML de ESPHome como proyecto nuevo. Si se puede, lo deja
        vinculado al fichero (Fase 3): los cambios se escribirán en él."""
        if not self._importer:
            raise RuntimeError("No hay importador configurado")
        project, report = self._importer(path, display)
        self.unlink_source()
        self.replace_project(project, None)
        linked = link and not project.source.get("from_html") and self.link_source(path, write_now=False)
        if linked:
            self.history.mark_clean()
            self._emit_dirty(force=True)
        else:
            self.mark_dirty_external()
        return report

    # ================================================================ sincronización (Fase 3)
    @property
    def document_path(self) -> str | None:
        """El fichero del proyecto: el .olvgl o, si no hay, el YAML vinculado."""
        return self.path or (self.sync.path if self.sync is not None else None)

    @property
    def linked(self) -> bool:
        return self.sync is not None

    def link_source(self, path: str, write_now: bool = True) -> bool:
        """Vincula el proyecto a un YAML. Devuelve False (y deja el motivo en
        sync_error) si el fichero no se puede sincronizar directamente."""
        if not self._sync_factory:
            self.sync_error = "Sincronización no disponible"
            return False
        try:
            self.sync = self._sync_factory(path)
        except Exception as exc:   # SyncUnsupported, OSError…
            self.sync = None
            self.sync_error = str(exc)
            self.sync_changed.emit()
            return False
        self.sync_error = None
        self.project.source = dict(self.project.source, path=os.path.abspath(path), kind="esphome-yaml",
                                   linked=True)
        self.sync_changed.emit()
        if write_now:
            self.sync_to_source()
        return True

    def unlink_source(self) -> None:
        if self.sync is not None:
            self.sync = None
            if self.project.source:
                self.project.source["linked"] = False
            self.sync_changed.emit()

    def sync_to_source(self):
        """Escribe en el YAML vinculado los cambios del editor (merge a 3 bandas)."""
        if self.sync is None:
            return None
        outcome = self.sync.write(self.project)
        if outcome.merged_external:
            # el fichero tenía cambios hechos a mano: el modelo los incorpora
            self._reload_from_text(outcome.text, "Cambios externos en el YAML")
        self.history.mark_clean()
        self._emit_dirty(force=True)
        if outcome.conflicts:
            self.sync_message.emit("Conflicto: el YAML y el editor cambiaron lo mismo; se aplicó el editor en "
                                   + ", ".join(outcome.conflicts[:4]))
        if outcome.rewritten:
            self.sync_message.emit("Se reescribieron enteras estas secciones del YAML: "
                                   + ", ".join(outcome.rewritten))
        self.sync_changed.emit()
        return outcome

    def reload_source(self) -> None:
        """Descarta la versión del editor y carga el YAML vinculado."""
        if self.sync is None:
            return
        text = self.sync.ports.read(self.sync.path)
        self._reload_from_text(text, "Cargar desde el YAML")
        self.sync.accept_external(text)
        self.history.mark_clean()
        self._emit_dirty(force=True)
        self.sync_changed.emit()

    def check_external(self) -> bool:
        """Llamar cuando el fichero vinculado cambia en disco. True si se incorporó algo."""
        if self.sync is None:
            return False
        try:
            text = self.sync.external_text()
        except OSError:
            return False
        if text is None:
            return False
        if self.dirty:
            self.sync_to_source()   # mezcla ambos lados y recarga
            return True
        try:
            self._reload_from_text(text, "Cambio externo en el YAML")
        except Exception as exc:     # YAML a medio escribir o inválido: se ignora hasta el próximo cambio
            self.sync_message.emit(f"El YAML vinculado no se puede leer ahora mismo: {exc}")
            return False
        self.sync.accept_external(text)
        self.history.mark_clean()
        self._emit_dirty(force=True)
        self.sync_changed.emit()
        self.sync_message.emit("Cambios del YAML incorporados (Ctrl+Z para deshacerlos)")
        return True

    def _reload_from_text(self, text: str, label: str) -> None:
        project, report = self.sync.import_text(text)
        if any("resolución" in w for w in getattr(report, "warnings", [])):
            project.display = self.project.display
        project.source = dict(self.project.source)
        before = self.project.to_dict()
        after = project.to_dict()
        if before == after:
            return
        self._execute(ReplaceProjectData(label, before, after))
        if self.current_screen is None and self.project.screens:
            self.current_screen_id = self.project.screens[0].id
            self.screen_changed.emit(self.current_screen_id)

    def apply_project(self, label: str, project, screen_id: str | None = None, keep_selection: bool = False) -> bool:
        """Sustituye el proyecto por `project` (IA, refactorizaciones) como un único
        cambio que se puede deshacer. Devuelve False si no cambia nada. Con
        `keep_selection` se conserva la selección (p. ej. al añadir una fuente)."""
        project.source = dict(self.project.source)
        before = self.project.to_dict()
        after = project.to_dict()
        if before == after:
            return False
        keep = list(self.selection) if keep_selection else []
        self.selection = []
        self._execute(ReplaceProjectData(label, before, after))
        keep = [i for i in keep if self.project.widget(i) is not None]
        self.selection = keep
        self.selection_changed.emit(list(keep))
        target = screen_id if screen_id and self.project.screen(screen_id) else self.current_screen_id
        if self.project.screen(target or "") is None and self.project.screens:
            target = self.project.screens[0].id
        if target and (target != self.current_screen_id or not keep_selection):
            self.current_screen_id = target
            self.screen_changed.emit(target)
        return True

    def save(self, path: str | None = None) -> str:
        if not self._saver:
            raise RuntimeError("No hay guardador configurado")
        path = path or self.path
        if not path:
            raise ValueError("Ruta de guardado no indicada")
        self.last_merge = None
        if (path == self.path and self._disk_hash and self._disk_base is not None and self._loader
                and os.path.exists(path) and _file_hash(path) != self._disk_hash):
            # otra persona guardó el mismo fichero desde que lo abrimos: se fusiona
            from olvgl.domain.project_merge import merge_projects
            base = Project.from_dict(self._disk_base)
            theirs = self._loader(path)
            result = merge_projects(base, self.project, theirs)
            result.project.source = dict(self.project.source)
            self.apply_project("Fusionar cambios de otra persona", result.project)
            self.last_merge = result
            self.sync_message.emit(f"Fusionados {result.from_theirs} cambios de otra persona"
                                   + (f"; {len(result.conflicts)} conflicto(s): se mantiene lo tuyo"
                                      if result.conflicts else ""))
        self._saver(self.project, path)
        self.path = path
        self._remember_disk(path)
        self.history.mark_clean()
        self.path_changed.emit(path)
        self._emit_dirty(force=True)
        return path

    def _remember_disk(self, path: str) -> None:
        """Lo que hay en disco ahora: la base de una futura fusión."""
        try:
            self._disk_hash = _file_hash(path)
            self._disk_base = self.project.to_dict()
        except OSError:
            self._disk_hash, self._disk_base = None, None

    def disk_changed(self) -> bool:
        """True si alguien ha guardado el .olvgl desde que lo abrimos o guardamos."""
        return bool(self.path and self._disk_hash and os.path.exists(self.path)
                    and _file_hash(self.path) != self._disk_hash)

    @property
    def dirty(self) -> bool:
        return not self.history.is_clean()

    def mark_dirty_external(self) -> None:
        """Proyectos recuperados o importados: quedan como no guardados."""
        self.history._clean_index = None
        self._emit_dirty(force=True)

    def generate_yaml(self) -> str:
        if not self._generator:
            raise RuntimeError("No hay generador configurado")
        return self._generator(self.project)

    def validate(self) -> list[str]:
        return self.project.validate()

    def resolve_path(self, path: str) -> str:
        if not path or os.path.isabs(path) or not self.path:
            return path
        return os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(self.path)), path))

    # ================================================================ disposición
    def _bump(self) -> None:
        self._version += 1

    def layout_context(self) -> LayoutContext:
        return LayoutContext(self.project, self.measure_text, self.image_size, self.active_tabs)

    def layout(self, screen_id: str | None = None) -> dict[str, Box]:
        sid = screen_id or self.current_screen_id
        cached = self._layout_cache.get(sid)
        if cached and cached[0] == self._version:
            return cached[1]
        screen = self.project.screen(sid)
        boxes = compute_layout(self.project, screen, self.layout_context()) if screen else {}
        self._layout_cache[sid] = (self._version, boxes)
        return boxes

    def box(self, widget_id: str) -> Box | None:
        loc = self.project.locate(widget_id)
        if loc is None:
            return None
        return self.layout(loc.screen.id).get(widget_id)

    def invalidate_layout(self) -> None:
        """Llamar cuando cambian medidas externas (fuentes, imágenes)."""
        self._bump()
        self.layout_changed.emit()

    def set_active_tab(self, container_id: str, index: int) -> None:
        if self.active_tabs.get(container_id, 0) == index:
            return
        self.active_tabs[container_id] = index
        self._bump()
        self.layout_changed.emit()

    def _reveal(self, widget_id: str) -> None:
        """Activa las pestañas necesarias para que el widget sea visible."""
        loc = self.project.locate(widget_id)
        while loc is not None and loc.parent is not None:
            parent = loc.parent
            if parent.type in catalog.CHILD_LISTS:
                self.set_active_tab(parent.id, loc.index)
            loc = self.project.locate(parent.id)

    # ================================================================ ejecución de comandos
    def _execute(self, command: Command, mergeable: bool = False) -> None:
        self.history.push(command, self.project, mergeable=mergeable)
        self._after_change(command)

    @staticmethod
    def describe_change(command: Command | None) -> "ChangeInfo":
        """Qué ha cambiado, para que las vistas actualicen sólo lo necesario."""
        if isinstance(command, cmd.UpdateWidgets):
            ids = set(command.changes)
            ids |= {a.get("id") for _b, a in command.changes.values()}
            keys: set[str] = set()
            for before, after in command.changes.values():
                for k in set(before) | set(after):
                    if before.get(k) != after.get(k):
                        keys.add(k)
            return ChangeInfo("geometry" if keys <= GEOMETRY_KEYS else "widgets", ids, keys)
        return ChangeInfo("structure", None, set())

    def _after_change(self, command: Command | None = None) -> None:
        self.last_change = self.describe_change(command)
        self._bump()
        ids = {w.id for _, w in self.project.iter_widgets()}
        sel = [i for i in self.selection if i in ids]
        if self.project.screen(self.current_screen_id) is None and self.project.screens:
            self.current_screen_id = self.project.screens[0].id
            self.screen_changed.emit(self.current_screen_id)
        self.project_changed.emit()
        if sel != self.selection:
            self.selection = sel
            self.selection_changed.emit(list(sel))
        self.history_changed.emit()
        self._emit_dirty()

    def _emit_dirty(self, force: bool = False) -> None:
        d = self.dirty
        if force or d != self._last_dirty:
            self._last_dirty = d
            self.dirty_changed.emit(d)

    def undo(self) -> bool:
        command = self.history._undo[-1] if self.history.can_undo else None
        ok = self.history.undo(self.project)
        if ok:
            self._after_change(command)
        return ok

    def redo(self) -> bool:
        command = self.history._redo[-1] if self.history.can_redo else None
        ok = self.history.redo(self.project)
        if ok:
            self._after_change(command)
        return ok

    def end_interaction(self) -> None:
        """Cierra la fusión de comandos (p. ej. al soltar un control deslizante)."""
        self.history.break_merge()

    # ================================================================ selección y pantallas
    @property
    def current_screen(self) -> Screen | None:
        return self.project.screen(self.current_screen_id)

    def set_current_screen(self, screen_id: str) -> None:
        if screen_id == self.current_screen_id or self.project.screen(screen_id) is None:
            return
        self.current_screen_id = screen_id
        self.set_selection([])
        self.screen_changed.emit(screen_id)

    def set_selection(self, ids: Iterable[str]) -> None:
        ids = [i for i in dict.fromkeys(ids) if self.project.widget(i) is not None]
        if ids == self.selection:
            return
        if ids:
            loc = self.project.locate(ids[0])
            if loc and loc.screen.id != self.current_screen_id:
                self.current_screen_id = loc.screen.id
                self.screen_changed.emit(self.current_screen_id)
            for i in ids:
                self._reveal(i)
        self.selection = ids
        self.selection_changed.emit(list(ids))

    def select_all(self) -> None:
        s = self.current_screen
        if s:
            self.set_selection([w.id for w in s.widgets])

    def selected_widgets(self) -> list[Widget]:
        return [w for w in (self.project.widget(i) for i in self.selection) if w is not None]

    def widget(self, widget_id: str) -> Widget | None:
        return self.project.widget(widget_id)

    # ================================================================ widgets
    def snap_value(self, v: float) -> int:
        if self.snap and self.grid_size > 1:
            return int(round(v / self.grid_size) * self.grid_size)
        return int(round(v))

    def container_at(self, x: float, y: float, screen_id: str | None = None) -> str | None:
        """Contenedor visible (obj, pestaña…) más profundo bajo el punto, o None."""
        sid = screen_id or self.current_screen_id
        screen = self.project.screen(sid)
        if screen is None:
            return None
        boxes = self.layout(sid)
        best = None

        def visit(lst: list[Widget]) -> None:
            nonlocal best
            for w in lst:
                b = boxes.get(w.id)
                if b is None or not b.shown or b.hidden:
                    continue
                r = b.rect
                if r.x <= x < r.right and r.y <= y < r.bottom:
                    if w.type in ("obj", "tab", "tile"):
                        best = w.id
                    visit(w.children)

        visit(screen.widgets)
        return best

    def add_widget(self, widget_type: str, x: float | None = None, y: float | None = None,
                   centered: bool = True, props: dict | None = None,
                   screen_id: str | None = None, parent_id: str | None = None) -> str:
        sp = catalog.spec(widget_type)
        sid = screen_id or self.current_screen_id
        if parent_id:
            loc = self.project.locate(parent_id)
            if loc is None:
                raise ValueError("El contenedor no existe")
            sid = loc.screen.id
        screen = self.project.screen(sid)
        if screen is None:
            raise ValueError("No hay pantalla activa")
        w, h = sp.default_size
        origin_x, origin_y = 0.0, 0.0
        limit_w, limit_h = self.project.display.width, self.project.display.height
        if parent_id:
            pb = self.layout(sid).get(parent_id)
            if pb is not None:
                origin_x, origin_y = pb.content.x, pb.content.y
                limit_w, limit_h = pb.content.w, pb.content.h
        if x is None or y is None:
            x = origin_x + (limit_w - w) / 2
            y = origin_y + (limit_h - h) / 2
        elif centered:
            x, y = x - w / 2, y - h / 2
        x, y = self.snap_value(x - origin_x), self.snap_value(y - origin_y)
        x = max(0, min(int(x), max(0, int(limit_w) - w)))
        y = max(0, min(int(y), max(0, int(limit_h) - h)))
        ids = self.project.all_ids()
        n = 1
        while f"{sp.id_prefix}_{n}" in ids:
            n += 1
        wid = f"{sp.id_prefix}_{n}"
        initial = dict(sp.initial_props)
        initial.update(props or {})
        widget = Widget(id=wid, type=widget_type, x=x, y=y, width=w, height=h, props=initial)
        if sp.auto_size:
            widget.width = widget.height = None   # tamaño según el contenido (imagen, texto…)
        if sp.child_type:
            taken = set(ids) | {wid}
            for i in range(sp.initial_children):
                widget.children.append(self._new_child(sp.child_type, i, taken))
        container = self.project.container(sid, parent_id)
        self._execute(cmd.InsertWidgets(f"Añadir {sp.label.lower()}", sid,
                                        [(parent_id, len(container), widget.to_dict())]))
        self.set_selection([wid])
        return wid

    def _new_child(self, child_type: str, index: int, taken: set[str]) -> Widget:
        csp = catalog.spec(child_type)
        n = 1
        while f"{csp.id_prefix}_{n}" in taken:
            n += 1
        cid = f"{csp.id_prefix}_{n}"
        taken.add(cid)
        if child_type == "tab":
            props: dict[str, Any] = {"name": f"Pestaña {index + 1}"}
        else:
            props = {"row": 0, "column": index}
        return Widget(id=cid, type=child_type, x=None, y=None, width=None, height=None, props=props)

    def add_child(self, container_id: str) -> str | None:
        """Añade una pestaña a un tabview o un mosaico a un tileview."""
        loc = self.project.locate(container_id)
        if loc is None:
            return None
        sp = catalog.spec(loc.widget.type)
        if not sp.child_type:
            return None
        child = self._new_child(sp.child_type, len(loc.widget.children), set(self.project.all_ids()))
        self._execute(cmd.InsertWidgets(f"Añadir {catalog.type_label(sp.child_type).lower()}", loc.screen.id,
                                        [(container_id, len(loc.widget.children), child.to_dict())]))
        self.set_active_tab(container_id, len(loc.widget.children) - 1)
        self.set_selection([child.id])
        return child.id

    def delete_widgets(self, ids: Iterable[str] | None = None) -> None:
        ids = list(ids if ids is not None else self.selection)
        ids = [i for i in ids if self.project.widget(i) is not None]
        if not ids:
            return
        self._execute(cmd.RemoveWidgets("Eliminar", self.project, ids))

    def _clone_with_new_ids(self, dicts: list[dict], dx: int, dy: int) -> list[dict]:
        existing = set(self.project.all_ids())
        out = []
        for d in dicts:
            w = Widget.from_dict(d)
            for node in w.walk():
                if node.auto_id:
                    # los ids automáticos llevan «_» delante: se busca uno libre con ese prefijo
                    # (antes «_obj_3» se copiaba como «_obj_3» y dos widgets compartían id)
                    taken = existing | {i[1:] for i in existing if i.startswith("_")}
                    node.id = "_" + unique_id(node.id.lstrip("_"), taken)
                else:
                    node.id = unique_id(node.id, existing)
                existing.add(node.id)
                existing.add(f"{node.id}_label")
            if isinstance(w.x, (int, float)) and not isinstance(w.x, bool):
                w.x = int(w.x + dx)
            if isinstance(w.y, (int, float)) and not isinstance(w.y, bool):
                w.y = int(w.y + dy)
            out.append(w.to_dict())
        return out

    def copy(self, ids: Iterable[str] | None = None) -> int:
        ids = list(ids if ids is not None else self.selection)
        self.clipboard = [w.to_dict() for w in (self.project.widget(i) for i in ids) if w]
        return len(self.clipboard)

    def paste(self, offset: int = 10) -> list[str]:
        screen = self.current_screen
        if not self.clipboard or screen is None:
            return []
        parent_id = None
        if self.selection:
            loc = self.project.locate(self.selection[0])
            if loc and loc.screen.id == screen.id and loc.parent is not None:
                parent_id = loc.parent.id
        container = self.project.container(screen.id, parent_id)
        new = self._clone_with_new_ids(self.clipboard, offset, offset)
        start = len(container)
        self._execute(cmd.InsertWidgets("Pegar", screen.id,
                                        [(parent_id, start + i, d) for i, d in enumerate(new)]))
        ids = [d["id"] for d in new]
        self.clipboard = [dict(d) for d in new]  # pegar de nuevo desplaza otra vez
        self.set_selection(ids)
        return ids

    def duplicate(self, ids: Iterable[str] | None = None, offset: int = 10) -> list[str]:
        ids = list(ids if ids is not None else self.selection)
        locs = [loc for loc in (self.project.locate(i) for i in ids) if loc]
        if not locs:
            return []
        first = locs[0]
        parent_id = first.parent.id if first.parent else None
        same = [loc for loc in locs if loc.screen.id == first.screen.id
                and (loc.parent.id if loc.parent else None) == parent_id]
        new = self._clone_with_new_ids([loc.widget.to_dict() for loc in same], offset, offset)
        start = len(first.container)
        self._execute(cmd.InsertWidgets("Duplicar", first.screen.id,
                                        [(parent_id, start + i, d) for i, d in enumerate(new)]))
        new_ids = [d["id"] for d in new]
        self.set_selection(new_ids)
        return new_ids

    def _update(self, label: str, changes: dict[str, tuple[dict, dict]], merge_key: str = "") -> None:
        changes = {k: v for k, v in changes.items() if v[0] != v[1]}
        if not changes:
            return
        self._execute(cmd.UpdateWidgets(label, changes, merge_key), mergeable=bool(merge_key))

    def move_widgets(self, positions: dict[str, tuple[int, int]]) -> None:
        """Fija x/y (relativos al padre) de varios widgets."""
        changes = {}
        for wid, (x, y) in positions.items():
            w = self.project.widget(wid)
            if w is None:
                continue
            before = w.to_dict()
            after = dict(before, x=int(round(x)), y=int(round(y)))
            changes[wid] = (before, after)
        self._update("Mover", changes)

    def _moved_dict(self, w: Widget, dx: float, dy: float) -> dict | None:
        b = self.box(w.id)
        if b is None or not b.movable:
            return None
        d = w.to_dict()
        if dx:
            d["x"] = int(round(b.rel_x + dx))
        if dy:
            d["y"] = int(round(b.rel_y + dy))
        return d

    def move_by(self, deltas: dict[str, tuple[float, float]], label: str = "Mover",
                merge_key: str = "") -> None:
        """Desplaza widgets en px de pantalla, respetando align y porcentajes."""
        changes = {}
        for wid, (dx, dy) in deltas.items():
            w = self.project.widget(wid)
            if w is None or (not dx and not dy):
                continue
            after = self._moved_dict(w, dx, dy)
            if after is not None:
                changes[wid] = (w.to_dict(), after)
        self._update(label, changes, merge_key=merge_key)

    def nudge(self, dx: int, dy: int) -> None:
        ids = sorted(w.id for w in self.selected_widgets())
        self.move_by({i: (dx, dy) for i in ids}, merge_key="nudge:" + ",".join(ids))

    def set_geometry(self, widget_id: str, rect: tuple[float, float, float, float], merge: bool = False) -> None:
        """Ajusta el rectángulo absoluto (px de pantalla) de un widget."""
        w = self.project.widget(widget_id)
        b = self.box(widget_id)
        if w is None or b is None:
            return
        x, y, width, height = rect
        after = w.to_dict()
        if b.movable:
            dx, dy = x - b.rect.x, y - b.rect.y
            if abs(dx) >= 0.5:
                after["x"] = int(round(b.rel_x + dx))
            if abs(dy) >= 0.5:
                after["y"] = int(round(b.rel_y + dy))
        if b.resizable:
            if abs(width - b.rect.w) >= 0.5:
                after["width"] = max(1, int(round(width)))
            if abs(height - b.rect.h) >= 0.5:
                after["height"] = max(1, int(round(height)))
        self._update("Cambiar geometría", {widget_id: (w.to_dict(), after)},
                     merge_key=f"geom:{widget_id}" if merge else "")

    def set_geom_value(self, widget_id: str, key: str, value: Any) -> str | None:
        """Fija x/y/width/height tal como se escribe en ESPHome (int, '50%', SIZE_CONTENT o None)."""
        if key not in ("x", "y", "width", "height"):
            raise ValueError(key)
        w = self.project.widget(widget_id)
        if w is None:
            return "El widget no existe"
        if isinstance(value, str):
            v = value.strip()
            if v == "":
                value = None
            elif v.lstrip("-").isdigit():
                value = int(v)
            elif v.upper() == "SIZE_CONTENT" and key in ("width", "height"):
                value = "SIZE_CONTENT"
            elif v.endswith("%") and v[:-1].replace(".", "", 1).lstrip("-").isdigit():
                value = v
            else:
                return "Usa un número de píxeles, un porcentaje (50%) o SIZE_CONTENT"
        before = w.to_dict()
        self._update("Cambiar geometría", {widget_id: (before, dict(before, **{key: value}))})
        return None

    def set_prop(self, ids: Iterable[str], name: str, value: Any, merge: bool = False) -> None:
        if name.split(".")[-1] == "text_font" and isinstance(value, str):
            self.ensure_font(value)                  # una fuente de la biblioteca se añade al elegirla
        changes = {}
        for wid in ids:
            w = self.project.widget(wid)
            if w is None:
                continue
            sp = catalog.spec(w.type).prop(name)
            v = value
            if sp is not None and sp.kind == catalog.KIND_COLOR and isinstance(v, str):
                v = normalize_color(v)
            if sp is None and catalog.STATE_KEY_COLORS(name) and isinstance(v, str) and v.startswith("#"):
                v = normalize_color(v)
            before = w.to_dict()
            drop = v is None or (sp is not None and v == sp.default and name != "text")
            props = catalog.set_path(before["props"], name, None if drop else v)
            changes[wid] = (before, dict(before, props=props))
        key = f"prop:{name}:" + ",".join(sorted(changes)) if merge else ""
        self._update(f"Cambiar {name.split('.')[-1]}", changes, merge_key=key)

    def set_raw_prop(self, ids: Iterable[str], key: str, value: Any) -> None:
        """Fija (o quita, con None) cualquier propiedad ESPHome sin valores por defecto."""
        changes = {}
        for wid in ids:
            w = self.project.widget(wid)
            if w is None:
                continue
            before = w.to_dict()
            props = dict(before["props"])
            if value is None:
                props.pop(key, None)
            else:
                props[key] = copy.deepcopy(value)
            changes[wid] = (before, dict(before, props=props))
        self._update(f"Cambiar {key}", changes)

    def replace_props(self, widget_id: str, scope: Iterable[str], values: dict[str, Any]) -> None:
        """Sustituye de una vez las propiedades del ámbito `scope` por `values`
        (las del ámbito que no estén en `values` se eliminan; el orden se conserva)."""
        w = self.project.widget(widget_id)
        if w is None:
            return
        scope = set(scope) | set(values)
        before = w.to_dict()
        props: dict[str, Any] = {}
        for k, v in before["props"].items():
            if k not in scope:
                props[k] = v
            elif k in values:
                props[k] = copy.deepcopy(values[k])
        for k, v in values.items():
            if k not in props:
                props[k] = copy.deepcopy(v)
        self._update("Editar propiedades", {widget_id: (before, dict(before, props=props))})

    def replace_screen_props(self, screen_id: str, values: dict[str, Any]) -> None:
        s = self.project.screen(screen_id)
        if s is None:
            return
        before = cmd.UpdateScreen.snapshot(s)
        after = dict(copy.deepcopy(before), props=copy.deepcopy(values))
        if after != before:
            self._execute(cmd.UpdateScreen("Editar propiedades de la página", before, after))

    def rename_widget(self, old_id: str, new_id: str) -> str | None:
        """Devuelve un mensaje de error o None si se ha renombrado."""
        new_id = new_id.strip()
        w = self.project.widget(old_id)
        if w is None:
            return "El widget no existe"
        if new_id == old_id:
            return None
        if not is_valid_id(new_id):
            return "Id no válido: usa letras, números y _ (sin empezar por número)"
        all_ids = self.project.all_ids()
        if new_id in all_ids or (w.type == "button" and f"{new_id}_label" in all_ids):
            return f"Ya existe un elemento con id «{new_id}»"
        before = w.to_dict()
        was_selected = old_id in self.selection
        self.selection = [new_id if i == old_id else i for i in self.selection]
        if old_id in self.active_tabs:
            self.active_tabs[new_id] = self.active_tabs.pop(old_id)
        self._update("Renombrar", {old_id: (before, dict(before, id=new_id, auto_id=False))})
        if was_selected:
            self.selection_changed.emit(list(self.selection))
        return None

    def set_events(self, widget_id: str, events: list[EventHandler]) -> None:
        w = self.project.widget(widget_id)
        if w is None:
            return
        merged: dict[str, EventHandler] = {}
        for e in events:            # ESPHome no admite el mismo disparador dos veces
            if e.trigger in merged:
                merged[e.trigger] = EventHandler(e.trigger, list(merged[e.trigger].actions) + list(e.actions))
            else:
                merged[e.trigger] = e
        before = w.to_dict()
        after = dict(before, events=[e.to_dict() for e in merged.values()])
        self._update("Editar eventos", {widget_id: (before, after)})

    # ---------------------------------------------------------------- organizar
    def align(self, mode: str) -> None:
        if mode not in ALIGN_MODES:
            raise ValueError(mode)
        ws = [w for w in self.selected_widgets() if self.box(w.id) is not None]
        if not ws:
            return
        boxes = {w.id: self.box(w.id) for w in ws}
        if len(ws) == 1:  # respecto al área de contenido del padre
            b = boxes[ws[0].id]
            pb = self.box(b.parent) if b.parent else None
            if pb is not None:
                c = pb.content
                left, top, right, bottom = c.x, c.y, c.right, c.bottom
            else:
                left, top = 0, 0
                right, bottom = self.project.display.width, self.project.display.height
        else:
            left = min(b.rect.x for b in boxes.values())
            top = min(b.rect.y for b in boxes.values())
            right = max(b.rect.right for b in boxes.values())
            bottom = max(b.rect.bottom for b in boxes.values())
        deltas = {}
        for w in ws:
            r = boxes[w.id].rect
            nx, ny = r.x, r.y
            if mode == "left":
                nx = left
            elif mode == "right":
                nx = right - r.w
            elif mode == "hcenter":
                nx = round((left + right) / 2 - r.w / 2)
            elif mode == "top":
                ny = top
            elif mode == "bottom":
                ny = bottom - r.h
            elif mode == "vcenter":
                ny = round((top + bottom) / 2 - r.h / 2)
            deltas[w.id] = (nx - r.x, ny - r.y)
        self.move_by(deltas, label="Alinear")

    def distribute(self, axis: str) -> None:
        ws = [w for w in self.selected_widgets() if self.box(w.id) is not None]
        if len(ws) < 3:
            return
        horizontal = axis == "h"
        boxes = {w.id: self.box(w.id).rect for w in ws}
        ws = sorted(ws, key=lambda w: boxes[w.id].x if horizontal else boxes[w.id].y)
        first, last = boxes[ws[0].id], boxes[ws[-1].id]
        if horizontal:
            total = last.right - first.x
            used = sum(boxes[w.id].w for w in ws)
            pos = first.x
        else:
            total = last.bottom - first.y
            used = sum(boxes[w.id].h for w in ws)
            pos = first.y
        gap = (total - used) / (len(ws) - 1)
        deltas = {}
        for w in ws:
            r = boxes[w.id]
            if horizontal:
                deltas[w.id] = (round(pos) - r.x, 0)
                pos += r.w + gap
            else:
                deltas[w.id] = (0, round(pos) - r.y)
                pos += r.h + gap
        self.move_by(deltas, label="Distribuir")

    # ---------------------------------------------------------------- mover en el árbol (arrastrar y soltar)
    def can_contain(self, parent_id: str | None, widget_type: str) -> bool:
        """¿Puede `parent_id` (None = la pantalla) tener como hijo un widget de este tipo?"""
        if parent_id is None:
            return widget_type not in catalog.PSEUDO_TYPES
        parent = self.project.widget(parent_id)
        if parent is None:
            return False
        if parent.type in catalog.CHILD_LISTS:
            return catalog.CHILD_LISTS[parent.type][1] == widget_type
        return parent.type in catalog.CONTAINER_TYPES and widget_type not in catalog.PSEUDO_TYPES

    def move_widgets_to(self, ids: Iterable[str], screen_id: str | None = None, parent_id: str | None = None,
                        anchor_id: str | None = None, after: bool = True, keep_position: bool = True) -> list[str]:
        """Mueve widgets a otro sitio del árbol (otro padre, otra página u otro orden).

        Se colocan junto a `anchor_id` (detrás de él en la pila si `after`, es decir, dibujados encima)
        o, sin ancla, al final (encima de todo). Con `keep_position` conservan su posición en pantalla.
        Devuelve los ids movidos ([] si el movimiento no es posible o no cambia nada)."""
        if parent_id:
            ploc = self.project.locate(parent_id)
            if ploc is None:
                return []
            screen_id = ploc.screen.id
        screen_id = screen_id or self.current_screen_id
        if self.project.screen(screen_id) is None:
            return []
        wanted = [i for i in dict.fromkeys(ids) if self.project.locate(i) is not None]
        locs = []
        for wid in wanted:
            loc = self.project.locate(wid)
            anc, inside = loc.parent, False                 # si un antecesor también se mueve, va con él
            while anc is not None:
                if anc.id in wanted:
                    inside = True
                    break
                pl = self.project.locate(anc.id)
                anc = pl.parent if pl else None
            if not inside:
                locs.append(loc)
        if not locs or anchor_id in {lc.widget.id for lc in locs}:
            return []
        # el destino no puede estar dentro de lo que se mueve
        p = parent_id
        while p is not None:
            if p in {lc.widget.id for lc in locs}:
                return []
            pl = self.project.locate(p)
            p = pl.parent.id if pl and pl.parent else None
        for lc in locs:
            if not self.can_contain(parent_id, lc.widget.type):
                return []
            if lc.widget.type in catalog.PSEUDO_TYPES and (lc.parent.id if lc.parent else None) != parent_id:
                return []                                    # una pestaña no sale de su tabview
        target = self.project.container(screen_id, parent_id)
        moved = [lc.widget.id for lc in locs]
        remaining = [w.id for w in target if w.id not in moved]
        if anchor_id is not None and anchor_id not in remaining:
            return []
        pos = remaining.index(anchor_id) + (1 if after else 0) if anchor_id is not None else len(remaining)
        new_order = remaining[:pos] + moved + remaining[pos:]
        same_place = all((lc.screen.id, lc.parent.id if lc.parent else None) == (screen_id, parent_id) for lc in locs)
        if same_place and new_order == [w.id for w in target]:
            return []
        # posición absoluta antes y origen del nuevo padre
        origin = (0.0, 0.0)
        if parent_id:
            pb = self.layout(screen_id).get(parent_id)
            if pb is not None:
                origin = (pb.content.x, pb.content.y)
        dicts = []
        for lc in locs:
            d = lc.widget.to_dict()
            b = self.layout(lc.screen.id).get(lc.widget.id)
            moving_parent = (lc.screen.id, lc.parent.id if lc.parent else None) != (screen_id, parent_id)
            if keep_position and moving_parent and b is not None and "align" not in lc.widget.props:
                for key, absolute, o in (("x", b.rect.x, origin[0]), ("y", b.rect.y, origin[1])):
                    cur = d.get(key)
                    if cur is None or (isinstance(cur, (int, float)) and not isinstance(cur, bool)):
                        d[key] = int(round(absolute - o))
            dicts.append(d)
        remove = cmd.RemoveWidgets("Mover en el árbol", self.project, moved)
        insert = cmd.InsertWidgets("Mover en el árbol", screen_id,
                                   [(parent_id, pos + i, d) for i, d in enumerate(dicts)])
        self._execute(CompositeCommand("Mover en el árbol", [remove, insert]))
        if screen_id != self.current_screen_id:
            self.set_current_screen(screen_id)
        self.set_selection(moved)
        return moved

    def change_order(self, how: str) -> None:
        """how: front, back, forward, backward (dentro del contenedor del primer seleccionado)."""
        if not self.selection:
            return
        loc = self.project.locate(self.selection[0])
        if loc is None:
            return
        parent_id = loc.parent.id if loc.parent else None
        before = [w.id for w in loc.container]
        sel = [i for i in before if i in self.selection]
        rest = [i for i in before if i not in self.selection]
        if how == "front":
            after = rest + sel
        elif how == "back":
            after = sel + rest
        else:
            after = list(before)
            rng = range(len(after) - 2, -1, -1) if how == "forward" else range(1, len(after))
            for i in rng:
                j = i + 1 if how == "forward" else i - 1
                if after[i] in self.selection and after[j] not in self.selection:
                    after[i], after[j] = after[j], after[i]
        if after != before:
            self._execute(cmd.ReorderWidgets("Cambiar orden", loc.screen.id, before, after, parent_id))

    # ================================================================ pantallas
    def add_screen(self, name: str = "Pantalla") -> str:
        sid = unique_id(sanitize_id(name, "page"), self.project.all_ids() | {TOP_LAYER_ID})
        cur = self.current_screen
        screen = Screen(id=sid, name=name, bg_color=cur.bg_color if cur and cur.id != TOP_LAYER_ID else None)
        self._execute(cmd.InsertScreen("Añadir pantalla", len(self.project.screens), screen.to_dict()))
        self.set_current_screen(sid)
        return sid

    def remove_screen(self, screen_id: str) -> bool:
        if screen_id == TOP_LAYER_ID and self.project.top_layer is not None:
            self._execute(SetTopLayer("Eliminar capa superior", self.project.top_layer.to_dict(), None))
            return True
        if len(self.project.screens) <= 1 or self.project.screen(screen_id) is None:
            return False
        self._execute(cmd.RemoveScreen("Eliminar pantalla", self.project, screen_id))
        return True

    def ensure_top_layer(self) -> str:
        if self.project.top_layer is None:
            tl = Screen(TOP_LAYER_ID, "Capa superior")
            self._execute(SetTopLayer("Crear capa superior", None, tl.to_dict()))
        self.set_current_screen(TOP_LAYER_ID)
        return TOP_LAYER_ID

    def update_screen(self, screen_id: str, *, name: str | None = None, new_id: str | None = None,
                      bg_color: str | None = None, merge: bool = False,
                      clear_bg: bool = False) -> str | None:
        s = self.project.screen(screen_id)
        if s is None:
            return "La pantalla no existe"
        before = cmd.UpdateScreen.snapshot(s)
        after = copy.deepcopy(before)
        if name is not None:
            after["name"] = name
        if bg_color is not None:
            after["bg_color"] = normalize_color(bg_color)
        if clear_bg:
            after["bg_color"] = None
        if new_id is not None and new_id != s.id:
            if screen_id == TOP_LAYER_ID:
                return "La capa superior no se puede renombrar"
            if not is_valid_id(new_id):
                return "Id no válido: usa letras, números y _ (sin empezar por número)"
            if new_id in self.project.all_ids() or new_id == TOP_LAYER_ID:
                return f"Ya existe un elemento con id «{new_id}»"
            after["id"] = new_id
        if after == before:
            return None
        self._execute(cmd.UpdateScreen("Editar pantalla", before, after,
                                       merge_key=f"screen:{screen_id}" if merge else ""),
                      mergeable=merge)
        if after["id"] != before["id"] and self.current_screen_id == before["id"]:
            self.current_screen_id = after["id"]
            self.screen_changed.emit(after["id"])
        return None

    def set_screen_prop(self, screen_id: str, key: str, value: Any) -> None:
        s = self.project.screen(screen_id)
        if s is None:
            return
        before = cmd.UpdateScreen.snapshot(s)
        after = copy.deepcopy(before)
        if value is None:
            after["props"].pop(key, None)
        else:
            after["props"][key] = copy.deepcopy(value)
        if after != before:
            self._execute(cmd.UpdateScreen(f"Cambiar {key}", before, after))

    def move_screen(self, screen_id: str, delta: int) -> None:
        before = [s.id for s in self.project.screens]
        if screen_id not in before:
            return
        i = before.index(screen_id)
        j = max(0, min(len(before) - 1, i + delta))
        if i == j:
            return
        after = list(before)
        after.insert(j, after.pop(i))
        self._execute(cmd.ReorderScreens("Mover pantalla", before, after))

    # ================================================================ imágenes
    def add_image(self, path: str, image_id: str | None = None) -> str:
        base = image_id or os.path.splitext(os.path.basename(path))[0]
        iid = unique_id("img_" + sanitize_id(base, "img") if not image_id else sanitize_id(base),
                        self.project.all_ids())
        self._execute(cmd.InsertImage("Añadir imagen", {
            "id": iid, "path": os.path.abspath(path), "type": "RGB565", "transparency": "alpha_channel"}))
        return iid

    def remove_image(self, image_id: str) -> None:
        if self.project.image(image_id) is None:
            return
        steps: list[Command] = []
        for _, w in self.project.iter_widgets():
            if w.type == "image" and w.props.get("src") == image_id:
                before = w.to_dict()
                props = dict(before["props"])
                props.pop("src", None)
                steps.append(cmd.UpdateWidgets("", {w.id: (before, dict(before, props=props))}))
        steps.append(cmd.RemoveImage("", self.project, image_id))
        self._execute(CompositeCommand("Eliminar imagen", steps))

    # ================================================================ metadatos
    def set_project_meta(self, *, name: str | None = None, display: DisplayProfile | None = None,
                         device_name: str | None = None) -> None:
        before = cmd.UpdateProjectMeta.snapshot(self.project)
        after = {k: (dict(v) if isinstance(v, dict) else v) for k, v in before.items()}
        if name is not None:
            after["name"] = name
        if display is not None:
            after["display"] = display.to_dict()
        if device_name is not None:
            after["esphome"]["device_name"] = device_name
        if after != before:
            self._execute(cmd.UpdateProjectMeta("Propiedades del proyecto", before, after))

    # ================================================================ estilos efectivos
    # ================================================================ estilos y tema (Fase 4)
    def _set_styles_and_theme(self, label: str, styles: list[dict] | None = None,
                              theme: dict | None = None) -> None:
        before = {"styles": [st.to_dict() for st in self.project.styles],
                  "theme": copy.deepcopy(self.project.lvgl_extra.get("theme"))}
        after = copy.deepcopy(before)
        if styles is not None:
            after["styles"] = copy.deepcopy(styles)
        if theme is not None:
            after["theme"] = copy.deepcopy(theme) or None
        if after != before:
            self._execute(SetStylesTheme(label, before, after))

    def add_style(self, name: str = "estilo") -> str:
        sid = unique_id(sanitize_id(name, "estilo"), self.project.all_ids())
        styles = [st.to_dict() for st in self.project.styles] + [{"id": sid, "props": {}}]
        self._set_styles_and_theme("Nuevo estilo", styles=styles)
        return sid

    def remove_style(self, style_id: str) -> None:
        styles = [st.to_dict() for st in self.project.styles if st.id != style_id]
        steps: list[Command] = []
        for _, w in self.project.iter_widgets():
            ids = _style_list(w.props.get("styles"))
            if style_id in ids:
                before = w.to_dict()
                rest = [i for i in ids if i != style_id]
                props = catalog.set_path(before["props"], "styles", _style_value(rest))
                steps.append(cmd.UpdateWidgets("", {w.id: (before, dict(before, props=props))}))
        before = {"styles": [st.to_dict() for st in self.project.styles],
                  "theme": copy.deepcopy(self.project.lvgl_extra.get("theme"))}
        steps.append(SetStylesTheme("", before, dict(before, styles=styles)))
        self._execute(CompositeCommand("Eliminar estilo", steps))

    def rename_style(self, old_id: str, new_id: str) -> str | None:
        new_id = new_id.strip()
        if new_id == old_id:
            return None
        if not is_valid_id(new_id):
            return "Id no válido: usa letras, números y _ (sin empezar por número)"
        if new_id in self.project.all_ids():
            return f"Ya existe un elemento con id «{new_id}»"
        steps: list[Command] = []
        for _, w in self.project.iter_widgets():
            ids = _style_list(w.props.get("styles"))
            if old_id in ids:
                before = w.to_dict()
                props = catalog.set_path(before["props"], "styles",
                                         _style_value([new_id if i == old_id else i for i in ids]))
                steps.append(cmd.UpdateWidgets("", {w.id: (before, dict(before, props=props))}))
        before = {"styles": [st.to_dict() for st in self.project.styles],
                  "theme": copy.deepcopy(self.project.lvgl_extra.get("theme"))}
        styles = [dict(st, id=new_id) if st["id"] == old_id else st for st in before["styles"]]
        steps.append(SetStylesTheme("", before, dict(before, styles=styles)))
        self._execute(CompositeCommand("Renombrar estilo", steps))
        return None

    def set_style_props(self, style_id: str, props: dict) -> None:
        styles = [dict(st.to_dict(), props=copy.deepcopy(props)) if st.id == style_id else st.to_dict()
                  for st in self.project.styles]
        self._set_styles_and_theme("Editar estilo", styles=styles)

    def set_theme_props(self, widget_type: str, props: dict) -> None:
        theme = copy.deepcopy(self.project.lvgl_extra.get("theme") or {})
        if props:
            theme[widget_type] = copy.deepcopy(props)
        else:
            theme.pop(widget_type, None)
        self._set_styles_and_theme("Editar tema", theme=theme if theme else {})

    def set_widget_styles(self, widget_id: str, style_ids: list[str]) -> None:
        self.set_raw_prop([widget_id], "styles", _style_value(style_ids))

    def font_ids(self, library: bool = True) -> list[str]:
        """Fuentes que se pueden elegir: las de LVGL (montserrat_N), las del proyecto y,
        con `library`, las de la biblioteca (Roboto, iconos MDI…), que se añaden al elegirlas."""
        from olvgl.domain.fonts import library_suggestions
        own = [f.id for f in self.project.fonts]
        out = list(catalog.FONTS) + own
        if library:
            out += [i for i in library_suggestions() if i not in own]
        return out

    def font_label(self, font_id: str) -> str:
        from olvgl.domain.fonts import describe, library_font
        f = self.project.font(font_id)
        if f is not None:
            return f"{font_id}  —  {describe(font_id, f.data)}"
        lib = library_font(font_id)
        if lib is not None:
            return f"{font_id}  —  {describe(font_id, lib)}  ＋"
        return font_id

    # ---------------------------------------------------------------- fuentes
    def _fonts_change(self, label: str, change) -> bool:
        p = self.project.clone()
        change(p)
        return self.apply_project(label, p, self.current_screen_id, keep_selection=True)

    def add_font(self, font_id: str, data: dict) -> str | None:
        """Añade una fuente (`font:`). Devuelve su id, o None si el id no es válido o ya existe."""
        from olvgl.domain.model import FontResource, is_valid_id
        if not is_valid_id(font_id) or font_id in self.project.all_ids() or self.project.font(font_id) \
                or font_id in catalog.FONTS:
            return None
        ok = self._fonts_change("Añadir fuente", lambda p: p.fonts.append(FontResource(font_id, copy.deepcopy(data))))
        return font_id if ok else None

    def update_font(self, font_id: str, data: dict) -> bool:
        def change(p):
            f = p.font(font_id)
            if f is not None:
                f.data = copy.deepcopy(data)
        return self.project.font(font_id) is not None and self._fonts_change("Editar fuente", change)

    def remove_font(self, font_id: str) -> bool:
        if self.project.font(font_id) is None:
            return False
        return self._fonts_change("Eliminar fuente",
                                  lambda p: setattr(p, "fonts", [f for f in p.fonts if f.id != font_id]))

    def font_uses(self, font_id: str) -> int:
        """Cuántos widgets (o estados/partes) usan la fuente."""
        n = 0
        for _s, w in self.project.iter_widgets():
            vals = [w.props.get("text_font")] + [v.get("text_font") for v in w.props.values() if isinstance(v, dict)]
            n += sum(1 for v in vals if v == font_id)
        n += sum(1 for st in self.project.styles if st.props.get("text_font") == font_id)
        return n

    def ensure_font(self, font_id: str) -> bool:
        """Si `font_id` es de la biblioteca y el proyecto aún no la tiene, la añade."""
        from olvgl.domain.fonts import library_font
        if not isinstance(font_id, str) or self.project.font(font_id) is not None:
            return False
        data = library_font(font_id)
        return data is not None and self.add_font(font_id, data) is not None
