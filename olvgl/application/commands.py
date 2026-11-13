"""Comandos concretos sobre el modelo.

Se guardan como diccionarios (instantáneas del elemento afectado) y se
localizan por id, de modo que son robustos y sirven de base al Diff/Merge de
la Fase 3.
"""
from __future__ import annotations

import copy

from olvgl.application.history import Command
from olvgl.domain.model import (DisplayProfile, EsphomeSettings, ImageResource, Project,
                                Screen, Widget)


def _apply_widget_dict(w: Widget, d: dict) -> None:
    """Aplica los campos propios del widget (los hijos los gestionan sus comandos)."""
    new = Widget.from_dict(dict(d, children=[]))
    w.id, w.type, w.auto_id = new.id, new.type, new.auto_id
    w.x, w.y, w.width, w.height = new.x, new.y, new.width, new.height
    w.props, w.events = new.props, new.events


def _own(d: dict) -> dict:
    return {k: v for k, v in d.items() if k != "children"}


class UpdateWidgets(Command):
    """Cambia uno o varios widgets: {id_actual: (antes, después)}."""

    def __init__(self, label: str, changes: dict[str, tuple[dict, dict]], merge_key: str = ""):
        self.label = label
        self.changes = {k: (copy.deepcopy(_own(b)), copy.deepcopy(_own(a))) for k, (b, a) in changes.items()}
        self.merge_key = merge_key

    def do(self, project: Project) -> None:
        for wid, (_, after) in self.changes.items():
            w = project.widget(wid)
            if w is None:
                raise KeyError(wid)
            _apply_widget_dict(w, after)

    def undo(self, project: Project) -> None:
        for before, after in self.changes.values():
            w = project.widget(after["id"])
            if w is None:
                raise KeyError(after["id"])
            _apply_widget_dict(w, before)

    def merge(self, other: Command) -> bool:
        if not isinstance(other, UpdateWidgets) or not self.merge_key:
            return False
        if other.merge_key != self.merge_key:
            return False
        # Sólo fusiona si actúa sobre los mismos widgets (por id posterior)
        mine = {a["id"]: k for k, (_, a) in self.changes.items()}
        if set(other.changes.keys()) != set(mine.keys()):
            return False
        for k, (_, after) in other.changes.items():
            orig_key = mine[k]
            before = self.changes[orig_key][0]
            self.changes[orig_key] = (before, after)
        return True


class InsertWidgets(Command):
    """Inserta widgets: lista de (id del padre o None, índice, dict) en una pantalla."""

    def __init__(self, label: str, screen_id: str, items: list[tuple]):
        self.label = label
        self.screen_id = screen_id
        norm = []
        for it in items:
            parent, index, d = (None, *it) if len(it) == 2 else it
            norm.append((parent, index, copy.deepcopy(d)))
        self.items = sorted(norm, key=lambda t: t[1])

    def do(self, project: Project) -> None:
        for parent, index, d in self.items:
            lst = project.container(self.screen_id, parent)
            lst.insert(min(index, len(lst)), Widget.from_dict(d))

    def undo(self, project: Project) -> None:
        for parent, _, d in self.items:
            lst = project.container(self.screen_id, parent)
            lst[:] = [w for w in lst if w.id != d["id"]]


class RemoveWidgets(Command):
    def __init__(self, label: str, project: Project, ids: list[str]):
        self.label = label
        wanted = set(ids)
        self.removed: list[tuple[str, str | None, int, dict]] = []
        for wid in ids:
            loc = project.locate(wid)
            if loc is None:
                continue
            # si un antecesor también se elimina, basta con eliminar el antecesor
            anc = loc.parent
            skip = False
            while anc is not None:
                if anc.id in wanted:
                    skip = True
                    break
                pl = project.locate(anc.id)
                anc = pl.parent if pl else None
            if not skip:
                self.removed.append((loc.screen.id, loc.parent.id if loc.parent else None,
                                     loc.index, loc.widget.to_dict()))

    def do(self, project: Project) -> None:
        for screen_id, parent, _, d in self.removed:
            lst = project.container(screen_id, parent)
            lst[:] = [w for w in lst if w.id != d["id"]]

    def undo(self, project: Project) -> None:
        for screen_id, parent, index, d in sorted(self.removed, key=lambda t: t[2]):
            lst = project.container(screen_id, parent)
            lst.insert(min(index, len(lst)), Widget.from_dict(d))


class ReorderWidgets(Command):
    def __init__(self, label: str, screen_id: str, before: list[str], after: list[str],
                 parent_id: str | None = None):
        self.label = label
        self.screen_id = screen_id
        self.parent_id = parent_id
        self.before, self.after = list(before), list(after)

    def _apply(self, project: Project, order: list[str]) -> None:
        lst = project.container(self.screen_id, self.parent_id)
        by_id = {w.id: w for w in lst}
        lst[:] = [by_id[i] for i in order if i in by_id]

    def do(self, project: Project) -> None:
        self._apply(project, self.after)

    def undo(self, project: Project) -> None:
        self._apply(project, self.before)


