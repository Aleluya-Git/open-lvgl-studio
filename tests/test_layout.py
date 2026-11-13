import pytest

from olvgl.domain.layout import compute_layout, effective_props, named_colors, resolve_color
from olvgl.domain.model import DisplayProfile, Project, Screen, Widget
from olvgl.infrastructure.esphome_importer import import_esphome_file, import_esphome_text


def boxes_of(text, w=1024, h=600, screen=0):
    p, _ = import_esphome_text(text, display=DisplayProfile("t", w, h))
    return p, compute_layout(p, p.screens[screen])


def r(b):
    return tuple(round(v) for v in (b.rect.x, b.rect.y, b.rect.w, b.rect.h))


def test_align_and_offsets():
    _, b = boxes_of("""lvgl:
  pages:
    - id: p
      widgets:
        - obj: {id: a, width: 100, height: 50, align: CENTER}
        - obj: {id: b, width: 25%, height: 10%, align: BOTTOM_RIGHT, x: -10, y: -20}
        - obj: {id: c, width: 100, height: 50, x: 10%, y: 30}
""", 1000, 500)
    assert r(b["a"]) == (450, 225, 100, 50)
    assert r(b["b"]) == (740, 430, 250, 50)
    assert r(b["c"]) == (100, 30, 100, 50)
    assert b["c"].rel_x == 100


def test_nested_padding_and_border():
    _, b = boxes_of("""lvgl:
  pages:
    - id: p
      widgets:
        - obj:
            id: card
            x: 100
            y: 100
            width: 300
            height: 200
            pad_all: 10
            border_width: 2
            widgets:
              - obj: {id: inner, width: 100%, height: 50, align: BOTTOM_MID}
""")
    assert r(b["inner"]) == (112, 238, 276, 50)
    assert b["inner"].parent == "card"


def test_flex_row_wrap_and_alignment():
    _, b = boxes_of("""lvgl:
  pages:
    - id: p
      widgets:
        - obj:
            id: f
            width: 300
            height: 300
            pad_all: 0
            border_width: 0
            layout:
              type: flex
              flex_flow: ROW_WRAP
              flex_align_main: CENTER
              pad_column: 10
              pad_row: 20
            widgets:
              - obj: {id: a, width: 100, height: 40, x: 999}
              - obj: {id: b, width: 100, height: 60}
              - obj: {id: c, width: 100, height: 40}
              - obj: {id: d, width: 100, height: 40, floating: true, x: 5, y: 5}
""")
    # dos filas: (a, b) ocupan 210 de 300; c no cabe y pasa a la segunda fila
    assert r(b["a"]) == (45, 0, 100, 40)
    assert r(b["b"]) == (155, 0, 100, 60)
    assert r(b["c"]) == (100, 80, 100, 40)
    assert b["a"].managed and not b["a"].movable
    assert r(b["d"]) == (5, 5, 100, 40) and b["d"].movable


def test_flex_column_grow():
    _, b = boxes_of("""lvgl:
  pages:
    - id: p
      layout: {type: flex, flex_flow: COLUMN}
      widgets:
        - obj: {id: a, width: 100, height: 100}
        - obj: {id: b, width: 100, height: 100, flex_grow: 1}
""", 400, 600)
    assert r(b["a"]) == (0, 0, 100, 100)
    assert r(b["b"]) == (0, 100, 100, 500)


def test_grid_tracks_and_cells():
    _, b = boxes_of("""lvgl:
  pages:
    - id: p
      widgets:
        - obj:
            id: g
            width: 420
            height: 300
            pad_all: 0
            border_width: 0
            layout:
              type: grid
              grid_columns: [100, FR(1), FR(2)]
              grid_rows: [50, FR(1)]
              pad_column: 10
              pad_row: 10
            widgets:
              - obj: {id: a, grid_cell_column_pos: 0, grid_cell_row_pos: 0, grid_cell_x_align: STRETCH, grid_cell_y_align: STRETCH}
              - obj: {id: b, grid_cell_column_pos: 1, grid_cell_row_pos: 1, grid_cell_column_span: 2, grid_cell_x_align: STRETCH, grid_cell_y_align: STRETCH}
              - obj: {id: c, width: 20, height: 20, grid_cell_column_pos: 2, grid_cell_row_pos: 0, grid_cell_x_align: END, grid_cell_y_align: CENTER}
""")
    # columnas: 100 | (420-100-20)/3=100 | 200
    assert r(b["a"]) == (0, 0, 100, 50)
    assert r(b["b"]) == (110, 60, 310, 240)
    assert r(b["c"]) == (400, 15, 20, 20)


