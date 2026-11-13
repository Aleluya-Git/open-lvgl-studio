import os
import shutil

import pytest

from olvgl.infrastructure.sync_adapters import BACKUP_SUFFIX, check_syncable


@pytest.fixture
def linked(vm, demo_path, tmp_path):
    folder = tmp_path / "proyecto"
    shutil.copytree(os.path.dirname(demo_path), folder)
    path = str(folder / "panel_demo.yaml")
    vm.import_yaml(path)
    assert vm.linked, vm.sync_error
    return vm, path


def read(path):
    with open(path, encoding="utf-8", newline="") as f:
        return f.read()


def write(path, text):
    with open(path, "w", encoding="utf-8", newline="") as f:
        f.write(text)


def test_editor_changes_are_written_minimally(linked):
    vm, path = linked
    original = read(path)
    vm.set_raw_prop(["lbl_titulo_luces"], "text", "Iluminación")
    assert vm.dirty
    out = vm.sync_to_source()
    assert out.written and not vm.dirty
    new = read(path)
    assert "text: Iluminación" in new and "text: Luces" not in new
    # todo lo demás intacto: comentarios y secciones no gestionadas
    assert new.count("\n") == original.count("\n")
    assert "# Panel de ejemplo para probar la importación" in new
    assert "entity_id: sensor.temperatura_exterior" in new
    assert os.path.exists(path + BACKUP_SUFFIX)
    assert read(path + BACKUP_SUFFIX) == original


def test_external_change_reloads_and_is_undoable(linked):
    vm, path = linked
    text = read(path)
    write(path, text.replace("text: Luces", "text: Luces de casa"))
    assert vm.check_external()
    assert vm.widget("lbl_titulo_luces").props["text"] == "Luces de casa"
    assert not vm.dirty
    assert vm.history.undo_label == "Cambio externo en el YAML"
    vm.undo()
    assert vm.widget("lbl_titulo_luces").props["text"] == "Luces"
    vm.sync_to_source()
    assert "text: Luces\n" in read(path)
    assert not vm.check_external()   # nuestra propia escritura no cuenta como cambio externo


def test_both_sides_change_are_merged(linked):
    vm, path = linked
    vm.set_raw_prop(["lbl_titulo_luces"], "text", "Desde el editor")
    text = read(path)
    write(path, text.replace("text: Volver", "text: Atrás  # cambiado a mano"))
    assert vm.check_external()          # hay cambios sin escribir: se mezclan
    final = read(path)
    assert "text: Desde el editor" in final and "text: Atrás  # cambiado a mano" in final
    assert vm.widget("btn_volver").props["text"] == "Atrás"
    assert vm.widget("lbl_titulo_luces").props["text"] == "Desde el editor"
    assert not vm.dirty


def test_structural_edits_roundtrip(linked):
    vm, path = linked
    vm.set_current_screen("ajustes")
    wid = vm.add_widget("label", 100, 100)
    vm.delete_widgets(["dd_reposo"])
    vm.add_screen("Clima")
    vm.move_by({"btn_volver": (10, -5)})
    vm.sync_to_source()
    from olvgl.infrastructure.esphome_importer import import_esphome_file
    p, rep = import_esphome_file(path)
    assert p.widget(wid) is not None and p.widget("dd_reposo") is None
    assert [s.id for s in p.screens] == ["inicio", "ajustes", "clima"]
    assert (p.widget("btn_volver").x, p.widget("btn_volver").y) == (30, -25)
    assert not rep.warnings


def test_crlf_and_bom_preserved(vm, tmp_path, demo_path):
    folder = tmp_path / "crlf"
    shutil.copytree(os.path.dirname(demo_path), folder)
    path = str(folder / "panel_demo.yaml")
    with open(demo_path, encoding="utf-8") as f:
        text = f.read()
    with open(path, "wb") as f:
        f.write(b"\xef\xbb\xbf" + text.replace("\n", "\r\n").encode("utf-8"))
    vm.import_yaml(path)
    vm.set_raw_prop(["lbl_titulo_luces"], "text", "CRLF")
    vm.sync_to_source()
    with open(path, "rb") as f:
        raw = f.read()
    assert raw.startswith(b"\xef\xbb\xbf")
    body = raw[3:].decode("utf-8")
    assert "\r\n" in body and "\n" not in body.replace("\r\n", "")
    assert "text: CRLF\r\n" in body


def test_unsupported_files_are_not_linked(vm, fixtures_dir):
    vm.import_yaml(os.path.join(fixtures_dir, "dispositivo.yaml"))
    assert not vm.linked and "packages" in vm.sync_error
    assert vm.dirty
    assert check_syncable("a: !include x.yaml\n", "x") is not None
    assert check_syncable("lvgl:\n  pages: []\n", "x") is None


def test_link_new_project_writes_sections(vm, tmp_path):
    path = str(tmp_path / "dispositivo.yaml")
    write(path, "# mi dispositivo\nesphome:\n  name: test\n\nlogger:\n")
    vm.add_widget("label")
    assert vm.link_source(path)
    text = read(path)
    assert text.startswith("# mi dispositivo\nesphome:\n  name: test\n")
    assert "lvgl:" in text and "pages:" in text and "text: Etiqueta" in text


def test_reopen_olvgl_relinks(linked, tmp_path):
    vm, path = linked
    olvgl = str(tmp_path / "p.olvgl")
    vm.save(olvgl)
    vm.new()
    assert not vm.linked
    vm.open(olvgl)
    assert vm.linked and vm.sync.path == os.path.abspath(path)
    assert not vm.sync.differs(vm.project)
    text = read(path)
    write(path, text.replace("text: Luces", "text: Otra cosa"))
    assert vm.sync.differs(vm.project)
    vm.reload_source()
    assert vm.widget("lbl_titulo_luces").props["text"] == "Otra cosa"


REAL = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                    "examples", "panel-domotica_final.yaml")


def test_real_panel_session(vm, tmp_path):
    if not os.path.exists(REAL):
        pytest.skip("examples/panel-domotica_final.yaml no está")
    path = str(tmp_path / "panel.yaml")
    shutil.copy(REAL, path)
    original = read(path)
    vm.import_yaml(path)
    assert vm.linked, vm.sync_error
    out = vm.sync_to_source()
    assert not out.written and read(path) == original   # sin cambios: el fichero no se toca
    vm.set_raw_prop(["lbl_fecha"], "text", "Lunes")
    out = vm.sync_to_source()
    assert out.written and not out.rewritten
    import difflib
    d = [x for x in difflib.unified_diff(original.splitlines(), read(path).splitlines(), lineterm="", n=0)
         if x[:1] in "+-" and x[:3] not in ("+++", "---")]
    assert len(d) == 2
