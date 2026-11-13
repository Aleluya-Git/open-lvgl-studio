"""Generador C para LVGL 9.

Si la variable de entorno LVGL_DIR apunta a un árbol de LVGL 9.5+ (y hay gcc),
el código generado se compila de verdad contra sus cabeceras."""
import os
import shutil
import subprocess

import pytest

from olvgl.domain.model import Action, EventHandler, Screen, Widget, new_project
from olvgl.infrastructure.esphome_importer import import_esphome_file
from olvgl.infrastructure.lvgl_c_generator import c_str, export_c, generate_c

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REAL = os.path.join(ROOT, "examples", "panel-domotica_final.yaml")


def full_project():
    p = new_project("Todos los widgets")
    s = p.screens[0]
    s.bg_color = "#101018"
    s.widgets += [
        Widget("lbl", "label", 10, 10, None, None, props={"text": "Hola \"mundo\"\nsegunda", "long_mode": "DOT",
                                                          "text_font": "montserrat_20", "recolor": True}),
        Widget("btn", "button", 10, 50, 120, 40, props={"text": "OK", "bg_color": "#FF0000",
                                                        "pressed": {"bg_color": "#880000"}},
               events=[EventHandler("on_click", [Action("page_show", {"page": "p2"}),
                                                 Action("widget_state", {"op": "hide", "id": "lbl"}),
                                                 Action("widget_update", {"type": "label", "id": "lbl",
                                                                          "props": {"text": "Nuevo"}}),
                                                 Action("ha_action", {"action": "light.toggle",
                                                                      "entity_id": "light.x"})])]),
        Widget("arc", "arc", 200, 10, 120, 120, props={"value": 30, "adjustable": True, "start_angle": 150,
                                                       "indicator": {"arc_color": "#00FF00"}}),
        Widget("bar", "bar", 10, 200, 200, 20, props={"value": 40, "mode": "RANGE", "start_value": 10}),
        Widget("sld", "slider", 10, 240, 200, 10, props={"value": 50, "knob": {"bg_color": "#FFFFFF"}}),
        Widget("sw", "switch", 10, 270, None, None, props={"state": {"checked": True}}),
        Widget("chk", "checkbox", 10, 310, None, None, props={"text": "Casilla"}),
        Widget("dd", "dropdown", 300, 200, 150, None, props={"options": ["a", "b"], "selected_index": 1,
                                                             "dir": "TOP"}),
        Widget("rol", "roller", 300, 260, 100, 100, props={"options": ["x", "y", "z"], "mode": "INFINITE"}),
        Widget("ta", "textarea", 10, 350, 200, 40, props={"placeholder_text": "…", "one_line": True}),
        Widget("kb", "keyboard", None, None, None, None, props={"textarea": "ta", "mode": "NUMBER",
                                                                "align": "BOTTOM_MID"}),
        Widget("spb", "spinbox", 500, 10, 100, 40, props={"digits": 5, "decimal_places": 1, "value": 123}),
        Widget("led", "led", 500, 60, 30, 30, props={"color": "#FF00FF", "brightness": "50%"}),
        Widget("spn", "spinner", 500, 100, 50, 50, props={"spin_time": "2s", "arc_length": 60}),
        Widget("ln", "line", 500, 160, None, None, props={"points": ["0,0", "50,20"], "line_width": 3}),
        Widget("qr", "qrcode", 600, 10, None, None, props={"text": "https://esphome.io", "size": 80}),
        Widget("bm", "buttonmatrix", 600, 100, 200, 80,
               props={"rows": [{"buttons": [{"text": "1"}, {"text": "2"}]}, {"buttons": [{"text": "3"}]}]}),
        Widget("tv", "tabview", 10, 420, 400, 150, props={"position": "BOTTOM"},
               children=[Widget("t1", "tab", None, None, None, None, props={"name": "Uno"},
                                children=[Widget("in_tab", "label", 5, 5, None, None, props={"text": "dentro"})]),
                         Widget("t2", "tab", None, None, None, None, props={"name": "Dos"})]),
        Widget("tile", "tileview", 450, 420, 200, 150,
               children=[Widget("tl1", "tile", None, None, None, None, props={"row": 0, "column": 0, "dir": "HOR"})]),
        Widget("grid", "obj", 700, 300, 200, 200, props={"layout": "2x2"},
               children=[Widget(f"g{i}", "obj", None, None, 20, 20) for i in range(4)]),
        Widget("mt", "meter", 800, 10, 100, 100),
        Widget("cv", "canvas", 800, 120, 50, 50),
    ]
    p.screens.append(Screen("p2", "Dos"))
    return p


