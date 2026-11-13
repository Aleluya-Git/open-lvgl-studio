"""Motor Diff/Merge de la Fase 3: sincroniza el modelo con el YAML original.

Recibe tres versiones de las secciones gestionadas (lvgl:, font:, image:, color:):

- **B** (base): el texto del fichero en la última sincronización,
- **O** (original actual): el texto del fichero ahora (puede tener cambios externos),
- **C** (editor): el AST generado a partir del modelo.

Calcula un *merge a tres bandas* nodo a nodo y lo aplica como **ediciones de
texto mínimas** sobre O, usando las posiciones (Span) del AST. Todo lo que no
cambia —comentarios, formato, comillas, el resto de secciones (sensor:,
script:…)— queda intacto. Si una edición no se puede aplicar de forma segura
se reescribe el nodo más pequeño que la contiene; y como red de seguridad el
resultado se vuelve a analizar y se comprueba que coincide con C.
"""
from __future__ import annotations

import difflib
import json
from dataclasses import dataclass, field
from typing import Any

from olvgl.domain.yaml_ast import LITERAL, YMap, YNode, YPair, YRaw, YScalar, YSeq
from olvgl.infrastructure.yaml_emitter import _emit_map, _emit_seq, format_scalar, quote
from olvgl.infrastructure.yaml_parser import parse

MANAGED_SECTIONS = ("color", "font", "image", "lvgl")

# Los últimos textos analizados: el resultado de una sincronización es el punto
# de partida de la siguiente, así que normalmente sólo hay que analizar uno nuevo.
# (El motor nunca modifica estos árboles.)
_PARSED: dict[str, Any] = {}
_PARSED_MAX = 3


def _parse_cached(text: str):
    tree = _PARSED.pop(text, None)
    if tree is None:
        tree = parse(text)
    _PARSED[text] = tree          # el más reciente, al final
    while len(_PARSED) > _PARSED_MAX:
        _PARSED.pop(next(iter(_PARSED)))
    return tree


# --------------------------------------------------------------------------- comparación semántica
_CANON: dict[tuple[int, str], Any] = {}
_ACTIVE = False   # la caché sólo es válida durante una sincronización (los árboles siguen vivos)
_RAW: dict[str, Any] = {}


def canon(node: YNode | None, key: str = "", parent_key: str = "") -> Any:
    if node is None:
        return None
    if not _ACTIVE:
        return _canon(node, key, parent_key)
    k = (id(node), key)
    if k in _CANON:
        return _CANON[k]
    v = _canon(node, key, parent_key)
    _CANON[k] = v
    return v


def _canon(node: YNode | None, key: str = "", parent_key: str = "") -> Any:
    """Forma canónica para comparar: ignora estilo, comillas, hex/decimal y
    las equivalencias que introduce el generador (ids de label de botón,
    `on_x: then: [...]` ≡ `on_x: [...]`)."""
    if node is None:
        return None
    if isinstance(node, YScalar):
        v = node.value
        if isinstance(v, str) and node.style == LITERAL:
            v = v.rstrip("\n")
        return {"!": node.tag, "v": v} if node.tag else v
    if isinstance(node, YRaw):
        if node.text not in _RAW:
            tree = parse(node.text)   # se guarda el árbol: sus ids no deben reutilizarse
            _RAW[node.text] = (tree, _canon(tree))
        return _RAW[node.text][1]
    if isinstance(node, YSeq):
        out = [canon(i, "", key) for i in node.items]
        return {"!": node.tag, "v": out} if node.tag else out
    if isinstance(node, YMap):
        d = {}
        for p in node.items:
            v = p.value
            if p.key.startswith("on_") and isinstance(v, YMap) and v.keys() == ["then"]:
                v = v.get("then")
            if p.key == "id" and key == "label" and _is_label_id(v):
                continue
            d[p.key] = canon(v, p.key, key)
        return {"!": node.tag, "v": d} if node.tag else d
    raise TypeError(type(node))


def _is_label_id(v: YNode | None) -> bool:
    return isinstance(v, YScalar) and isinstance(v.value, str) and v.value.endswith("_label")


def same(a: YNode | None, b: YNode | None, key: str = "") -> bool:
    return canon(a, key) == canon(b, key)


