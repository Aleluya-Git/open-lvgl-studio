"""Fuentes: biblioteca (Montserrat, Roboto, Material Design Icons), GitHub/URL, ficheros y Google Fonts."""
import os

import pytest
import yaml

from olvgl.application.viewmodel import ProjectViewModel
from olvgl.domain import fonts as F
from olvgl.infrastructure import font_cache
from olvgl.infrastructure.esphome_generator import generate_yaml
from olvgl.infrastructure.esphome_importer import import_esphome_text
from olvgl.infrastructure.exporter import export_esphome

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GH = "https://github.com/Templarian/MaterialDesign-Webfont/raw/v7.4.47/fonts/materialdesignicons-webfont.ttf"
BULB = chr(0xF0335)


def vm():
    v = ProjectViewModel(generator=generate_yaml)
    v.new("Fuentes")
    return v


def test_library_ids():
    assert F.library_font("roboto_20") == {"file": "gfonts://Roboto", "size": 20}
    assert F.library_font("roboto_bold_24")["file"] == "gfonts://Roboto@700"
    assert F.library_font("montserrat_bold_32")["file"] == "gfonts://Montserrat@700"
    assert F.library_font("montserrat_20") is None            # montserrat_N es la de LVGL
    mdi = F.library_font("mdi_32")
    assert mdi["file"] == {"type": "web", "url": GH} and mdi["bpp"] == 4 and F.MDI_URL == GH
    assert F.library_font("roboto_huge_20") is None and F.library_font("mdi_bold_20") is None
    assert "roboto_20" in F.library_suggestions() and "mdi_48" in F.library_suggestions()


def test_bundled_library_files():
    for file in ("gfonts://Roboto@700", "gfonts://Montserrat", {"type": "web", "url": GH}, GH):
        p = font_cache.bundled_path(file)
        assert p and os.path.getsize(p) > 100_000, file
    assert font_cache.bundled_path("gfonts://Lato") is None
    assert len(F.mdi_icons()) > 7000 and F.icon_name(BULB) == "lightbulb"


def test_urls_and_ids():
    blob = "https://github.com/user/repo/blob/main/fonts/Inter-Bold.ttf"
    assert F.normalize_url(blob) == "https://github.com/user/repo/raw/main/fonts/Inter-Bold.ttf"
    assert F.normalize_url(GH) == GH
    raw = "https://raw.githubusercontent.com/user/repo/main/f/X.otf"
    assert F.normalize_url(raw) == raw
    for bad in ("github.com/x.ttf", "https://github.com/user/repo"):
        with pytest.raises(F.FontSourceError):
            F.normalize_url(bad)
    assert F.font_from_url(blob, 24)["file"]["url"].endswith("/raw/main/fonts/Inter-Bold.ttf")
    assert F.suggest_id(blob, 24) == "inter_bold_24"
    assert F.suggest_id("Roboto[wdth,wght].ttf", 20, {"roboto_20"}) == "roboto_2_20"
    assert F.font_from_gfonts("Open Sans", 600, 18)["file"] == "gfonts://Open Sans@600"
    with pytest.raises(F.FontSourceError):
        F.font_from_file("logo.png", 20)
    assert font_cache.looks_like_font(b"\x00\x01\x00\x00rest") and not font_cache.looks_like_font(b"<!DOCTYPE html>")


def test_choosing_a_library_font_adds_it():
    v = vm()
    lbl = v.add_widget("label")
    assert "roboto_bold_24" in v.font_ids() and "mdi_32" in v.font_ids()
    v.set_prop([lbl], "text_font", "roboto_bold_24")
    assert v.project.font("roboto_bold_24").data == {"file": "gfonts://Roboto@700", "size": 24}
    assert v.widget(lbl).props["text_font"] == "roboto_bold_24"
    assert "＋" not in v.font_label("roboto_bold_24") and "＋" in v.font_label("roboto_20")
    v.set_prop([lbl], "text_font", "montserrat_20")              # la de LVGL no se añade
    assert v.project.font("montserrat_20") is None
    assert v.font_uses("roboto_bold_24") == 0
    assert v.remove_font("roboto_bold_24") and v.project.font("roboto_bold_24") is None
    v.undo()
    assert v.project.font("roboto_bold_24") is not None


