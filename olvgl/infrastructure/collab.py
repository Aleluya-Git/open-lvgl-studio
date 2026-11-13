"""Colaboración en una carpeta compartida (red, OneDrive, Dropbox, Syncthing…).

Sin servidor: todo son ficheros pequeños junto al proyecto, así funciona con
cualquier carpeta que se sincronice.

- `Presence`: quién más tiene abierto el proyecto (`<doc>.presencia/`). Cada
  instancia escribe su latido cada minuto; se considera ausente a los 3 min.
- `CommentStore`: comentarios de revisión sobre widgets (`<doc>.comentarios.json`),
  con respuestas y «resuelto». Al guardar se fusiona con lo que hayan escrito
  los demás (por id de comentario), así no se pisan.
"""
from __future__ import annotations

import datetime as _dt
import json
import os
import re
import socket
import time
import uuid
from dataclasses import asdict, dataclass, field

from olvgl.infrastructure.versions import default_author

STALE_SECONDS = 180


def _now() -> str:
    return _dt.datetime.now().replace(microsecond=0).isoformat()


def _safe(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", name)[:60] or "x"


# --------------------------------------------------------------------------- presencia
@dataclass
class Peer:
    user: str
    host: str
    since: str
    last: float

    @property
    def label(self) -> str:
        return f"{self.user} ({self.host})"


class Presence:
    def __init__(self, document: str, user: str | None = None, host: str | None = None):
        self.dir = document + ".presencia"
        self.user = user or default_author()
        self.host = host or socket.gethostname()
        self.since = _now()
        self.file = os.path.join(self.dir, f"{_safe(self.user)}@{_safe(self.host)}.json")

    def heartbeat(self) -> None:
        os.makedirs(self.dir, exist_ok=True)
        tmp = self.file + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump({"user": self.user, "host": self.host, "since": self.since, "last": time.time()}, f)
        os.replace(tmp, self.file)

    def others(self, now: float | None = None) -> list[Peer]:
        now = now or time.time()
        out = []
        if not os.path.isdir(self.dir):
            return out
        for name in os.listdir(self.dir):
            path = os.path.join(self.dir, name)
            if not name.endswith(".json") or path == self.file:
                continue
            try:
                with open(path, encoding="utf-8") as f:
                    d = json.load(f)
                if now - float(d.get("last", 0)) < STALE_SECONDS:
                    out.append(Peer(str(d.get("user", "?")), str(d.get("host", "?")), str(d.get("since", "")),
                                    float(d["last"])))
            except (OSError, ValueError, KeyError):
                continue
        return sorted(out, key=lambda p: p.user)

    def leave(self) -> None:
        try:
            os.remove(self.file)
            if not os.listdir(self.dir):
                os.rmdir(self.dir)
        except OSError:
            pass


# --------------------------------------------------------------------------- comentarios
@dataclass
class Reply:
    author: str
    text: str
    created: str = field(default_factory=_now)


@dataclass
class Comment:
    id: str
    page: str
    widget: str | None
    author: str
    text: str
    created: str = field(default_factory=_now)
    updated: str = field(default_factory=_now)
    resolved: bool = False
    replies: list[Reply] = field(default_factory=list)

    @classmethod
    def from_dict(cls, d: dict) -> "Comment":
        return cls(str(d["id"]), str(d.get("page", "")), d.get("widget"), str(d.get("author", "")),
                   str(d.get("text", "")), str(d.get("created", "")), str(d.get("updated", d.get("created", ""))),
                   bool(d.get("resolved")), [Reply(**r) for r in d.get("replies", [])])


class CommentStore:
    def __init__(self, document: str | None):
        self.path = document + ".comentarios.json" if document else None
        self.comments: dict[str, Comment] = {}
        self.deleted: set[str] = set()
        self.reload()

    def reload(self) -> None:
        disk = self._read()
        for cid, c in disk.items():
            mine = self.comments.get(cid)
            if mine is None or c.updated >= mine.updated:
                self.comments[cid] = c

    def _read(self) -> dict[str, Comment]:
        if not self.path or not os.path.exists(self.path):
            return {}
        try:
            with open(self.path, encoding="utf-8") as f:
                data = json.load(f)
            return {c["id"]: Comment.from_dict(c) for c in data.get("comments", [])}
        except (OSError, ValueError, KeyError, TypeError):
            return {}

    def save(self) -> None:
        if not self.path:
            return
        disk = self._read()                    # lo que otros hayan añadido mientras tanto
        for cid, c in disk.items():
            if cid in self.deleted:
                continue
            mine = self.comments.get(cid)
            if mine is None or c.updated > mine.updated:
                self.comments[cid] = c
        data = {"format": "olvgl-comments", "comments": [asdict(c) for c in
                                                          sorted(self.comments.values(), key=lambda c: c.created)]}
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=1)
        os.replace(tmp, self.path)

    # ------------------------------------------------ operaciones
    def add(self, page: str, widget: str | None, text: str, author: str | None = None) -> Comment:
        c = Comment(uuid.uuid4().hex[:12], page, widget, author or default_author(), text.strip())
        self.comments[c.id] = c
        self.save()
        return c

    def reply(self, cid: str, text: str, author: str | None = None) -> None:
        c = self.comments[cid]
        c.replies.append(Reply(author or default_author(), text.strip()))
        c.updated = _now()
        self.save()

    def set_resolved(self, cid: str, resolved: bool = True) -> None:
        c = self.comments[cid]
        c.resolved = resolved
        c.updated = _now()
        self.save()

    def delete(self, cid: str) -> None:
        self.comments.pop(cid, None)
        self.deleted.add(cid)
        self.save()

    def for_page(self, page: str, include_resolved: bool = True) -> list[Comment]:
        return sorted((c for c in self.comments.values() if c.page == page and (include_resolved or not c.resolved)),
                      key=lambda c: c.created)

    def open_by_widget(self, page: str) -> dict[str, int]:
        out: dict[str, int] = {}
        for c in self.for_page(page, include_resolved=False):
            if c.widget:
                out[c.widget] = out.get(c.widget, 0) + 1
        return out

    def rename_widgets(self, mapping: dict[str, str]) -> None:
        changed = False
        for c in self.comments.values():
            if c.widget in mapping:
                c.widget = mapping[c.widget]
                changed = True
        if changed:
            self.save()
