"""Herramienta del vendedor: claves y licencias de Open LVGL Studio.

    python tools/license_tool.py keygen [--out RUTA_CLAVE_PRIVADA] [--register]
    python tools/license_tool.py sign --key RUTA_CLAVE_PRIVADA --licensee "Empresa S.L." \\
           [--email x@y] [--edition pro|enterprise] [--seats 5] [--days 365] [--features a,b] --out licencia.olvgl-lic
    python tools/license_tool.py verify licencia.olvgl-lic

La clave privada se guarda por defecto en ~/.olvgl/licencias/clave_privada.txt
(fuera del proyecto). Guárdala bien: quien la tenga puede emitir licencias.
`--register` añade la clave pública a olvgl/resources/license_public_keys.txt.
"""
from __future__ import annotations

import argparse
import datetime as _dt
import os
import sys
import uuid

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from olvgl.application import licensing  # noqa: E402
from olvgl.domain import ed25519  # noqa: E402

DEFAULT_KEY = os.path.join(os.path.expanduser("~"), ".olvgl", "licencias", "clave_privada.txt")


def read_secret(path: str) -> bytes:
    with open(path, encoding="utf-8") as f:
        line = next(x.strip() for x in f if x.strip() and not x.startswith("#"))
    return bytes.fromhex(line)


def keygen(out: str, register: bool) -> str:
    if os.path.exists(out):
        raise SystemExit(f"Ya existe {out}: no se sobrescribe (bórrala a mano si de verdad quieres otra)")
    secret = ed25519.generate_secret()
    pub = ed25519.public_key(secret).hex()
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        f.write("# Clave privada Ed25519 de licencias de Open LVGL Studio. NO la compartas.\n" + secret.hex() + "\n")
    try:
        os.chmod(out, 0o600)
    except OSError:
        pass
    if register:
        with open(licensing._KEYS_FILE, "a", encoding="utf-8") as f:
            f.write(f"{pub}  # {_dt.date.today().isoformat()}\n")
    return pub


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    k = sub.add_parser("keygen")
    k.add_argument("--out", default=DEFAULT_KEY)
    k.add_argument("--register", action="store_true")
    s = sub.add_parser("sign")
    s.add_argument("--key", default=DEFAULT_KEY)
    s.add_argument("--licensee", required=True)
    s.add_argument("--email", default="")
    s.add_argument("--edition", default="pro", choices=["pro", "enterprise"])
    s.add_argument("--seats", type=int, default=1)
    s.add_argument("--days", type=int, default=365, help="0 = sin caducidad")
    s.add_argument("--features", default="")
    s.add_argument("--out", required=True)
    v = sub.add_parser("verify")
    v.add_argument("path")
    a = ap.parse_args(argv)
    if a.cmd == "keygen":
        pub = keygen(a.out, a.register)
        print(f"Clave privada: {a.out}\nClave pública: {pub}")
        if not a.register:
            print(f"Añádela a {licensing._KEYS_FILE} (o repite con --register).")
        return 0
    if a.cmd == "sign":
        today = _dt.date.today()
        lic = licensing.License(id=uuid.uuid4().hex[:16], licensee=a.licensee, email=a.email, edition=a.edition,
                                seats=a.seats, issued=today.isoformat(),
                                expires=(today + _dt.timedelta(days=a.days)).isoformat() if a.days else None,
                                features=[x.strip() for x in a.features.split(",") if x.strip()])
        licensing.sign_license(lic, read_secret(a.key))
        with open(a.out, "w", encoding="utf-8") as f:
            f.write(lic.to_json())
        st = licensing.check(lic)
        print(f"{a.out}: {st.message}" + ("" if st.state == "valid" else
                                          " (registra la clave pública para que la aplicación la acepte)"))
        return 0
    with open(a.path, encoding="utf-8") as f:
        st = licensing.check(licensing.License.from_json(f.read()))
    print(f"{st.state}: {st.message} · {st.name}")
    return 0 if st.state == "valid" else 1


if __name__ == "__main__":
    sys.exit(main())