def test_add_update_remove_fonts():
    v = vm()
    assert v.add_font("inter_24", F.font_from_url("https://github.com/u/r/blob/main/Inter.ttf", 24)) == "inter_24"
    assert v.add_font("inter_24", {"file": "x.ttf", "size": 10}) is None          # repetido
    assert v.add_font("montserrat_20", {"file": "x.ttf", "size": 10}) is None     # de LVGL
    assert v.add_font("mal id", {"file": "x.ttf", "size": 10}) is None
    assert v.update_font("inter_24", dict(v.project.font("inter_24").data, size=30))
    assert v.project.font("inter_24").size == 30
    data = yaml.safe_load(generate_yaml(v.project))
    assert data["font"] == [{"file": {"type": "web", "url": "https://github.com/u/r/raw/main/Inter.ttf"},
                             "id": "inter_24", "size": 30}]


def test_icon_glyphs_added_automatically():
    v = vm()
    lbl = v.add_widget("label")
    v.set_prop([lbl], "text_font", "mdi_48")
    v.set_prop([lbl], "text", BULB)
    btn = v.add_widget("button")
    v.set_prop([btn], "text", chr(0xF0425))            # power, pero con fuente de texto: no cuenta
    data = yaml.safe_load(generate_yaml(v.project))
    f = next(x for x in data["font"] if x["id"] == "mdi_48")
    assert f["glyphs"] == [BULB] and f["file"]["url"] == GH and f["size"] == 48
    assert not any("mdi_48" in w for w in v.project.validate())
    # vuelve igual al importar y no se duplica
    p2, _r = import_esphome_text(generate_yaml(v.project), "x.yaml", v.project.display)
    assert yaml.safe_load(generate_yaml(p2))["font"] == data["font"]


def test_icon_font_without_icons_warns():
    v = vm()
    v.ensure_font("mdi_32")
    assert any("mdi_32" in w for w in v.project.validate())
    data = yaml.safe_load(generate_yaml(v.project))
    assert "glyphs" not in data["font"][0]


def test_user_glyph_strings_are_kept():
    text = """
font:
  - file: "fonts/materialdesignicons-webfont.ttf"
    id: m24
    size: 24
    glyphs: "\\U000F0335"
lvgl:
  pages:
    - id: p
      widgets:
        - label: {text: "\\U000F0335\\U000F0425", text_font: m24}
"""
    p, _r = import_esphome_text(text, "x.yaml")
    f = yaml.safe_load(generate_yaml(p))["font"][0]
    assert f["glyphs"] == BULB + chr(0xF0425)          # se respeta la cadena y se añade el que faltaba


def test_export_copies_local_font_files(tmp_path):
    v = vm()
    src = os.path.join(ROOT, "olvgl", "resources", "fonts", "Roboto-Variable.ttf")
    v.add_font("mi_roboto_20", F.font_from_file(src, 20))
    lbl = v.add_widget("label")
    v.set_prop([lbl], "text_font", "mi_roboto_20")
    rep = export_esphome(v.project, str(tmp_path))
    assert os.path.exists(tmp_path / "fonts" / "Roboto-Variable.ttf")
    assert "file: fonts/Roboto-Variable.ttf" in (tmp_path / "ui_lvgl.yaml").read_text(encoding="utf-8")
    assert not [w for w in rep.warnings if "Fuente" in w]


def test_choosing_a_font_keeps_the_selection():
    """Elegir una fuente de la biblioteca la añade al proyecto sin perder el widget seleccionado
    (antes el panel volvía a las propiedades del proyecto)."""
    v = vm()
    lbl = v.add_widget("label")
    v.set_selection([lbl])
    seen = []
    v.selection_changed.connect(lambda ids: seen.append(list(ids)))
    v.set_prop([lbl], "text_font", "roboto_24")
    assert v.selection == [lbl] and [] not in seen, seen
    assert v.project.font("roboto_24") is not None


def test_icon_categories_and_search():
    cats = dict(F.mdi_categories())
    assert cats["Home Automation"] > 500 and F.OTHER_CATEGORY in cats
    bulbs = F.search_icons("lightbulb", "Home Automation")
    assert bulbs and all("Home Automation" in i.categories for i in bulbs)
    assert any(i.name == "lightbulb" for i in F.search_icons("light"))       # también por alias
    assert all(F.category_label(c) for c in cats)
