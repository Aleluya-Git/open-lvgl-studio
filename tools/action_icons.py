"""Iconos de las acciones del menú (SVG 24×24 en color).

`tools/build_assets.py` los convierte en PNG para olvgl/resources/actions/."""

W = "#ECEFF1"   # trazo claro
G = "#90A4AE"   # gris
B = "#42A5F5"   # azul
GR = "#66BB6A"  # verde
R = "#EF5350"   # rojo
Y = "#FFCA28"   # amarillo
O = "#FFA726"   # naranja
P = "#AB47BC"   # morado
C = "#26C6DA"   # cian


def s(body: str) -> str:
    return ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" '
            'stroke-linecap="round" stroke-linejoin="round">' + body + "</svg>")


DOC = f'<path d="M6 2.5h8l4.5 4.5v14.5h-12.5z" fill="#37474F" stroke="{W}" stroke-width="1.5"/><path d="M14 2.5v4.5h4.5" stroke="{W}" stroke-width="1.5"/>'
FLOPPY = f'<path d="M3.5 3.5h13l4 4v13h-17z" fill="{B}"/><rect x="7" y="3.5" width="8" height="5" fill="#E3F2FD"/><rect x="6.5" y="13" width="11" height="7.5" rx="1" fill="#E3F2FD"/>'
TRAY = f'<path d="M3 14v5.5h18V14" stroke="{G}" stroke-width="2"/>'


def mag(extra: str) -> str:
    return s(f'<circle cx="10" cy="10" r="6.5" fill="#263238" stroke="{B}" stroke-width="2"/>'
             f'<path d="M15 15l6 6" stroke="{O}" stroke-width="3"/>' + extra)


def align(lines: str, guide: str) -> str:
    return s(lines + guide)


