"""Pantallas: las de serie (DISPLAY_PRESETS) y las propias del usuario.

Las propias se guardan en los ajustes (`custom_displays`) y aparecen en todos
los sitios donde se elige pantalla: nuevo proyecto, propiedades del proyecto,
resolución al importar y dispositivos del simulador.
"""
from __future__ import annotations

from olvgl.domain.model import DISPLAY_PRESETS, DisplayProfile

KEY = "custom_displays"
MIN_SIZE, MAX_SIZE = 32, 4096
CUSTOM: list[DisplayProfile] = []
SETTINGS = None                       # los ajustes de la aplicación (los fija load)


class DisplayError(ValueError):
    pass


def load(settings) -> list[DisplayProfile]:
    global SETTINGS
    SETTINGS = settings
    CUSTOM.clear()
    for d in settings.get(KEY, []) or []:
        try:
            p = DisplayProfile.from_dict(d)
        except (TypeError, ValueError, AttributeError):
            continue
        if p.name and MIN_SIZE <= p.width <= MAX_SIZE and MIN_SIZE <= p.height <= MAX_SIZE:
            CUSTOM.append(p)
    return list(CUSTOM)


def _store(settings) -> None:
    settings.set(KEY, [d.to_dict() for d in CUSTOM])


def presets() -> list[DisplayProfile]:
    return list(DISPLAY_PRESETS) + list(CUSTOM)


def is_custom(name: str) -> bool:
    return any(d.name == name for d in CUSTOM)


def validate(name: str, width: int, height: int) -> str:
    name = (name or "").strip()
    if not name:
        raise DisplayError("Ponle un nombre a la pantalla")
    if any(d.name.lower() == name.lower() for d in DISPLAY_PRESETS):
        raise DisplayError("Ya hay una pantalla de serie con ese nombre")
    for v in (width, height):
        if not MIN_SIZE <= int(v) <= MAX_SIZE:
            raise DisplayError(f"El tamaño debe estar entre {MIN_SIZE} y {MAX_SIZE} px")
    return name


def save(settings, name: str, width: int, height: int) -> DisplayProfile:
    """Añade (o actualiza, si ya existe con ese nombre) una pantalla propia."""
    settings = settings if settings is not None else SETTINGS
    if settings is None:
        raise DisplayError("No se pueden guardar pantallas sin los ajustes de la aplicación")
    name = validate(name, width, height)
    prof = DisplayProfile(name, int(width), int(height))
    for i, d in enumerate(CUSTOM):
        if d.name.lower() == name.lower():
            CUSTOM[i] = prof
            break
    else:
        CUSTOM.append(prof)
    _store(settings)
    return prof


def remove(settings, name: str) -> bool:
    before = len(CUSTOM)
    CUSTOM[:] = [d for d in CUSTOM if d.name != name]
    if len(CUSTOM) != before:
        _store(settings)
        return True
    return False


def is_known(d: DisplayProfile) -> bool:
    """¿Es una pantalla de la lista (de serie o propia) con ese nombre y tamaño?"""
    return any((x.name, x.width, x.height) == (d.name, d.width, d.height) for x in presets())


def label(d: DisplayProfile) -> str:
    return f"{'★ ' if is_custom(d.name) else ''}{d.name} ({d.width}×{d.height})"
