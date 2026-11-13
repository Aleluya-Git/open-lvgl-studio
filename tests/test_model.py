import pytest

from olvgl.domain import catalog
from olvgl.domain.model import (EventHandler, Action, Project, Screen, Widget, is_valid_id,
                                new_project, normalize_color, sanitize_id, unique_id, migrate)


def test_ids():
    assert is_valid_id("btn_1")
    assert not is_valid_id("1btn")
    assert not is_valid_id("int")
    assert not is_valid_id("con espacio")
    assert sanitize_id("Salón Principal") == "salon_principal"
    assert sanitize_id("3 luces") == "obj_3_luces"
    assert unique_id("btn", {"btn"}) == "btn_1"
    assert unique_id("btn_1", {"btn_1", "btn_2"}) == "btn_3"


def test_colors():
    assert normalize_color("#abc") == "#AABBCC"
    assert normalize_color("0x1e88e5") == "#1E88E5"
    assert normalize_color(0xFF0000) == "#FF0000"
    with pytest.raises(ValueError):
        normalize_color("rojo")


def test_roundtrip_dict():
    p = new_project("Panel salón")
    w = Widget("btn_1", "button", 10, 20, 100, 50, props={"text": "Luz"},
               events=[EventHandler("on_click", [Action("logger", {"message": "hola"})])])
    p.screens[0].widgets.append(w)
    p2 = Project.from_dict(p.to_dict())
    assert p2.to_dict() == p.to_dict()
    assert p2.widget("btn_1").events[0].actions[0].params["message"] == "hola"


def test_find_and_all_ids():
    p = new_project()
    p.screens.append(Screen("ajustes"))
    p.screens[1].widgets.append(Widget("btn_volver", "button", props={"text": "Volver"}))
    s, lst, w = p.find_widget("btn_volver")
    assert s.id == "ajustes" and w.id == "btn_volver" and lst is s.widgets
    ids = p.all_ids()
    assert {"main_page", "ajustes", "btn_volver", "btn_volver_label"} <= ids


def test_validate_detects_problems():
    p = new_project()
    p.screens[0].widgets += [Widget("dup", "label"), Widget("dup", "label")]
    p.screens[0].widgets.append(Widget("image_1", "image", props={"src": "no_existe"}))
    p.screens[0].widgets.append(Widget("b", "button", events=[
        EventHandler("on_click", [Action("page_show", {"page": "nada"})])]))
    problems = "\n".join(p.validate())
    assert "duplicado" in problems
    assert "no_existe" in problems
    assert "nada" in problems


def test_newer_schema_rejected():
    with pytest.raises(ValueError):
        migrate({"schema_version": 999})


def test_catalog_defaults():
    esphome_widgets = {"label", "button", "image", "obj", "arc", "bar", "slider", "switch", "checkbox",
                       "dropdown", "roller", "textarea", "spinbox", "keyboard", "buttonmatrix", "led",
                       "spinner", "line", "qrcode", "meter", "tabview", "tab", "tileview", "tile",
                       "canvas", "animimg"}
    assert set(catalog.CATALOG) == esphome_widgets
    assert all(s.known for s in catalog.CATALOG.values())
    assert {s.category for s in catalog.palette_specs()} == set(catalog.CATEGORIES)
    w = Widget("l", "label")
    assert catalog.prop_value(w, "text_font") == "montserrat_14"
    assert "montserrat_48" in catalog.FONTS and "montserrat_8" in catalog.FONTS
    assert not catalog.IMAGE.resizable
    assert "on_click" in catalog.BUTTON.events


def test_nested_prop_paths():
    props = {"text": "a"}
    p2 = catalog.set_path(props, "indicator.pressed.bg_color", "#FF0000")
    assert p2 == {"text": "a", "indicator": {"pressed": {"bg_color": "#FF0000"}}} and props == {"text": "a"}
    assert catalog.get_path(p2, "indicator.pressed.bg_color") == "#FF0000"
    p3 = catalog.set_path(p2, "indicator.pressed.bg_color", None)
    assert p3 == {"text": "a"}          # se limpian los mapas vacíos
    w = Widget("s", "switch")
    assert catalog.prop_value(w, "state.checked") is False
    w.props = {"state": {"checked": True}}
    assert catalog.prop_value(w, "state.checked") is True
