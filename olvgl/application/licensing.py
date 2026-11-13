"""Licencias comerciales (Fase 10).

Una licencia es un fichero JSON firmado con Ed25519 por quien vende la
aplicación. La aplicación sólo lleva las **claves públicas** (no se puede
crear una licencia con ellas); la clave privada la genera y guarda el
vendedor con `tools/license_tool.py`.

    {"id": "...", "licensee": "Empresa S.L.", "email": "...", "edition": "pro",
     "seats": 5, "issued": "2026-11-11", "expires": "2027-11-11" | null,
     "features": [], "signature": "<base64>"}

Ediciones (licencia doble: GPL-3.0-or-later o comercial, ver LICENSING.md):
- Community: el diseñador completo (lienzo, todos los widgets, simulador,
  exportar ESPHome y C, plugins, versiones, colaboración, componentes).
- Pro: además, importar y sincronizar YAML de ESPHome y la extensión de VS Code.
- Enterprise: además, las herramientas de IA.

`has(feature)` dice si una función está disponible. `OLVGL_LICENSE_ENFORCE=0`
desactiva las comprobaciones (desarrollo y pruebas); `OLVGL_LICENSE=ruta` usa
un fichero de licencia compartido (p. ej. en la red de la empresa).
"""
from __future__ import annotations

import base64
import datetime as _dt
import json
import os
import shutil
from dataclasses import dataclass, field

from olvgl.domain import ed25519

ENFORCE = os.environ.get("OLVGL_LICENSE_ENFORCE", "1") != "0"
EDITIONS = ("community", "pro", "enterprise")
EDITION_NAMES = {"community": "Community", "pro": "Pro", "enterprise": "Enterprise"}
# función → edición mínima
FEATURES = {
    "importar_yaml": "pro",
    "vscode": "pro",
    "ia": "enterprise",
}
FEATURE_NAMES = {
    "importar_yaml": "Importar y sincronizar YAML de ESPHome",
    "vscode": "Extensión de VS Code (vista previa, Live Sync, diagnósticos)",
    "ia": "Herramientas de IA (generar, refactorizar, estilos e ids)",
}
LICENSE_FILE = "licencia.olvgl-lic"
_KEYS_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "resources",
                          "license_public_keys.txt")
EXTRA_PUBLIC_KEYS: list[bytes] = []   # las pruebas añaden aquí claves temporales


class LicenseError(Exception):
    pass


@dataclass
class License:
    id: str
    licensee: str
    email: str = ""
    edition: str = "pro"
    seats: int = 1
    issued: str = ""
    expires: str | None = None
    features: list[str] = field(default_factory=list)
    signature: str = ""

    def payload(self) -> bytes:
        d = {k: v for k, v in self.__dict__.items() if k != "signature"}
        return json.dumps(d, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")

    def to_json(self) -> str:
        return json.dumps(self.__dict__, ensure_ascii=False, indent=1)

    @classmethod
    def from_json(cls, text: str) -> "License":
        try:
            d = json.loads(text)
            return cls(id=str(d["id"]), licensee=str(d["licensee"]), email=str(d.get("email", "")),
                       edition=str(d.get("edition", "pro")), seats=int(d.get("seats", 1)),
                       issued=str(d.get("issued", "")), expires=d.get("expires"),
                       features=[str(x) for x in d.get("features", [])], signature=str(d.get("signature", "")))
        except (ValueError, KeyError, TypeError) as exc:
            raise LicenseError(f"El fichero no es una licencia: {exc}") from exc

    def expired(self, today: _dt.date | None = None) -> bool:
        if not self.expires:
            return False
        try:
            return (today or _dt.date.today()) > _dt.date.fromisoformat(self.expires)
        except ValueError:
            return True


@dataclass
class LicenseStatus:
    edition: str                      # community | pro | enterprise
    license: License | None = None
    state: str = "none"               # none | valid | expired | invalid
    message: str = ""

    @property
    def name(self) -> str:
        return EDITION_NAMES.get(self.edition, self.edition)


def public_keys() -> list[bytes]:
    keys = list(EXTRA_PUBLIC_KEYS)
    try:
        with open(_KEYS_FILE, encoding="utf-8") as f:
            for line in f:
                line = line.split("#", 1)[0].strip()
                if len(line) == 64:
                    keys.append(bytes.fromhex(line))
    except (OSError, ValueError):
        pass
    return keys


def sign_license(lic: License, secret: bytes) -> License:
    lic.signature = base64.b64encode(ed25519.sign(secret, lic.payload())).decode("ascii")
    return lic


def check(lic: License, today: _dt.date | None = None) -> LicenseStatus:
    try:
        sig = base64.b64decode(lic.signature, validate=True)
    except ValueError:
        return LicenseStatus("community", lic, "invalid", "Firma ilegible")
    if lic.edition not in EDITIONS:
        return LicenseStatus("community", lic, "invalid", f"Edición desconocida: {lic.edition}")
    if not any(ed25519.verify(k, lic.payload(), sig) for k in public_keys()):
        return LicenseStatus("community", lic, "invalid",
                             "La firma no corresponde a ninguna clave de esta aplicación (licencia manipulada o de "
                             "otro vendedor)")
    if lic.expired(today):
        return LicenseStatus("community", lic, "expired", f"Caducó el {lic.expires}")
    return LicenseStatus(lic.edition, lic, "valid", "Licencia válida")


# --------------------------------------------------------------------------- licencia instalada
def local_license_path() -> str:
    from olvgl.infrastructure.settings_db import app_data_dir
    return os.path.join(app_data_dir(), LICENSE_FILE)


def license_path() -> str:
    """La licencia instalada en este equipo o, si no hay, la compartida de OLVGL_LICENSE."""
    local = local_license_path()
    shared = os.environ.get("OLVGL_LICENSE")
    if not os.path.exists(local) and shared and os.path.exists(shared):
        return shared
    return local


def current() -> LicenseStatus:
    path = license_path()
    if not os.path.exists(path):
        return LicenseStatus("community", None, "none", "Sin licencia: edición Community")
    try:
        with open(path, encoding="utf-8") as f:
            return check(License.from_json(f.read()))
    except (OSError, LicenseError) as exc:
        return LicenseStatus("community", None, "invalid", str(exc))


def install(path: str) -> LicenseStatus:
    with open(path, encoding="utf-8") as f:
        lic = License.from_json(f.read())
    st = check(lic)
    if st.state != "valid":
        raise LicenseError(st.message)
    os.makedirs(os.path.dirname(local_license_path()), exist_ok=True)
    if os.path.abspath(path) != os.path.abspath(local_license_path()):
        shutil.copyfile(path, local_license_path())
    return st


def remove() -> None:
    try:
        os.remove(local_license_path())
    except OSError:
        pass


def required_message(feature: str) -> str:
    need = EDITION_NAMES[FEATURES[feature]]
    return (f"«{FEATURE_NAMES.get(feature, feature)}» requiere la edición {need} de Open LVGL Studio. "
            "Carga tu licencia en Ayuda › Licencia.")


def has(feature: str, status: LicenseStatus | None = None) -> bool:
    """¿Está disponible la función? Con ENFORCE = False (OLVGL_LICENSE_ENFORCE=0), siempre."""
    if not ENFORCE:
        return True
    need = FEATURES.get(feature)
    if need is None:
        return True
    st = status or current()
    if feature in (st.license.features if st.license and st.state == "valid" else []):
        return True
    return EDITIONS.index(st.edition) >= EDITIONS.index(need)
