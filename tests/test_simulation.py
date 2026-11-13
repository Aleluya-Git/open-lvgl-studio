from olvgl.application.simulation import SimulatorEngine
from olvgl.domain.model import Action, EventHandler


def build(vm):
    first = vm.current_screen_id
    second = vm.add_screen("Ajustes")
    vm.set_current_screen(first)
    go = vm.add_widget("button", 0, 0, centered=False)
    vm.set_prop([go], "checkable", True)
    vm.set_events(go, [
        EventHandler("on_press", [Action("logger", {"message": "pulsado"})]),
        EventHandler("on_click", [Action("ha_action", {"action": "light.toggle", "entity_id": "light.x"}),
                                  Action("page_show", {"page": second})]),
    ])
    back = vm.add_widget("button", 0, 0, centered=False, screen_id=second)
    vm.set_events(back, [EventHandler("on_click", [Action("page_prev")]),
                         EventHandler("on_long_press", [Action("logger", {"message": "largo"})])])
    hidden = vm.add_widget("button", 0, 0, centered=False, screen_id=first)
    vm.set_prop([hidden], "hidden", True)
    return first, second, go, back


def test_click_navigation_and_log(vm):
    first, second, go, back = build(vm)
    log = []
    eng = SimulatorEngine(vm, log.append)
    eng.page_id = first
    assert eng.widget_at(10, 10).id == go  # el oculto de encima no recibe el toque
    assert eng.press(10, 10)
    assert eng.pressed == go
    eng.release(10, 10)
    assert eng.page_id == second
    assert go in eng.checked
    text = "\n".join(log)
    assert "pulsado" in text and "light.toggle" in text and "lvgl.page.show" in text
    # pulsación larga: no se dispara on_short_click y sí on_long_press
    eng.press(5, 5)
    eng.long_press()
    eng.release(5, 5)
    assert "largo" in log[-2] or "largo" in "\n".join(log)
    assert eng.page_id == first  # page_prev con vuelta


def test_release_outside_does_not_click(vm):
    first, second, go, _ = build(vm)
    eng = SimulatorEngine(vm)
    eng.page_id = first
    eng.press(10, 10)
    eng.release(900, 500)
    assert eng.page_id == first and go not in eng.checked
    assert not eng.press(900, 500)


def test_imported_nested_tabs_and_top_layer(vm, demo_path):
    vm.import_yaml(demo_path)
    log = []
    eng = SimulatorEngine(vm, log.append)
    assert eng.page_id == "inicio"
    b = vm.box("btn_comedor").rect
    eng.press(b.x + 5, b.y + 5)
    assert eng.pressed == "btn_comedor"   # botón anidado dentro de un contenedor flex
    eng.release(b.x + 5, b.y + 5)
    assert "btn_comedor" in eng.checked and any("light.comedor" in m for m in log)
    sw = vm.box("sw_ventilador").rect
    eng.press(sw.x + 2, sw.y + 2)
    eng.release(sw.x + 2, sw.y + 2)
    assert "sw_ventilador" in eng.checked and any("YAML: if:" in m for m in log)
    # barra de pestañas: cambia a la segunda
    bar = eng.boxes("inicio")["pestanas"].extra["tab_buttons"][1][0]
    assert not eng.press(bar.x + 5, bar.y + 5)
    assert eng.active_tabs["pestanas"] == 1
    assert eng.boxes("inicio")["chk_bano"].shown
    # la capa superior no tiene botones: el clic llega a la página
    assert eng.widget_at(1000, 10) is None


def test_phase4_actions_and_controls(vm):
    from olvgl.domain.model import Action, EventHandler
    lbl = vm.add_widget("label", 10, 10, centered=False)
    btn = vm.add_widget("button", 10, 100, centered=False)
    vm.set_events(btn, [EventHandler("on_click", [
        Action("widget_state", {"op": "hide", "id": lbl}),
        Action("widget_update", {"type": "label", "id": lbl, "props": {"text": "Cambiado"}}),
        Action("call", {"action": "light.toggle", "target": "luz"}),
        Action("delay", {"duration": "1s"})])])
    sld = vm.add_widget("slider", 10, 300, centered=False)   # 200 x 12
    vm.set_events(sld, [EventHandler("on_value", [Action("logger", {"message": "nuevo valor"})])])
    dd = vm.add_widget("dropdown", 300, 300, centered=False)
    log = []
    eng = SimulatorEngine(vm, log.append)
    b = eng.box_of(btn).rect
    eng.press(b.x + 5, b.y + 5)
    eng.release(b.x + 5, b.y + 5)
    assert eng.widget(lbl).props["hidden"] is True and eng.widget(lbl).props["text"] == "Cambiado"
    assert vm.widget(lbl).props.get("hidden") is None      # el diseño no cambia
    assert any("light.toggle: luz" in m for m in log) and any("Esperar 1s" in m for m in log)
    s = eng.box_of(sld).rect
    eng.press(s.x + s.w * 0.25, s.y + s.h / 2)
    eng.move(s.x + s.w * 0.8, s.y + s.h / 2)
    eng.release(s.x + s.w * 0.8, s.y + s.h / 2)
    assert eng.widget(sld).props["value"] == 80
    assert any("nuevo valor" in m for m in log)
    d = eng.box_of(dd).rect
    eng.press(d.x + 5, d.y + 5)
    eng.release(d.x + 5, d.y + 5)
    assert eng.widget(dd).props["selected_index"] == 1
    eng.reload()
    assert eng.widget(lbl).props.get("hidden") is None     # recargar vuelve al diseño