def _ident(item: YNode) -> Any:
    """Identidad de un elemento de lista: (tipo, id) de un widget, id de página/recurso."""
    if isinstance(item, YMap):
        idn = item.get("id")
        if isinstance(idn, YScalar) and isinstance(idn.value, str):
            return ("id", idn.value)
        if len(item.items) == 1 and isinstance(item.items[0].value, YMap):
            inner = item.items[0].value.get("id")
            if isinstance(inner, YScalar) and isinstance(inner.value, str):
                return (item.items[0].key, inner.value)
    return ("anon", json.dumps(canon(item), sort_keys=True, default=str))


# --------------------------------------------------------------------------- texto
class TextIndex:
    def __init__(self, text: str):
        self.text = text
        self.starts = [0]
        for i, ch in enumerate(text):
            if ch == "\n":
                self.starts.append(i + 1)

    def offset(self, line: int, col: int) -> int:
        """line/col en base 1 (como Span)."""
        line = max(1, min(line, len(self.starts)))
        return min(len(self.text), self.starts[line - 1] + col - 1)

    def line_of(self, off: int) -> int:
        lo, hi = 0, len(self.starts) - 1
        while lo < hi:
            mid = (lo + hi + 1) // 2
            if self.starts[mid] <= off:
                lo = mid
            else:
                hi = mid - 1
        return lo + 1

    def line_start(self, off: int) -> int:
        return self.starts[self.line_of(off) - 1]

    def line_end(self, off: int) -> int:
        """Posición del salto de línea de la línea de `off` (o fin de texto)."""
        n = self.text.find("\n", off)
        return len(self.text) if n < 0 else n

    def col(self, off: int) -> int:
        return off - self.line_start(off)


@dataclass
class Edit:
    start: int
    end: int
    text: str


@dataclass
class SyncResult:
    text: str
    edits: int = 0
    conflicts: list[str] = field(default_factory=list)
    rewritten: list[str] = field(default_factory=list)   # secciones reescritas enteras (repliegue)
    changed: bool = False


class UnsafeEdit(Exception):
    pass


# --------------------------------------------------------------------------- emisión
_FLOW_SPECIAL = set(",[]{}#&*!|>'\"%@`")


def _flow(node: YNode) -> str:
    if isinstance(node, YScalar):
        s = format_scalar(node)
        if isinstance(node.value, str) and not s.startswith('"') and any(c in _FLOW_SPECIAL for c in s):
            return quote(node.value) if not node.tag else s
        return s
    if isinstance(node, YSeq):
        return "[" + ", ".join(_flow(i) for i in node.items) + "]"
    if isinstance(node, YMap):
        return "{" + ", ".join(f"{p.key}: {_flow(p.value)}" for p in node.items) + "}"
    if isinstance(node, YRaw):
        raise UnsafeEdit("YAML libre dentro de una colección en línea")
    raise TypeError(type(node))


def _pair_lines(key: str, value: YNode, indent: int) -> list[str]:
    return _emit_map(YMap([YPair(key, value)]), indent)


def _item_lines(item: YNode, dash_col: int) -> list[str]:
    return _emit_seq(YSeq([item]), dash_col)


def _join_first_stripped(lines: list[str]) -> str:
    if not lines:
        return ""
    return "\n".join([lines[0].lstrip(" ")] + lines[1:])


