"""Instalador de Windows: OpenLVGLStudio-<versión>-Setup.exe

    python tools/build_installer.py [--out dist]

1. Empaqueta la aplicación con build_release (el mismo .zip de la beta).
2. Lo mete dentro de un programa en Go (tools/installer) con su icono y su
   manifiesto, y lo compila para Windows de 64 bits (necesita Go 1.21+; no
   hace falta Windows para compilarlo).

El instalador no pide permisos de administrador: instala para el usuario en
%LOCALAPPDATA%\\Programs\\Open LVGL Studio, busca (u ofrece instalar) Python
3.11+, crea el entorno con PySide6 y PyYAML, los accesos directos y la entrada
de «Aplicaciones instaladas» para desinstalarlo. Ver tools/installer/main.go.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "tools", "installer")
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tools"))


def build(out_dir: str | None = None, test: bool = True) -> dict:
    import build_release
    from olvgl import __version__
    out_dir = os.path.abspath(out_dir or os.path.join(ROOT, "dist"))
    os.makedirs(out_dir, exist_ok=True)
    go = shutil.which("go")
    if not go:
        raise build_release.ReleaseError("Hace falta Go 1.21 o posterior (https://go.dev/dl/) para compilar el instalador")
    rel = build_release.build(out_dir)
    with tempfile.TemporaryDirectory() as tmp:
        work = os.path.join(tmp, "installer")
        shutil.copytree(SRC, work, ignore=shutil.ignore_patterns("*.syso", "payload.zip", "version.txt", "*.exe"))
        shutil.copy(rel["zip"], os.path.join(work, "payload.zip"))
        with open(os.path.join(work, "version.txt"), "w", encoding="utf-8") as f:
            f.write(__version__ + "\n")
        subprocess.run([sys.executable, os.path.join(work, "make_syso.py"),
                        os.path.join(ROOT, "olvgl", "resources", "app_icon.ico"),
                        os.path.join(work, "rsrc_windows_amd64.syso"), __version__], check=True)
        env = dict(os.environ, CGO_ENABLED="0", GOFLAGS="-mod=mod", GOTOOLCHAIN="local",
                   GOCACHE=os.environ.get("GOCACHE", os.path.join(tmp, "gocache")))
        if test:
            subprocess.run([go, "test", "./..."], cwd=work, env=env, check=True, capture_output=True)
        exe = os.path.join(out_dir, f"OpenLVGLStudio-{__version__}-Setup.exe")
        subprocess.run([go, "build", "-trimpath", "-ldflags", "-s -w", "-o", exe, "."], cwd=work,
                       env=dict(env, GOOS="windows", GOARCH="amd64"), check=True)
    h = hashlib.sha256()
    with open(exe, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    with open(exe + ".sha256", "w", encoding="utf-8") as f:
        f.write(f"{h.hexdigest()}  {os.path.basename(exe)}\n")
    return {"exe": exe, "sha256": h.hexdigest(), "bytes": os.path.getsize(exe), "zip": rel["zip"]}


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=None)
    ap.add_argument("--no-test", action="store_true")
    a = ap.parse_args()
    print(json.dumps(build(a.out, not a.no_test), ensure_ascii=False, indent=1))
