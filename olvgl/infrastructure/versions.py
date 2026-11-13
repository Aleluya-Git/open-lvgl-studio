"""Versiones de un proyecto: instantáneas guardadas y el historial de Git.

- `VersionStore`: instantáneas con nombre en `<documento>.versiones/` junto al
  proyecto (o al YAML vinculado), así viajan con él a una carpeta compartida.
  Cada versión es un JSON con el proyecto completo y quién/cuándo/por qué.
- `GitHistory`: si el documento está en un repositorio Git, sus commits y el
  contenido en cada uno (sin tocar el repositorio: sólo `git log` y `git show`).
"""
from __future__ import annotations

import datetime as _dt
import json
import os
import re
import shutil
import subprocess
from dataclasses import dataclass

from olvgl import __version__
from olvgl.domain.model import Project


@dataclass
class VersionInfo:
    id: str
    label: str
    author: str
    created: str          # ISO 8601
    source: str           # local | git
    detail: str = ""      # commit, nº de widgets…

    @property
    def when(self) -> str:
        try:
            return _dt.datetime.fromisoformat(self.created).strftime("%Y-%m-%d %H:%M")
        except ValueError:
            return self.created


def default_author() -> str:
    for k in ("OLVGL_USER", "USERNAME", "USER"):
        if os.environ.get(k):
            return os.environ[k]
    try:
        return os.getlogin()
    except OSError:
        return "usuario"


class VersionStore:
    def __init__(self, document: str | None, fallback_dir: str | None = None):
        if document:
            self.dir = document + ".versiones"
        else:
            from olvgl.infrastructure.settings_db import app_data_dir
            self.dir = fallback_dir or os.path.join(app_data_dir(), "versiones", "sin_titulo")

    def _path(self, vid: str) -> str:
        if not re.fullmatch(r"[A-Za-z0-9_.-]+", vid):
            raise ValueError(f"id de versión no válido: {vid}")
        return os.path.join(self.dir, vid + ".json")

    def list(self) -> list[VersionInfo]:
        if not os.path.isdir(self.dir):
            return []
        out = []
        for name in os.listdir(self.dir):
            if not name.endswith(".json"):
                continue
            try:
                with open(os.path.join(self.dir, name), encoding="utf-8") as f:
                    meta = json.load(f).get("meta", {})
            except (OSError, ValueError):
                continue
            out.append(VersionInfo(name[:-5], meta.get("label", ""), meta.get("author", ""),
                                   meta.get("created", ""), "local", meta.get("detail", "")))
        out.sort(key=lambda v: v.created, reverse=True)
        return out

    def save(self, project: Project, label: str, author: str | None = None) -> VersionInfo:
        os.makedirs(self.dir, exist_ok=True)
        now = _dt.datetime.now().replace(microsecond=0)
        vid = now.strftime("v_%Y%m%d_%H%M%S")
        n = 1
        while os.path.exists(self._path(vid)):
            n += 1
            vid = now.strftime("v_%Y%m%d_%H%M%S") + f"_{n}"
        widgets = sum(1 for _ in project.iter_widgets())
        info = VersionInfo(vid, label.strip() or now.strftime("Versión %Y-%m-%d %H:%M"), author or default_author(),
                           now.isoformat(), "local", f"{len(project.screens)} páginas, {widgets} widgets")
        data = {"meta": {"label": info.label, "author": info.author, "created": info.created,
                         "detail": info.detail, "app": __version__},
                "project": project.to_dict()}
        tmp = self._path(vid) + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)
        os.replace(tmp, self._path(vid))
        return info

    def load(self, vid: str) -> Project:
        with open(self._path(vid), encoding="utf-8") as f:
            return Project.from_dict(json.load(f)["project"])

    def delete(self, vid: str) -> None:
        os.remove(self._path(vid))

    def clear(self) -> None:
        shutil.rmtree(self.dir, ignore_errors=True)


# --------------------------------------------------------------------------- Git
class GitHistory:
    """Commits que tocan `path` (un .olvgl o un .yaml) y su contenido en cada uno."""

    def __init__(self, path: str | None):
        self.path = os.path.abspath(path) if path else None
        self.root: str | None = None
        if self.path and shutil.which("git"):
            r = self._git(["rev-parse", "--show-toplevel"])
            if r is not None:
                self.root = r.strip()

    def _git(self, args: list[str]) -> str | None:
        assert self.path
        kw = {}
        if os.name == "nt":
            kw["creationflags"] = 0x08000000          # CREATE_NO_WINDOW
        try:
            p = subprocess.run(["git", *args], cwd=os.path.dirname(self.path), capture_output=True,
                               timeout=15, **kw)
        except (OSError, subprocess.SubprocessError):
            return None
        if p.returncode:
            return None
        return p.stdout.decode("utf-8", "replace")

    @property
    def available(self) -> bool:
        return self.root is not None

    def rel(self) -> str:
        assert self.path and self.root
        return os.path.relpath(self.path, self.root).replace(os.sep, "/")

    def log(self, limit: int = 50) -> list[VersionInfo]:
        if not self.available:
            return []
        out = self._git(["log", f"-n{limit}", "--follow", "--format=%H%x1f%h%x1f%an%x1f%aI%x1f%s", "--",
                         self.rel()]) or ""
        res = []
        for line in out.splitlines():
            parts = line.split("\x1f")
            if len(parts) == 5:
                full, short, author, date, subject = parts
                res.append(VersionInfo(full, subject, author, date, "git", short))
        return res

    def content(self, commit: str) -> str | None:
        if not self.available or not re.fullmatch(r"[0-9a-fA-F]{7,40}", commit):
            return None
        return self._git(["show", f"{commit}:{self.rel()}"])

    def project_at(self, commit: str, display=None) -> Project | None:
        text = self.content(commit)
        if text is None:
            return None
        if self.path and self.path.lower().endswith((".yaml", ".yml")):
            from olvgl.infrastructure.esphome_importer import import_esphome_text
            project, _rep = import_esphome_text(text, self.path, display)
            return project
        from olvgl.infrastructure.json_store import loads
        return loads(text)
