"""Colaboración: fusión a tres bandas, presencia y comentarios."""
import random

from olvgl.domain.model import Screen, Widget, new_project
from olvgl.domain.project_merge import merge_projects


def _base():
    p = new_project("c")
    p.screens[0].widgets = [
        Widget("btn", "button", 10, 10, 100, 40, props={"text": "A", "bg_color": "#111111"}),
        Widget("panel", "obj", 0, 100, 300, 200, children=[
            Widget("lbl", "label", 5, 5, None, None, props={"text": "x"}),
            Widget("sw", "switch", 50, 5, 60, 30)]),
    ]
    return p


def test_independent_changes_are_combined():
    base = _base()
    mine, theirs = base.clone(), base.clone()
    mine.widget("btn").x = 50                                   # yo muevo el botón
    mine.screens[0].widgets.append(Widget("nuevo_mio", "label", 0, 0, None, None))
    theirs.widget("btn").props["text"] = "B"                     # el otro cambia su texto
    theirs.widget("panel").children.append(Widget("nuevo_suyo", "led", 0, 0, 20, 20))
    theirs.screens.append(Screen("p2", "Dos", None, [Widget("x2", "label", 0, 0, None, None)]))
    r = merge_projects(base, mine, theirs)
    p = r.project
    assert r.clean, [str(c) for c in r.conflicts]
    assert p.widget("btn").x == 50 and p.widget("btn").props["text"] == "B"
    assert p.widget("nuevo_mio") and p.locate("nuevo_suyo").screen.id == base.screens[0].id
    assert [c.id for c in p.widget("panel").children] == ["lbl", "sw", "nuevo_suyo"]
    assert p.screen("p2") is not None and p.widget("x2") is not None
    assert r.from_theirs >= 3


def test_conflicts_keep_mine_and_are_reported():
    base = _base()
    mine, theirs = base.clone(), base.clone()
    mine.widget("btn").props["bg_color"] = "#FF0000"
    theirs.widget("btn").props["bg_color"] = "#00FF00"
    r = merge_projects(base, mine, theirs)
    assert r.project.widget("btn").props["bg_color"] == "#FF0000"
    assert len(r.conflicts) == 1 and "bg_color" in r.conflicts[0].key


def test_deletions():
    base = _base()
    mine, theirs = base.clone(), base.clone()
    mine.screens[0].widgets = [w for w in mine.screens[0].widgets if w.id != "panel"]   # borro el panel (y sus hijos)
    theirs.widget("btn").y = 77
    r = merge_projects(base, mine, theirs)
    assert r.clean and r.project.widget("panel") is None and r.project.widget("lbl") is None
    assert r.project.widget("btn").y == 77
    # borrado en un lado y cambiado en el otro: se conserva y se avisa
    theirs2 = base.clone()
    theirs2.widget("panel").props["bg_color"] = "#123456"
    r2 = merge_projects(base, mine, theirs2)
    assert r2.project.widget("panel") is not None and len(r2.conflicts) == 1


def test_random_merges_are_consistent():
    """Fusionar consigo mismo o con la base no cambia nada; ids siempre únicos."""
    import os
    import sys
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools"))
    import fuzz
    for seed in range(1, 9):
        a = fuzz.Fuzzer(seed, 25)
        a.run()
        b = fuzz.Fuzzer(seed + 100, 25)
        b.run()
        base = a.vm.project
        assert merge_projects(base, base, base).project.to_dict() == base.to_dict()
        mine = a.vm.project
        r = merge_projects(base, mine, base)
        assert r.project.to_dict() == mine.to_dict() and r.clean
        r = merge_projects(base, base, mine)
        assert r.project.to_dict() == mine.to_dict() and r.clean
        ids = list(merge_projects(base, mine, b.vm.project).project.all_ids())
        assert len(ids) == len(set(ids))
    assert random  # noqa


def test_presence_between_two_instances(tmp_path):
    import time
    from olvgl.infrastructure.collab import Presence
    doc = str(tmp_path / "p.olvgl")
    a, b = Presence(doc, "ana", "pc1"), Presence(doc, "luis", "pc2")
    a.heartbeat()
    b.heartbeat()
    assert [p.user for p in a.others()] == ["luis"] and [p.user for p in b.others()] == ["ana"]
    assert a.others(now=time.time() + 1000) == []          # latido viejo: ausente
    b.leave()
    assert a.others() == []


def test_comments_from_two_people_merge(tmp_path):
    from olvgl.infrastructure.collab import CommentStore
    doc = str(tmp_path / "p.olvgl")
    ana, luis = CommentStore(doc), CommentStore(doc)
    c1 = ana.add("main_page", "btn", "Más grande", "ana")
    c2 = luis.add("main_page", "lbl", "Cambiar texto", "luis")      # luis no había recargado
    luis.reply(c1.id, "Hecho", "luis") if c1.id in luis.comments else None
    ana.reload()
    assert {c.id for c in ana.for_page("main_page")} == {c1.id, c2.id}
    ana.set_resolved(c2.id)
    assert ana.open_by_widget("main_page") == {"btn": 1}
    fresh = CommentStore(doc)
    assert fresh.comments[c2.id].resolved and len(fresh.comments) == 2
    fresh.rename_widgets({"btn": "btn_salon"})
    assert CommentStore(doc).comments[c1.id].widget == "btn_salon"
    ana.delete(c1.id)
    assert c1.id not in CommentStore(doc).comments


def test_save_merges_when_someone_else_saved(vm, tmp_path):
    from olvgl.infrastructure import json_store
    path = str(tmp_path / "p.olvgl")
    vm.add_widget("button")
    vm.save(path)
    vm.open(path)
    other = json_store.load_project(path)                    # otra persona…
    lbl = Widget("lbl_otro", "label", 0, 0, None, None, props={"text": "suyo"})
    other.screens[0].widgets.append(lbl)
    json_store.save_project(other, path)                     # …guarda antes que yo
    assert vm.disk_changed()
    b = vm.add_widget("slider")
    vm.save()
    assert vm.last_merge is not None and vm.last_merge.clean
    saved = json_store.load_project(path)
    assert saved.widget("lbl_otro") is not None and saved.widget(b) is not None
    assert not vm.disk_changed()
    vm.undo()                                                # deshacer la fusión
    assert vm.project.widget("lbl_otro") is None
