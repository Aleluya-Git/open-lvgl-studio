"""Adaptadores de infraestructura para la sesión de sincronización (Fase 3)."""
from __future__ import annotations

import os
import shutil
import time

from olvgl.application.sync_service import SyncPorts, SyncSession
from olvgl.domain.yaml_ast import YMap, walk
from olvgl.infrastructure.esphome_generator import generate_ast, is_local_file
from olvgl.infrastructure.esphome_importer import import_esphome_text
from olvgl.infrastructure.yaml_parser import YamlParseError, parse
from olvgl.infrastructure.yaml_sync import sync_text

BACKUP_SUFFIX = ".olvgl.bak"


class _Text:
    """Lee y escribe conservando BOM y finales de línea (CRLF en Windows)."""

    def __init__(self) -> None:
        self.crlf: dict[str, bool] = {}
        self.bom: dict[str, bool] = {}

    def read(self, path: str) -> str:
        with open(path, "rb") as f:
            raw = f.read()
        bom = raw.startswith(b"\xef\xbb\xbf")
        text = raw.decode("utf-8-sig")
        self.bom[path] = bom
        self.crlf[path] = "\r\n" in text
        return text.replace("\r\n", "\n")

    def write(self, path: str, text: str) -> None:
        if self.crlf.get(path):
            text = text.replace("\n", "\r\n")
        data = text.encode("utf-8")
        if self.bom.get(path):
            data = b"\xef\xbb\xbf" + data
        directory = os.path.dirname(os.path.abspath(path))
        tmp = os.path.join(directory, f".{os.path.basename(path)}.olvgl-tmp")
        with open(tmp, "wb") as f:
            f.write(data)
        replace_with_retry(tmp, path, data)


def replace_with_retry(tmp: str, path: str, data: bytes, attempts: int = 6) -> None:
    """os.replace con reintentos: en Windows falla si otro programa (antivirus,
    indexador, un editor) tiene el fichero abierto un instante. Como último
    recurso se escribe directamente sobre el fichero."""
    for i in range(attempts):
        try:
            os.replace(tmp, path)
            return
        except PermissionError:
            time.sleep(0.05 * (i + 1))
    try:
        with open(path, "wb") as f:
            f.write(data)
    finally:
        try:
            os.remove(tmp)
        except OSError:
            pass


def backup(path: str) -> str | None:
    target = path + BACKUP_SUFFIX
    try:
        shutil.copy2(path, target)
        return target
    except OSError:
        return None


def check_syncable(text: str, path: str) -> str | None:
    try:
        root = parse(text, path)
    except YamlParseError as exc:
        return f"El YAML no es válido: {exc}"
    if not isinstance(root, YMap):
        return "El documento no es un mapa YAML"
    if root.get("packages") is not None or "<<" in root:
        return ("El fichero usa packages: la escritura directa todavía no está soportada; "
                "usa Exportar ESPHome")
    for node in walk(root):
        if getattr(node, "tag", None) == "!include":
            return ("El fichero usa !include: la escritura directa todavía no está soportada; "
                    "usa Exportar ESPHome")
    return None


def relative_to(path: str):
    base = os.path.dirname(os.path.abspath(path))

    def mapper(p: str) -> str:
        if not is_local_file(p) or not os.path.isabs(p):
            return p.replace("\\", "/") if isinstance(p, str) else p
        try:
            rel = os.path.relpath(p, base)
        except ValueError:
            return p
        return rel.replace("\\", "/")
    return mapper


def make_session(path: str) -> SyncSession:
    text_io = _Text()
    rel = relative_to(path)
    ports = SyncPorts(
        read=text_io.read,
        write=text_io.write,
        backup=backup,
        generate_ast=lambda project: generate_ast(project, rel, rel),
        merge=sync_text,
        import_text=lambda text, p: import_esphome_text(text, p),
        check=check_syncable,
    )
    return SyncSession(path, ports)


