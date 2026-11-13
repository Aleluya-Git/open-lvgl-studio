"""Historial ilimitado de deshacer/rehacer (patrón Command)."""
from __future__ import annotations

from olvgl.domain.model import Project


class Command:
    label: str = "Cambio"

    def do(self, project: Project) -> None:  # pragma: no cover - abstracto
        raise NotImplementedError

    def undo(self, project: Project) -> None:  # pragma: no cover - abstracto
        raise NotImplementedError

    def merge(self, other: "Command") -> bool:
        """Intenta absorber `other` (ya ejecutado). True si lo ha absorbido."""
        return False


class CompositeCommand(Command):
    def __init__(self, label: str, commands: list[Command]):
        self.label = label
        self.commands = list(commands)

    def do(self, project: Project) -> None:
        for c in self.commands:
            c.do(project)

    def undo(self, project: Project) -> None:
        for c in reversed(self.commands):
            c.undo(project)


class History:
    def __init__(self) -> None:
        self._undo: list[Command] = []
        self._redo: list[Command] = []
        self._clean_index: int | None = 0  # longitud de _undo en el último guardado
        self._merge_open = False

    # -------------------------------------------------------------- estado
    @property
    def can_undo(self) -> bool:
        return bool(self._undo)

    @property
    def can_redo(self) -> bool:
        return bool(self._redo)

    @property
    def undo_label(self) -> str:
        return self._undo[-1].label if self._undo else ""

    @property
    def redo_label(self) -> str:
        return self._redo[-1].label if self._redo else ""

    def __len__(self) -> int:
        return len(self._undo)

    def is_clean(self) -> bool:
        return self._clean_index == len(self._undo)

    def mark_clean(self) -> None:
        self._clean_index = len(self._undo)
        self._merge_open = False

    def clear(self) -> None:
        self._undo.clear()
        self._redo.clear()
        self._clean_index = 0
        self._merge_open = False

    def break_merge(self) -> None:
        """El siguiente comando no se fusionará con el anterior."""
        self._merge_open = False

    # -------------------------------------------------------------- operaciones
    def push(self, cmd: Command, project: Project, mergeable: bool = False) -> None:
        cmd.do(project)
        self._redo.clear()
        if (mergeable and self._merge_open and self._undo
                and len(self._undo) != self._clean_index and self._undo[-1].merge(cmd)):
            return
        if self._clean_index is not None and self._clean_index > len(self._undo):
            self._clean_index = None  # el estado guardado ya no es alcanzable
        self._undo.append(cmd)
        self._merge_open = mergeable

    def undo(self, project: Project) -> bool:
        if not self._undo:
            return False
        cmd = self._undo.pop()
        cmd.undo(project)
        self._redo.append(cmd)
        self._merge_open = False
        return True

    def redo(self, project: Project) -> bool:
        if not self._redo:
            return False
        cmd = self._redo.pop()
        cmd.do(project)
        self._undo.append(cmd)
        self._merge_open = False
        return True
