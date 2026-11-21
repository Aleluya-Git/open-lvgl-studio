"""Instalador de Windows: recursos (icono + manifiesto asInvoker) y, si hay Go, compilación."""
import importlib.util
import os
import shutil
import struct

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def load_make_syso():
    spec = importlib.util.spec_from_file_location("make_syso", os.path.join(ROOT, "tools", "installer", "make_syso.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_syso_has_icon_group_and_manifest():
    ms = load_make_syso()
    data = ms.build(os.path.join(ROOT, "olvgl", "resources", "app_icon.ico"), "0.10.0b3")
    machine, nsec, _t, symptr, nsym, _o, _c = struct.unpack_from("<HHIIIHH", data, 0)
    assert machine == 0x8664 and nsec == 1 and nsym == 1
    name, _vs, _va, size, raw, relptr, _l, nrel, _nl, chars = struct.unpack_from("<8sIIIIIIHHI", data, 20)
    assert name.rstrip(b"\0") == b".rsrc" and chars == 0x40000040
    sec = data[raw:raw + size]
    _c1, _t1, _ma, _mi, named, ids = struct.unpack_from("<IIHHHH", sec, 0)
    types = [struct.unpack_from("<I", sec, 16 + 8 * k)[0] for k in range(named + ids)]
    assert types == [3, 14, 24]                    # RT_ICON, RT_GROUP_ICON, RT_MANIFEST (ordenados)
    assert nrel == len(ms.read_ico(os.path.join(ROOT, "olvgl", "resources", "app_icon.ico"))) + 2
    assert b'level="asInvoker"' in sec and b'version="0.10.0.3"' in sec
    assert symptr == relptr + 10 * nrel


@pytest.mark.skipif(not shutil.which("go"), reason="sin Go no se compila el instalador")
def test_build_installer(tmp_path):
    import sys
    sys.path.insert(0, os.path.join(ROOT, "tools"))
    import build_installer
    res = build_installer.build(str(tmp_path))
    with open(res["exe"], "rb") as f:
        head = f.read(2)
    assert head == b"MZ" and res["bytes"] > 3_000_000
