# Fase 0 · 02 — Casos de uso ESPHome

## Actores

- **Maker domótico**: tiene Home Assistant y una pantalla ESP32 (p. ej. Waveshare ESP32-S3 7" 1024×600). Quiere un panel táctil sin escribir cientos de líneas de YAML.
- **Desarrollador ESPHome**: ya tiene un YAML grande y quiere verlo y retocarlo visualmente sin perder sus cambios manuales.
- **Integrador/empresa**: crea paneles para clientes; necesita plantillas, componentes reutilizables y licencias claras.

## Casos de uso

| ID | Caso | Actor | Fase |
|---|---|---|:-:|
| CU-01 | Crear proyecto eligiendo resolución de la pantalla | Maker | 1 |
| CU-02 | Colocar etiquetas, botones e imágenes arrastrando desde la paleta | Maker | 1 |
| CU-03 | Mover, redimensionar, alinear y seleccionar varios widgets | Maker | 1 |
| CU-04 | Editar propiedades (texto, colores, fuente, radio…) | Maker | 1 |
| CU-05 | Varias páginas y navegación entre ellas con un botón | Maker | 1 |
| CU-06 | Llamar a una acción de Home Assistant al pulsar un botón (`light.toggle`) | Maker | 1 |
| CU-07 | Ver el YAML generado en vivo y exportarlo como paquete `!include` | Maker | 1 |
| CU-08 | Probar la interfaz en el simulador antes de flashear | Maker | 1 |
| CU-09 | Deshacer/rehacer sin límite; autoguardado y recuperación | Todos | 1 |
| CU-10 | Importar un YAML ESPHome existente y verlo en el canvas | Desarrollador | 2 |
| CU-11 | Editar el YAML a mano y ver el cambio en el diseño (y viceversa) sin perder comentarios ni lambdas | Desarrollador | 3 |
| CU-12 | Mostrar estado de entidades HA (sensor → texto de etiqueta) | Maker | 4 |
| CU-13 | Estilos compartidos y temas por página | Maker | 4 |
| CU-14 | Abrir el diseñador desde VS Code sobre el YAML abierto | Desarrollador | 5 |
| CU-15 | Generar una pantalla completa desde un prompt | Todos | 8 |

## Escenario de referencia (prueba de aceptación de Fase 1)

1. Nuevo proyecto «Panel salón», 1024×600.
2. Página `inicio`, fondo `#1A1A2E`.
3. Etiqueta «Salón» arriba a la izquierda, Montserrat 28, blanca.
4. Botón «Luz» que ejecuta `homeassistant.action: light.toggle` sobre `light.salon`.
5. Botón «Ajustes» que hace `lvgl.page.show: ajustes`.
6. Página `ajustes` con botón «Volver».
7. El simulador navega entre páginas y registra la acción HA.
8. Exportar → carpeta con `ui_lvgl.yaml`, `main.yaml` e `images/`.
9. `ui_lvgl.yaml` se incluye en el YAML del dispositivo con `packages:` y compila.

## Requisitos no funcionales

- Proyecto en texto (JSON) estable y diffable en Git.
- YAML generado legible, con el estilo de la documentación de ESPHome (sangría de 2, colores `0xRRGGBB`).
- Sólo se emiten propiedades distintas de las de por defecto del tema LVGL.
- IDs válidos como identificadores C (requisito de ESPHome).
- Arranque < 2 s, canvas fluido con 500 widgets.
