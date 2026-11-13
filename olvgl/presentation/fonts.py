"""Fuentes de la interfaz con familias explícitas.

Si Qt tiene que adivinar la familia (fuente por defecto en negrita, «fuente
de sistema monoespaciada»), en algunas configuraciones elige una fuente
decorativa o diminuta. Con una lista de familias en orden la elección es
siempre la misma."""
from __future__ import annotations

from PySide6.QtGui import QFont

UI_FAMILIES = ["Segoe UI", "Arial", "Helvetica", "DejaVu Sans", "Noto Sans"]
MONO_FAMILIES = ["Consolas", "Cascadia Mono", "Courier New", "DejaVu Sans Mono", "Liberation Mono", "monospace"]
UI_POINT_SIZE = 9
_known: set[str] | None = None


def invalidate() -> None:
    """Llamar tras registrar fuentes nuevas con QFontDatabase.addApplicationFont."""
    global _known
    _known = None


def pick_family(candidates: list[str]) -> str:
    """La primera familia de la lista que existe de verdad. Así nunca se deja a
    Qt elegir una sustituta al azar (en Windows, la primera alfabética, que
    puede ser una fuente decorativa)."""
    global _known
    from PySide6.QtGui import QFontDatabase
    if _known is None:
        _known = {f.lower() for f in QFontDatabase.families()}
    for fam in candidates:
        if fam and fam.lower() in _known:
            return fam
    return candidates[-1] if candidates else ""


def ui_font(bold: bool = False, point_size: float | None = None) -> QFont:
    f = QFont(pick_family(UI_FAMILIES))
    f.setPointSizeF(point_size or UI_POINT_SIZE)
    if bold:
        f.setWeight(QFont.Weight.Bold)
    return f


def mono_font(point_size: float | None = None) -> QFont:
    f = QFont(pick_family(MONO_FAMILIES))
    f.setStyleHint(QFont.StyleHint.Monospace)
    f.setFixedPitch(True)
    f.setPointSizeF(point_size or UI_POINT_SIZE + 0.5)
    return f
