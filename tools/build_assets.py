"""Genera los recursos gráficos de olvgl/resources a partir de la ilustración
original (tools/artwork/olvgl_artwork.png) y de los SVG de tools/action_icons.py.

Uso:  python tools/build_assets.py
Requiere Pillow y, para los iconos del menú, Playwright con Chromium."""
from __future__ import annotations

import os
import shutil
import sys

from PIL import Image, ImageDraw, ImageFilter

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ART = os.path.join(ROOT, "tools", "artwork", "olvgl_artwork.png")
RES = os.path.join(ROOT, "olvgl", "resources")
sys.path.insert(0, os.path.join(ROOT, "tools"))

# Rejilla del «Set de iconos – Widgets de LVGL» (fila, columna) → tipo de LVGL
GRID = [["arc", "bar", "button", "buttonmatrix", "calendar", "canvas", "checkbox", "chart", "colorpicker", "dropdown"],
        ["image", "imagebutton", "keyboard", "label", "led", "line", "list", "menu", "meter", "msgbox"],
        ["roller", "slider", "spinbox", "switch", "table", "tabview", "tileview", "textarea", "timeline", "win"]]
ROW_Y = (754, 898, 1044)
COL_X0, COL_DX = 82, 120.5
TILE = (44, 48, 54, 255)
SS = 4


def alpha_bbox(im: Image.Image, box, thr=40):
    reg = im.getchannel("A").crop(box).point(lambda v: 255 if v > thr else 0)
    b = reg.getbbox()
    return (b[0] + box[0], b[1] + box[1], b[2] + box[0], b[3] + box[1])


