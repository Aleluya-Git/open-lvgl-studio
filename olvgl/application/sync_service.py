"""Sesión de sincronización bidireccional con un YAML de ESPHome (Fase 3).

El ViewModel delega aquí la relación con el fichero vinculado:

- `write(project)`: aplica en el fichero los cambios del editor con el motor
  Diff/Merge (merge a tres bandas: lo que el usuario haya cambiado a mano en
  el fichero se conserva).
- `external_text()`: devuelve el texto del fichero si ha cambiado por fuera
  desde la última sincronización.

Las funciones de lectura/escritura, generación, merge e importación se
inyectan (inversión de dependencias), así la sesión se prueba sin disco ni Qt.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable


class SyncUnsupported(Exception):
    """El fichero no se puede sincronizar directamente (p. ej. usa !include)."""


@dataclass
class SyncOutcome:
    written: bool = False
    merged_external: bool = False       # el fichero tenía cambios externos que se han mezclado
    conflicts: list[str] = field(default_factory=list)
    rewritten: list[str] = field(default_factory=list)
    edits: int = 0
    text: str = ""


@dataclass
class SyncPorts:
    read: Callable[[str], str]
    write: Callable[[str, str], None]
    backup: Callable[[str], str | None]
    generate_ast: Callable[[Any], Any]
    merge: Callable[[str, str | None, Any], Any]          # sync_text(current, base, generated) → SyncResult
    import_text: Callable[[str, str], tuple[Any, Any]]    # (texto, ruta) → (Project, informe)
    check: Callable[[str, str], str | None]               # motivo por el que no se puede sincronizar


class SyncSession:
    def __init__(self, path: str, ports: SyncPorts):
        self.path = path
        self.ports = ports
        text = ports.read(path)
        reason = ports.check(text, path)
        if reason:
            raise SyncUnsupported(reason)
        self.base_text = text
        self.auto = True
        self.backup_path: str | None = None
        self.last: SyncOutcome | None = None

    @property
    def name(self) -> str:
        import os
        return os.path.basename(self.path)

    def external_text(self) -> str | None:
        text = self.ports.read(self.path)
        return None if text == self.base_text else text

    def accept_external(self, text: str) -> None:
        """El modelo ya refleja `text` (se ha reimportado)."""
        self.base_text = text

    def import_text(self, text: str):
        return self.ports.import_text(text, self.path)

    def write(self, project) -> SyncOutcome:
        current = self.ports.read(self.path)
        merged_external = current != self.base_text
        result = self.ports.merge(current, self.base_text, self.ports.generate_ast(project))
        out = SyncOutcome(merged_external=merged_external, conflicts=list(result.conflicts),
                          rewritten=list(result.rewritten), edits=result.edits, text=result.text)
        if result.changed:
            if self.backup_path is None:
                self.backup_path = self.ports.backup(self.path)
            self.ports.write(self.path, result.text)
            out.written = True
        self.base_text = result.text
        self.last = out
        return out

    def differs(self, project) -> bool:
        """¿El fichero y el modelo dicen cosas distintas?"""
        current = self.ports.read(self.path)
        return bool(self.ports.merge(current, current, self.ports.generate_ast(project)).changed)
