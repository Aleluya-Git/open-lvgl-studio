"""Control de versiones visual: diferencias, instantáneas e historial de Git."""
import os
import shutil
import subprocess

import pytest

from olvgl.domain.model import Action, EventHandler, Screen, Widget, new_project
from olvgl.domain.visual_diff import diff_projects
from olvgl.infrastructure import json_store
from olvgl.infrastructure.versions import GitHistory, VersionStore


def _p():
    p = new_project("v")
    p.screens[0].widgets = [Widget("btn", "button", 10, 10, 100, 40, props={"text": "A"}),
                            Widget("panel", "obj", 0, 100, 300, 200,
                                   children=[Widget("lbl", "label", 5, 5, None, None, props={"text": "x"})])]
    return p


def test_diff_detects_added_removed_changed_and_pages():
    a = _p()
    b = a.clone()
    b.widget("btn").x = 30
    b.widget("btn").props["text"] = "B"
    b.widget("btn").events = [EventHandler("on_click", [Action("page_next", {})])]
    b.screens[0].widgets[1].children = []                       # lbl eliminado
    b.screens[0].widgets.append(Widget("nuevo", "label", 0, 0, None, None))
    b.screens.append(Screen("p2", "Dos", None, []))
    d = diff_projects(a, b)
    pg = d.page(a.screens[0].id)
    st = {w.id: w for w in pg.widgets}
    assert st["nuevo"].status == "added" and st["lbl"].status == "removed"
    assert st["btn"].status == "changed" and set(st["btn"].aspects) == {"geometría", "propiedades", "eventos"}
    assert d.page("p2").status == "added"
    assert d.counts() == {"added": 1, "removed": 1, "changed": 1}
    assert any("x 10→30" in line for line in "\n".join(d.summary()).splitlines() for _ in [0])
    assert diff_projects(a, a.clone()).empty


def test_version_store_roundtrip(tmp_path):
    doc = str(tmp_path / "panel.olvgl")
    store = VersionStore(doc)
    p = _p()
    v1 = store.save(p, "primera", "ana")
    p.widget("btn").x = 99
    v2 = store.save(p, "", "luis")
    vs = store.list()
    assert [v.id for v in vs] == [v2.id, v1.id] or {v.id for v in vs} == {v1.id, v2.id}
    assert store.load(v1.id).widget("btn").x == 10 and store.load(v2.id).widget("btn").x == 99
    assert vs[0].author in ("ana", "luis") and v1.detail.startswith("1 páginas")
    store.delete(v1.id)
    assert [v.id for v in store.list()] == [v2.id]
    with pytest.raises(ValueError):
        store.load("../x")


@pytest.mark.skipif(not shutil.which("git"), reason="git no disponible")
def test_git_history_of_a_project(tmp_path):
    env = dict(os.environ, GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@t", GIT_COMMITTER_NAME="t",
               GIT_COMMITTER_EMAIL="t@t")
    run = lambda *a: subprocess.run(["git", *a], cwd=tmp_path, check=True, capture_output=True, env=env)  # noqa: E731
    run("init", "-q")
    doc = str(tmp_path / "panel.olvgl")
    p = _p()
    json_store.save_project(p, doc)
    run("add", "panel.olvgl")
    run("commit", "-qm", "primero")
    p.widget("btn").x = 55
    json_store.save_project(p, doc)
    run("commit", "-qam", "mover botón")
    os.environ.update({k: v for k, v in env.items() if k.startswith("GIT_")})
    g = GitHistory(doc)
    assert g.available
    log = g.log()
    assert [v.label for v in log] == ["mover botón", "primero"]
    old = g.project_at(log[1].id)
    assert old.widget("btn").x == 10
    assert diff_projects(old, g.project_at(log[0].id)).counts()["changed"] == 1
    assert GitHistory(str(tmp_path.parent / "fuera.olvgl")).log() == []
