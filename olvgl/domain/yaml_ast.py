"""AST YAML de Open LVGL Studio.

Árbol sintáctico fiel al texto: conserva orden de claves, estilo de escalares,
comentarios y posiciones de origen (Span). Lo produce el generador (Fase 1) y
lo producirán los parsers (Fase 2); la sincronización (Fase 3) usará los Span
para reescribir sólo los nodos modificados.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterator, Union

# Estilos de escalar
PLAIN = "plain"        # el emitter decide si necesita comillas
DOUBLE = "double"      # comillas dobles forzadas
HEX = "hex"            # entero como 0xRRGGBB
LITERAL = "literal"    # bloque |-
VERBATIM = "verbatim"  # se escribe tal cual (!include, !secret, lambdas cortas)


@dataclass
class Span:
    line: int
    col: int
    end_line: int = -1
    end_col: int = -1


@dataclass
class YScalar:
    value: Any
    style: str = PLAIN
    span: Span | None = None
    tag: str | None = None      # etiqueta explícita: !lambda, !secret, !include…


@dataclass
class YRaw:
    """Bloque YAML no interpretado: se emite con la sangría del contexto."""
    text: str
    span: Span | None = None


@dataclass
class YSeq:
    items: list["YNode"] = field(default_factory=list)
    span: Span | None = None
    tag: str | None = None

    def append(self, node: "YNode") -> "YSeq":
        self.items.append(node)
        return self


@dataclass
class YPair:
    key: str
    value: "YNode"
    comment: str | None = None
    key_span: Span | None = None   # posición de la clave en el texto original


@dataclass
class YMap:
    items: list[YPair] = field(default_factory=list)
    span: Span | None = None
    comment: str | None = None
    tag: str | None = None

    def set(self, key: str, value: "YNode | Any", comment: str | None = None) -> "YMap":
        node = value if isinstance(value, (YScalar, YRaw, YSeq, YMap)) else YScalar(value)
        for p in self.items:
            if p.key == key:
                p.value = node
                if comment is not None:
                    p.comment = comment
                return self
        self.items.append(YPair(key, node, comment))
        return self

    def get(self, key: str) -> "YNode | None":
        return next((p.value for p in self.items if p.key == key), None)

    def keys(self) -> list[str]:
        return [p.key for p in self.items]

    def __contains__(self, key: str) -> bool:
        return any(p.key == key for p in self.items)


YNode = Union[YScalar, YRaw, YSeq, YMap]


def walk(node: YNode) -> Iterator[YNode]:
    yield node
    if isinstance(node, YMap):
        for p in node.items:
            yield from walk(p.value)
    elif isinstance(node, YSeq):
        for it in node.items:
            yield from walk(it)


def to_python(node: YNode) -> Any:
    """Convierte el AST a estructuras Python (útil para tests y comparación)."""
    if isinstance(node, YScalar):
        return node.value
    if isinstance(node, YRaw):
        return node.text
    if isinstance(node, YSeq):
        return [to_python(i) for i in node.items]
    if isinstance(node, YMap):
        return {p.key: to_python(p.value) for p in node.items}
    raise TypeError(type(node))
