"""Paquete de la beta pública: un .zip listo para descomprimir y ejecutar install.bat.

    python tools/build_release.py [--out dist]  →  dist/OpenLVGLStudio-<versión>.zip (+ .sha256)

Incluye la aplicación, plugins de ejemplo, documentación, ejemplos, pruebas,
la extensión de VS Code (.vsix recién empaquetado) y los .bat. Excluye
entornos virtuales, cachés, capturas, autoguardados, resultados de pruebas y
los ficheros privados del desarrollador (PRIVATE). Se niega a empaquetar si
encuentra algo con aspecto de clave o contraseña.
"""
from __future__ import annotations

import argparse
import fnmatch
import hashlib
import os
import re
import sys
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

INCLUDE_DIRS = ["olvgl", "plugins", "docs", "examples", "tests", "tools", "vscode-extension", "marketplace"]
INCLUDE_FILES = ["README.md", "LICENSE", "LICENSING.md", "COMMERCIAL-LICENSE.md", "CHANGELOG.md", "requirements.txt", "pyproject.toml", "main.py", "autoprueba.py",
                 "install.bat", "run.bat", "autoprueba.bat", "install_vscode.bat", ".gitignore"]
EXCLUDE = ["*/__pycache__/*", "*.pyc", "*/.pytest_cache/*", "*/node_modules/*", "*.autosave", "*.bak", "*.lnk",
           "*/fuzz_fallos/*", "capturas/*", ".venv/*", "*/dist/*", "*.vsix", "*/.DS_Store", "*/Thumbs.db",
           "*.versiones/*", "*.presencia/*", "*.comentarios.json", "*.olvgl-lic", "*.exe", "*.syso",
           "tools/installer/payload.zip", "tools/installer/version.txt"]
# Ficheros personales que nunca se publican (el panel real del desarrollador, etc.)
PRIVATE = ["examples/panel-domotica_final.yaml", "examples/panel-domotica_final.*", "examples/privado/*"]
SECRET_RE = re.compile(rb"(sk-ant-[A-Za-z0-9_-]{10,}|sk-[A-Za-z0-9]{32,}|-----BEGIN [A-Z ]*PRIVATE KEY-----"
                       rb"|api_encryption_key\s*:\s*[A-Za-z0-9+/=]{20,}|wifi_password\s*:\s*[^!\s][^\n]{3,})")


class ReleaseError(Exception):
    pass


def wanted(rel: str) -> bool:
    rel = rel.replace(os.sep, "/")
    if any(fnmatch.fnmatch(rel, p) or fnmatch.fnmatch("/" + rel, p) for p in EXCLUDE):
        return False
    return not any(fnmatch.fnmatch(rel, p) for p in PRIVATE)


def collect() -> list[str]:
    out = [f for f in INCLUDE_FILES if os.path.isfile(os.path.join(ROOT, f))]
    for d in INCLUDE_DIRS:
        for base, dirs, files in os.walk(os.path.join(ROOT, d)):
            dirs[:] = sorted(x for x in dirs if x not in ("__pycache__", "node_modules", ".pytest_cache", "dist"))
            for f in sorted(files):
                rel = os.path.relpath(os.path.join(base, f), ROOT).replace(os.sep, "/")
                if wanted(rel):
                    out.append(rel)
    return out


def check_secrets(files: list[str]) -> list[str]:
    bad = []
    for rel in files:
        if rel.endswith((".png", ".ico", ".ttf", ".otf", ".woff", ".woff2", ".zip", ".vsix")):
            continue
        with open(os.path.join(ROOT, rel), "rb") as f:
            m = SECRET_RE.search(f.read())
        if m:
            bad.append(f"{rel}: {m.group(0)[:30]!r}…")
    return bad


def build(out_dir: str | None = None) -> dict:
    from olvgl import __version__
    out_dir = out_dir or os.path.join(ROOT, "dist")
    os.makedirs(out_dir, exist_ok=True)
    files = collect()
    bad = check_secrets(files)
    if bad:
        raise ReleaseError("Posibles secretos, no se empaqueta:\n  " + "\n  ".join(bad))
    sys.path.insert(0, os.path.join(ROOT, "tools"))
    import build_vsix
    vsix = build_vsix.build()
    name = f"OpenLVGLStudio-{__version__}"
    target = os.path.join(out_dir, name + ".zip")
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for rel in files:
            z.write(os.path.join(ROOT, rel), f"{name}/{rel}")
        z.write(vsix, f"{name}/vscode-extension/dist/{os.path.basename(vsix)}")
    h = hashlib.sha256()
    with open(target, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    with open(target + ".sha256", "w", encoding="utf-8") as f:
        f.write(f"{h.hexdigest()}  {os.path.basename(target)}\n")
    return {"zip": target, "sha256": h.hexdigest(), "files": len(files) + 1,
            "bytes": os.path.getsize(target), "vsix": os.path.basename(vsix)}


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=None)
    a = ap.parse_args()
    import json
    try:
        print(json.dumps(build(a.out), ensure_ascii=False, indent=1))
    except ReleaseError as exc:
        print(exc, file=sys.stderr)
        sys.exit(1)
