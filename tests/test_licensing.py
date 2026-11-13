"""Licencias: Ed25519 (RFC 8032), firma, caducidad, manipulación y funciones."""
import datetime as dt

import pytest

from olvgl.application import licensing as lc
from olvgl.domain import ed25519


def test_rfc8032_vector_1():
    sk = bytes.fromhex("9d61b19deffd5a60ba844af492ec2cc44449c5697b326919703bac031cae7f60")
    pk = bytes.fromhex("d75a980182b10ab7d54bfed3c964073a0ee172f3daa62325af021a68f707511a")
    sig = bytes.fromhex("e5564300c360ac729086e2cc806e828a84877f1eb8e5d974d873e065224901555fb8821590a33bac"
                        "c61e39701cf9b46bd25bf5f0595bbe24655141438e7a100b")
    assert ed25519.public_key(sk) == pk and ed25519.sign(sk, b"") == sig
    assert ed25519.verify(pk, b"", sig) and not ed25519.verify(pk, b"x", sig)
    assert not ed25519.verify(pk, b"", sig[:-1] + b"\x00")


@pytest.fixture
def key(monkeypatch):
    secret = ed25519.generate_secret()
    monkeypatch.setattr(lc, "EXTRA_PUBLIC_KEYS", [ed25519.public_key(secret)])
    return secret


def _lic(**kw):
    d = dict(id="abc", licensee="Empresa", edition="pro", issued="2026-11-11", expires="2027-11-11")
    d.update(kw)
    return lc.License(**d)


def test_valid_expired_tampered_and_foreign(key):
    lic = lc.sign_license(_lic(), key)
    st = lc.check(lic, dt.date(2027, 1, 1))
    assert st.state == "valid" and st.edition == "pro" and st.name == "Pro"
    assert lc.check(lic, dt.date(2028, 1, 1)).state == "expired"
    again = lc.License.from_json(lic.to_json())
    assert lc.check(again, dt.date(2027, 1, 1)).state == "valid"
    again.edition = "enterprise"                              # manipulada
    assert lc.check(again, dt.date(2027, 1, 1)).state == "invalid"
    other = lc.sign_license(_lic(), ed25519.generate_secret())   # firmada por otra clave
    assert lc.check(other).state == "invalid"


def test_install_current_and_features(key, tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    assert lc.current().edition == "community"
    path = tmp_path / "l.olvgl-lic"
    path.write_text(lc.sign_license(_lic(expires=None, edition="enterprise"), key).to_json(), encoding="utf-8")
    assert lc.install(str(path)).edition == "enterprise" and lc.current().state == "valid"
    monkeypatch.setattr(lc, "ENFORCE", False)
    assert lc.has("ia")                                       # sin comprobaciones: todo disponible
    monkeypatch.setattr(lc, "ENFORCE", True)
    assert lc.has("ia") and lc.has("vscode") and lc.has("importar_yaml")          # Enterprise
    pro = lc.check(lc.sign_license(_lic(), key), dt.date(2027, 1, 1))
    assert lc.has("importar_yaml", pro) and lc.has("vscode", pro) and not lc.has("ia", pro)
    community = lc.LicenseStatus("community")
    assert not lc.has("importar_yaml", community) and not lc.has("ia", community)
    assert lc.has("versiones", community)                     # lo no listado es para todos
    assert lc.has("ia", lc.check(lc.sign_license(_lic(features=["ia"]), key), dt.date(2027, 1, 1)))
    assert "Pro" in lc.required_message("vscode") and "Enterprise" in lc.required_message("ia")
    lc.remove()
    assert lc.current().state == "none"
    bad = tmp_path / "bad.olvgl-lic"
    bad.write_text("{}", encoding="utf-8")
    with pytest.raises(lc.LicenseError):
        lc.install(str(bad))


def test_license_tool_roundtrip(tmp_path, monkeypatch):
    import os
    import sys
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools"))
    import license_tool
    keyfile = str(tmp_path / "k.txt")
    pub = license_tool.keygen(keyfile, register=False)
    monkeypatch.setattr(lc, "EXTRA_PUBLIC_KEYS", [bytes.fromhex(pub)])
    out = str(tmp_path / "x.olvgl-lic")
    assert license_tool.main(["sign", "--key", keyfile, "--licensee", "ACME", "--edition", "enterprise",
                              "--seats", "3", "--out", out]) == 0
    assert license_tool.main(["verify", out]) == 0
    with pytest.raises(SystemExit):
        license_tool.keygen(keyfile, register=False)          # no sobrescribe una clave


def test_author_public_key_is_registered():
    keys = [k.hex() for k in lc.public_keys()]
    assert "705c4f233a4fa72311386dce0e3b7f1acb108c286f3dcc65b4c64ccb6e8d9f2d" in keys


def test_shared_license_from_environment(key, tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path / "app"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "app"))
    shared = tmp_path / "red" / "empresa.olvgl-lic"
    shared.parent.mkdir()
    shared.write_text(lc.sign_license(_lic(expires=None, edition="pro"), key).to_json(), encoding="utf-8")
    monkeypatch.setenv("OLVGL_LICENSE", str(shared))
    assert lc.current().edition == "pro"
    lc.remove()                                               # nunca borra la compartida
    assert shared.exists()


def test_cli_requires_pro_without_license(tmp_path):
    import json
    import os
    import subprocess
    import sys
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    env = dict(os.environ, OLVGL_LICENSE_ENFORCE="1", APPDATA=str(tmp_path), XDG_DATA_HOME=str(tmp_path),
               OLVGL_NO_PLUGINS="1", PYTHONIOENCODING="utf-8")
    env.pop("OLVGL_LICENSE", None)
    demo = os.path.join(root, "examples", "importar", "panel_demo.yaml")
    p = subprocess.run([sys.executable, "-m", "olvgl.cli", "info", demo], capture_output=True, text=True,
                       encoding="utf-8", cwd=root, env=env, timeout=120)
    assert p.returncode == 3 and json.loads(p.stdout)["license"] is True
    p = subprocess.run([sys.executable, "-m", "olvgl.cli", "serve"], input=json.dumps(
        {"id": 1, "cmd": "info", "path": demo}) + "\n" + json.dumps({"id": 2, "cmd": "ping"}) + "\n",
        capture_output=True, text=True, encoding="utf-8", cwd=root, env=env, timeout=120)
    lines = [json.loads(x) for x in p.stdout.splitlines() if x.strip()]
    assert lines[0]["ok"] is False and lines[0]["license"] is True and "Pro" in lines[0]["error"]
    assert lines[1]["ok"] is True
