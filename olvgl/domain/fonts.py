"""Fuentes del proyecto: biblioteca integrada, fuentes de GitHub/URL, ficheros y Google Fonts.

ESPHome declara las fuentes en la sección `font:`:

    font:
      - file: "gfonts://Roboto@700"          # Google Fonts
        id: roboto_bold_24
        size: 24
      - file: {type: web, url: "https://github.com/…/materialdesignicons-webfont.ttf"}
        id: mdi_32
        size: 32
        glyphs: ["\\U000F0335", …]            # iconos que se usan
      - file: fonts/MiFuente.ttf              # fichero local (se copia al exportar)

Las fuentes de la **biblioteca** (Montserrat, Roboto y Material Design Icons)
van con la aplicación (se dibujan sin conexión) y aparecen siempre en las
listas de fuentes: al elegir una se añade sola al proyecto. Los iconos que usa
el proyecto se añaden solos a `glyphs:` de las fuentes de iconos.
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass
from typing import Any

MDI_VERSION = "7.4.47"
MDI_URL = ("https://github.com/Templarian/MaterialDesign-Webfont/raw/v"
           + MDI_VERSION + "/fonts/materialdesignicons-webfont.ttf")
FONT_EXTENSIONS = (".ttf", ".otf", ".woff", ".woff2", ".bdf", ".pcf")
SUGGESTED_SIZES = (12, 14, 16, 20, 24, 28, 32, 40, 48)
ICON_SIZES = (16, 20, 24, 32, 40, 48, 64, 80)
BPP_OPTIONS = (1, 2, 4, 8)
WEIGHT_NAMES = {100: "Thin", 200: "ExtraLight", 300: "Light", 400: "Regular", 500: "Medium", 600: "SemiBold",
                700: "Bold", 800: "ExtraBold", 900: "Black"}


@dataclass(frozen=True)
class LibraryFamily:
    key: str                         # prefijo del id: roboto, montserrat, mdi
    label: str
    weights: tuple[int, ...]
    icons: bool = False
    gfonts: str = ""                 # familia de Google Fonts
    license: str = ""

    def file(self, weight: int = 400) -> Any:
        if self.icons:
            return {"type": "web", "url": MDI_URL}
        return f"gfonts://{self.gfonts}@{weight}" if weight != 400 else f"gfonts://{self.gfonts}"


LIBRARY = (
    LibraryFamily("roboto", "Roboto", (300, 400, 500, 700), gfonts="Roboto", license="SIL OFL 1.1"),
    LibraryFamily("montserrat", "Montserrat", (400, 500, 700), gfonts="Montserrat", license="SIL OFL 1.1"),
    LibraryFamily("mdi", "Material Design Icons " + MDI_VERSION, (400,), icons=True, license="Apache 2.0"),
)
LIBRARY_BY_KEY = {f.key: f for f in LIBRARY}
_WEIGHT_SUFFIX = {300: "light", 400: "", 500: "medium", 700: "bold"}
_SUFFIX_WEIGHT = {v: k for k, v in _WEIGHT_SUFFIX.items() if v}
_BUILTIN_RE = re.compile(r"^montserrat_(\d+)$")      # las fuentes de LVGL (Montserrat Medium)


def library_id(key: str, size: int, weight: int = 400) -> str:
    suffix = _WEIGHT_SUFFIX.get(weight, "")
    if key == "montserrat" and weight == 400:
        suffix = "regular"                            # montserrat_N es la de LVGL (Medium)
    return f"{key}_{suffix + '_' if suffix else ''}{int(size)}"


def parse_library_id(font_id: str) -> tuple[LibraryFamily, int, int] | None:
    """roboto_bold_24 → (Roboto, 700, 24); montserrat_regular_20 → (Montserrat, 400, 20)."""
    m = re.match(r"^(roboto|montserrat|mdi)(?:_(light|regular|medium|bold))?_(\d{1,3})$", str(font_id))
    if not m:
        return None
    fam = LIBRARY_BY_KEY[m.group(1)]
    suffix = m.group(2) or ""
    if fam.key == "montserrat" and not suffix:
        return None                                   # montserrat_N: fuente integrada de LVGL
    if fam.icons and suffix:
        return None
    weight = 400 if suffix in ("", "regular") else _SUFFIX_WEIGHT.get(suffix, 400)
    if weight not in fam.weights:
        return None
    size = int(m.group(3))
    if not 6 <= size <= 200:
        return None
    return fam, weight, size


def library_font(font_id: str) -> dict | None:
    """Los datos de `font:` de una fuente de la biblioteca a partir de su id, o None."""
    p = parse_library_id(font_id)
    if p is None:
        return None
    fam, weight, size = p
    data: dict[str, Any] = {"file": fam.file(weight), "size": size}
    if fam.icons:
        data["bpp"] = 4
        data["glyphs"] = []
    return data


def library_suggestions() -> list[str]:
    """Ids de la biblioteca que se ofrecen en las listas de fuentes."""
    out = [library_id("roboto", s) for s in SUGGESTED_SIZES]
    out += [library_id("roboto", s, 700) for s in SUGGESTED_SIZES]
    out += [library_id("mdi", s) for s in ICON_SIZES]
    return out


def is_builtin(font_id: str) -> bool:
    return bool(_BUILTIN_RE.match(str(font_id)))


# --------------------------------------------------------------------------- URL, ficheros y Google Fonts
_GH_BLOB = re.compile(r"^https?://github\.com/([^/]+)/([^/]+)/blob/(.+)$")
_GH_RAW = re.compile(r"^https?://raw\.githubusercontent\.com/([^/]+)/([^/]+)/(.+)$")


class FontSourceError(ValueError):
    pass


def normalize_url(url: str) -> str:
    """Enlace de GitHub («…/blob/…» o «…/raw/…») o URL directa → URL que descarga el fichero."""
    u = str(url or "").strip().strip('"').strip("'")
    if not re.match(r"^https?://", u):
        raise FontSourceError("La dirección debe empezar por https://")
    m = _GH_BLOB.match(u)
    if m:
        u = f"https://github.com/{m.group(1)}/{m.group(2)}/raw/{m.group(3)}"
    u = u.split("#", 1)[0]
    if not u.lower().split("?", 1)[0].endswith(FONT_EXTENSIONS):
        raise FontSourceError("El enlace no apunta a un fichero de fuente (.ttf, .otf, .woff, .woff2, .bdf o .pcf)")
    return u


def suggest_id(name: str, size: int, taken: set[str] | frozenset[str] = frozenset()) -> str:
    """Id de ESPHome a partir del nombre del fichero o la familia: «Inter-Bold.ttf», 24 → inter_bold_24."""
    from olvgl.domain.model import sanitize_id
    base = os.path.splitext(os.path.basename(str(name).split("?", 1)[0]))[0]
    base = re.sub(r"[-\s]+webfont$", "", base, flags=re.I)
    base = re.sub(r"\[.*?\]", "", base)
    base = sanitize_id(re.sub(r"[^A-Za-z0-9]+", "_", base).strip("_").lower() or "fuente", "fuente")
    cand, n = f"{base}_{int(size)}", 2
    while cand in taken:                      # roboto_20 ocupado → roboto_2_20 (el tamaño sigue al final)
        cand, n = f"{base}_{n}_{int(size)}", n + 1
    return cand


def font_from_url(url: str, size: int, bpp: int | None = None) -> dict:
    data: dict[str, Any] = {"file": {"type": "web", "url": normalize_url(url)}, "size": int(size)}
    if bpp:
        data["bpp"] = int(bpp)
    return data


def font_from_file(path: str, size: int, bpp: int | None = None) -> dict:
    if not str(path).lower().endswith(FONT_EXTENSIONS):
        raise FontSourceError("El fichero no es una fuente (.ttf, .otf, .woff, .woff2, .bdf o .pcf)")
    data: dict[str, Any] = {"file": str(path), "size": int(size)}
    if bpp:
        data["bpp"] = int(bpp)
    return data


def font_from_gfonts(family: str, weight: int, size: int, italic: bool = False, bpp: int | None = None) -> dict:
    fam = re.sub(r"\s+", " ", str(family or "").strip())
    if not fam or not re.fullmatch(r"[A-Za-z0-9 ]+", fam):
        raise FontSourceError("Escribe el nombre de la familia tal como aparece en fonts.google.com (p. ej. «Open Sans»)")
    w = f"{int(weight)}{'italic' if italic else ''}"
    data: dict[str, Any] = {"file": f"gfonts://{fam}" + ("" if w == "400" else f"@{w}"), "size": int(size)}
    if bpp:
        data["bpp"] = int(bpp)
    return data


def file_url(file: Any) -> str:
    if isinstance(file, dict):
        return str(file.get("url") or file.get("path") or file.get("family") or "")
    return str(file or "")


def is_icon_font(data: dict) -> bool:
    """Material Design Icons (o cualquier fuente con iconos en la zona de uso privado)."""
    f = file_url(data.get("file")).lower()
    if "materialdesignicons" in f or f.startswith("mdi:"):
        return True
    g = glyph_list(data.get("glyphs"))
    return bool(g) and all(is_private_use(c) for c in g)


def describe(font_id: str, data: dict) -> str:
    """«Roboto Bold · 24 px · Google Fonts» para las listas."""
    file = data.get("file")
    size = data.get("size", 20)
    lib = parse_library_id(font_id)
    if lib:
        fam, w, _s = lib
        name = fam.label + ("" if fam.icons or w == 400 else " " + WEIGHT_NAMES.get(w, str(w)))
    elif isinstance(file, str) and file.startswith("gfonts://"):
        fam_, _, w = file[len("gfonts://"):].partition("@")
        name = f"{fam_} {w}".strip() + " · Google Fonts"
    else:
        url = file_url(file)
        name = os.path.basename(url.split("?", 1)[0]) or url
        if "github.com" in url or "githubusercontent" in url:
            name += " · GitHub"
        elif url.startswith("http"):
            name += " · web"
    extra = ""
    if is_icon_font(data):
        n = len(glyph_list(data.get("glyphs")))
        extra = f" · {n} iconos" if n else ""
    return f"{name} · {size} px{extra}"


# --------------------------------------------------------------------------- glifos usados
def is_private_use(ch: str) -> bool:
    o = ord(ch)
    return 0xE000 <= o <= 0xF8FF or 0xF0000 <= o <= 0x10FFFD


def glyph_list(value: Any) -> list[str]:
    """glyphs de ESPHome (cadena o lista de cadenas) → lista de caracteres sin repetir."""
    chars: list[str] = []
    items = value if isinstance(value, list) else [value] if isinstance(value, str) else []
    for item in items:
        if isinstance(item, str):
            for ch in item:
                if ch not in chars and not ch.isspace():
                    chars.append(ch)
    return chars


TEXT_KEYS = ("text", "placeholder_text")


def _texts(props: dict) -> list[str]:
    from olvgl.domain.values import is_tagged
    out = []
    for k in TEXT_KEYS:
        v = props.get(k)
        if isinstance(v, str):
            out.append(v)
        elif isinstance(v, dict) and not is_tagged(v) and isinstance(v.get("format"), str):
            out.append(v["format"])
    for k in ("options",):
        v = props.get(k)
        if isinstance(v, list):
            out += [x for x in v if isinstance(x, str)]
        elif isinstance(v, str):
            out.append(v)
    rows = props.get("rows")
    if isinstance(rows, list):
        for r in rows:
            for b in (r.get("buttons", []) if isinstance(r, dict) else []):
                if isinstance(b, dict) and isinstance(b.get("text"), str):
                    out.append(b["text"])
    return out


def used_chars(project) -> dict[str, set[str]]:
    """{id de fuente: caracteres que se escriben con ella} en todas las páginas."""
    from olvgl.domain.layout import effective_props, page_props
    out: dict[str, set[str]] = {}

    def visit(widgets, parent_eff):
        for w in widgets:
            eff = effective_props(project, w, parent_eff)
            font = eff.get("text_font")
            if isinstance(font, str):
                for t in _texts(w.props):
                    out.setdefault(font, set()).update(ch for ch in t if not ch.isspace())
                # partes y estados con su propia fuente (pressed: text_font…) usan el mismo texto
                for sub in w.props.values():
                    if isinstance(sub, dict) and isinstance(sub.get("text_font"), str):
                        for t in _texts(w.props):
                            out.setdefault(sub["text_font"], set()).update(ch for ch in t if not ch.isspace())
            visit(w.children, eff)

    for s in project.all_screens():
        visit(s.widgets, page_props(project, s))
    return out


def glyphs_for_export(project, font, used: dict[str, set[str]] | None = None) -> Any:
    """El valor de `glyphs:` que se escribe para la fuente, o None si no se toca.

    Sólo en las fuentes de iconos: se añaden los iconos que usa el proyecto y aún
    no estaban, respetando cómo los escribió el usuario (cadena o lista). Las demás
    fuentes se dejan tal cual."""
    data = font.data
    if not is_icon_font(data):
        return None
    value = data.get("glyphs")
    current = glyph_list(value)
    used = (used if used is not None else used_chars(project)).get(font.id, set())
    extra = sorted((c for c in used if is_private_use(c) and c not in current), key=ord)
    if not extra:
        return value if current else None
    if isinstance(value, str):
        return value + "".join(extra)
    return (list(value) if isinstance(value, list) else []) + extra


# --------------------------------------------------------------------------- iconos MDI
_ICONS: list[tuple[str, str]] = []
_ICON_LIST = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "resources", "fonts",
                          "mdi_icons.txt")


def mdi_icons() -> list[tuple[str, str]]:
    """[(nombre, carácter)] de los 7447 iconos de Material Design Icons que van con la aplicación."""
    if not _ICONS:
        try:
            with open(_ICON_LIST, encoding="utf-8") as f:
                for line in f:
                    if line.startswith("#") or not line.strip():
                        continue
                    name, code = line.split()
                    _ICONS.append((name, chr(int(code, 16))))
        except OSError:
            pass
    return _ICONS


def icon_name(ch: str) -> str | None:
    return next((n for n, c in mdi_icons() if c == ch), None)


def escape_glyph(ch: str) -> str:
    """'\\U000F0335' — como se escriben los iconos en el YAML de ESPHome."""
    return f"\\U{ord(ch):08X}" if ord(ch) > 0xFFFF else f"\\u{ord(ch):04X}"
