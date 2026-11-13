"""Base de datos SQLite de la aplicación: ajustes y proyectos recientes."""
from __future__ import annotations

import json
import os
import sqlite3
import sys
import time
from typing import Any

SCHEMA = """
CREATE TABLE IF NOT EXISTS settings (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS recent_projects (
    path      TEXT PRIMARY KEY,
    name      TEXT NOT NULL DEFAULT '',
    opened_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""
DB_VERSION = 1


def app_data_dir() -> str:
    if sys.platform.startswith("win"):
        base = os.environ.get("APPDATA") or os.path.expanduser("~")
        path = os.path.join(base, "OpenLVGLStudio")
    elif sys.platform == "darwin":
        path = os.path.expanduser("~/Library/Application Support/OpenLVGLStudio")
    else:
        base = os.environ.get("XDG_DATA_HOME") or os.path.expanduser("~/.local/share")
        path = os.path.join(base, "open-lvgl-studio")
    os.makedirs(path, exist_ok=True)
    return path


class SettingsDB:
    def __init__(self, path: str | None = None):
        self.path = path or os.path.join(app_data_dir(), "studio.db")
        self._conn = sqlite3.connect(self.path)
        self._conn.executescript(SCHEMA)
        self._conn.execute("INSERT OR IGNORE INTO meta(key, value) VALUES ('db_version', ?)",
                           (str(DB_VERSION),))
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()

    # ------------------------------------------------------------------ ajustes
    def get(self, key: str, default: Any = None) -> Any:
        row = self._conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
        if row is None:
            return default
        try:
            return json.loads(row[0])
        except json.JSONDecodeError:
            return default

    def set(self, key: str, value: Any) -> None:
        self._conn.execute("INSERT OR REPLACE INTO settings(key, value) VALUES (?, ?)",
                           (key, json.dumps(value)))
        self._conn.commit()

    # ------------------------------------------------------------------ recientes
    def add_recent(self, path: str, name: str = "") -> None:
        self._conn.execute(
            "INSERT OR REPLACE INTO recent_projects(path, name, opened_at) VALUES (?, ?, ?)",
            (os.path.abspath(path), name, time.time()))
        self._conn.commit()

    def remove_recent(self, path: str) -> None:
        self._conn.execute("DELETE FROM recent_projects WHERE path = ?", (os.path.abspath(path),))
        self._conn.commit()

    def recent(self, limit: int = 10, only_existing: bool = True) -> list[tuple[str, str]]:
        rows = self._conn.execute(
            "SELECT path, name FROM recent_projects ORDER BY opened_at DESC").fetchall()
        result = []
        for path, name in rows:
            if only_existing and not os.path.exists(path):
                continue
            result.append((path, name))
            if len(result) >= limit:
                break
        return result
