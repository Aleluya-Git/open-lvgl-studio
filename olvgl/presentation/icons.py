"""Iconos y logotipo de la aplicación (olvgl/resources)."""
from __future__ import annotations

import os
from functools import lru_cache

from PySide6.QtGui import QIcon, QPixmap

RES = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "resources")


def resource(*parts: str) -> str:
    return os.path.join(RES, *parts)


@lru_cache(maxsize=None)
def action_icon(name: str) -> QIcon:
    path = resource("actions", f"{name}.png")
    return QIcon(path) if os.path.exists(path) else QIcon()


def widget_icon(widget_type: str) -> QIcon | None:
    from olvgl.application.plugins import PLUGIN_ICONS
    path = PLUGIN_ICONS.get(widget_type) or resource("widgets", f"{widget_type}.png")
    return _icon_file(path)


@lru_cache(maxsize=None)
def _icon_file(path: str) -> QIcon | None:
    return QIcon(path) if os.path.exists(path) else None


@lru_cache(maxsize=None)
def app_icon() -> QIcon:
    icon = QIcon()
    for name in ("app_icon.ico", "app_icon.png"):
        path = resource(name)
        if os.path.exists(path):
            icon.addFile(path)
    return icon


def logo_pixmap(dark_background: bool = True, height: int = 96) -> QPixmap:
    pm = QPixmap(resource("logo_light.png" if dark_background else "logo.png"))
    if pm.isNull():
        return pm
    from PySide6.QtCore import Qt
    return pm.scaledToHeight(height, Qt.TransformationMode.SmoothTransformation)
