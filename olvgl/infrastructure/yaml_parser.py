"""Parser YAML → AST de Open LVGL Studio.

Usa el *composer* de PyYAML (no construye objetos Python), así conserva:
- el orden de claves y las claves duplicadas,
- las etiquetas desconocidas (!lambda, !secret, !include, !extend…),
- el estilo de cada escalar (comillas, bloques |, hexadecimal),
- la posición de cada nodo (Span), base de la sincronización de la Fase 3.

PyYAML no conserva los comentarios; la Fase 3 trabajará sobre el texto
original guiándose por los Span.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field

import yaml
from yaml.constructor import SafeConstructor
from yaml.nodes import MappingNode, Node, ScalarNode, SequenceNode

from olvgl.domain.yaml_ast import (DOUBLE, HEX, LITERAL, PLAIN, Span, YMap, YNode, YPair,
                                   YScalar, YSeq)

STD_PREFIX = "tag:yaml.org,2002:"
_LOADER = getattr(yaml, "CSafeLoader", yaml.SafeLoader)   # libyaml si está disponible (≈10× más rápido)
MAX_INCLUDE_DEPTH = 8


class YamlParseError(Exception):
    def __init__(self, message: str, line: int | None = None, col: int | None = None, path: str = ""):
        where = f"{os.path.basename(path)}:" if path else ""
        if line is not None:
            where += f"{line}:{col}: "
        super().__init__(where + message)
        self.line, self.col, self.path = line, col, path


def _span(node: Node) -> Span:
    s, e = node.start_mark, node.end_mark
    return Span(s.line + 1, s.column + 1, e.line + 1, e.column + 1)


class _Converter:
    def __init__(self, path: str = "") -> None:
        self._constructor = SafeConstructor()
        self.path = path

    def scalar(self, node: ScalarNode) -> YScalar:
        span = _span(node)
        if node.tag.startswith(STD_PREFIX):
            try:
                value = self._constructor.construct_object(node, deep=True)
            except Exception:
                value = node.value
            if isinstance(value, (bytes, bytearray)):
                value = node.value
            if not isinstance(value, (str, int, float, bool)) and value is not None:
                value = str(node.value)   # fechas, etc.: se conservan como texto
            tag = None
        else:
            value = node.value
            tag = node.tag
        style = PLAIN
        if node.style == '"' or node.style == "'":
            style = DOUBLE
        elif node.style in ("|", ">"):
            style = LITERAL
        elif isinstance(value, int) and not isinstance(value, bool) and node.value.lower().startswith("0x"):
            style = HEX
        return YScalar(value, style, span, tag)

    def convert(self, node: Node) -> YNode:
        if isinstance(node, ScalarNode):
            return self.scalar(node)
        tag = None if node.tag.startswith(STD_PREFIX) else node.tag
        if isinstance(node, SequenceNode):
            return YSeq([self.convert(n) for n in node.value], _span(node), tag)
        if isinstance(node, MappingNode):
            items = []
            seen: dict[str, int] = {}
            for k, v in node.value:
                if isinstance(k, ScalarNode):
                    key = k.value
                else:
                    key = str(self.convert(k))
                if key in seen and key != "<<":
                    # ESPHome rechaza las claves repetidas: se avisa igual, con la línea
                    raise YamlParseError(f"clave repetida «{key}» (ya aparece en la línea {seen[key]})",
                                         k.start_mark.line + 1, k.start_mark.column + 1, self.path)
                seen[key] = k.start_mark.line + 1
                items.append(YPair(key, self.convert(v), None, _span(k)))
            return YMap(items, _span(node), None, tag)
        raise YamlParseError(f"Nodo YAML no soportado: {type(node).__name__}")


def parse(text: str, path: str = "") -> YNode:
    """Texto YAML → AST. Un documento vacío devuelve un YMap vacío."""
    try:
        node = yaml.compose(text, Loader=_LOADER)
    except yaml.MarkedYAMLError as exc:
        mark = exc.problem_mark
        problem = str(exc.problem or exc)
        if "unacceptable character" in problem or "special characters are not allowed" in problem:
            problem += (" — el fichero tiene caracteres de control: puede que no sea texto (¿un fichero binario o "
                        "una página web?) o que esté dañado")
        raise YamlParseError(problem, mark.line + 1 if mark else None,
                             mark.column + 1 if mark else None, path) from exc
    except yaml.reader.ReaderError as exc:
        pos = getattr(exc, "position", 0) or 0
        line = text.count("\n", 0, pos) + 1
        col = pos - (text.rfind("\n", 0, pos) + 1) + 1
        code = getattr(exc, "character", "")
        if isinstance(code, str) and code:
            code = ord(code)
        code = f"#x{code:04x}" if isinstance(code, int) else str(code)
        raise YamlParseError(f"carácter no permitido {code}: el fichero no es un YAML de texto válido (¿un "
                             "fichero binario, una página web o un fichero dañado?)", line, col, path) from exc
    except yaml.YAMLError as exc:
        raise YamlParseError(str(exc), path=path) from exc
    if node is None:
        return YMap()
    return _Converter(path).convert(node)


def read_text(path: str, notes: list[str] | None = None) -> str:
    """Texto de un YAML: codificación, caracteres nulos y páginas web guardadas como .yaml (source_text)."""
    from olvgl.infrastructure.source_text import NotYamlError, read_source
    try:
        src = read_source(path)
    except NotYamlError as exc:
        raise YamlParseError(str(exc), path=path) from exc
    if notes is not None:
        notes.extend(src.notes)
        if src.from_html:
            notes.append("__from_html__")
    return src.text


def parse_file(path: str, notes: list[str] | None = None) -> YNode:
    return parse(read_text(path, notes), path)


# --------------------------------------------------------------------------- includes
@dataclass
class IncludeLog:
    included: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    from_html: bool = False          # el YAML se recuperó de una página web


def _include_target(node: YNode) -> str | None:
    if isinstance(node, YScalar) and node.tag == "!include" and isinstance(node.value, str):
        return node.value
    if isinstance(node, YMap) and node.tag == "!include":
        f = node.get("file")
        if isinstance(f, YScalar) and isinstance(f.value, str):
            return f.value
    return None


def expand_includes(node: YNode, base_dir: str, log: IncludeLog | None = None, depth: int = 0) -> YNode:
    """Sustituye cada `!include fichero` por el AST del fichero (recursivo)."""
    log = log or IncludeLog()
    target = _include_target(node)
    if target is not None:
        if isinstance(node, YMap) and node.get("vars") is not None:
            log.warnings.append(f"!include {target}: las variables (vars) no se sustituyen")
        path = os.path.normpath(os.path.join(base_dir, target))
        if depth >= MAX_INCLUDE_DEPTH:
            log.warnings.append(f"!include {target}: demasiados niveles de inclusión")
            return node
        if not os.path.exists(path):
            log.warnings.append(f"!include {target}: no se encuentra {path}")
            return node
        log.included.append(path)
        sub = parse_file(path)
        return expand_includes(sub, os.path.dirname(path), log, depth + 1)
    if isinstance(node, YMap):
        for p in node.items:
            p.value = expand_includes(p.value, base_dir, log, depth)
    elif isinstance(node, YSeq):
        node.items = [expand_includes(i, base_dir, log, depth) for i in node.items]
    return node


def merge_packages(root: YMap, log: IncludeLog) -> YMap:
    """Mezcla `packages:` y `<<:` (ya expandidos) como hace ESPHome: primero los
    paquetes y encima el fichero principal; las listas se concatenan."""
    def merge_into(dst: YMap, src: YMap) -> None:
        for p in src.items:
            existing = dst.get(p.key)
            if existing is None:
                dst.items.append(YPair(p.key, p.value))
            elif isinstance(existing, YSeq) and isinstance(p.value, YSeq):
                existing.items.extend(p.value.items)
            elif isinstance(existing, YMap) and isinstance(p.value, YMap):
                merge_into(existing, p.value)
            else:  # el valor posterior (fichero principal) gana
                for q in dst.items:
                    if q.key == p.key:
                        q.value = p.value

    main = YMap(span=root.span)
    pending: list[YMap] = []
    for p in root.items:
        if p.key == "packages" and isinstance(p.value, YMap):
            for pkg in p.value.items:
                if isinstance(pkg.value, YMap) and _include_target(pkg.value) is None:
                    if pkg.value.get("url") is not None or pkg.value.get("github") is not None:
                        log.warnings.append(f"Paquete remoto '{pkg.key}' no importado")
                        continue
                    pending.append(pkg.value)
                else:
                    log.warnings.append(f"Paquete '{pkg.key}' no se pudo cargar")
        elif p.key == "<<" and isinstance(p.value, YMap):
            pending.append(p.value)
        else:
            main.items.append(YPair(p.key, p.value))
    out = YMap(span=root.span)
    for pkg in pending:
        merge_into(out, pkg)
    merge_into(out, main)
    return out


def load_esphome(path: str) -> tuple[YMap, IncludeLog]:
    """Carga un YAML de ESPHome resolviendo !include y packages locales."""
    log = IncludeLog()
    notes: list[str] = []
    root = parse_file(path, notes)
    log.from_html = "__from_html__" in notes
    log.warnings.extend(n for n in notes if n != "__from_html__")
    if not isinstance(root, YMap):
        raise YamlParseError("El documento no es un mapa YAML", path=path)
    root = expand_includes(root, os.path.dirname(os.path.abspath(path)), log)
    if not isinstance(root, YMap):
        raise YamlParseError("El documento no es un mapa YAML", path=path)
    return merge_packages(root, log), log
