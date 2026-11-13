import os

import yaml

from olvgl.domain.model import Action, EventHandler, ImageResource, Screen, Widget, new_project
from olvgl.domain.yaml_ast import HEX, LITERAL, VERBATIM, YMap, YRaw, YScalar, YSeq
from olvgl.infrastructure.esphome_generator import generate_main_yaml, generate_yaml
from olvgl.infrastructure.exporter import export_esphome
from olvgl.infrastructure.yaml_emitter import emit


class _AnyTagLoader(yaml.SafeLoader):
    pass


_AnyTagLoader.add_multi_constructor("!", lambda loader, suffix, node: f"!{suffix} {node.value}")


def sample_project():
    p = new_project("Panel salón")
    s = p.screens[0]
    s.id = "inicio"
    s.bg_color = "#1A1A2E"
    s.widgets.append(Widget("lbl_titulo", "label", 24, 20, 300, 40, props={
        "text": "Salón", "text_color": "#FFFFFF", "text_font": "montserrat_28"}))
    s.widgets.append(Widget("btn_luz", "button", 24, 100, 160, 60, props={"text": "Luz"}, events=[
        EventHandler("on_click", [Action("ha_action", {"action": "light.toggle",
                                                       "entity_id": "light.salon"})])]))
    s.widgets.append(Widget("btn_ajustes", "button", 200, 100, 160, 60,
                            props={"text": "Ajustes", "bg_color": "#444444", "radius": 30,
                                   "checkable": True},
                            events=[EventHandler("on_click", [Action("page_show", {"page": "ajustes"})])]))
    s.widgets.append(Widget("image_1", "image", 400, 20, None, None, props={"src": "img_logo"}))
    s.widgets.append(Widget("image_2", "image", 500, 20, 64, 64))  # sin src → no se emite
    p.images.append(ImageResource("img_logo", "C:/fotos/logo.png"))
    p.images.append(ImageResource("img_sin_usar", "x.png"))
    aj = Screen("ajustes", "Ajustes")
    aj.widgets.append(Widget("btn_volver", "button", 10, 10, 120, 50, props={"text": "Volver"}, events=[
        EventHandler("on_click", [Action("page_prev"), Action("logger", {"message": "volver: ok"}),
                                  Action("raw", {"yaml": "delay: 1s"})])]))
    p.screens.append(aj)
    return p


def test_emitter_style():
    root = YMap().set("lvgl", YMap().set("pages", YSeq([
        YMap().set("id", "p").set("bg_color", YScalar(0x1A1A2E, HEX)).set("widgets", YSeq([
            YMap().set("label", YMap().set("text", "Hola: mundo").set("hidden", True))]))])))
    text = emit(root)
    assert text == (
        "lvgl:\n"
        "  pages:\n"
        "    - id: p\n"
        "      bg_color: 0x1A1A2E\n"
        "      widgets:\n"
        "        - label:\n"
        "            text: \"Hola: mundo\"\n"
        "            hidden: true\n"
    )


def test_emitter_scalars_and_raw():
    root = YMap()
    root.set("a", YScalar("true")).set("b", YScalar("123")).set("c", YScalar(""))
    root.set("d", YScalar("!secret x", VERBATIM)).set("e", YScalar(None))
    root.set("f", YScalar("línea1\nlínea2", LITERAL))
    root.set("g", YSeq([YRaw("light.toggle:\n  id: luz"), YScalar(5)]))
    root.set("h", YMap()).set("i", YSeq())
    text = emit(root)
    data = yaml.load(text, Loader=_AnyTagLoader)
    assert data["a"] == "true" and data["b"] == "123" and data["c"] == ""
    assert data["d"] == "!secret x" and data["e"] is None
    assert data["f"] == "línea1\nlínea2"
    assert data["g"] == [{"light.toggle": {"id": "luz"}}, 5]
    assert data["h"] == {} and data["i"] == []


def test_generate_esphome_yaml():
    text = generate_yaml(sample_project())
    assert "0x1A1A2E" in text
    data = yaml.safe_load(text)
    assert data["image"] == [{"file": "images/logo.png", "id": "img_logo", "type": "RGB565",
                              "transparency": "alpha_channel"}]
    pages = data["lvgl"]["pages"]
    assert [p["id"] for p in pages] == ["inicio", "ajustes"]
    assert pages[0]["bg_color"] == 0x1A1A2E
    assert "bg_color" not in pages[1]  # sin color propio
    widgets = pages[0]["widgets"]
    assert len(widgets) == 4  # image_2 sin src se omite
    lbl = widgets[0]["label"]
    assert lbl == {"id": "lbl_titulo", "x": 24, "y": 20, "width": 300, "height": 40,
                   "text": "Salón", "text_color": 0xFFFFFF, "text_font": "montserrat_28"}
    luz = widgets[1]["button"]
    assert "bg_color" not in luz and "radius" not in luz
    assert luz["widgets"][0]["label"] == {"id": "btn_luz_label", "align": "CENTER", "text": "Luz"}
    assert luz["on_click"] == [{"homeassistant.action": {"action": "light.toggle",
                                                         "data": {"entity_id": "light.salon"}}}]
    aj = widgets[2]["button"]
    assert aj["bg_color"] == 0x444444 and aj["radius"] == 30 and aj["checkable"] is True
    assert aj["on_click"] == [{"lvgl.page.show": "ajustes"}]
    assert widgets[3]["image"] == {"id": "image_1", "x": 400, "y": 20, "src": "img_logo"}
    volver = pages[1]["widgets"][0]["button"]
    assert volver["on_click"] == [{"lvgl.page.previous": None}, {"logger.log": "volver: ok"},
                                  {"delay": "1s"}]


def test_generate_main_yaml():
    text = generate_main_yaml(sample_project())
    data = yaml.load(text, Loader=_AnyTagLoader)
    assert data["packages"] == {"ui": "!include ui_lvgl.yaml"}
    assert data["esphome"]["name"] == "panel-salon"
    assert "logger" in data and data["logger"] is None
    assert "Permitir que el dispositivo" in text


def test_export(tmp_path):
    p = sample_project()
    img = tmp_path / "src" / "logo.png"
    img.parent.mkdir()
    img.write_bytes(b"\x89PNG fake")
    p.images[0].path = str(img)
    out = tmp_path / "esphome"
    rep = export_esphome(p, str(out))
    assert (out / "ui_lvgl.yaml").exists()
    assert (out / "main.yaml").exists()
    assert (out / "images" / "logo.png").read_bytes() == b"\x89PNG fake"
    # main.yaml del usuario nunca se sobrescribe
    (out / "main.yaml").write_text("mio", encoding="utf-8")
    rep = export_esphome(p, str(out))
    assert (out / "main.yaml").read_text(encoding="utf-8") == "mio"
    assert str(out / "main.yaml") in rep.skipped


def test_export_missing_image_warns(tmp_path):
    p = sample_project()
    rep = export_esphome(p, str(tmp_path))
    assert any("img_logo" in w for w in rep.warnings)
    assert os.path.exists(tmp_path / "ui_lvgl.yaml")
