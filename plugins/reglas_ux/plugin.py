"""Reglas de usabilidad: ejemplo de validador y de orden del SDK de plugins."""

TOUCH_TYPES = {"button", "switch", "checkbox", "slider", "arc", "dropdown", "roller", "spinbox"}
MIN_TOUCH = 40       # px: por debajo cuesta acertar con el dedo
TARGET = 48
MIN_CONTRAST = 3.0   # WCAG para texto grande; el pequeño pide 4,5


def _lum(hex_color):
    h = hex_color.lstrip("#")
    if len(h) != 6:
        return None
    try:
        rgb = [int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)]
    except ValueError:
        return None
    lin = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in rgb]
    return 0.2126 * lin[0] + 0.7152 * lin[1] + 0.0722 * lin[2]


def contrast(a, b):
    la, lb = _lum(a), _lum(b)
    if la is None or lb is None:
        return None
    hi, lo = max(la, lb), min(la, lb)
    return (hi + 0.05) / (lo + 0.05)


def _small(w):
    out = []
    for dim in ("width", "height"):
        v = getattr(w, dim)
        if isinstance(v, int) and not isinstance(v, bool) and v < MIN_TOUCH and not (w.type == "slider" and dim == "height"):
            out.append((dim, v))
    return out


def register(ctx):
    def check(project):
        issues = []
        for s in project.all_screens():
            def walk(ws, bg):
                for w in ws:
                    own_bg = w.props.get("bg_color") if isinstance(w.props.get("bg_color"), str) else bg
                    if w.type in TOUCH_TYPES:
                        for dim, v in _small(w):
                            issues.append(ctx.Issue(f"{w.id}: {'ancho' if dim == 'width' else 'alto'} de {v} px; "
                                                    f"los elementos táctiles deberían medir al menos {MIN_TOUCH} px",
                                                    "warning", w.id, s.id))
                    tc = w.props.get("text_color")
                    if w.type == "label" and isinstance(tc, str) and isinstance(bg, str):
                        c = contrast(tc, own_bg if w.props.get("bg_opa") not in (None, "TRANSP") else bg)
                        if c is not None and c < MIN_CONTRAST:
                            issues.append(ctx.Issue(f"{w.id}: contraste del texto {c:.1f}:1 (mínimo {MIN_CONTRAST}:1)",
                                                    "warning", w.id, s.id))
                    if w.type == "image" and not w.props.get("src"):
                        issues.append(ctx.Issue(f"{w.id}: imagen sin origen (no compila en ESPHome)", "error", w.id, s.id))
                    walk(w.children, own_bg)
            walk(s.widgets, s.bg_color or "#FFFFFF")
        return issues

    def enlarge(c):
        n = 0
        for _s, w in list(c.project.iter_widgets()):
            if w.type in TOUCH_TYPES:
                for dim, _v in _small(w):
                    c.vm.set_geom_value(w.id, dim, str(TARGET))
                    n += 1
        c.log(f"{n} medida(s) ampliadas a {TARGET} px (Ctrl+Z para deshacer)")

    ctx.register_validator(check)
    ctx.register_command("agrandar", "Agrandar elementos táctiles pequeños (48 px)", enlarge,
                         f"Pone a {TARGET} px el ancho o alto de botones, interruptores… menores de {MIN_TOUCH} px")
