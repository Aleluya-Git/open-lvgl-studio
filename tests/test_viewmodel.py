import yaml

from olvgl.domain.model import Action, DisplayProfile, EventHandler
from olvgl.infrastructure import json_store


def test_add_move_undo_redo(vm):
    events = []
    vm.project_changed.connect(lambda: events.append("changed"))
    wid = vm.add_widget("button", 100, 100)
    assert wid == "btn_1"
    w = vm.widget(wid)
    assert (w.width, w.height) == (140, 50)
    assert (w.x, w.y) == (30, 80)  # centrado (30, 75) y ajustado a rejilla de 10
    assert vm.selection == [wid]
    vm.move_widgets({wid: (200, 210)})
    assert (w.x, w.y) == (200, 210)
    assert vm.undo() and (vm.widget(wid).x, vm.widget(wid).y) == (30, 80)
    assert vm.undo() and vm.widget(wid) is None
    assert vm.selection == []
    assert vm.redo() and vm.widget(wid) is not None
    assert vm.redo() and vm.widget(wid).x == 200
    assert not vm.redo()
    assert events


def test_unlimited_history(vm):
    wid = vm.add_widget("label", 0, 0, centered=False)
    for i in range(1, 501):
        vm.move_widgets({wid: (i, i)})
    assert len(vm.history) == 501
    while vm.undo():
        pass
    assert vm.widget(wid) is None


def test_set_prop_merge_and_defaults(vm):
    wid = vm.add_widget("button")
    vm.set_prop([wid], "bg_color", "#ff0000", merge=True)
    vm.set_prop([wid], "bg_color", "#00ff00", merge=True)
    vm.set_prop([wid], "bg_color", "#0000ff", merge=True)
    assert vm.widget(wid).props["bg_color"] == "#0000FF"
    assert len(vm.history) == 2  # añadir + un único cambio de color fusionado
    vm.undo()
    assert "bg_color" not in vm.widget(wid).props
    vm.set_prop([wid], "radius", 8)  # igual al defecto → no se guarda
    assert "radius" not in vm.widget(wid).props


def test_nudge_merges(vm):
    wid = vm.add_widget("label", 0, 0, centered=False)
    for _ in range(5):
        vm.nudge(1, 0)
    assert vm.widget(wid).x == 5
    assert len(vm.history) == 2
    vm.end_interaction()
    vm.nudge(0, 10)
    assert len(vm.history) == 3


def test_delete_duplicate_copy_paste(vm):
    a = vm.add_widget("label", 0, 0, centered=False)
    b = vm.add_widget("button", 100, 100, centered=False)
    vm.set_selection([a, b])
    dup = vm.duplicate()
    assert len(dup) == 2 and all(vm.widget(i) for i in dup)
    assert vm.widget(dup[0]).x == vm.widget(a).x + 10
    vm.copy([b])
    pasted = vm.paste()
    assert len(pasted) == 1 and pasted[0] not in (a, b) + tuple(dup)
    vm.delete_widgets([a, b])
    assert vm.widget(a) is None and vm.widget(b) is None
    vm.undo()
    ids = [w.id for w in vm.current_screen.widgets]
    assert ids.index(a) < ids.index(b)  # orden restaurado


def test_rename_and_validation(vm):
    wid = vm.add_widget("button")
    other = vm.add_widget("label")
    vm.set_selection([wid])
    assert vm.rename_widget(wid, "1malo")
    assert vm.rename_widget(wid, other)
    assert vm.rename_widget(wid, "btn_luz") is None
    assert vm.widget("btn_luz") and vm.selection == ["btn_luz"]
    vm.undo()
    assert vm.widget(wid)


def test_align_distribute_order(vm):
    ids = [vm.add_widget("label", x, y, centered=False) for x, y in ((0, 0), (100, 50), (300, 120))]
    vm.set_selection(ids)
    vm.align("top")
    assert {vm.widget(i).y for i in ids} == {0}
    vm.align("right")
    rights = {vm.widget(i).x + vm.widget(i).width for i in ids}
    assert len(rights) == 1
    vm.undo()
    vm.distribute("h")
    xs = sorted(vm.widget(i).x for i in ids)
    assert xs[1] - xs[0] == xs[2] - xs[1]
    vm.set_selection([ids[0]])
    vm.change_order("front")
    assert vm.current_screen.widgets[-1].id == ids[0]
    vm.change_order("back")
    assert vm.current_screen.widgets[0].id == ids[0]
    vm.change_order("forward")
    assert vm.current_screen.widgets[1].id == ids[0]


