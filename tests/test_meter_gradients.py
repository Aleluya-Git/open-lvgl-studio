"""Indicador de aguja (meter), degradados y sistema de licencias desactivado."""
import yaml

from olvgl.application import licensing as lc
from olvgl.domain import catalog
from olvgl.domain import meter as mt
from olvgl.domain.model import Widget, new_project
from olvgl.infrastructure.esphome_generator import generate_yaml
from olvgl.infrastructure.esphome_importer import import_esphome_text
from olvgl.infrastructure.lvgl_c_generator import generate_c

SCALES = [{
    "range_from": 0, "range_to": 200, "angle_range": 240,
    "ticks": {"count": 11, "width": 2, "length": 10, "color": "#808080",
              "major": {"stride": 5, "length": "15%", "color": "#FF0000", "label_gap": 8}},
    "indicators": [
        {"arc": {"start_value": 150, "end_value": 200, "color": "#F44336", "width": 6}},
        {"tick_style": {"start_value": 0, "end_value": 100, "color_start": "#00FF00", "color_end": "#0000FF",
                        "width": 3, "local": True}},
        {"line": {"id": "aguja", "value": 120, "width": 4, "color": "#2196F3", "r_mod": -10}},
    ]}]


def meter_project():
    p = new_project("Meter")
    p.screens[0].widgets.append(Widget("mt", "meter", 10, 10, 200, 200, props={"scales": SCALES}))
    return p


def test_geometry():
    g = mt.scale_geo(SCALES[0])
    assert g.rotation == 90 + (360 - 240) / 2 == 150          # rotación automática de ESPHome
    assert g.angle(0) == 150 and g.angle(200) == 390 and g.angle(100) == 270
    assert g.angle(999) == 390                                  # fuera de rango: se queda en el extremo
    vals = mt.tick_values(SCALES[0])
    assert len(vals) == 11 and vals[0] == (0, True) and vals[5] == (100, True) and vals[1] == (20, False)
    assert mt.length("15%", 100) == 15 and mt.length(12, 100) == 12
    ticks, major = mt.ticks_of({"ticks": {"count": 4}})
    assert ticks["width"] == 2 and major is None
    assert mt.first_value({"scales": SCALES}) == 120
    new = mt.set_first_value({"scales": SCALES}, 42)
    assert new[0]["indicators"][2]["line"]["value"] == 42 and SCALES[0]["indicators"][2]["line"]["value"] == 120


def test_new_meter_has_a_scale():
    sp = catalog.spec("meter")
    scales = dict(sp.initial_props)["scales"]
    assert scales and scales[0]["indicators"] and "ticks" in scales[0]
    assert {"main", "ticks", "indicator"} <= set(sp.parts)


def test_meter_yaml_round_trip():
    text = generate_yaml(meter_project())
    data = yaml.safe_load(text)
    m = data["lvgl"]["pages"][0]["widgets"][0]["meter"]
    sc = m["scales"][0]
    assert sc["ticks"]["major"]["color"] == 0xFF0000 and sc["ticks"]["major"]["length"] == "15%"
    ts = sc["indicators"][1]["tick_style"]
    assert ts["color_start"] == 0x00FF00 and ts["color_end"] == 0x0000FF and ts["local"] is True
    assert sc["indicators"][2]["line"]["id"] == "aguja"
    back, _rep = import_esphome_text(text)
    w = back.widget("mt")
    assert w.props["scales"] == SCALES


def test_meter_c_uses_lv_scale():
    src = generate_c(meter_project()).source
    assert "ui_mt = lv_scale_create(" in src
    assert "lv_scale_set_range(ui_mt, 0, 200);" in src
    assert "lv_scale_set_rotation(ui_mt, 150);" in src
    assert "lv_scale_set_total_tick_count(ui_mt, 11);" in src
    assert "lv_scale_set_major_tick_every(ui_mt, 5);" in src
    assert "ui_aguja = lv_line_create(ui_mt);" in src
    assert "lv_scale_set_line_needle_value(ui_mt, ui_aguja, lv_obj_get_width(ui_mt) / 2 + (-10), 120);" in src
    assert "lv_scale_section_set_range(" in src and "lv_style_set_arc_color(" in src
    assert "lv_obj_t * ui_aguja;" in src