ICONS = {
    "new": s(DOC + f'<circle cx="17.5" cy="17.5" r="5" fill="{GR}"/><path d="M17.5 15v5M15 17.5h5" stroke="#fff" stroke-width="1.8"/>'),
    "open": s(f'<path d="M2.5 6.5a1.5 1.5 0 0 1 1.5-1.5h5l2 2h8a1.5 1.5 0 0 1 1.5 1.5v1H2.5z" fill="#F9A825"/>'
              f'<path d="M2.5 9.5h19l-2 10h-15z" fill="{Y}"/>'),
    "recent": s(f'<circle cx="12" cy="12" r="9" fill="#263238" stroke="{C}" stroke-width="2"/><path d="M12 7v5l3.5 2.5" stroke="{W}" stroke-width="2"/>'),
    "save": s(FLOPPY),
    "save_as": s(FLOPPY + f'<path d="M14 21l1-3.5 6-6 2.5 2.5-6 6z" fill="{O}" stroke="#263238" stroke-width="1"/>'),
    "import": s(TRAY + f'<path d="M12 3v11M7.5 9.5L12 14l4.5-4.5" stroke="{GR}" stroke-width="2.5"/>'),
    "export": s(TRAY + f'<path d="M12 14V3M7.5 7.5L12 3l4.5 4.5" stroke="{O}" stroke-width="2.5"/>'),
    "export_c": s(DOC + f'<circle cx="16.5" cy="16.5" r="6" fill="{P}"/><path d="M18.8 14.4a3 3 0 1 0 0 4.2" stroke="#fff" stroke-width="1.8"/>'),
    "link": s(f'<path d="M10 14a4 4 0 0 0 5.7 0l3-3a4 4 0 0 0-5.7-5.7l-1 1" stroke="{C}" stroke-width="2.2"/>'
              f'<path d="M14 10a4 4 0 0 0-5.7 0l-3 3a4 4 0 0 0 5.7 5.7l1-1" stroke="{C}" stroke-width="2.2"/>'),
    "unlink": s(f'<path d="M14.5 6.3l1-1a4 4 0 0 1 5.7 5.7l-1.5 1.5M9.5 17.7l-1 1a4 4 0 0 1-5.7-5.7l1.5-1.5" stroke="{G}" stroke-width="2.2"/>'
                f'<path d="M5 5l14 14" stroke="{R}" stroke-width="2.2"/>'),
    "sync": s(f'<path d="M20 11a8 8 0 0 0-14.5-4.5M4 13a8 8 0 0 0 14.5 4.5" stroke="{GR}" stroke-width="2.2"/>'
              f'<path d="M5 2.5v4.5h4.5M19 21.5V17h-4.5" stroke="{GR}" stroke-width="2.2"/>'),
    "autosync": s(f'<path d="M20 11a8 8 0 0 0-14.5-4.5M4 13a8 8 0 0 0 14.5 4.5" stroke="{C}" stroke-width="2.2"/>'
                  f'<path d="M5 2.5v4.5h4.5M19 21.5V17h-4.5" stroke="{C}" stroke-width="2.2"/><path d="M13 7l-3 5.5h4L11 17" stroke="{Y}" stroke-width="2"/>'),
    "quit": s(f'<path d="M7.5 6.5a8 8 0 1 0 9 0" stroke="{R}" stroke-width="2.5"/><path d="M12 3v8" stroke="{R}" stroke-width="2.5"/>'),
    "undo": s(f'<path d="M9 14L4 9l5-5" stroke="{B}" stroke-width="2.5"/><path d="M4 9h10a6 6 0 0 1 0 12h-3" stroke="{B}" stroke-width="2.5"/>'),
    "redo": s(f'<path d="M15 14l5-5-5-5" stroke="{B}" stroke-width="2.5"/><path d="M20 9H10a6 6 0 0 0 0 12h3" stroke="{B}" stroke-width="2.5"/>'),
    "cut": s(f'<circle cx="6.5" cy="17.5" r="3" stroke="{R}" stroke-width="2"/><circle cx="17.5" cy="17.5" r="3" stroke="{R}" stroke-width="2"/>'
             f'<path d="M8.5 15.5L18 3M15.5 15.5L6 3" stroke="{W}" stroke-width="2"/>'),
    "copy": s(f'<rect x="8.5" y="8.5" width="12" height="12" rx="2" fill="{B}"/><path d="M15.5 5.5v-1a1.5 1.5 0 0 0-1.5-1.5H5a1.5 1.5 0 0 0-1.5 1.5V14A1.5 1.5 0 0 0 5 15.5h1" stroke="{W}" stroke-width="1.8"/>'),
    "paste": s(f'<rect x="4" y="4" width="16" height="18" rx="2" fill="#8D6E63"/><rect x="8" y="2" width="8" height="4" rx="1" fill="{G}"/><rect x="7" y="9" width="10" height="10" rx="1" fill="{W}"/>'),
    "duplicate": s(f'<rect x="3" y="3" width="12" height="12" rx="2" stroke="{W}" stroke-width="1.8"/><rect x="9" y="9" width="12" height="12" rx="2" fill="{GR}"/>'
                   f'<path d="M15 12.5v5M12.5 15h5" stroke="#fff" stroke-width="1.8"/>'),
    "delete": s(f'<path d="M4 6.5h16M9.5 6.5V4h5v2.5" stroke="{W}" stroke-width="1.8"/><path d="M6 6.5l1 14h10l1-14z" fill="{R}"/><path d="M10 10v7M14 10v7" stroke="#fff" stroke-width="1.5"/>'),
    "select_all": s(f'<rect x="3" y="3" width="18" height="18" rx="2" stroke="{P}" stroke-width="2" stroke-dasharray="3 2.5"/><rect x="8" y="8" width="8" height="8" rx="1" fill="{P}"/>'),
    "styles": s(f'<path d="M12 3a9 9 0 1 0 0 18c1.5 0 2-1 1.5-2.2-.6-1.4.3-2.8 1.8-2.8H18a3 3 0 0 0 3-3c0-5.5-4-10-9-10z" fill="#ECEFF1"/>'
                f'<circle cx="7.5" cy="11" r="1.7" fill="{R}"/><circle cx="10" cy="7" r="1.7" fill="{Y}"/><circle cx="15" cy="7" r="1.7" fill="{GR}"/><circle cx="17.5" cy="11" r="1.7" fill="{B}"/>'),
    "align_left": align(f'<rect x="6" y="5" width="12" height="5" rx="1" fill="{B}"/><rect x="6" y="14" width="8" height="5" rx="1" fill="{O}"/>', f'<path d="M3.5 2.5v19" stroke="{W}" stroke-width="2"/>'),
    "align_hcenter": align(f'<rect x="5" y="5" width="14" height="5" rx="1" fill="{B}"/><rect x="7.5" y="14" width="9" height="5" rx="1" fill="{O}"/>', f'<path d="M12 2.5v19" stroke="{W}" stroke-width="2"/>'),
    "align_right": align(f'<rect x="6" y="5" width="12" height="5" rx="1" fill="{B}"/><rect x="10" y="14" width="8" height="5" rx="1" fill="{O}"/>', f'<path d="M20.5 2.5v19" stroke="{W}" stroke-width="2"/>'),
    "align_top": align(f'<rect x="5" y="6" width="5" height="12" rx="1" fill="{B}"/><rect x="14" y="6" width="5" height="8" rx="1" fill="{O}"/>', f'<path d="M2.5 3.5h19" stroke="{W}" stroke-width="2"/>'),
    "align_vcenter": align(f'<rect x="5" y="5" width="5" height="14" rx="1" fill="{B}"/><rect x="14" y="7.5" width="5" height="9" rx="1" fill="{O}"/>', f'<path d="M2.5 12h19" stroke="{W}" stroke-width="2"/>'),
    "align_bottom": align(f'<rect x="5" y="6" width="5" height="12" rx="1" fill="{B}"/><rect x="14" y="10" width="5" height="8" rx="1" fill="{O}"/>', f'<path d="M2.5 20.5h19" stroke="{W}" stroke-width="2"/>'),
    "dist_h": s(f'<path d="M3 3v18M21 3v18" stroke="{W}" stroke-width="2"/><rect x="9" y="6" width="6" height="12" rx="1" fill="{C}"/>'),
    "dist_v": s(f'<path d="M3 3h18M3 21h18" stroke="{W}" stroke-width="2"/><rect x="6" y="9" width="12" height="6" rx="1" fill="{C}"/>'),
    "front": s(f'<rect x="3" y="11" width="10" height="10" rx="1.5" stroke="{G}" stroke-width="1.8"/><rect x="9" y="3" width="12" height="12" rx="1.5" fill="{B}"/>'),
    "forward": s(f'<rect x="3" y="9" width="10" height="10" rx="1.5" stroke="{G}" stroke-width="1.8"/><rect x="9" y="5" width="11" height="11" rx="1.5" fill="{B}" opacity=".8"/>'),
    "backward": s(f'<rect x="9" y="5" width="11" height="11" rx="1.5" stroke="{G}" stroke-width="1.8"/><rect x="3" y="9" width="10" height="10" rx="1.5" fill="{O}" opacity=".8"/>'),
    "back": s(f'<rect x="9" y="3" width="12" height="12" rx="1.5" stroke="{G}" stroke-width="1.8"/><rect x="3" y="11" width="10" height="10" rx="1.5" fill="{O}"/>'),
    "zoom_in": mag(f'<path d="M10 7v6M7 10h6" stroke="{W}" stroke-width="2"/>'),
    "zoom_out": mag(f'<path d="M7 10h6" stroke="{W}" stroke-width="2"/>'),
    "zoom_fit": s(f'<path d="M3 8V3h5M16 3h5v5M21 16v5h-5M8 21H3v-5" stroke="{C}" stroke-width="2.2"/><rect x="8" y="8" width="8" height="8" rx="1" fill="{B}"/>'),
    "zoom_100": mag(f'<text x="10" y="12.8" font-size="7" font-family="Arial" font-weight="bold" fill="{W}" text-anchor="middle">1:1</text>'),
    "grid": s(f'<rect x="3" y="3" width="18" height="18" rx="2" stroke="{B}" stroke-width="1.8"/><path d="M9 3v18M15 3v18M3 9h18M3 15h18" stroke="{B}" stroke-width="1.2"/>'),
    "snap": s(f'<path d="M5 3.5v8a7 7 0 0 0 14 0v-8h-4.5v8a2.5 2.5 0 0 1-5 0v-8z" fill="{R}"/><path d="M5 3.5h4.5v3H5zM14.5 3.5H19v3h-4.5z" fill="{W}"/>'),
    "outlines": s(f'<rect x="3" y="5" width="18" height="14" rx="2" stroke="{O}" stroke-width="2" stroke-dasharray="3 2.5"/>'),
    "layers": s(f'<path d="M12 3l9 5-9 5-9-5z" fill="{P}"/><path d="M3 12l9 5 9-5M3 16l9 5 9-5" stroke="{W}" stroke-width="1.8"/>'),
    "layers_edit": s(f'<path d="M12 3l9 5-9 5-9-5z" fill="{P}"/><path d="M3 12l9 5 9-5" stroke="{W}" stroke-width="1.8"/>'
                     f'<path d="M14 22l1-3.5 5.5-5.5 2.5 2.5-5.5 5.5z" fill="{O}"/>'),
    "simulator": s(f'<circle cx="12" cy="12" r="10" fill="{GR}"/><path d="M9.5 7.5v9l7-4.5z" fill="#fff"/>'),
    "about": s(f'<circle cx="12" cy="12" r="10" fill="{B}"/><path d="M12 11v6" stroke="#fff" stroke-width="2.5"/><circle cx="12" cy="7.3" r="1.5" fill="#fff"/>'),
    "language": s(f'<circle cx="12" cy="12" r="9.5" fill="#1565C0"/><path d="M2.5 12h19M12 2.5c3 3.2 3 15.8 0 19M12 2.5c-3 3.2-3 15.8 0 19" stroke="#E3F2FD" stroke-width="1.5"/>'
                  f'<path d="M5 6.5c2 1.5 12 1.5 14 0M5 17.5c2-1.5 12-1.5 14 0" stroke="{GR}" stroke-width="1.5"/>'),
    "add_page": s(f'<rect x="3" y="4" width="15" height="12" rx="1.5" fill="#37474F" stroke="{W}" stroke-width="1.5"/>'
                  f'<circle cx="17.5" cy="17.5" r="5" fill="{GR}"/><path d="M17.5 15v5M15 17.5h5" stroke="#fff" stroke-width="1.8"/>'),
    "page": s(f'<rect x="3" y="5" width="18" height="14" rx="2" fill="#37474F" stroke="{B}" stroke-width="1.8"/><rect x="6" y="8" width="5" height="4" rx="1" fill="{R}"/><rect x="6" y="13" width="5" height="3" rx="1" fill="{GR}"/><rect x="13" y="8" width="5" height="8" rx="1" fill="{B}"/>'),
    "move_up": s(f'<path d="M12 20V5M6 11l6-6 6 6" stroke="{C}" stroke-width="2.5"/>'),
    "move_down": s(f'<path d="M12 4v15M6 13l6 6 6-6" stroke="{C}" stroke-width="2.5"/>'),
    "remove_page": s(f'<rect x="3" y="4" width="15" height="12" rx="1.5" fill="#37474F" stroke="{W}" stroke-width="1.5"/>'
                     f'<circle cx="17.5" cy="17.5" r="5" fill="{R}"/><path d="M15 17.5h5" stroke="#fff" stroke-width="1.8"/>'),
    "plugin": s(f'<path d="M4 8h4a2.5 2.5 0 1 1 5 0h4v4a2.5 2.5 0 1 1 0 5v4h-4a2.5 2.5 0 1 0-5 0H4v-4a2.5 2.5 0 1 0 0-5z" fill="{P}"/>'
                f'<path d="M4 8h4a2.5 2.5 0 1 1 5 0h4v4" stroke="#E1BEE7" stroke-width="1.2" fill="none"/>'),
    "check": s(f'<circle cx="12" cy="12" r="10" fill="{GR}"/><path d="M7 12.5l3.2 3.2L17 9" stroke="#fff" stroke-width="2.6"/>'),
    "insert": s(f'<rect x="3" y="3" width="8" height="8" rx="1.5" fill="{R}"/><rect x="3" y="13" width="8" height="8" rx="1.5" fill="{GR}"/>'
                f'<rect x="13" y="8" width="8" height="13" rx="1.5" fill="{B}"/>'),
    "panels": s(f'<rect x="3" y="4" width="18" height="16" rx="2" stroke="{W}" stroke-width="1.8"/><rect x="3" y="4" width="6" height="16" fill="{B}" opacity=".8"/><rect x="16" y="4" width="5" height="16" fill="{O}" opacity=".8"/>'),
    "ai": s(f'<path d="M10 2.5l1.8 5.2 5.2 1.8-5.2 1.8L10 16.5l-1.8-5.2L3 9.5l5.2-1.8z" fill="{P}"/>'
            f'<path d="M18 13l.9 2.6 2.6.9-2.6.9L18 20l-.9-2.6-2.6-.9 2.6-.9z" fill="{Y}"/>'
            f'<circle cx="18.5" cy="4.5" r="1.6" fill="{C}"/>'),
    "refactor": s(f'<rect x="2.5" y="4" width="11" height="13" rx="1.5" fill="#37474F" stroke="{W}" stroke-width="1.4"/>'
                  f'<path d="M5 8h6M5 11h4M5 14h5" stroke="{B}" stroke-width="1.6"/>'
                  f'<path d="M16 9l1.2 3.3 3.3 1.2-3.3 1.2L16 18l-1.2-3.3-3.3-1.2 3.3-1.2z" fill="{P}"/>'),
    "rename": s(f'<rect x="2.5" y="7" width="15" height="10" rx="1.5" fill="#37474F" stroke="{W}" stroke-width="1.4"/>'
                f'<path d="M5.5 12h6" stroke="{GR}" stroke-width="2"/><path d="M19.5 4v16M17.5 4h4M17.5 20h4" stroke="{O}" stroke-width="1.8"/>'),
    "settings": s(f'<circle cx="12" cy="12" r="7" fill="{G}"/>'
                  f'<path d="M12 2.5v3M12 18.5v3M2.5 12h3M18.5 12h3M5.3 5.3l2.1 2.1M16.6 16.6l2.1 2.1M5.3 18.7l2.1-2.1M16.6 7.4l2.1-2.1" stroke="{G}" stroke-width="3"/>'
                  f'<circle cx="12" cy="12" r="3" fill="#263238"/>'),
    "guide": s(f'<path d="M3 5.5c3-1.5 6-1.5 9 .5v14c-3-2-6-2-9-.5z" fill="{B}"/><path d="M21 5.5c-3-1.5-6-1.5-9 .5v14c3-2 6-2 9-.5z" fill="#90CAF9"/>'
               f'<path d="M12 6v14" stroke="#263238" stroke-width="1.2"/>'),
    "news": s(f'<path d="M12 2.5l2.6 5.4 5.9.8-4.3 4.1 1 5.9L12 15.9l-5.2 2.8 1-5.9-4.3-4.1 5.9-.8z" fill="{Y}"/>'
              f'<circle cx="12" cy="11" r="2" fill="{O}"/>'),
    "bug": s(f'<ellipse cx="12" cy="14" rx="5.5" ry="6.5" fill="{R}"/><circle cx="12" cy="6.5" r="3" fill="#B71C1C"/>'
             f'<path d="M12 8.5v12M6.5 11H3M21 11h-3.5M6.5 15.5H3M21 15.5h-3.5M7 19.5l-2.5 2M17 19.5l2.5 2M9.5 4.5L8 2.5M14.5 4.5L16 2.5" stroke="{W}" stroke-width="1.5"/>'),
    "history": s(f'<circle cx="12" cy="12" r="9" fill="#263238" stroke="{P}" stroke-width="2"/>'
                 f'<path d="M12 7v5l3.5 2.5" stroke="{W}" stroke-width="2"/><path d="M3 5v4h4" stroke="{P}" stroke-width="2"/>'),
    "version_save": s(f'<path d="M6 3h9l3 3v15H6z" fill="{P}"/><path d="M9 3v5h6V3" fill="#E1BEE7"/>'
                      f'<circle cx="17.5" cy="17.5" r="5" fill="{GR}"/><path d="M17.5 15v5M15 17.5h5" stroke="#fff" stroke-width="1.8"/>'),
    "comment": s(f'<path d="M3 5.5A2.5 2.5 0 0 1 5.5 3h13A2.5 2.5 0 0 1 21 5.5v9a2.5 2.5 0 0 1-2.5 2.5H10l-5 4v-4h0A2 2 0 0 1 3 15z" fill="{Y}"/>'
                 f'<path d="M7 8h10M7 12h7" stroke="#5D4037" stroke-width="1.8"/>'),
    "component": s(f'<rect x="3" y="3" width="8" height="8" rx="2" fill="{C}"/><rect x="13" y="3" width="8" height="8" rx="2" fill="{B}"/>'
                   f'<rect x="3" y="13" width="8" height="8" rx="2" fill="{B}"/><rect x="13" y="13" width="8" height="8" rx="2" fill="{O}"/>'),
    "component_save": s(f'<rect x="3" y="3" width="8" height="8" rx="2" fill="{C}"/><rect x="13" y="3" width="8" height="8" rx="2" fill="{B}"/>'
                        f'<rect x="3" y="13" width="8" height="8" rx="2" fill="{B}"/>'
                        f'<circle cx="17.5" cy="17.5" r="5" fill="{GR}"/><path d="M17.5 15v5M15 17.5h5" stroke="#fff" stroke-width="1.8"/>'),
    "license": s(f'<rect x="3" y="5" width="18" height="13" rx="2" fill="#37474F" stroke="{W}" stroke-width="1.4"/>'
                 f'<path d="M6 9h8M6 12h6" stroke="{G}" stroke-width="1.6"/><circle cx="17" cy="14" r="3" fill="{Y}"/>'
                 f'<path d="M15.5 16.5l-1 4.5 2.5-1.5 2.5 1.5-1-4.5" fill="{O}"/>'),
    "fonts": s(f'<rect x="2.5" y="3.5" width="19" height="17" rx="2.5" fill="#263238" stroke="{G}" stroke-width="1.2"/>'
               f'<path d="M5 17.5L9 6.5l4 11M6.4 13.6h5.2" stroke="{B}" stroke-width="2"/>'
               f'<circle cx="16.8" cy="14.6" r="2.6" stroke="{O}" stroke-width="1.8"/><path d="M19.4 11.5v6" stroke="{O}" stroke-width="1.8"/>'),
    "icons": s(f'<rect x="2.5" y="2.5" width="19" height="19" rx="4" fill="#263238" stroke="{G}" stroke-width="1.2"/>'
               f'<path d="M12 5.5l1.9 4 4.4.5-3.3 3 .9 4.4L12 15.2 8.1 17.4l.9-4.4-3.3-3 4.4-.5z" fill="{Y}" stroke="{O}" stroke-width="1"/>'),
}