def test_screens(vm):
    first = vm.current_screen_id
    sid = vm.add_screen("Ajustes")
    assert sid == "ajustes" and vm.current_screen_id == sid
    b = vm.add_widget("button", screen_id=first)
    vm.set_events(b, [EventHandler("on_click", [Action("page_show", {"page": sid})])])
    assert vm.update_screen(sid, new_id="config") is None
    assert vm.widget(b).events[0].actions[0].params["page"] == "config"
    vm.undo()
    assert vm.widget(b).events[0].actions[0].params["page"] == "ajustes"
    assert not vm.remove_screen("no_existe")
    assert vm.remove_screen(sid)
    assert not vm.remove_screen(first)  # nunca se queda sin pantallas
    vm.undo()
    assert vm.project.screen(sid)


def test_images(vm, tmp_path):
    png = tmp_path / "Logo Casa.png"
    png.write_bytes(b"x")
    iid = vm.add_image(str(png))
    assert iid == "img_logo_casa"
    w = vm.add_widget("image")
    vm.set_prop([w], "src", iid)
    vm.remove_image(iid)
    assert "src" not in vm.widget(w).props and vm.project.image(iid) is None
    vm.undo()
    assert vm.widget(w).props["src"] == iid


def test_save_load_dirty(vm, tmp_path):
    dirty = []
    vm.dirty_changed.connect(dirty.append)
    png = tmp_path / "img" / "a.png"
    png.parent.mkdir()
    png.write_bytes(b"x")
    vm.add_image(str(png))
    vm.add_widget("label")
    assert vm.dirty
    path = str(tmp_path / "p.olvgl")
    vm.save(path)
    assert not vm.dirty and dirty[-1] is False
    raw = (tmp_path / "p.olvgl").read_text(encoding="utf-8")
    assert '"path": "img/a.png"' in raw  # ruta relativa
    vm.undo()
    assert vm.dirty
    vm.redo()
    assert not vm.dirty
    vm.open(path)
    assert vm.project.widget("lbl_1") and not vm.dirty
    assert vm.resolve_path(vm.project.images[0].path) == str(png)


def test_project_meta_and_yaml(vm):
    vm.set_project_meta(name="Cocina", display=DisplayProfile("X", 480, 272), device_name="cocina")
    assert vm.project.display.width == 480
    vm.add_widget("label")
    data = yaml.safe_load(vm.generate_yaml())
    assert data["lvgl"]["pages"][0]["widgets"][0]["label"]["text"] == "Etiqueta"
    vm.undo()
    vm.undo()
    assert vm.project.name != "Cocina"


def test_autosave(tmp_path, vm):
    path = str(tmp_path / "p.olvgl")
    vm.save(path)
    assert json_store.pending_autosave(path, str(tmp_path)) is None
    auto = json_store.write_autosave(vm.project, path, str(tmp_path))
    json_store.touch(auto)
    import os
    os.utime(path, (0, 0))
    assert json_store.pending_autosave(path, str(tmp_path)) == auto
    p = json_store.load_project(auto)
    assert p.name == vm.project.name
    json_store.discard_autosave(path, str(tmp_path))
    assert json_store.pending_autosave(path, str(tmp_path)) is None


def test_bad_files(tmp_path):
    import pytest
    bad = tmp_path / "x.olvgl"
    bad.write_text("{no json", encoding="utf-8")
    with pytest.raises(json_store.ProjectFormatError):
        json_store.load_project(str(bad))
    bad.write_text('{"format": "otro"}', encoding="utf-8")
    with pytest.raises(json_store.ProjectFormatError):
        json_store.load_project(str(bad))


def test_last_change_describes_geometry_widget_and_structure_changes(vm):
    b = vm.add_widget("button")
    assert vm.last_change.kind == "structure"
    vm.set_selection([b])
    vm.nudge(1, 0)
    assert vm.last_change.kind == "geometry" and vm.last_change.ids == {b}
    vm.set_prop([b], "bg_color", "#FF0000")
    assert vm.last_change.kind == "widgets" and "props" in vm.last_change.keys
    vm.undo()
    assert vm.last_change.kind == "widgets"
    vm.undo()
    assert vm.last_change.kind == "geometry"
    vm.add_screen("Otra")
    assert vm.last_change.kind == "structure" and vm.last_change.ids is None