def test_gradient_props_in_catalog_and_c():
    for t in ("button", "obj", "bar", "slider", "arc"):
        names = {p.name for p in catalog.spec(t).props}
        assert {"bg_grad_dir", "bg_grad_color", "bg_main_stop", "bg_grad_stop"} <= names, t
    for t in ("bar", "slider"):
        names = {p.name for p in catalog.spec(t).props}
        assert {"indicator.bg_grad_color", "indicator.bg_grad_dir"} <= names, t
    assert "knob.bg_grad_color" in {p.name for p in catalog.spec("arc").props}
    p = new_project("Degradados")
    p.screens[0].widgets += [
        Widget("b", "button", 0, 0, 100, 40, props={"bg_color": "#FF0000", "bg_grad_color": "#0000FF",
                                                     "bg_grad_dir": "VER", "bg_main_stop": 40, "bg_grad_stop": 200}),
        Widget("s", "slider", 0, 60, 200, 10, props={"indicator": {"bg_color": "#00FF00", "bg_grad_color": "#FFFF00",
                                                                   "bg_grad_dir": "HOR"}}),
    ]
    src = generate_c(p).source
    assert "lv_obj_set_style_bg_grad_dir(ui_b, LV_GRAD_DIR_VER, LV_PART_MAIN | LV_STATE_DEFAULT);" in src
    assert "lv_obj_set_style_bg_main_stop(ui_b, 40, LV_PART_MAIN | LV_STATE_DEFAULT);" in src
    assert "lv_obj_set_style_bg_grad_color(ui_s, lv_color_hex(0xFFFF00), LV_PART_INDICATOR | LV_STATE_DEFAULT);" in src
    data = yaml.safe_load(generate_yaml(p))
    b = data["lvgl"]["pages"][0]["widgets"][0]["button"]
    assert b["bg_grad_color"] == 0x0000FF and b["bg_grad_dir"] == "VER" and b["bg_grad_stop"] == 200


def test_licensing_disabled_by_default():
    assert lc.ENFORCE_DEFAULT == "0"
    # el código sigue ahí: con ENFORCE se exige la edición
    assert lc.FEATURES["ia"] == "enterprise"


def test_copy_paste_auto_id_widgets_get_new_ids():
    """Un widget sin id (id automático «_obj_3») se copiaba con el mismo id: el original
    desaparecía del lienzo y la copia no se podía mover."""
    from olvgl.application.viewmodel import ProjectViewModel
    from olvgl.infrastructure.esphome_generator import generate_yaml
    vm = ProjectViewModel(generator=generate_yaml)
    p = new_project("Copiar")
    p.screens[0].widgets += [
        Widget("_obj_3", "obj", 100, 100, 80, 80, auto_id=True,
               children=[Widget("_label_1", "label", 5, 5, None, None, props={"text": "a"}, auto_id=True)]),
        Widget("obj_3", "obj", 300, 100, 80, 80),
    ]
    vm.replace_project(p)
    for op in ("paste", "duplicate"):
        vm.set_selection(["_obj_3"])
        if op == "paste":
            vm.copy()
            new = vm.paste()
        else:
            new = vm.duplicate()
        ids = [w.id for _s, w in vm.project.iter_widgets()]
        assert len(ids) == len(set(ids)), (op, ids)
        assert new[0] not in ("_obj_3", "obj_3") and new[0].startswith("_")
        assert vm.widget("_obj_3").x == 100 and vm.widget(new[0]).x == 110
        assert vm.box(new[0]).movable


def test_duplicate_auto_ids_repaired_on_open():
    from olvgl.application.viewmodel import ProjectViewModel
    from olvgl.infrastructure.esphome_generator import generate_yaml
    p = new_project("Dañado")
    p.screens[0].widgets += [Widget("_obj_3", "obj", 0, 0, 50, 50, auto_id=True),
                             Widget("_obj_3", "obj", 10, 10, 50, 50, auto_id=True)]
    vm = ProjectViewModel(generator=generate_yaml)
    vm.replace_project(p)
    ids = [w.id for w in vm.current_screen.widgets]
    assert len(set(ids)) == 2 and ids[0] == "_obj_3"