def test_generates_all_widgets():
    res = generate_c(full_project())
    src = res.source
    for fn in ("lv_label_create", "lv_button_create", "lv_arc_create", "lv_bar_create", "lv_slider_create",
               "lv_switch_create", "lv_checkbox_create", "lv_dropdown_create", "lv_roller_create",
               "lv_textarea_create", "lv_keyboard_create", "lv_spinbox_create", "lv_led_create",
               "lv_spinner_create", "lv_line_create", "lv_qrcode_create", "lv_buttonmatrix_create",
               "lv_tabview_create", "lv_tabview_add_tab", "lv_tileview_add_tile", "lv_canvas_create"):
        assert fn in src, fn
    assert "lv_label_set_long_mode(ui_lbl, LV_LABEL_LONG_MODE_DOTS);" in src
    assert 'lv_label_set_text(ui_lbl, "Hola \\"mundo\\"\\nsegunda");' in src
    assert "lv_obj_set_style_bg_color(ui_btn, lv_color_hex(0x880000), LV_PART_MAIN | LV_STATE_PRESSED);" in src
    assert "lv_obj_set_style_arc_color(ui_arc, lv_color_hex(0x00FF00), LV_PART_INDICATOR | LV_STATE_DEFAULT);" in src
    assert "lv_obj_add_state(ui_sw, LV_STATE_CHECKED);" in src
    assert "lv_screen_load(ui_p2);" in src and "ui_set_flag(ui_lbl, LV_OBJ_FLAG_HIDDEN, true);" in src
    assert 'lv_label_set_text(ui_lbl, "Nuevo");' in src
    assert "ui_action_handler(\"btn\"" in src                    # acción de HA delegada
    assert "lv_keyboard_set_textarea(ui_kb, ui_ta);" in src       # diferida tras crear el textarea
    assert "lv_obj_set_grid_cell(ui_g3, LV_GRID_ALIGN_START, 1, 1, LV_GRID_ALIGN_START, 1, 1);" in src
    assert "LV_FONT_MONTSERRAT_20" in res.fonts
    assert "extern lv_obj_t * ui_btn;" in res.header and "void ui_init(void);" in res.header


def test_c_string_escaping():
    assert c_str('a"b\\c\nd??=') == '"a\\"b\\\\c\\nd?\\?="'


def test_styles_and_theme(demo_path):
    p, _ = import_esphome_file(demo_path)
    res = generate_c(p)
    assert "static lv_style_t ui_style_tarjeta;" in res.source
    assert "lv_style_set_bg_color(&ui_style_tarjeta, lv_color_hex(0x1F1F29));" in res.source  # color con nombre
    assert "ui_style_tarjeta_pressed" in res.source
    assert "lv_obj_add_style(ui_btn_comedor, &ui_theme_button" in res.source
    assert "LV_IMAGE_DECLARE(img_bombilla);" in res.source
    assert "extern const lv_font_t font_roboto_20;" in res.source
    assert "lv_layer_top()" in res.source


def test_export_writes_files(tmp_path, demo_path):
    p, _ = import_esphome_file(demo_path)
    files, _ = export_c(p, str(tmp_path / "c"))
    assert sorted(os.path.basename(f) for f in files) == ["ui.c", "ui.h"]


def _compile(source_dir):
    lvgl = os.environ.get("LVGL_DIR")
    conf = os.environ.get("LVGL_CONF_DIR")
    if not lvgl or not conf or not shutil.which("gcc"):
        pytest.skip("Define LVGL_DIR y LVGL_CONF_DIR para compilar contra LVGL")
    proc = subprocess.run(["gcc", "-fsyntax-only", "-std=c11", "-Wall", "-Wextra", "-Wpedantic",
                           "-DLV_CONF_INCLUDE_SIMPLE", f"-I{conf}", f"-I{lvgl}",
                           os.path.join(source_dir, "ui.c")], capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr[-3000:]
    assert "warning" not in proc.stderr, proc.stderr[-3000:]


def test_compiles_with_lvgl(tmp_path, demo_path):
    export_c(full_project(), str(tmp_path / "full"))
    _compile(str(tmp_path / "full"))
    p, _ = import_esphome_file(demo_path)
    export_c(p, str(tmp_path / "demo"))
    _compile(str(tmp_path / "demo"))
    if os.path.exists(REAL):
        p, _ = import_esphome_file(REAL)
        export_c(p, str(tmp_path / "real"))
        _compile(str(tmp_path / "real"))
