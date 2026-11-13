"""Fase 6: gestos, desplazamiento, mosaicos, rotación, reposo y estimación de recursos."""
import time

from olvgl.application.simulation import SimulatorEngine, parse_duration
from olvgl.domain.model import Action, EventHandler, Widget
from olvgl.domain.resources import estimate_resources


def logger(msg):
    return [Action("logger", {"message": msg})]


def test_page_scroll_and_press_lost(vm):
    btn = vm.add_widget("button", 20, 20, centered=False)
    vm.set_events(btn, [EventHandler("on_click", logger("clic")),
                        EventHandler("on_press_lost", logger("perdida"))])
    low = vm.add_widget("label", 20, 20, centered=False)
    vm.set_geom_value(low, "y", "900")                           # fuera de la pantalla (600 px)
    log = []
    eng = SimulatorEngine(vm, log.append)
    sid = eng.page_id
    mx, my = eng.scroll_range(sid, sid)
    assert mx == 0 and my > 300
    y0 = eng.box_of(low).rect.y
    b = eng.box_of(btn).rect
    eng.drag(b.x + 5, b.y + 30, b.x + 5, b.y - 170)            # arrastrar hacia arriba desde el botón
    assert eng.scroll[sid][1] > 150
    assert eng.box_of(low).rect.y < y0 - 150
    text = "\n".join(log)
    assert "perdida" in text and "clic" not in text            # desplazar cancela el clic


def test_swipe_triggers_and_double_click(vm):
    panel = vm.add_widget("obj", 100, 100, centered=False)
    vm.set_events(panel, [EventHandler("on_swipe_left", logger("izquierda")),
                          EventHandler("on_swipe_up", logger("arriba")),
                          EventHandler("on_double_click", logger("doble"))])
    log = []
    eng = SimulatorEngine(vm, log.append)
    r = eng.box_of(panel).rect
    cx, cy = r.x + r.w / 2, r.y + r.h / 2
    eng.drag(cx + 40, cy, cx - 40, cy)
    assert any("izquierda" in m for m in log)
    eng.drag(cx, cy + 40, cx, cy - 40)
    assert any("arriba" in m for m in log)
    eng.press(cx, cy)
    eng.release(cx, cy)
    eng.press(cx, cy)
    eng.release(cx, cy)
    assert any("doble" in m for m in log)


def test_tileview_and_tabview_swipe(vm):
    tv = vm.add_widget("tileview", 0, 0, centered=False)
    w = vm.widget(tv)
    tiles = [c.id for c in w.children]
    vm.replace_props(tiles[0], list(vm.widget(tiles[0]).props), {"row": 0, "column": 0, "dir": "HOR"})
    if len(tiles) < 2:
        tiles.append(vm.add_child(tv))
    vm.replace_props(tiles[1], list(vm.widget(tiles[1]).props), {"row": 0, "column": 1, "dir": "LEFT"})
    log = []
    eng = SimulatorEngine(vm, log.append)
    r = eng.box_of(tv).rect
    cy = r.y + r.h / 2
    eng.drag(r.x + 300, cy, r.x + 100, cy)         # dedo a la izquierda → mosaico de la derecha
    assert eng.active_tabs[tv] == 1
    eng.drag(r.x + 300, cy, r.x + 100, cy)         # el mosaico 1 sólo permite volver a la izquierda
    assert eng.active_tabs[tv] == 1 and any("no permite" in m for m in log)
    eng.drag(r.x + 100, cy, r.x + 300, cy)
    assert eng.active_tabs[tv] == 0


def test_tabview_swipe(vm, demo_path):
    vm.import_yaml(demo_path)
    eng = SimulatorEngine(vm)
    r = eng.boxes("inicio")["pestanas"].rect
    cy = r.y + r.h - 20
    eng.drag(r.x + r.w - 40, cy, r.x + 40, cy)
    assert eng.active_tabs["pestanas"] == 1


def test_rotation_and_orientation_triggers(vm):
    vm.project.lvgl_extra["on_portrait"] = [{"logger.log": "vertical"}]
    lbl = vm.add_widget("label", 0, 0, centered=False)
    vm.set_raw_prop([lbl], "align", "BOTTOM_RIGHT")
    log = []
    eng = SimulatorEngine(vm, log.append)
    d = vm.project.display
    assert eng.box_of(lbl).rect.right == d.width
    eng.set_rotation(90)
    assert (eng.display().width, eng.display().height) == (d.height, d.width)
    assert eng.box_of(lbl).rect.right == d.height                 # disposición recalculada
    assert any("on_portrait" in m for m in log)
    assert vm.project.display.width == d.width                    # el diseño no cambia


def test_page_wrap_skip_and_load(vm):
    first = vm.current_screen_id
    second = vm.add_screen("Dos")
    third = vm.add_screen("Tres")
    vm.project.screen(second).props["skip"] = True
    vm.project.screen(third).props["on_load"] = [{"logger.log": "cargada"}]
    vm.project.lvgl_extra["page_wrap"] = False
    vm.set_current_screen(first)
    nxt = vm.add_widget("button", 0, 0, centered=False)
    vm.set_events(nxt, [EventHandler("on_click", [Action("page_next")])])
    log = []
    eng = SimulatorEngine(vm, log.append)
    eng.page_id = first
    b = eng.box_of(nxt).rect
    eng.press(b.x + 2, b.y + 2)
    eng.release(b.x + 2, b.y + 2)
    assert eng.page_id == third                                   # «Dos» tiene skip
    assert any("cargada" in m for m in log)


def test_idle_timeout(vm):
    vm.project.lvgl_extra["on_idle"] = [{"timeout": "2s", "then": [{"lvgl.pause": None}]},
                                        {"timeout": "1min", "then": []}]
    log = []
    eng = SimulatorEngine(vm, log.append)
    assert [t for t, _ in eng.idle_timeouts()] == [2.0, 60.0]
    now = time.monotonic()
    assert eng.check_idle(now + 3) == [2.0]
    assert eng.check_idle(now + 4) == []
    assert any("on_idle 2s" in m for m in log)
    eng.press(1, 1)
    assert not eng.idle_fired
    assert parse_duration("500ms") == 0.5 and parse_duration("1min") == 60 and parse_duration(250) == 0.25


def test_resource_estimate(vm, demo_path):
    vm.import_yaml(demo_path)
    rep = estimate_resources(vm.project)
    assert rep.objects >= 25 and [p.id for p in rep.pages] == ["inicio", "ajustes"]
    d = vm.project.display
    assert rep.draw_buffer_bytes == int(d.width * d.height * 2 * rep.buffer_fraction)
    assert any(f[0] == "montserrat_14" for f in rep.fonts)
    big = vm.project.screens[0]
    big.widgets += [Widget(f"x{i}", "label", 0, 0, props={"text": "x"}) for i in range(300)]
    rep = estimate_resources(vm.project)
    assert any("300" in w or "objetos" in w for w in rep.warnings)
    assert rep.as_dict()["pages"][0]["objects"] > 250
