"""Emitter: AST YAML → texto, con el estilo de la documentación de ESPHome.

- Sangría de 2 espacios; las secuencias bajo una clave se sangran 2 más.
- Enteros con estilo HEX como 0xRRGGBB.
- Comillas dobles sólo cuando hacen falta.
"""
from __future__ import annotations

import re

from olvgl.domain.yaml_ast import (DOUBLE, HEX, LITERAL, VERBATIM, YMap, YNode, YRaw,
                                   YScalar, YSeq)

INDENT = 2
_PLAIN_SAFE = re.compile(r"^[^\W\d][\w.\-/ ]*$")
_RESERVED = {"true", "false", "yes", "no", "on", "off", "null", "~", "y", "n"}
_NUMBER_LIKE = re.compile(r"^[-+]?(\d|\.\d|0x|0o|0b)")


def quote(s: str) -> str:
    escaped = (s.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")
               .replace("\t", "\\t").replace("\r", "\\r"))
    return f'"{escaped}"'


def needs_quotes(s: str) -> bool:
    if s == "" or s != s.strip():
        return True
    if s.lower() in _RESERVED:
        return True
    if _NUMBER_LIKE.match(s):
        return True
    if not _PLAIN_SAFE.match(s):
        return True
    return False


def format_scalar(node: YScalar) -> str:
    text = _format_scalar_value(node)
    if node.tag:
        return f"{node.tag} {text}".rstrip()
    return text


def _format_scalar_value(node: YScalar) -> str:
    v = node.value
    if node.style == VERBATIM:
        return str(v)
    if v is None:
        return ""
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, int):
        if node.style == HEX:
            return f"0x{v:06X}" if v >= 0 else str(v)
        return str(v)
    if isinstance(v, float):
        return repr(v)
    s = str(v)
    if node.style == DOUBLE or needs_quotes(s):
        return quote(s)
    return s


def _is_block_literal(node: YNode) -> bool:
    return isinstance(node, YScalar) and node.style == LITERAL and node.value is not None


def _literal_lines(text: str, indent: int) -> list[str]:
    pad = " " * indent
    return [pad + line if line else "" for line in str(text).splitlines()] or [pad]


def _emit_value_after_key(key_prefix: str, value: YNode, key_col: int) -> list[str]:
    """Líneas para 'clave: valor' donde key_prefix ya incluye sangría y 'clave:'."""
    if isinstance(value, YScalar):
        if _is_block_literal(value):
            tag = f" {value.tag}" if value.tag else ""
            return [key_prefix + tag + " |-"] + _literal_lines(value.value, key_col + INDENT)
        text = format_scalar(value)
        return [key_prefix + (" " + text if text != "" else "")]
    tag = f" {value.tag}" if getattr(value, "tag", None) else ""
    if isinstance(value, YMap):
        if not value.items:
            return [key_prefix + tag + " {}"]
        return [key_prefix + tag] + _emit_map(value, key_col + INDENT)
    if isinstance(value, YSeq):
        if not value.items:
            return [key_prefix + tag + " []"]
        return [key_prefix + tag] + _emit_seq(value, key_col + INDENT)
    if isinstance(value, YRaw):
        return [key_prefix] + _raw_lines(value.text, key_col + INDENT)
    raise TypeError(type(value))


def _emit_map(m: YMap, indent: int) -> list[str]:
    lines: list[str] = []
    pad = " " * indent
    if m.comment:
        lines += [f"{pad}# {c}" if c else f"{pad}#" for c in m.comment.splitlines()]
    for pair in m.items:
        if pair.comment:
            lines += [f"{pad}# {c}" if c else f"{pad}#" for c in pair.comment.splitlines()]
        lines += _emit_value_after_key(f"{pad}{pair.key}:", pair.value, indent)
    return lines


def _raw_lines(text: str, indent: int) -> list[str]:
    raw = [ln.rstrip() for ln in str(text).strip("\n").splitlines()]
    # quita la sangría común
    common = min((len(ln) - len(ln.lstrip()) for ln in raw if ln.strip()), default=0)
    pad = " " * indent
    return [pad + ln[common:] if ln.strip() else "" for ln in raw]


def _emit_seq(s: YSeq, indent: int) -> list[str]:
    lines: list[str] = []
    pad = " " * indent
    for item in s.items:
        if isinstance(item, YScalar):
            if _is_block_literal(item):
                lines.append(f"{pad}- {item.tag + ' ' if item.tag else ''}|-")
                lines += _literal_lines(item.value, indent + INDENT)
            else:
                text = format_scalar(item)
                lines.append(f"{pad}-" + (f" {text}" if text != "" else ""))
        elif isinstance(item, YMap) and item.tag:
            sub = _emit_map(item, indent + INDENT)
            lines.append(f"{pad}- {item.tag}")
            lines += sub
        elif isinstance(item, YMap):
            if not item.items:
                lines.append(f"{pad}- {{}}")
                continue
            sub = _emit_map(item, indent + INDENT)
            # el primer elemento no comentario va en la línea del guion
            first = next(i for i, ln in enumerate(sub) if not ln.lstrip().startswith("#"))
            lines += sub[:first]
            lines.append(f"{pad}- " + sub[first][indent + INDENT:])
            lines += sub[first + 1:]
        elif isinstance(item, YSeq):
            sub = _emit_seq(item, indent + INDENT)
            lines.append(f"{pad}- " + sub[0][indent + INDENT:])
            lines += sub[1:]
        elif isinstance(item, YRaw):
            sub = _raw_lines(item.text, indent + INDENT)
            if not sub:
                continue
            lines.append(f"{pad}- " + sub[0][indent + INDENT:])
            lines += sub[1:]
        else:
            raise TypeError(type(item))
    return lines


def emit(node: YNode, header: str | None = None) -> str:
    """Convierte un nodo raíz en texto YAML terminado en salto de línea."""
    lines: list[str] = []
    if header:
        lines += [f"# {h}" if h else "#" for h in header.splitlines()]
    if isinstance(node, YMap):
        # línea en blanco entre bloques de primer nivel, como en ESPHome
        for i, pair in enumerate(node.items):
            if i > 0:
                lines.append("")
            lines += _emit_map(YMap([pair]), 0)
    elif isinstance(node, YSeq):
        lines += _emit_seq(node, 0)
    elif isinstance(node, YScalar):
        lines.append(format_scalar(node))
    elif isinstance(node, YRaw):
        lines += _raw_lines(node.text, 0)
    return "\n".join(lines) + "\n"
