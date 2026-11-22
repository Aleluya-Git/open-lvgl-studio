"""Exportación de un proyecto a una carpeta ESPHome."""
from __future__ import annotations

import os
import shutil
from dataclasses import dataclass, field

from olvgl.domain.model import Project
from olvgl.infrastructure.esphome_generator import (font_file_path, generate_main_yaml, generate_yaml,
                                                    image_file_path, is_local_file)
from olvgl.infrastructure.json_store import atomic_write_text, resolve_path


@dataclass
class ExportReport:
    written: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def export_esphome(project: Project, out_dir: str, project_path: str | None = None,
                   ui_filename: str = "ui_lvgl.yaml") -> ExportReport:
    report = ExportReport()
    report.warnings += project.validate()
    os.makedirs(out_dir, exist_ok=True)

    ui_path = os.path.join(out_dir, ui_filename)
    atomic_write_text(ui_path, generate_yaml(project))
    report.written.append(ui_path)

    main_path = os.path.join(out_dir, "main.yaml")
    if os.path.exists(main_path):
        report.skipped.append(main_path)
    else:
        atomic_write_text(main_path, generate_main_yaml(project))
        report.written.append(main_path)

    used = {w.props.get("src") for _, w in project.iter_widgets() if w.type == "image"}
    for img in project.images:
        if img.id not in used:
            continue
        if not img.path or "file" in img.extra:
            continue  # imágenes en línea (online_image) o con file especial
        src = resolve_path(img.path, project_path)
        dst = os.path.join(out_dir, *image_file_path(img.path).split("/"))
        if not src or not os.path.exists(src):
            report.warnings.append(f"Imagen '{img.id}': no se encuentra {img.path}")
            continue
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        if os.path.abspath(src) != os.path.abspath(dst):
            shutil.copy2(src, dst)
        report.written.append(dst)
    # fuentes en ficheros del equipo → carpeta fonts/ junto al YAML
    for f in project.fonts:
        fv = f.data.get("file")
        if not is_local_file(fv):
            continue
        src = resolve_path(fv, project_path)
        dst = os.path.join(out_dir, *font_file_path(fv).split("/"))
        if not src or not os.path.exists(src):
            report.warnings.append(f"Fuente '{f.id}': no se encuentra {fv}")
            continue
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        if os.path.abspath(src) != os.path.abspath(dst):
            shutil.copy2(src, dst)
        report.written.append(dst)
    return report