# --------------------------------------------------------------------------- parcheador
class Patcher:
    def __init__(self, text: str):
        self.ix = TextIndex(text)
        self.text = text
        self.edits: list[Edit] = []
        self.conflicts: list[str] = []

    # ----------------------------------------------------------------- posiciones
    def start(self, node: YNode) -> int:
        return self.ix.offset(node.span.line, node.span.col)

    def is_flow(self, node: YNode) -> bool:
        if isinstance(node, (YMap, YSeq)) and node.span is not None:
            ch = self.text[self.start(node):self.start(node) + 1]
            return ch in "[{"
        return False

    def key_start(self, pair: YPair) -> int:
        return self.ix.offset(pair.key_span.line, pair.key_span.col)

    def _after_colon(self, pair: YPair) -> int:
        k_end = self.ix.offset(pair.key_span.end_line, pair.key_span.end_col)
        i = self.text.find(":", k_end)
        return i + 1 if i >= 0 else k_end

    def content_end(self, node: YNode) -> int:
        """Fin real del contenido (sin comentarios ni líneas en blanco posteriores)."""
        if isinstance(node, YScalar):
            s = self.start(node)
            e = self.ix.offset(node.span.end_line, node.span.end_col)
            if e <= s:
                return s
            while e > s and self.text[e - 1] in " \t\r\n":
                e -= 1
            return e
        if self.is_flow(node):
            return self.ix.offset(node.span.end_line, node.span.end_col)
        if isinstance(node, YSeq):
            if not node.items:
                return self.start(node)
            return self.content_end(node.items[-1])
        if isinstance(node, YMap):
            if not node.items:
                return self.start(node)
            return self.pair_end(node.items[-1])
        raise UnsafeEdit("nodo sin posición")

    def pair_end(self, pair: YPair) -> int:
        v = pair.value
        if isinstance(v, YScalar) and v.value is None and not v.tag:
            s, e = self.start(v), self.ix.offset(v.span.end_line, v.span.end_col)
            if e <= s:   # valor vacío: termina en los dos puntos
                return self._after_colon(pair)
        return max(self._after_colon(pair), self.content_end(v))

    def first_on_line(self, off: int) -> bool:
        return self.text[self.ix.line_start(off):off].strip() == ""

    def dash_of(self, item: YNode) -> int:
        """Posición del guion de un elemento de lista en bloque."""
        s = self.start(item)
        i = s - 1
        while i >= 0 and self.text[i] in " \t":
            i -= 1
        if i < 0 or self.text[i] != "-":
            raise UnsafeEdit("no se encuentra el guion del elemento")
        return i

    def add(self, start: int, end: int, text: str) -> None:
        self.edits.append(Edit(start, end, text))

    # ----------------------------------------------------------------- reemplazos
    def replace_pair(self, pair: YPair, new_value: YNode) -> None:
        ks = self.key_start(pair)
        end = self.pair_end(pair)
        indent = self.ix.col(ks)
        lines = _pair_lines(pair.key, new_value, indent)
        self.add(ks, end, _join_first_stripped(lines))

    def replace_item(self, item: YNode, new_item: YNode) -> None:
        s = self.start(item)
        end = self.content_end(item)
        col = self.ix.col(s)
        lines = _item_lines(new_item, max(0, col - 2))
        # quita el "- " del principio: el guion original se conserva
        first = lines[0].lstrip(" ")
        first = first[2:] if first.startswith("- ") else first
        self.add(s, end, "\n".join([first] + lines[1:]))

    def replace_flow(self, node: YNode, new_node: YNode) -> None:
        s = self.start(node)
        e = self.ix.offset(node.span.end_line, node.span.end_col)
        self.add(s, e, _flow(new_node))

    def delete_pair(self, m: YMap, pair: YPair, owner_item: YNode | None) -> None:
        ks = self.key_start(pair)
        if self.first_on_line(ks):
            end = self.pair_end(pair)
            self.add(self.ix.line_start(ks), min(len(self.text), self.ix.line_end(end) + 1), "")
            return
        raise UnsafeEdit("la clave comparte línea con el guion")

    def delete_item(self, item: YNode) -> None:
        d = self.dash_of(item)
        if not self.first_on_line(d):
            raise UnsafeEdit("elemento en línea compartida")
        end = self.content_end(item)
        self.add(self.ix.line_start(d), min(len(self.text), self.ix.line_end(end) + 1), "")

    def _append_after(self, end: int, lines: list[str]) -> None:
        """Inserta líneas completas justo después de la línea que contiene `end`."""
        eol = self.ix.line_end(end)
        if eol >= len(self.text):
            self.add(eol, eol, "\n" + "\n".join(lines))
        else:
            self.add(eol + 1, eol + 1, "\n".join(lines) + "\n")

    def insert_pair(self, m: YMap, key: str, value: YNode) -> None:
        if not m.items or self.is_flow(m):
            raise UnsafeEdit("mapa vacío o en línea")
        indent = self.ix.col(self.key_start(m.items[0]))
        self._append_after(self.content_end(m), _pair_lines(key, value, indent))

    def insert_item(self, seq: YSeq, index: int, item: YNode) -> None:
        if not seq.items or self.is_flow(seq):
            raise UnsafeEdit("lista vacía o en línea")
        dash = self.dash_of(seq.items[0])
        dash_col = self.ix.col(dash)
        lines = _item_lines(item, dash_col)
        if index < len(seq.items):
            d = self.dash_of(seq.items[index])
            if not self.first_on_line(d):
                raise UnsafeEdit("elemento en línea compartida")
            pos = self.ix.line_start(d)
            self.add(pos, pos, "\n".join(lines) + "\n")
        else:
            self._append_after(self.content_end(seq), lines)

    # ----------------------------------------------------------------- edición O → C
    def edit_value(self, pair: YPair, c: YNode, owner: YMap) -> None:
        """Lleva el valor de `pair` (en O) a `c`, con la edición más pequeña posible."""
        o = pair.value
        if same(o, c, pair.key):
            return
        v = o
        if pair.key.startswith("on_") and isinstance(o, YMap) and o.keys() == ["then"] and isinstance(c, YSeq):
            inner = next(p for p in o.items if p.key == "then")
            return self.edit_value(inner, c, o)
        try:
            if self.is_flow(v):
                self.replace_flow(v, c)
            elif isinstance(v, YMap) and isinstance(c, YMap) and v.tag == c.tag:
                self.edit_map(v, c, pair.key)
            elif isinstance(v, YSeq) and isinstance(c, YSeq) and v.tag == c.tag:
                self.edit_seq(v, c, pair.key)
            else:
                self.replace_pair(pair, c)
        except UnsafeEdit:
            self._drop_edits_inside(self.key_start(pair), self.pair_end(pair))
            self.replace_pair(pair, c)

    def _drop_edits_inside(self, s: int, e: int) -> None:
        self.edits = [x for x in self.edits if not (s <= x.start and x.end <= e)]

    def edit_map(self, o: YMap, c: YMap, key: str = "", owner_item: YNode | None = None) -> None:
        okeys = {p.key: p for p in o.items}
        ckeys = {p.key: p for p in c.items}
        for p in o.items:
            if p.key not in ckeys:
                if p.key == "id" and key == "label" and _is_label_id(p.value):
                    continue
                self.delete_pair(o, p, owner_item)
        for p in c.items:
            if p.key in okeys:
                self.edit_value(okeys[p.key], p.value, o)
        # las claves nuevas, después: así quedan detrás de lo que se añada dentro de la última clave
        for p in c.items:
            if p.key not in okeys:
                if p.key == "id" and key == "label" and _is_label_id(p.value):
                    continue
                self.insert_pair(o, p.key, p.value)

    def edit_item(self, o: YNode, c: YNode, parent_key: str) -> None:
        if same(o, c, parent_key):
            return
        try:
            if self.is_flow(o):
                self.replace_flow(o, c)
            elif isinstance(o, YMap) and isinstance(c, YMap) and o.tag == c.tag:
                if len(o.items) == 1 and len(c.items) == 1 and o.items[0].key == c.items[0].key:
                    # widget: `- tipo: {...}` → se edita el cuerpo
                    self.edit_value(o.items[0], c.items[0].value, o)
                else:
                    self.edit_map(o, c, "", owner_item=o)
            else:
                self.replace_item(o, c)
        except UnsafeEdit:
            self._drop_edits_inside(self.start(o), self.content_end(o))
            self.replace_item(o, c)

    def edit_seq(self, o: YSeq, c: YSeq, key: str = "") -> None:
        ok = [_ident(i) for i in o.items]
        ck = [_ident(i) for i in c.items]
        sm = difflib.SequenceMatcher(a=ok, b=ck, autojunk=False)
        for tag, i1, i2, j1, j2 in sm.get_opcodes():
            if tag == "equal":
                for a, b in zip(range(i1, i2), range(j1, j2)):
                    self.edit_item(o.items[a], c.items[b], key)
            elif tag == "replace" and (i2 - i1) == (j2 - j1):
                for a, b in zip(range(i1, i2), range(j1, j2)):
                    self.edit_item(o.items[a], c.items[b], key)
            else:
                for a in range(i1, i2):
                    self.delete_item(o.items[a])
                for b in range(j1, j2):
                    self.insert_item(o, i1, c.items[b])

    # ----------------------------------------------------------------- merge a tres bandas
    def merge_map(self, o: YMap, b: YMap | None, c: YMap, path: str, key: str = "") -> None:
        bmap = {p.key: p for p in b.items} if isinstance(b, YMap) else {}
        omap = {p.key: p for p in o.items}
        cmap = {p.key: p for p in c.items}
        inserts: list[tuple[str, YNode]] = []
        for k in list(dict.fromkeys(list(omap) + list(bmap) + list(cmap))):
            op, bp, cp = omap.get(k), bmap.get(k), cmap.get(k)
            ov = op.value if op else None
            bv = bp.value if bp else None
            cv = cp.value if cp else None
            if k == "id" and key == "label" and (_is_label_id(cv) or _is_label_id(ov)):
                continue
            if same(bv, cv, k):
                continue                      # el editor no cambió esto
            if same(ov, bv, k):               # sólo cambió el editor
                if cp is None:
                    self.delete_pair(o, op, None)
                elif op is None:
                    inserts.append((k, cv))
                else:
                    self.edit_value(op, cv, o)
                continue
            if same(ov, cv, k):
                continue                      # ambos hicieron el mismo cambio
            if op and bp and cp and isinstance(ov, YMap) and isinstance(bv, YMap) and isinstance(cv, YMap) \
                    and not self.is_flow(ov):
                self.merge_map(ov, bv, cv, f"{path}/{k}", k)
            elif op and bp and cp and isinstance(ov, YSeq) and isinstance(bv, YSeq) and isinstance(cv, YSeq) \
                    and not self.is_flow(ov):
                self.merge_seq(op, bv, cv, f"{path}/{k}", k)
            else:
                self.conflicts.append(f"{path}/{k}")
                if cp is None:
                    self.delete_pair(o, op, None)
                elif op is None:
                    inserts.append((k, cv))
                else:
                    self.edit_value(op, cv, o)
        for k, cv in inserts:
            self.insert_pair(o, k, cv)

    def merge_seq(self, opair: YPair, b: YSeq, c: YSeq, path: str, key: str) -> None:
        o = opair.value
        oi = [_ident(i) for i in o.items]
        bi = [_ident(i) for i in b.items]
        ci = [_ident(i) for i in c.items]
        identified = all(x[0] != "anon" for x in oi + bi + ci)
        if identified and oi == bi == ci:
            for a, bb, cc in zip(o.items, b.items, c.items):
                self.merge_item(a, bb, cc, f"{path}[{_ident(a)[1]}]", key)
            return
        if identified and oi == bi:
            # el editor añadió/quitó/reordenó: se aplica sobre O
            self.edit_value(opair, c, None)
            return
        if identified and bi == ci:
            # sólo el fichero cambió la lista; mezclar el contenido de los comunes
            cmap = {_ident(x): x for x in c.items}
            bmap = {_ident(x): x for x in b.items}
            for a in o.items:
                k = _ident(a)
                if k in bmap and k in cmap:
                    self.merge_item(a, bmap[k], cmap[k], f"{path}[{k[1]}]", key)
            return
        self.conflicts.append(path)
        self.edit_value(opair, c, None)

    def merge_item(self, o: YNode, b: YNode, c: YNode, path: str, key: str) -> None:
        if same(b, c, key) or same(o, c, key):
            return
        if same(o, b, key):
            self.edit_item(o, c, key)
            return
        if isinstance(o, YMap) and isinstance(b, YMap) and isinstance(c, YMap) and not self.is_flow(o):
            if len(o.items) == 1 and len(b.items) == 1 and len(c.items) == 1 \
                    and o.items[0].key == b.items[0].key == c.items[0].key \
                    and all(isinstance(x.items[0].value, YMap) for x in (o, b, c)):
                self.merge_map(o.items[0].value, b.items[0].value, c.items[0].value, path, o.items[0].key)
            else:
                self.merge_map(o, b, c, path, key)
            return
        self.conflicts.append(path)
        self.edit_item(o, c, key)

    # ----------------------------------------------------------------- aplicar
    def apply(self) -> str:
        order = sorted(range(len(self.edits)),
                       key=lambda i: (self.edits[i].start, self.edits[i].end, i), reverse=True)
        edits = [self.edits[i] for i in order]
        last_start = len(self.text) + 1
        text = self.text
        for e in edits:
            if e.end > last_start:
                raise UnsafeEdit("ediciones solapadas")
            text = text[:e.start] + e.text + text[e.end:]
            last_start = e.start
        return text