def test_grid_shorthand_autoplacement():
    _, b = boxes_of("""lvgl:
  pages:
    - id: p
      widgets:
        - obj:
            id: g
            width: 200
            height: 200
            pad_all: 0
            border_width: 0
            pad_row: 0
            pad_column: 0
            layout: 2x2
            widgets:
              - obj: {id: a, width: 10, height: 10}
              - obj: {id: b, width: 10, height: 10}
              - obj: {id: c, width: 10, height: 10}
""")
    assert [r(b[i])[:2] for i in "abc"] == [(0, 0), (100, 0), (0, 100)]


def test_tabs_and_top_layer(demo_path):
    p, _ = import_esphome_file(demo_path)
    b = compute_layout(p, p.screen("inicio"))
    assert b["tab_pb"].shown and not b["tab_pp"].shown and not b["lbl_pp"].shown
    bar = b["pestanas"].extra["tab_bar"]
    assert (bar.y, bar.h) == (340, 50)
    assert [n for _, n, _ in b["pestanas"].extra["tab_buttons"]] == ["Planta baja", "Primera planta"]
    from olvgl.domain.layout import LayoutContext
    b2 = compute_layout(p, p.screen("inicio"), LayoutContext(p, active_tabs={"pestanas": 1}))
    assert b2["lbl_pp"].shown and not b2["tab_pb"].shown
    tl = compute_layout(p, p.top_layer)
    assert r(tl["barra_superior"]) == (0, 0, 1024, 60)
    assert tl["lbl_temp_ext"].rect.right == pytest.approx(1004)
    clima = b["panel_clima"]
    assert round(clima.rect.right) == 1004 and round(clima.rect.w) == 461


def test_effective_styles_and_inheritance(demo_path):
    p, _ = import_esphome_file(demo_path)
    colors = named_colors(p)
    assert colors["morado"] == "#7E57C2" and colors["gris_tarjeta"] == "#1F1F29"
    card = p.widget("panel_luces")
    eff = effective_props(p, card)
    assert eff["radius"] == 16 and eff["border_width"] == 0
    assert resolve_color(eff["bg_color"], colors) == "#1F1F29"
    btn = p.widget("btn_comedor")
    beff = effective_props(p, btn, eff)
    assert beff["radius"] == 14 and resolve_color(beff["bg_color"], colors) == "#7E57C2"
    lbl = p.widget("lbl_titulo_luces")
    leff = effective_props(p, lbl)
    assert leff["text_color"] == "#FFFFFF" and leff["text_font"] == "roboto_20"


def test_size_content_and_defaults():
    p = Project(display=DisplayProfile("t", 800, 480))
    s = Screen("p")
    s.widgets.append(Widget("l", "label", x=0, y=0, width=None, height=None,
                            props={"text": "Hola mundo", "text_font": "montserrat_20"}))
    s.widgets.append(Widget("sw", "switch", x=0, y=100, width=None, height=None))
    s.widgets.append(Widget("o", "obj", x=0, y=200, width="SIZE_CONTENT", height="SIZE_CONTENT",
                            props={"pad_all": 5, "border_width": 0},
                            children=[Widget("in", "obj", x=10, y=10, width=50, height=20)]))
    p.screens.append(s)
    b = compute_layout(p, s)
    assert b["l"].rect.w > 50 and b["l"].rect.h == 24
    assert r(b["sw"]) == (0, 100, 50, 26)
    assert r(b["o"]) == (0, 200, 70, 40)


def test_image_resize_sets_size():
    _, b = boxes_of("""image:
  - platform: online_image
    id: cover
    url: http://x/y.jpg
    format: JPEG
    resize: 290x290
lvgl:
  pages:
    - id: p
      widgets:
        - image: {id: im, src: cover, x: 10, y: 20}
""")
    assert r(b["im"]) == (10, 20, 290, 290)
