"""Pantallas propias del usuario."""
import pytest

from olvgl.application import displays
from olvgl.domain.model import DISPLAY_PRESETS


class FakeSettings(dict):
    def get(self, k, default=None):
        return dict.get(self, k, default)

    def set(self, k, v):
        self[k] = v


def test_save_list_update_remove():
    s = FakeSettings()
    displays.load(s)
    d = displays.save(s, "Mi placa", 466, 466)
    assert d.name == "Mi placa" and displays.presets()[-1] == d
    displays.save(s, "mi placa", 480, 480)                       # mismo nombre: se actualiza
    assert [(x.name, x.width) for x in displays.load(s)] == [("mi placa", 480)]
    assert displays.label(displays.CUSTOM[0]).startswith("★ ")
    assert len(displays.presets()) == len(DISPLAY_PRESETS) + 1
    assert displays.remove(s, "mi placa") and displays.load(s) == []


@pytest.mark.parametrize("name,w,h", [("", 100, 100), ("x", 10, 100), ("x", 100, 5000),
                                      (DISPLAY_PRESETS[0].name, 100, 100)])
def test_invalid(name, w, h):
    with pytest.raises(displays.DisplayError):
        displays.save(FakeSettings(), name, w, h)


def test_corrupt_settings_are_ignored():
    s = FakeSettings(custom_displays=[{"name": "ok", "width": 200, "height": 100}, {"width": "x"}, 7,
                                      {"name": "enorme", "width": 99999, "height": 10}])
    assert [d.name for d in displays.load(s)] == ["ok"]
    displays.load(FakeSettings())


def test_save_uses_loaded_settings_and_known():
    from olvgl.domain.model import DisplayProfile
    s = FakeSettings()
    displays.load(s)
    displays.save(None, "Lateral", 720, 720)                    # como el panel lateral
    assert s["custom_displays"][0]["name"] == "Lateral"
    assert displays.is_known(DisplayProfile("Lateral", 720, 720))
    assert not displays.is_known(DisplayProfile("Personalizada", 640, 360))
    assert displays.is_known(DISPLAY_PRESETS[0])
    displays.SETTINGS = None
    with pytest.raises(displays.DisplayError):
        displays.save(None, "Otra", 100, 100)