# --------------------------------------------------------------------------- entrada
def _section_text(root: YMap, key: str) -> str:
    return "\n".join(_pair_lines(key, root.get(key), 0))


def sync_text(current_text: str, base_text: str | None, generated: YMap,
              managed: tuple[str, ...] = MANAGED_SECTIONS) -> SyncResult:
    """Escribe en `current_text` los cambios del editor (generated) respecto a `base_text`.

    Si base_text es None, el editor manda (merge a dos bandas: O → C)."""
    global _ACTIVE
    _CANON.clear()
    _ACTIVE = True
    try:
        return _sync_text(current_text, base_text, generated, managed)
    finally:
        _ACTIVE = False
        _CANON.clear()


def _sync_text(current_text: str, base_text: str | None, generated: YMap,
               managed: tuple[str, ...]) -> SyncResult:
    o_root = _parse_cached(current_text)
    if not isinstance(o_root, YMap):
        raise ValueError("El fichero no es un mapa YAML")
    b_root = _parse_cached(base_text) if base_text is not None and base_text != current_text else o_root
    if not isinstance(b_root, YMap):
        b_root = YMap()
    gen = YMap([p for p in generated.items if p.key in managed])
    # secciones gestionadas que el editor no genera (p. ej. color: vacío) se tratan como ausentes
    o_view = YMap([p for p in o_root.items if p.key in managed])
    b_view = YMap([p for p in b_root.items if p.key in managed])

    patcher = Patcher(current_text)
    result = SyncResult(current_text)
    try:
        patcher.merge_map(o_view, b_view, gen, "", "")
        text = patcher.apply()
    except UnsafeEdit:
        text = None
    # inserción de secciones nuevas al final del fichero (insert_pair necesita un mapa con elementos)
    if text is not None:
        check = _parse_cached(text)
        ok = isinstance(check, YMap)
        for k in managed:
            exp = _expected(o_root, b_root, gen, k)
            if ok and exp is not _SKIP and not same(check.get(k), exp, k):
                ok = False
    else:
        ok = False
    if not ok:
        text, rewritten = _rewrite_sections(current_text, o_root, gen, managed)
        result.rewritten = rewritten
    result.text = text
    result.edits = len(patcher.edits)
    result.conflicts = patcher.conflicts
    result.changed = text != current_text
    return result


