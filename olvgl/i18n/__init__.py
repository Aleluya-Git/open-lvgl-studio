"""Traducción de la interfaz (español, inglés, francés y alemán).

Los textos se escriben en español en el código y se pasan por `tr()`. Las
tablas `<idioma>.json` traducen cada texto original. Si falta una entrada se
muestra el original, así que la aplicación nunca enseña una clave vacía."""
from __future__ import annotations

import json
import os

LANGUAGES = {"es": "Español", "en": "English", "fr": "Français", "de": "Deutsch"}
DEFAULT = "es"
_HERE = os.path.dirname(os.path.abspath(__file__))
_lang = DEFAULT
_table: dict[str, str] = {}
_extra: dict[str, dict[str, str]] = {}      # traducciones aportadas por plugins, por idioma


def add_translations(code: str, mapping: dict[str, str]) -> None:
    """Un plugin añade sus propias traducciones (texto original → traducción)."""
    _extra.setdefault(code, {}).update({str(k): str(v) for k, v in mapping.items()})
    if code == _lang:
        _table.update(_extra[code])


def table(code: str) -> dict[str, str]:
    path = os.path.join(_HERE, f"{code}.json")
    if code == DEFAULT or not os.path.exists(path):
        return {}
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def set_language(code: str | None) -> str:
    global _lang, _table
    code = code if code in LANGUAGES else DEFAULT
    _lang, _table = code, dict(table(code))
    if code != DEFAULT:
        _table.update(_extra.get(code, {}))
    return code


def language() -> str:
    return _lang


def tr(text: str) -> str:
    if not text or not _table:
        return text
    return _table.get(text, text)


def trf(text: str, **kw) -> str:
    """Traduce una plantilla con {campos} y la rellena."""
    return tr(text).format(**kw)
