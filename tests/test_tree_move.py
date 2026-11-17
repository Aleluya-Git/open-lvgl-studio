"""Mover widgets en el árbol del proyecto (arrastrar y soltar): orden, padre y página."""
from olvgl.application.viewmodel import ProjectViewModel
from olvgl.domain.model import Screen, Widget, new_project
from olvgl.infrastructure.esphome_generator import generate_yaml


def make():
    p = new_project("Árbol")
    p.screens[0].widgets += [
        Widget("a", "button", 10, 10, 100, 40),
        Widget("box", "obj", 200, 100, 300, 200, props={"pad_all": 10}),
        Widget("b", "label", 50, 300, None, None, props={"text": "b"}),
        Widget("tv", "tabview", 0, 400, 400, 150, children=[
            Widget("t1", "tab", None, None, None, None, props={"name": "Uno"}),
            Widget("t2", "tab", None, None, None, None, props={"name": "Dos"})]),
    ]
    p.screens.append(Screen("p2", "Dos"))
    vm = ProjectViewModel(generator=generate_yaml)
    vm.replace_project(p)
    return vm


def ids(lst):
    return [w.id for w in lst]


def test_reorder_same_parent():
    vm = make()
    assert vm.move_widgets_to(["a"], parent_id=None, anchor_id="b", after=True) == ["a"]
    assert ids(vm.current_screen.widgets) == ["box", "b", "a", "tv"]
    vm.undo()
    assert ids(vm.current_screen.widgets) == ["a", "box", "b", "tv"]
    assert vm.move_widgets_to(["b"], anchor_id="a", after=False) == ["b"]
    assert ids(vm.current_screen.widgets) == ["b", "a", "box", "tv"]
    assert vm.move_widgets_to(["b"], anchor_id="a", after=False) == []      # ya está ahí


def test_into_container_keeps_position_and_out_again():
    vm = make()
    before = vm.box("a").rect
    assert vm.move_widgets_to(["a"], parent_id="box") == ["a"]
    assert ids(vm.widget("box").children) == ["a"]
    after = vm.box("a").rect
    assert (after.x, after.y) == (before.x, before.y)
    assert vm.widget("a").x == 10 - 212 and vm.widget("a").y == 10 - 112     # relativo al contenido (borde 2 + relleno 10)
    assert vm.move_widgets_to(["a"], parent_id=None, anchor_id="box", after=False) == ["a"]
    assert ids(vm.current_screen.widgets)[:2] == ["a", "box"] and (vm.widget("a").x, vm.widget("a").y) == (10, 10)
    vm.undo()
    vm.undo()
    assert ids(vm.current_screen.widgets) == ["a", "box", "b", "tv"] and vm.widget("a").x == 10


def test_rules():
    vm = make()
    assert vm.move_widgets_to(["box"], parent_id="box") == []                # en sí mismo
    vm.move_widgets_to(["a"], parent_id="box")
    assert vm.move_widgets_to(["box"], parent_id="a") == []                  # un botón sí es contenedor…
    assert vm.move_widgets_to(["box"], parent_id="b") == []                  # …una etiqueta no
    assert vm.move_widgets_to(["t1"], parent_id="box") == []                 # la pestaña no sale de su tabview
    assert vm.move_widgets_to(["b"], parent_id="tv") == []                   # en un tabview sólo pestañas
    assert vm.move_widgets_to(["t2"], parent_id="tv", anchor_id="t1", after=False) == ["t2"]
    assert ids(vm.widget("tv").children) == ["t2", "t1"]
    assert vm.move_widgets_to(["b"], parent_id="t1") == ["b"]                # dentro de una pestaña


def test_to_other_page_and_with_children():
    vm = make()
    vm.move_widgets_to(["b"], parent_id="box")
    assert vm.move_widgets_to(["box", "b"], screen_id="p2") == ["box"]       # el hijo viaja con el padre
    assert vm.current_screen_id == "p2" and ids(vm.current_screen.widgets) == ["box"]
    assert ids(vm.widget("box").children) == ["b"]
    assert vm.selection == ["box"]
    vm.undo()
    assert vm.project.locate("box").screen.id == "main_page" or vm.project.locate("box").screen.id != "p2"
