"""Genera rsrc_windows_amd64.syso: icono y manifiesto del instalador (.exe de Windows).

El manifiesto pide «asInvoker»: sin él Windows trataría un programa llamado
«…Setup.exe» como instalador y pediría permisos de administrador, que no hacen
falta (se instala para el usuario actual). Es un objeto COFF con una sección
.rsrc que el enlazador de Go incorpora al .exe.

    python make_syso.py <icono.ico> <salida.syso> <versión>
"""
from __future__ import annotations

import struct
import sys

RT_ICON, RT_GROUP_ICON, RT_MANIFEST = 3, 14, 24
LANG = 0x0409

MANIFEST = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<assembly xmlns="urn:schemas-microsoft-com:asm.v1" manifestVersion="1.0">
  <assemblyIdentity type="win32" name="OpenLVGLStudio.Setup" version="{v}" processorArchitecture="amd64"/>
  <description>Instalador de Open LVGL Studio</description>
  <trustInfo xmlns="urn:schemas-microsoft-com:asm.v3">
    <security><requestedPrivileges>
      <requestedExecutionLevel level="asInvoker" uiAccess="false"/>
    </requestedPrivileges></security>
  </trustInfo>
  <compatibility xmlns="urn:schemas-microsoft-com:compatibility.v1"><application>
    <supportedOS Id="{{8e0f7a12-bfb3-4fe8-b9a5-48fd50a15a9a}}"/>
  </application></compatibility>
  <application xmlns="urn:schemas-microsoft-com:asm.v3"><windowsSettings>
    <activeCodePage xmlns="http://schemas.microsoft.com/SMI/2019/WindowsSettings">UTF-8</activeCodePage>
  </windowsSettings></application>
</assembly>
"""


def manifest_version(v: str) -> str:
    nums = [int(x) for x in __import__("re").findall(r"\d+", v)][:4]
    return ".".join(str(n) for n in (nums + [0, 0, 0, 0])[:4])


def read_ico(path: str) -> list[tuple[bytes, bytes]]:
    """[(cabecera de 12 bytes del GRPICONDIRENTRY sin el id, imagen)]"""
    data = open(path, "rb").read()
    _r, typ, n = struct.unpack("<HHH", data[:6])
    if typ != 1:
        raise ValueError("no es un .ico")
    out = []
    for i in range(n):
        w, h, colors, res, planes, bits, size, off = struct.unpack("<BBBBHHII", data[6 + 16 * i:22 + 16 * i])
        out.append((struct.pack("<BBBBHHI", w, h, colors, res, planes or 1, bits, size), data[off:off + size]))
    return out


def build(ico: str, version: str) -> bytes:
    icons = read_ico(ico)
    group = struct.pack("<HHH", 0, 1, len(icons)) + b"".join(h + struct.pack("<H", i + 1)
                                                              for i, (h, _img) in enumerate(icons))
    manifest = MANIFEST.format(v=manifest_version(version)).encode("utf-8")
    # tipo → [(id, datos)]  (ordenados por id, como exige el formato)
    tree = [(RT_ICON, [(i + 1, img) for i, (_h, img) in enumerate(icons)]),
            (RT_GROUP_ICON, [(1, group)]),
            (RT_MANIFEST, [(1, manifest)])]

    def dir_size(n: int) -> int:
        return 16 + 8 * n
    # 1) directorios: raíz, uno por tipo, uno de idioma por recurso
    off = dir_size(len(tree))
    type_dirs = []
    for _t, items in tree:
        type_dirs.append(off)
        off += dir_size(len(items))
    lang_dirs = []
    for _t, items in tree:
        row = []
        for _ in items:
            row.append(off)
            off += dir_size(1)
        lang_dirs.append(row)
    # 2) entradas de datos (16 bytes)
    entries = []
    for _t, items in tree:
        row = []
        for _ in items:
            row.append(off)
            off += 16
        entries.append(row)
    # 3) los datos, alineados a 8
    blobs = []
    for _t, items in tree:
        row = []
        for _id, data in items:
            off = (off + 7) & ~7
            row.append(off)
            off += len(data)
        blobs.append(row)
    size = (off + 7) & ~7
    sec = bytearray(size)

    def put_dir(at: int, ents: list[tuple[int, int]]) -> None:
        struct.pack_into("<IIHHHH", sec, at, 0, 0, 0, 0, 0, len(ents))
        for k, (ident, target) in enumerate(ents):
            struct.pack_into("<II", sec, at + 16 + 8 * k, ident, target)
    SUB = 0x80000000
    put_dir(0, [(t, type_dirs[k] | SUB) for k, (t, _i) in enumerate(tree)])
    relocs = []
    for k, (_t, items) in enumerate(tree):
        put_dir(type_dirs[k], [(ident, lang_dirs[k][j] | SUB) for j, (ident, _d) in enumerate(items)])
        for j, (_ident, data) in enumerate(items):
            put_dir(lang_dirs[k][j], [(LANG, entries[k][j])])
            struct.pack_into("<IIII", sec, entries[k][j], blobs[k][j], len(data), 0, 0)
            relocs.append(entries[k][j])           # OffsetToData es una RVA: el enlazador la ajusta
            sec[blobs[k][j]:blobs[k][j] + len(data)] = data
    # objeto COFF: cabecera, sección, datos, reubicaciones, tabla de símbolos
    raw_ptr = 20 + 40
    reloc_ptr = raw_ptr + size
    sym_ptr = reloc_ptr + 10 * len(relocs)
    out = bytearray()
    out += struct.pack("<HHIIIHH", 0x8664, 1, 0, sym_ptr, 1, 0, 0)
    out += struct.pack("<8sIIIIIIHHI", b".rsrc", 0, 0, size, raw_ptr, reloc_ptr, 0, len(relocs), 0, 0x40000040)
    out += sec
    for r in relocs:
        out += struct.pack("<IIH", r, 0, 3)        # IMAGE_REL_AMD64_ADDR32NB respecto al símbolo .rsrc
    out += struct.pack("<8sIhHBB", b".rsrc", 0, 1, 0, 3, 0)
    out += struct.pack("<I", 4)                    # tabla de cadenas vacía
    return bytes(out)


if __name__ == "__main__":
    ico, dest, version = sys.argv[1:4]
    with open(dest, "wb") as f:
        f.write(build(ico, version))
