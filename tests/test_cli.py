"""Línea de órdenes y extensión de VS Code (lo que no necesita Qt)."""
import io
import json
import os
import shutil
import subprocess
import sys
import zipfile

import pytest

from olvgl import cli

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EXT = os.path.join(ROOT, "vscode-extension")


def test_info_and_id_lines(demo_path):
    res = cli.info(demo_path)
    assert [p["id"] for p in res["pages"]] == ["inicio", "ajustes"]
    assert res["display"]["width"] == 1024 and res["top_layer"]
    text = open(demo_path, encoding="utf-8").read()
    lines = cli.id_lines(text)
    assert text.splitlines()[lines["arc_temp"]].strip() == "id: arc_temp"


def test_validate_reports_syntax_error_line(tmp_path):
    bad = tmp_path / "bad.yaml"
    bad.write_text("lvgl:\n  pages:\n    - id: p1\n      widgets: [\n", encoding="utf-8")
    d = cli.validate(str(bad))["diagnostics"]
    assert d[0]["severity"] == "error" and d[0]["line"] >= 3


def test_validate_unsaved_text_and_warning_line(demo_path):
    text = "lvgl:\n  pages:\n    - id: p1\n      widgets:\n        - label:\n            id: a\n        - label:\n            id: a\n"
    d = cli.validate(demo_path, text)["diagnostics"]
    rep = [x for x in d if "repetido" in x["message"]]
    assert rep and rep[0]["line"] == 5


def test_serve_protocol(demo_path):
    reqs = [{"id": 1, "cmd": "ping"}, {"id": 2, "cmd": "info", "path": demo_path},
            {"id": 3, "cmd": "nada"}, {"id": 4, "cmd": "ping"}, {"cmd": "quit"}, {"id": 5, "cmd": "ping"}]
    out = io.StringIO()
    cli.serve(io.StringIO("\n".join(json.dumps(r) for r in reqs) + "\n"), out)
    resp = [json.loads(x) for x in out.getvalue().splitlines()]
    assert [r["id"] for r in resp] == [1, 2, 3, 4]          # se para en «quit»
    assert resp[0]["ok"] and resp[1]["result"]["pages"][0]["id"] == "inicio"
    assert not resp[2]["ok"] and "desconocida" in resp[2]["error"]
    assert resp[3]["ok"]


def test_export_c_from_cli(tmp_path, demo_path):
    res = cli.export_c(demo_path, str(tmp_path))
    assert sorted(os.path.basename(f) for f in res["files"]) == ["ui.c", "ui.h"]


def test_vsix_package():
    sys.path.insert(0, os.path.join(ROOT, "tools"))
    import build_vsix
    path = build_vsix.build()
    pkg = json.load(open(os.path.join(EXT, "package.json"), encoding="utf-8"))
    with zipfile.ZipFile(path) as z:
        names = z.namelist()
        manifest = z.read("extension.vsixmanifest").decode("utf-8")
    for need in ("extension/package.json", "extension/extension.js", "extension/lib/core.js",
                 "extension/media/preview.js", "extension/media/icon.png", "extension/snippets/lvgl.json"):
        assert need in names, need
    assert not any(n.startswith("extension/test/") for n in names)
    assert f'Version="{pkg["version"]}"' in manifest and f'Publisher="{pkg["publisher"]}"' in manifest
    assert pkg["main"] == "./extension.js"
    cmds = {c["command"] for c in pkg["contributes"]["commands"]}
    src = open(os.path.join(EXT, "extension.js"), encoding="utf-8").read()
    for c in cmds:
        assert f'"{c}"' in src, c


@pytest.mark.skipif(not shutil.which("node"), reason="Node.js no está instalado")
def test_extension_node_tests():
    for t in ("core.test.js", "activate.test.js"):
        proc = subprocess.run(["node", os.path.join(EXT, "test", t)], capture_output=True, text=True)
        assert proc.returncode == 0, proc.stdout + proc.stderr
    proc = subprocess.run(["node", os.path.join(EXT, "test", "server.test.js"), sys.executable],
                          capture_output=True, text=True, cwd=ROOT)
    assert proc.returncode == 0, proc.stdout + proc.stderr


def test_profile(demo_path):
    res = cli.profile(demo_path)
    assert res["objects"] >= 25 and res["ram_bytes"] > res["heap_bytes"]
    assert res["images"] and res["images"][0]["id"] == "img_bombilla"
