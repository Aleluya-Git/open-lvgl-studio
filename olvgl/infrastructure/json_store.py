"""Persistencia del proyecto en JSON (.olvgl) y autoguardado."""
from __future__ import annotations

import json
import os
import tempfile
import time

from olvgl.domain.model import FORMAT_NAME, Project

EXTENSION = ".olvgl"
AUTOSAVE_SUFFIX = ".autosave"


class ProjectFormatError(Exception):
    pass


def _relative_images(project: Project, base_dir: str) -> dict:
    data = project.to_dict()
    for img in data["images"]:
        path = img["path"]
        if path and os.path.isabs(path):
            try:
                rel = os.path.relpath(path, base_dir)
                if not rel.startswith(".."):
                    path = rel.replace("\\", "/")   # relativa: siempre con /
            except ValueError:  # otra unidad en Windows
                pass
        img["path"] = path
    return data


def atomic_write_text(path: str, text: str) -> None:
    directory = os.path.dirname(os.path.abspath(path)) or "."
    os.makedirs(directory, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".tmp_", dir=directory)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:
            f.write(text)
        for attempt in range(6):   # en Windows otro programa puede tener el fichero abierto un instante
            try:
                os.replace(tmp, path)
                break
            except PermissionError:
                if attempt == 5:
                    raise
                time.sleep(0.05 * (attempt + 1))
    except BaseException:
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise


def dumps(project: Project, base_dir: str | None = None) -> str:
    data = _relative_images(project, base_dir) if base_dir else project.to_dict()
    return json.dumps(data, ensure_ascii=False, indent=2) + "\n"


def save_project(project: Project, path: str) -> None:
    atomic_write_text(path, dumps(project, os.path.dirname(os.path.abspath(path))))


def loads(text: str) -> Project:
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ProjectFormatError(f"El fichero no es JSON válido: {exc}") from exc
    if not isinstance(data, dict) or data.get("format") != FORMAT_NAME:
        raise ProjectFormatError("El fichero no es un proyecto de Open LVGL Studio")
    try:
        return Project.from_dict(data)
    except (KeyError, TypeError, ValueError) as exc:
        raise ProjectFormatError(f"Proyecto dañado: {exc}") from exc


def load_project(path: str) -> Project:
    with open(path, encoding="utf-8") as f:
        project = loads(f.read())
    # en memoria las rutas de recursos son absolutas (en disco, relativas al .olvgl)
    base = os.path.dirname(os.path.abspath(path))
    for img in project.images:
        if img.path and not os.path.isabs(img.path) and "://" not in img.path:
            img.path = os.path.normpath(os.path.join(base, img.path))
    return project


def resolve_path(path: str, project_path: str | None) -> str:
    """Ruta absoluta de un recurso (relativa al .olvgl si no es absoluta)."""
    if not path or os.path.isabs(path) or not project_path:
        return path
    return os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(project_path)), path))


# --------------------------------------------------------------------------- autosave
def autosave_path(project_path: str | None, fallback_dir: str) -> str:
    if project_path:
        return project_path + AUTOSAVE_SUFFIX
    return os.path.join(fallback_dir, "sin_titulo" + EXTENSION + AUTOSAVE_SUFFIX)


def write_autosave(project: Project, project_path: str | None, fallback_dir: str) -> str:
    path = autosave_path(project_path, fallback_dir)
    base = os.path.dirname(os.path.abspath(project_path)) if project_path else None
    atomic_write_text(path, dumps(project, base))
    return path


def pending_autosave(project_path: str | None, fallback_dir: str) -> str | None:
    """Devuelve la ruta del autoguardado si es más reciente que el proyecto."""
    path = autosave_path(project_path, fallback_dir)
    if not os.path.exists(path):
        return None
    if project_path and os.path.exists(project_path):
        if os.path.getmtime(path) <= os.path.getmtime(project_path):
            return None
    return path


def discard_autosave(project_path: str | None, fallback_dir: str) -> None:
    path = autosave_path(project_path, fallback_dir)
    try:
        os.remove(path)
    except OSError:
        pass


def touch(path: str) -> None:
    now = time.time()
    os.utime(path, (now, now))