# --------------------------------------------------------------------------- pantallas
class InsertScreen(Command):
    def __init__(self, label: str, index: int, screen: dict):
        self.label = label
        self.index = index
        self.screen = copy.deepcopy(screen)

    def do(self, project: Project) -> None:
        project.screens.insert(min(self.index, len(project.screens)), Screen.from_dict(self.screen))

    def undo(self, project: Project) -> None:
        project.screens[:] = [s for s in project.screens if s.id != self.screen["id"]]


class RemoveScreen(Command):
    def __init__(self, label: str, project: Project, screen_id: str):
        self.label = label
        self.index = next(i for i, s in enumerate(project.screens) if s.id == screen_id)
        self.screen = project.screens[self.index].to_dict()

    def do(self, project: Project) -> None:
        project.screens[:] = [s for s in project.screens if s.id != self.screen["id"]]

    def undo(self, project: Project) -> None:
        project.screens.insert(min(self.index, len(project.screens)), Screen.from_dict(self.screen))


class UpdateScreen(Command):
    """Cambia id/nombre/color/propiedades de una pantalla y actualiza las referencias page_show."""

    FIELDS = ("id", "name", "bg_color", "props")

    def __init__(self, label: str, before: dict, after: dict, merge_key: str = ""):
        self.label = label
        self.before = {k: copy.deepcopy(before.get(k, {} if k == "props" else None)) for k in self.FIELDS}
        self.after = {k: copy.deepcopy(after.get(k, {} if k == "props" else None)) for k in self.FIELDS}
        self.merge_key = merge_key

    @staticmethod
    def snapshot(screen: Screen) -> dict:
        return {"id": screen.id, "name": screen.name, "bg_color": screen.bg_color,
                "props": copy.deepcopy(screen.props)}

    @staticmethod
    def _apply(project: Project, src: dict, dst: dict) -> None:
        s = project.screen(src["id"])
        if s is None:
            raise KeyError(src["id"])
        s.id, s.name, s.bg_color = dst["id"], dst["name"], dst["bg_color"]
        s.props = copy.deepcopy(dst["props"])
        if src["id"] != dst["id"]:
            for _, w in project.iter_widgets():
                for ev in w.events:
                    for a in ev.actions:
                        if a.kind == "page_show" and a.params.get("page") == src["id"]:
                            a.params["page"] = dst["id"]

    def do(self, project: Project) -> None:
        self._apply(project, self.before, self.after)

    def undo(self, project: Project) -> None:
        self._apply(project, self.after, self.before)

    def merge(self, other: Command) -> bool:
        if (isinstance(other, UpdateScreen) and self.merge_key and other.merge_key == self.merge_key
                and other.before["id"] == self.after["id"]):
            self.after = copy.deepcopy(other.after)
            return True
        return False


class ReorderScreens(Command):
    def __init__(self, label: str, before: list[str], after: list[str]):
        self.label = label
        self.before, self.after = list(before), list(after)

    @staticmethod
    def _apply(project: Project, order: list[str]) -> None:
        by_id = {s.id: s for s in project.screens}
        project.screens[:] = [by_id[i] for i in order if i in by_id]

    def do(self, project: Project) -> None:
        self._apply(project, self.after)

    def undo(self, project: Project) -> None:
        self._apply(project, self.before)


# --------------------------------------------------------------------------- recursos y proyecto
class InsertImage(Command):
    def __init__(self, label: str, image: dict):
        self.label = label
        self.image = copy.deepcopy(image)

    def do(self, project: Project) -> None:
        project.images.append(ImageResource.from_dict(self.image))

    def undo(self, project: Project) -> None:
        project.images[:] = [i for i in project.images if i.id != self.image["id"]]


class RemoveImage(Command):
    def __init__(self, label: str, project: Project, image_id: str):
        self.label = label
        self.index = next(i for i, im in enumerate(project.images) if im.id == image_id)
        self.image = project.images[self.index].to_dict()

    def do(self, project: Project) -> None:
        project.images[:] = [i for i in project.images if i.id != self.image["id"]]

    def undo(self, project: Project) -> None:
        project.images.insert(self.index, ImageResource.from_dict(self.image))


class UpdateProjectMeta(Command):
    """Cambia nombre, pantalla física y ajustes ESPHome del proyecto."""

    def __init__(self, label: str, before: dict, after: dict):
        self.label = label
        self.before, self.after = copy.deepcopy(before), copy.deepcopy(after)

    @staticmethod
    def snapshot(project: Project) -> dict:
        return {"name": project.name, "display": project.display.to_dict(),
                "esphome": project.esphome.to_dict()}

    @staticmethod
    def _apply(project: Project, d: dict) -> None:
        project.name = d["name"]
        project.display = DisplayProfile.from_dict(d["display"])
        project.esphome = EsphomeSettings.from_dict(d["esphome"])

    def do(self, project: Project) -> None:
        self._apply(project, self.after)

    def undo(self, project: Project) -> None:
        self._apply(project, self.before)