_SKIP = object()


def _expected(o_root: YMap, b_root: YMap, gen: YMap, key: str):
    """Lo que debería contener la sección tras el merge (para verificar)."""
    o, b, c = o_root.get(key), b_root.get(key), gen.get(key)
    if same(b, c, key):
        return o
    if same(o, b, key):
        return c
    return _SKIP   # cambios en ambos lados: el resultado mezcla los dos


def _rewrite_sections(text: str, o_root: YMap, gen: YMap, managed: tuple[str, ...]) -> tuple[str, list[str]]:
    """Repliegue seguro: reescribe enteras las secciones gestionadas que difieren."""
    ix = TextIndex(text)
    edits: list[Edit] = []
    rewritten = []
    for p in o_root.items:
        if p.key not in managed:
            continue
        c = gen.get(p.key)
        if same(p.value, c, p.key):
            continue
        rewritten.append(p.key)
        s = ix.offset(p.key_span.line, p.key_span.col)
        patcher = Patcher(text)
        e = ix.line_end(patcher.pair_end(p))
        new = _section_text(gen, p.key) if c is not None else ""
        edits.append(Edit(ix.line_start(s), e, new.rstrip("\n")))
    out = text
    for e in sorted(edits, key=lambda x: x.start, reverse=True):
        out = out[:e.start] + e.text + out[e.end:]
    missing = [k for k in managed if gen.get(k) is not None and o_root.get(k) is None]
    if missing:
        if not out.endswith("\n"):
            out += "\n"
        for k in missing:
            out += "\n" + _section_text(gen, k) + "\n"
            rewritten.append(k)
    return out, rewritten
