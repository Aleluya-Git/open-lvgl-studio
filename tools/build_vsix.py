"""Empaqueta vscode-extension/ como .vsix sin necesidad de Node ni de vsce.

Uso: python tools/build_vsix.py  →  vscode-extension/dist/open-lvgl-studio-<versión>.vsix
Instálalo con:  code --install-extension <fichero.vsix>
(o en VS Code: Extensiones › ⋯ › Instalar desde VSIX…)."""
from __future__ import annotations

import json
import os
import sys
import zipfile
from xml.sax.saxutils import escape

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EXT = os.path.join(ROOT, "vscode-extension")
SKIP_DIRS = {"dist", "test", "node_modules", ".vscode"}

CONTENT_TYPES = """<?xml version="1.0" encoding="utf-8"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
<Default Extension=".json" ContentType="application/json"/>
<Default Extension=".js" ContentType="application/javascript"/>
<Default Extension=".png" ContentType="image/png"/>
<Default Extension=".svg" ContentType="image/svg+xml"/>
<Default Extension=".md" ContentType="text/markdown"/>
<Default Extension=".txt" ContentType="text/plain"/>
<Default Extension=".vsixmanifest" ContentType="text/xml"/>
</Types>
"""


def manifest(pkg: dict) -> str:
    props = {
        "Microsoft.VisualStudio.Code.Engine": pkg["engines"]["vscode"],
        "Microsoft.VisualStudio.Code.ExtensionDependencies": "",
        "Microsoft.VisualStudio.Code.ExtensionPack": "",
        "Microsoft.VisualStudio.Code.ExtensionKind": "workspace",
        "Microsoft.VisualStudio.Code.LocalizedLanguages": "",
    }
    prop_xml = "\n".join(f'      <Property Id="{k}" Value="{escape(v)}" />' for k, v in props.items())
    return f"""<?xml version="1.0" encoding="utf-8"?>
<PackageManifest Version="2.0.0" xmlns="http://schemas.microsoft.com/developer/vsx-schema/2011" xmlns:d="http://schemas.microsoft.com/developer/vsx-schema-design/2011">
  <Metadata>
    <Identity Language="en-US" Id="{pkg['name']}" Version="{pkg['version']}" Publisher="{pkg['publisher']}" />
    <DisplayName>{escape(pkg['displayName'])}</DisplayName>
    <Description xml:space="preserve">{escape(pkg['description'])}</Description>
    <Tags>{escape(','.join(pkg.get('keywords', [])))}</Tags>
    <Categories>{escape(','.join(pkg.get('categories', [])))}</Categories>
    <GalleryFlags>Public</GalleryFlags>
    <Properties>
{prop_xml}
    </Properties>
    <License>extension/LICENSE.txt</License>
    <Icon>extension/{pkg['icon']}</Icon>
  </Metadata>
  <Installation>
    <InstallationTarget Id="Microsoft.VisualStudio.Code" />
  </Installation>
  <Dependencies />
  <Assets>
    <Asset Type="Microsoft.VisualStudio.Code.Manifest" Path="extension/package.json" Addressable="true" />
    <Asset Type="Microsoft.VisualStudio.Services.Content.Details" Path="extension/README.md" Addressable="true" />
    <Asset Type="Microsoft.VisualStudio.Services.Content.License" Path="extension/LICENSE.txt" Addressable="true" />
    <Asset Type="Microsoft.VisualStudio.Services.Icons.Default" Path="extension/{pkg['icon']}" Addressable="true" />
  </Assets>
</PackageManifest>
"""


def files() -> list[str]:
    out = []
    for base, dirs, names in os.walk(EXT):
        dirs[:] = sorted(d for d in dirs if d not in SKIP_DIRS)
        for n in sorted(names):
            out.append(os.path.relpath(os.path.join(base, n), EXT).replace(os.sep, "/"))
    return out


def build() -> str:
    with open(os.path.join(EXT, "package.json"), encoding="utf-8") as f:
        pkg = json.load(f)
    dist = os.path.join(EXT, "dist")
    os.makedirs(dist, exist_ok=True)
    target = os.path.join(dist, f"{pkg['name']}-{pkg['version']}.vsix")
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", CONTENT_TYPES)
        z.writestr("extension.vsixmanifest", manifest(pkg))
        for rel in files():
            z.write(os.path.join(EXT, rel), "extension/" + rel)
    return target


if __name__ == "__main__":
    path = build()
    print(path)
    sys.exit(0)
