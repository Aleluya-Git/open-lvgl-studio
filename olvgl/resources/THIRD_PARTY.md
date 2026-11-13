# Componentes de terceros

Open LVGL Studio se publica con licencia doble (GPL-3.0-or-later o comercial, ver LICENSING.md) y usa estos componentes. Si distribuyes la aplicación (también en una edición comercial), respeta sus licencias.

| Componente | Uso | Licencia | Qué implica |
|---|---|---|---|
| Python | Intérprete | PSF License | Permisiva |
| Qt 6 / PySide6 (Qt for Python) | Interfaz gráfica | LGPL v3 (o comercial de The Qt Company) | Se puede usar en software comercial enlazándolo de forma dinámica (como aquí, instalado con pip) y permitiendo que el usuario lo sustituya; hay que incluir el aviso de la LGPL y no impedir que se cambie por otra versión |
| PyYAML (y libyaml) | Leer y escribir YAML | MIT | Permisiva: conservar el aviso de copyright |
| Montserrat (fuente) | Dibujar como LVGL | SIL Open Font License 1.1 | Se puede incluir y redistribuir con la aplicación; la fuente no se vende por separado |
| LVGL | Destino del código C generado (no se incluye) | MIT | El código que generas es tuyo; tu firmware enlaza LVGL bajo MIT |
| ESPHome | Destino del YAML generado (no se incluye) | MIT (código) / GPLv3 (partes en C++) | El YAML que generas es tuyo |
| pytest | Sólo para las pruebas | MIT | No se distribuye con la aplicación |

Los componentes del catálogo de ejemplo (`marketplace/`) se publican con licencia MIT. Cada componente que instales de otros catálogos indica su propia licencia en su ficha.
