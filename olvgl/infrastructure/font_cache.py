"""Caché local de las fuentes que ESPHome descarga (Google Fonts y fuentes web).

Para que el canvas dibuje con las mismas fuentes que el dispositivo (Roboto,
Material Design Icons…), se descargan una vez a la carpeta de datos de la
aplicación. Si no hay red, el dibujo usa una fuente de sustitución.
"""
from __future__ import annotations

import hashlib
import os
import re
import urllib.request
from typing import Any

TIMEOUT = 20
_UA = "Mozilla/4.0"   # Google Fonts sirve TTF a agentes antiguos (no WOFF2)


def cache_dir() -> str:
    from olvgl.infrastructure.settings_db import app_data_dir
    path = os.path.join(app_data_dir(), "fonts")
    os.makedirs(path, exist_ok=True)
    return path


def gfonts_spec(file: Any) -> tuple[str, int, bool] | None:
    """(familia, peso, cursiva) de 'gfonts://Familia@700' o {type: gfonts, family, weight, italic}."""
    if isinstance(file, str) and file.startswith("gfonts://"):
        rest = file[len("gfonts://"):]
        family, _, weight = rest.partition("@")
        w = re.sub(r"\D", "", weight) or "400"
        return family.strip(), int(w), "italic" in weight.lower()
    if isinstance(file, dict) and str(file.get("type", "")).lower() == "gfonts":
        weight = file.get("weight", 400)
        named = {"thin": 100, "extra-light": 200, "light": 300, "regular": 400, "medium": 500,
                 "semi-bold": 600, "bold": 700, "extra-bold": 800, "black": 900}
        w = named.get(str(weight).lower(), weight)
        try:
            w = int(w)
        except (TypeError, ValueError):
            w = 400
        return str(file.get("family", "Roboto")), w, bool(file.get("italic", False))
    return None


def web_url(file: Any) -> str | None:
    if isinstance(file, dict) and str(file.get("type", "")).lower() == "web" and file.get("url"):
        return str(file["url"])
    if isinstance(file, str) and file.startswith(("http://", "https://")):
        return file
    return None


def font_weight(file: Any) -> int:
    g = gfonts_spec(file)
    return g[1] if g else 400


def _key(file: Any) -> str | None:
    g = gfonts_spec(file)
    if g:
        return f"gfonts:{g[0]}:{g[1]}:{int(g[2])}"
    url = web_url(file)
    return f"web:{url}" if url else None


def cached_path(file: Any) -> str | None:
    key = _key(file)
    if not key:
        return None
    path = os.path.join(cache_dir(), hashlib.sha1(key.encode("utf-8")).hexdigest()[:16] + ".ttf")
    return path if os.path.exists(path) and os.path.getsize(path) > 0 else None


def _download(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": _UA})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:  # noqa: S310 - URLs de fuentes de ESPHome
        return resp.read()


def fetch(file: Any) -> str | None:
    """Descarga la fuente si hace falta. Devuelve la ruta en caché o None."""
    existing = cached_path(file)
    if existing:
        return existing
    key = _key(file)
    if not key:
        return None
    target = os.path.join(cache_dir(), hashlib.sha1(key.encode("utf-8")).hexdigest()[:16] + ".ttf")
    try:
        g = gfonts_spec(file)
        if g:
            family, weight, italic = g
            css_url = ("https://fonts.googleapis.com/css2?family="
                       + family.replace(" ", "+") + f":{'ital,' if italic else ''}wght@"
                       + (f"1,{weight}" if italic else str(weight)))
            css = _download(css_url).decode("utf-8", "replace")
            m = re.search(r"url\((https://[^)]+\.ttf)\)", css)
            if not m:
                return None
            data = _download(m.group(1))
        else:
            data = _download(web_url(file) or "")
        if not data:
            return None
        tmp = target + ".part"
        with open(tmp, "wb") as f:
            f.write(data)
        os.replace(tmp, target)
        return target
    except Exception:
        return None


_BUNDLED = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "resources", "fonts")


def bundled_path(file: Any) -> str | None:
    """Las fuentes de la biblioteca van con la aplicación: Montserrat, Roboto y Material Design Icons."""
    g = gfonts_spec(file)
    name = None
    if g:
        fam, weight, _it = g
        if fam.lower() == "roboto":
            name = "Roboto-Variable.ttf"
        elif fam.lower() == "montserrat":
            name = "Montserrat-Bold.ttf" if weight >= 650 else "Montserrat-Medium.ttf" if weight >= 500 \
                else "Montserrat-Regular.ttf"
    else:
        url = web_url(file) or (file if isinstance(file, str) else "")
        if isinstance(url, str) and os.path.basename(url.split("?", 1)[0]).lower() == "materialdesignicons-webfont.ttf":
            name = "materialdesignicons-webfont.ttf"
    if name:
        path = os.path.join(_BUNDLED, name)
        return path if os.path.exists(path) else None
    return None


_MAGIC = (b"\x00\x01\x00\x00", b"OTTO", b"true", b"typ1", b"wOFF", b"wOF2", b"STARTFONT", b"\x01fcp")


def looks_like_font(data: bytes) -> bool:
    return any(data.startswith(m) for m in _MAGIC)


def check_download(url: str) -> tuple[str | None, str]:
    """Descarga una fuente de una URL (GitHub…) y comprueba que lo sea. (ruta en caché, error)."""
    file = {"type": "web", "url": url}
    existing = cached_path(file)
    if existing:
        return existing, ""
    try:
        data = _download(url)
    except Exception as exc:          # sin red, 404…
        return None, f"No se pudo descargar: {exc}"
    if not looks_like_font(data):
        head = data[:200].lstrip().lower()
        if head.startswith((b"<!doctype", b"<html")):
            return None, ("El enlace es una página web, no el fichero: en GitHub usa el enlace «Raw» o "
                          "«Download raw file»")
        return None, "Lo descargado no es una fuente TTF/OTF/WOFF"
    target = os.path.join(cache_dir(), hashlib.sha1(_key(file).encode("utf-8")).hexdigest()[:16] + ".ttf")
    tmp = target + ".part"
    with open(tmp, "wb") as f:
        f.write(data)
    os.replace(tmp, target)
    return target, ""


def missing_fonts(fonts: list) -> list:
    """Entradas `file` de las fuentes del proyecto que aún no están en caché (ni van con la aplicación)."""
    out, seen = [], set()
    for f in fonts:
        file = f.file if hasattr(f, "file") else f
        key = _key(file)
        if key and key not in seen and cached_path(file) is None and bundled_path(file) is None:
            seen.add(key)
            out.append(file)
    return out
