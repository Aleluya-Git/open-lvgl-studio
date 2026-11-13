import pytest

from olvgl.domain.yaml_ast import HEX, LITERAL, YMap, YScalar, YSeq, to_python
from olvgl.infrastructure.yaml_emitter import emit
from olvgl.infrastructure.yaml_parser import YamlParseError, load_esphome, parse

SAMPLE = """wifi:
  ssid: !secret wifi_ssid
lvgl:
  pages:
    - id: p
      bg_color: 0x1a1a2e
      widgets:
        - label:
            text: !lambda |-
              return "hola";
        - obj:
"""


def test_spans_tags_and_styles():
    root = parse(SAMPLE)
    assert isinstance(root, YMap)
    ssid = root.get("wifi").get("ssid")
    assert ssid.tag == "!secret" and ssid.value == "wifi_ssid"
    page = root.get("lvgl").get("pages").items[0]
    assert page.span.line == 5 and page.span.col == 7
    bg = page.get("bg_color")
    assert bg.value == 0x1A1A2E and bg.style == HEX
    lam = page.get("widgets").items[0].get("label").get("text")
    assert lam.tag == "!lambda" and lam.style == LITERAL and lam.value == 'return "hola";'
    empty = page.get("widgets").items[1].get("obj")
    assert isinstance(empty, YScalar) and empty.value is None


def test_roundtrip_preserves_semantics_and_tags():
    root = parse(SAMPLE)
    text = emit(root)
    again = parse(text)
    assert to_python(root) == to_python(again)
    assert "ssid: !secret wifi_ssid" in text
    assert "text: !lambda |-" in text
    assert "0x1A1A2E" in text


def test_parse_errors_have_position():
    with pytest.raises(YamlParseError) as exc:
        parse("lvgl:\n  pages: [\n", "malo.yaml")
    assert "malo.yaml:" in str(exc.value)


def test_empty_document():
    assert parse("") == YMap()


def test_includes_and_packages(fixtures_dir):
    import os
    root, log = load_esphome(os.path.join(fixtures_dir, "dispositivo.yaml"))
    pages = [p.get("id").value for p in root.get("lvgl").get("pages").items]
    assert pages == ["desde_paquete", "principal"]  # primero el paquete, como ESPHome
    inc = root.get("lvgl").get("pages").items[0].get("widgets").items[0]
    assert inc.get("button").get("id").value == "btn_incluido"
    assert any("remoto" in w for w in log.warnings)
    assert len(log.included) == 2
    assert isinstance(root.get("image").get("rgb565"), YSeq)