def square(im: Image.Image) -> Image.Image:
    n = max(im.size)
    out = Image.new("RGBA", (n, n), (0, 0, 0, 0))
    out.paste(im, ((n - im.width) // 2, (n - im.height) // 2))
    return out


def tile_base(size=96) -> Image.Image:
    im = Image.new("RGBA", (size * SS, size * SS), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    box = (2 * SS, 2 * SS, (size - 2) * SS, (size - 2) * SS)
    d.rounded_rectangle(box, radius=18 * SS, fill=TILE)
    d.rounded_rectangle(box, radius=18 * SS, outline=(62, 67, 74, 255), width=SS)
    return im


def custom(name: str, draw) -> None:
    im = tile_base()
    draw(ImageDraw.Draw(im), SS)
    im.resize((96, 96), Image.LANCZOS).save(os.path.join(RES, "widgets", f"{name}.png"))


def draw_spinner(d, s):
    d.ellipse((24 * s, 24 * s, 72 * s, 72 * s), outline=(84, 90, 98, 255), width=8 * s)
    d.arc((24 * s, 24 * s, 72 * s, 72 * s), start=-90, end=40, fill=(33, 150, 243, 255), width=8 * s)


def draw_qr(d, s):
    import random
    random.seed(3)
    d.rounded_rectangle((18 * s, 18 * s, 78 * s, 78 * s), radius=6 * s, fill=(236, 239, 241, 255))
    for i in range(13):
        for j in range(13):
            if random.random() < 0.45:
                x, y = 22 + i * 4, 22 + j * 4
                d.rectangle((x * s, y * s, (x + 4) * s - 1, (y + 4) * s - 1), fill=(30, 33, 38, 255))
    for fx, fy in ((22, 22), (58, 22), (22, 58)):
        d.rectangle((fx * s, fy * s, (fx + 16) * s, (fy + 16) * s), fill=(236, 239, 241, 255))
        d.rectangle((fx * s, fy * s, (fx + 16) * s, (fy + 16) * s), outline=(30, 33, 38, 255), width=3 * s)
        d.rectangle(((fx + 5) * s, (fy + 5) * s, (fx + 11) * s, (fy + 11) * s), fill=(30, 33, 38, 255))


def draw_animimg(d, s):
    d.rounded_rectangle((18 * s, 24 * s, 70 * s, 66 * s), radius=5 * s, outline=(220, 224, 228, 255), width=4 * s)
    d.polygon([(24 * s, 60 * s), (38 * s, 42 * s), (50 * s, 56 * s), (58 * s, 48 * s), (66 * s, 60 * s)],
              fill=(220, 224, 228, 255))
    d.ellipse((26 * s, 30 * s, 34 * s, 38 * s), fill=(255, 183, 77, 255))
    d.ellipse((52 * s, 50 * s, 80 * s, 78 * s), fill=(33, 150, 243, 255))
    d.polygon([(62 * s, 57 * s), (62 * s, 71 * s), (73 * s, 64 * s)], fill=(255, 255, 255, 255))


def draw_obj(d, s):
    d.rounded_rectangle((20 * s, 22 * s, 76 * s, 74 * s), radius=8 * s, outline=(220, 224, 228, 255), width=4 * s)
    d.rounded_rectangle((30 * s, 32 * s, 52 * s, 50 * s), radius=4 * s, fill=(33, 150, 243, 255))
    d.rounded_rectangle((44 * s, 46 * s, 66 * s, 64 * s), radius=4 * s, fill=(76, 175, 80, 255))


def build_branding(src: Image.Image) -> None:
    icon = square(src.crop(alpha_bbox(src, (0, 0, 440, 385))))
    icon.resize((256, 256), Image.LANCZOS).save(os.path.join(RES, "app_icon.png"))
    icon.resize((256, 256), Image.LANCZOS).save(os.path.join(RES, "app_icon.ico"),
                                                sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64),
                                                       (128, 128), (256, 256)])
    logo = src.crop(alpha_bbox(src, (500, 100, 1254, 420)))
    logo.save(os.path.join(RES, "logo.png"))
    # Variante para fondos oscuros: «Open» y «Studio» (texto oscuro) pasan a claro
    light = logo.copy()
    px = light.load()
    x0 = int(light.width * 0.36)
    for y in range(light.height):
        for x in range(x0, light.width):
            r, g, b, a = px[x, y]
            if a and max(r, g, b) < 90 and abs(r - g) < 25 and abs(g - b) < 25:
                px[x, y] = (236, 239, 241, a)
    light.save(os.path.join(RES, "logo_light.png"))


def build_widgets(src: Image.Image) -> None:
    out = os.path.join(RES, "widgets")
    os.makedirs(out, exist_ok=True)
    mask = Image.new("L", (82, 82), 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, 81, 81), radius=14, fill=255)
    mask = mask.filter(ImageFilter.GaussianBlur(2))
    for r, cy in enumerate(ROW_Y):
        for c, name in enumerate(GRID[r]):
            cx = round(COL_X0 + COL_DX * c)
            inner = src.crop((cx - 41, cy - 41, cx + 41, cy + 41))
            base = tile_base().resize((96, 96), Image.LANCZOS)
            base.paste(inner, (7, 7), mask)
            base.save(os.path.join(out, f"{name}.png"))
    custom("spinner", draw_spinner)
    custom("qrcode", draw_qr)
    custom("animimg", draw_animimg)
    custom("obj", draw_obj)
    shutil.copy(os.path.join(out, "tabview.png"), os.path.join(out, "tab.png"))
    shutil.copy(os.path.join(out, "tileview.png"), os.path.join(out, "tile.png"))


def build_actions() -> None:
    from action_icons import ICONS
    from playwright.sync_api import sync_playwright
    out = os.path.join(RES, "actions")
    os.makedirs(out, exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 64, "height": 64})
        for name, svg in ICONS.items():
            with open(os.path.join(out, f"{name}.svg"), "w", encoding="utf-8") as f:
                f.write(svg)
            page.set_content('<html><body style="margin:0;background:transparent">'
                             + svg.replace("<svg ", '<svg width="64" height="64" ') + "</body></html>")
            page.screenshot(path=os.path.join(out, f"{name}.png"), omit_background=True,
                            clip={"x": 0, "y": 0, "width": 64, "height": 64})
        browser.close()


def main() -> None:
    os.makedirs(RES, exist_ok=True)
    src = Image.open(ART).convert("RGBA")
    build_branding(src)
    build_widgets(src)
    build_actions()
    print("Recursos generados en", RES)


if __name__ == "__main__":
    main()
