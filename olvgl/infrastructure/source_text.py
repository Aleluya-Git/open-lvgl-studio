"""Leer el texto de un YAML tal como llega «del mundo real».

- Codificación: UTF-8 (con o sin BOM), UTF-16/UTF-32 (con BOM o sin él, como
  los guarda el Bloc de notas o PowerShell) y, si no es UTF-8, Windows-1252.
- Caracteres nulos sueltos: se quitan y se avisa.
- Páginas web guardadas por error con extensión .yaml (el botón «Guardar como»
  del navegador en GitHub en lugar de «Raw»): si es una página de GitHub se
  recupera el YAML que lleva dentro y se avisa; si no, se explica qué pasa en
  vez de mostrar un error incomprensible del analizador.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field


@dataclass
class SourceText:
    text: str
    notes: list[str] = field(default_factory=list)
    from_html: bool = False
    encoding: str = "utf-8"


class NotYamlError(ValueError):
    pass


def decode_bytes(raw: bytes) -> tuple[str, str]:
    """(texto, codificación) de un fichero de texto."""
    for bom, enc in ((b"\x00\x00\xfe\xff", "utf-32-be"), (b"\xff\xfe\x00\x00", "utf-32-le"),
                     (b"\xef\xbb\xbf", "utf-8-sig"), (b"\xff\xfe", "utf-16-le"), (b"\xfe\xff", "utf-16-be")):
        if raw.startswith(bom):
            return raw[len(bom):].decode(enc.replace("-sig", ""), errors="replace"), enc
    sample = raw[:4000]
    if len(sample) >= 4 and sample.count(0) > len(sample) // 4:
        # UTF-16 sin BOM: la mitad de los bytes son ceros, en las posiciones pares o impares
        odd = sum(1 for b in sample[1::2] if b == 0)
        even = sum(1 for b in sample[0::2] if b == 0)
        enc = "utf-16-le" if odd > even else "utf-16-be"
        return raw.decode(enc, errors="replace"), enc
    try:
        return raw.decode("utf-8"), "utf-8"
    except UnicodeDecodeError:
        return raw.decode("cp1252", errors="replace"), "cp1252"


def looks_like_html(text: str) -> bool:
    head = text.lstrip()[:2000].lower()
    return head.startswith("<!doctype html") or head.startswith("<html") or "<html" in head[:300]


_JS_ESC = {"n": "\n", "t": "\t", "r": "\r", "b": "\b", "f": "\f", "v": "\v", "0": "\0", "'": "'",
           '"': '"', "\\": "\\", "/": "/"}


def _js_array_after(text: str, start: int) -> list | None:
    """El array JS de cadenas ("…", escapes \\n, \\xHH, \\uHHHH…) que empieza en text[start]."""
    if start < 0 or start >= len(text) or text[start] != "[":
        return None
    out: list[str] = []
    i = start + 1
    n = len(text)
    while i < n:
        c = text[i]
        if c in " \n\r\t,":
            i += 1
            continue
        if c == "]":
            return out
        if c != '"':
            return None                      # algo que no es una cadena: no es el contenido del fichero
        i += 1
        buf = []
        while i < n and text[i] != '"':
            ch = text[i]
            if ch == "\\" and i + 1 < n:
                e = text[i + 1]
                if e == "x" and re.fullmatch(r"[0-9a-fA-F]{2}", text[i + 2:i + 4]):
                    buf.append(chr(int(text[i + 2:i + 4], 16)))
                    i += 4
                    continue
                if e == "u" and re.fullmatch(r"[0-9a-fA-F]{4}", text[i + 2:i + 6]):
                    code = int(text[i + 2:i + 6], 16)
                    i += 6
                    if 0xD800 <= code < 0xDC00 and text[i:i + 2] == "\\u" and \
                            re.fullmatch(r"[0-9a-fA-F]{4}", text[i + 2:i + 6]):
                        low = int(text[i + 2:i + 6], 16)
                        code = 0x10000 + ((code - 0xD800) << 10) + (low - 0xDC00)
                        i += 6
                    buf.append(chr(code))
                    continue
                buf.append(_JS_ESC.get(e, e))
                i += 2
                continue
            buf.append(ch)
            i += 1
        out.append("".join(buf))
        i += 1
    return None


def extract_github_yaml(html: str) -> str | None:
    """El contenido de un fichero en una página «blob» de GitHub (rawLines)."""
    for m in re.finditer(r'"?rawLines"?\s*:\s*(?:\$R\[\d+\]\s*=\s*)?', html):
        lines = _js_array_after(html, m.end())
        if lines:
            return "\n".join(lines) + "\n"
    return None


def _github_raw_url(html: str) -> str | None:
    m = re.search(r'https://github\.com/[^"\s<>]+/raw/[^"\s<>]+\.ya?ml', html)
    return m.group(0) if m else None


def from_bytes(raw: bytes, path: str = "") -> SourceText:
    text, enc = decode_bytes(raw)
    notes: list[str] = []
    if enc.startswith(("utf-16", "utf-32")):
        notes.append(f"El fichero estaba en {enc.upper()}; se ha leído bien, pero ESPHome necesita UTF-8: "
                     "guárdalo como UTF-8")
    elif enc == "cp1252":
        notes.append("El fichero no estaba en UTF-8 (se ha leído como Windows-1252); ESPHome necesita UTF-8")
    if looks_like_html(text):
        yaml_text = extract_github_yaml(text)
        if yaml_text is None:
            url = _github_raw_url(text)
            raise NotYamlError(
                "El fichero es una página web (HTML) guardada con extensión .yaml, no un YAML de ESPHome. "
                "Si lo bajaste de GitHub, abre el fichero allí y usa el botón «Raw» o «Download raw file»"
                + (f" ({url})" if url else "") + ".")
        url = _github_raw_url(text)
        notes.append("El fichero era una página web de GitHub guardada como .yaml: se ha recuperado el YAML que "
                     "contiene. Descárgalo con «Raw» o «Download raw file»" + (f" ({url})" if url else "")
                     + " para poder vincularlo y que los cambios se escriban en él.")
        return SourceText(yaml_text, notes, True, enc)
    if "\x00" in text:
        n = text.count("\x00")
        text = text.replace("\x00", "")
        notes.append(f"Se han quitado {n} caracteres nulos (\\0) que no pueden estar en un YAML")
    return SourceText(text, notes, False, enc)


def read_source(path: str) -> SourceText:
    with open(path, "rb") as f:
        return from_bytes(f.read(), path)
