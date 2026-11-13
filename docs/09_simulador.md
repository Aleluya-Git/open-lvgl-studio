# Fase 6 — Simulador profesional

## Pantalla táctil

El motor (`olvgl/application/simulation.py`, sin Qt) reproduce cómo LVGL interpreta el dedo.

| Gesto | Comportamiento | Triggers de ESPHome |
|---|---|---|
| Pulsar y soltar | clic, clic corto, conmutar, valores | `on_press`, `on_release`, `on_click`, `on_short_click`, `on_value` |
| Mantener 400 ms | pulsación larga y, cada 100 ms, repetición | `on_long_press`, `on_long_press_repeat` |
| Dos clics en < 0,4 s | doble clic | `on_double_click` |
| Arrastrar ≥ 10 px (`scroll_limit`) | desplaza el contenedor más interno que se pueda desplazar en ese eje, o la página. Si el dedo empezó en un botón, se pierde la pulsación y **no hay clic**, como en el equipo | `on_press_lost`, `on_scroll_begin`, `on_scroll`, `on_scroll_end` |
| Deslizar ≥ 50 px (`gesture_limit`) sin desplazar nada | gesto en el widget y sus antecesores | `on_gesture`, `on_swipe_left/right/up/down` (también `top`/`bottom`) |
| Deslizar en un **tileview** | pasa al mosaico vecino según `row`/`column`, respetando el `dir` de cada mosaico | `on_value` del tileview |
| Deslizar en un **tabview** | pestaña siguiente o anterior | `on_value` |
| Rueda del ratón | desplaza el contenedor bajo el cursor | — |

El simulador también tiene en cuenta:

- `scrollable: false` y `scroll_dir` de páginas y contenedores;
- `skip` de las páginas y `page_wrap` de `lvgl:` al usar `lvgl.page.next` y `lvgl.page.previous`;
- `on_load` y `on_unload` de las páginas, que se muestran en el registro;
- `on_idle`: cuando vence el `timeout`, la pantalla se oscurece con el aviso «Reposo» y el registro
  muestra sus acciones. Al tocar, se despierta.

En el C generado (Fase 4), los `on_swipe_*` se traducen a `LV_EVENT_GESTURE` filtrando con
`lv_indev_get_gesture_dir()`. `on_double_click` y `on_press_lost` se traducen a sus eventos de LVGL.

## Varios dispositivos y rotación

- **Añadir dispositivo** muestra el mismo proyecto en otra pantalla (las placas predefinidas o la del
  proyecto), cada una con su propio estado.
- **Navegación sincronizada** hace que al cambiar de página en una pantalla cambien las demás.
- Cada dispositivo se puede girar 0/90/180/270°. La disposición se recalcula con la resolución
  girada, igual que con `rotation:` en `lvgl:`. Al pasar de horizontal a vertical se registran
  `on_landscape` y `on_portrait`.
- Cada dispositivo tiene un botón de captura a resolución real.
- **Grabar** guarda los toques con sus tiempos y **Reproducir** los repite. Sirve para repetir una
  prueba tras cambiar el diseño.

## Rendimiento

La pestaña **Rendimiento** del simulador tiene dos partes.

**En directo, por dispositivo:**

- tiempo medio y máximo de dibujo;
- FPS posibles en este PC;
- tiempo de disposición;
- objetos visibles y eventos disparados.

**Estimación en el dispositivo** (`olvgl/domain/resources.py`, también con
`python -m olvgl.cli profile panel.yaml`):

| Concepto | Cálculo (ESP32, LVGL 9, 32 bits) |
|---|---|
| RAM de objetos | 96 B por objeto + extra por tipo (etiqueta 48 B + texto, teclado 1,5 KB…) + 12 B por propiedad de estilo local + 8 B por estilo aplicado + 24 B por evento; un lienzo suma su búfer (ancho×alto×2) |
| Búfer de dibujo | ancho × alto × `color_depth`/8 × `buffer_size` |
| Imágenes (flash) | ancho × alto × bytes/píxel según `type` (+1 con `alpha_channel`) |
| Fuentes (flash) | glifos × (tamaño² × 0,55 × bpp/8 + 16 B); `bpp` 1 por defecto en ESPHome; Montserrat integradas a 4 bpp |

Se avisa si:

- una página tiene más de 250 objetos o más de 8 niveles de anidamiento;
- la RAM estimada supera unos 256 KB, lo que obliga a usar PSRAM;
- hay más de 16 fuentes o tamaños distintos;
- alguna imagen es mayor que la pantalla.

Son órdenes de magnitud para comparar diseños, no una medida exacta: la medida real se obtiene con
`lv_mem_monitor` en el equipo.

## Pruebas

- `tests/test_simulation_pro.py`:
  - desplazamiento de página y pulsación perdida;
  - deslizamientos y doble clic;
  - mosaicos con `dir`;
  - pestañas;
  - rotación y `on_portrait`;
  - `page_wrap` y `skip`;
  - `on_idle`;
  - estimación de recursos.
- Autoprueba F6:
  - gestos con captura;
  - tres dispositivos, uno girado, con navegación sincronizada y capturas a resolución real;
  - rendimiento y perfil de tu panel;
  - grabar y reproducir.
