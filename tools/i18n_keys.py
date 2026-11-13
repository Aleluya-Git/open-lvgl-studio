"""Lista todos los textos traducibles (para mantener olvgl/i18n/*.json).

Uso: python tools/i18n_keys.py  → imprime los textos que faltan en cada idioma."""
from __future__ import annotations

import ast
import glob
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)


def keys() -> list[str]:
    out: list[str] = []
    for f in sorted(glob.glob(os.path.join(ROOT, "olvgl", "**", "*.py"), recursive=True)):
        tree = ast.parse(open(f, encoding="utf-8").read())
        for n in ast.walk(tree):
            if isinstance(n, ast.Call) and getattr(n.func, "id", "") in ("tr", "trf") and n.args:
                a = n.args[0]
                if isinstance(a, ast.Constant) and isinstance(a.value, str):
                    out.append(a.value)
    from olvgl.domain import catalog
    from olvgl.i18n.extra import EXTRA
    out += list(catalog.CATEGORIES)
    for sp in catalog.ALL_SPECS:
        out += [sp.label, sp.description]
        for p in sp.props:
            out += [p.label, p.group]
    out += list(catalog.EVENT_LABELS.values()) + list(catalog.ACTION_KINDS.values())
    out += list(catalog.STATE_LABELS.values()) + list(catalog.PART_LABELS.values())
    out += list(catalog.WIDGET_STATE_OPS.values()) + list(EXTRA)
    seen, res = set(), []
    for k in out:
        if k and k not in seen:
            seen.add(k)
            res.append(k)
    return res


if __name__ == "__main__":
    ks = keys()
    print(len(ks), "textos")
    for code in ("en", "fr", "de"):
        path = os.path.join(ROOT, "olvgl", "i18n", f"{code}.json")
        table = json.load(open(path, encoding="utf-8")) if os.path.exists(path) else {}
        missing = [k for k in ks if k not in table]
        print(code, "faltan", len(missing))
        if "--dump" in sys.argv:
            print(json.dumps(missing, ensure_ascii=False, indent=0))
