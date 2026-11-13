"""Leer YAML «del mundo real»: codificaciones, nulos y páginas web guardadas como .yaml."""
import pytest

from olvgl.infrastructure.esphome_importer import import_esphome_file
from olvgl.infrastructure.source_text import from_bytes
from olvgl.infrastructure.yaml_parser import YamlParseError, parse

YAML = "esphome:\n  name: panel\nlvgl:\n  pages:\n    - id: p1\n      widgets:\n        - label:\n            text: \"Hola < 2 ñ\"\n"

GITHUB_PAGE = ('<!DOCTYPE html><html><head><title>panel.yaml at main · alguien/repo</title></head><body>'
               '<script>$R[1]={payload:$R[2]={"codeViewBlobLayoutRoute.StyledBlob":$R[3]={rawLines:$R[4]=['
               '"esphome:","  name: panel","lvgl:","  pages:","    - id: p1","      widgets:","        - label:",'
               '"            text: \\"Hola \\x3C 2 \\u00f1\\""]}}}</script>'
               '<a href="https://github.com/alguien/repo/raw/refs/heads/main/panel.yaml">Raw</a></body></html>')


@pytest.mark.parametrize("enc", ["utf-8", "utf-8-sig", "utf-16", "utf-16-le", "utf-16-be", "utf-32"])
def test_encodings(enc):
    raw = YAML.encode(enc)
    src = from_bytes(raw)
    assert src.text.replace("\r\n", "\n") == YAML and not src.from_html
    assert parse(src.text).get("lvgl") is not None


def test_windows_1252_and_nuls():
    src = from_bytes(YAML.encode("cp1252"))
    assert "ñ" in src.text and "UTF-8" in src.notes[0]
    src = from_bytes(YAML.replace("panel", "pa\x00nel").encode("utf-8"))
    assert "pa\x00nel" not in src.text and "nulos" in src.notes[0]


def test_github_page_saved_as_yaml_is_recovered(tmp_path, vm):
    path = tmp_path / "panel.yaml"
    path.write_text(GITHUB_PAGE, encoding="utf-8")
    project, report = import_esphome_file(str(path))
    assert project.source.get("from_html") and "página web de GitHub" in report.warnings[0]
    assert "/raw/" in report.warnings[0]
    lbl = next(w for _s, w in project.iter_widgets() if w.type == "label")
    assert lbl.props["text"] == "Hola < 2 ñ"
    vm.import_yaml(str(path))
    assert not vm.linked                                      # nunca se escribe en la página web
    assert path.read_text(encoding="utf-8") == GITHUB_PAGE


def test_other_html_explains_what_happened(tmp_path):
    path = tmp_path / "x.yaml"
    path.write_text("<!DOCTYPE html><html><body>Hola</body></html>", encoding="utf-8")
    with pytest.raises(YamlParseError) as e:
        import_esphome_file(str(path))
    assert "página web" in str(e.value) and "Raw" in str(e.value)


def test_control_characters_have_a_clear_message():
    with pytest.raises(YamlParseError) as e:
        parse("a: 1\nb: x\x01y\n", "f.yaml")
    assert e.value.line == 2 and "no permitido" in str(e.value)
