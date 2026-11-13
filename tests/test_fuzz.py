"""Pruebas masivas reducidas (las completas: python tools/fuzz.py --sessions 500 --yaml 2000)."""
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import fuzz  # noqa: E402


@pytest.mark.parametrize("seed", range(1, 26))
def test_random_editing_sessions(seed):
    fail = fuzz.run_session(seed, 40)
    assert fail is None, (fail["error"], fail["steps"][-8:], fail["trace"])


def test_damaged_yaml_never_crashes(monkeypatch):
    monkeypatch.setattr(fuzz, "CORPUS", [os.path.join(ROOT, "examples", "importar", "panel_demo.yaml")])
    fails = fuzz.yaml_fuzz(250, seed=3)
    assert not fails, [(f["error"], f["trace"]) for f in fails[:2]]
    assert fuzz.YAML_STATS["importados"] > 50


def test_duplicate_triggers_are_merged(vm):
    from olvgl.domain.model import Action, EventHandler
    b = vm.add_widget("button")
    vm.set_events(b, [EventHandler("on_click", [Action("page_next", {})]),
                      EventHandler("on_click", [Action("logger", {"message": "x"})])])
    evs = vm.widget(b).events
    assert len(evs) == 1 and [a.kind for a in evs[0].actions] == ["page_next", "logger"]


def test_validation_catches_ranges_and_missing_targets(vm):
    from olvgl.domain.model import Action, EventHandler
    s = vm.add_widget("slider")
    vm.set_prop([s], "min_value", 50)
    vm.set_prop([s], "max_value", 10)
    vm.set_events(s, [EventHandler("on_value", [Action("widget_state", {"op": "hide", "id": "nada"})])])
    problems = vm.validate()
    assert any("mínimo" in p for p in problems) and any("'nada'" in p for p in problems)


def test_c_directions_are_sanitized():
    from olvgl.domain.model import Screen, Widget, new_project
    from olvgl.infrastructure.lvgl_c_generator import generate_c
    p = new_project("d")
    tv = Widget("tv", "tileview", 0, 0, 200, 200, children=[
        Widget("t1", "tile", None, None, None, None, props={"row": 0, "column": 0, "dir": "LEFT | right, *x*"})])
    dd = Widget("dd", "dropdown", 0, 0, 100, 40, props={"dir": "€"})
    p.screens = [Screen("main_page", "P", None, [tv, dd])]
    out = generate_c(p)
    assert "LV_DIR_LEFT | LV_DIR_RIGHT" in out.source and "LV_DIR_*X*" not in out.source
    assert "lv_dropdown_set_dir(ui_dd, LV_DIR_BOTTOM)" in out.source
    assert any("no válida" in w for w in out.warnings)


def test_duplicate_yaml_keys_are_reported_with_line():
    from olvgl.infrastructure.esphome_importer import import_esphome_text
    from olvgl.infrastructure.yaml_parser import YamlParseError
    with pytest.raises(YamlParseError) as e:
        import_esphome_text("lvgl:\n  pages:\n    - id: a\n      widgets: []\n      widgets: []\n", "p.yaml")
    assert e.value.line == 5 and "widgets" in str(e.value)


def test_button_text_label_never_duplicates_an_existing_child_id():
    from olvgl.infrastructure.esphome_generator import generate_yaml
    from olvgl.infrastructure.esphome_importer import import_esphome_text
    text = ("lvgl:\n  pages:\n    - id: p\n      widgets:\n        - button:\n            id: b\n"
            "            text: Hola\n            widgets:\n              - label:\n                  id: b_label\n"
            "                  align: CENTER\n")
    p, _r = import_esphome_text(text, "x.yaml")
    out = generate_yaml(p)
    assert out.count("id: b_label\n") == 1 and "id: b_label_2" in out
    again, _r = import_esphome_text(out, "x.yaml", p.display)
    assert generate_yaml(again) == out
