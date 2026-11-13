"""Traducciones: todos los textos de la interfaz en inglés, francés y alemán."""
import os
import re
import sys

from olvgl import i18n

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))


def test_every_text_translated_with_same_fields():
    from i18n_keys import keys
    ks = keys()
    assert len(ks) > 400
    for code in ("en", "fr", "de"):
        table = i18n.table(code)
        missing = [k for k in ks if k not in table]
        assert not missing, (code, missing[:10])
        for k in ks:
            v = table[k]
            assert v.strip(), (code, k)
            assert set(re.findall(r"\{(\w+)\}", k)) == set(re.findall(r"\{(\w+)\}", v)), (code, k, v)
            assert k.count("\n") == v.count("\n"), (code, k)
            if "&" in k:
                assert v.count("&") == 1, (code, k, v)


def test_switch_language_and_fallback():
    try:
        assert i18n.set_language("de") == "de"
        assert i18n.tr("&Archivo") == "&Datei"
        assert i18n.trf("Pantalla {n}", n=3) == "Bildschirm 3"
        assert i18n.tr("texto que no existe") == "texto que no existe"
        from olvgl.domain import catalog
        assert catalog.describe_action("delay", {"duration": "2s"}) == "2s warten"
        assert i18n.set_language("xx") == "es"
        assert i18n.tr("&Archivo") == "&Archivo"
    finally:
        i18n.set_language("es")
