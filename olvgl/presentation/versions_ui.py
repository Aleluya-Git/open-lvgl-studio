"""Equipo › Versiones: instantáneas, historial de Git y diferencias visuales."""
from __future__ import annotations

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QImage, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (QComboBox, QDialog, QDialogButtonBox, QHBoxLayout, QInputDialog, QLabel,
                               QMessageBox, QPlainTextEdit, QPushButton, QSplitter, QTreeWidget, QTreeWidgetItem,
                               QVBoxLayout, QWidget)

from olvgl.domain.model import Project
from olvgl.domain.visual_diff import ProjectDiff, diff_projects
from olvgl.i18n import tr, trf
from olvgl.infrastructure.versions import GitHistory, VersionInfo, VersionStore, default_author
from olvgl.presentation.fonts import mono_font

COLORS = {"added": QColor("#43A047"), "removed": QColor("#E53935"), "changed": QColor("#FFB300")}
NOW = "__ahora__"


def render_with_marks(project: Project | None, page_id: str, marks: dict[str, str], max_w: int = 420) -> QImage:
    """La página dibujada como en el canvas, con un recuadro de color por widget cambiado."""
    from olvgl.domain.extensions import expand_project
    from olvgl.domain.layout import LayoutContext, compute_layout
    from olvgl.presentation import render as rnd
    w0, h0 = (project.display.width, project.display.height) if project else (400, 240)
    scale = min(1.0, max_w / max(1, w0))
    img = QImage(max(1, int(w0 * scale)), max(1, int(h0 * scale)), QImage.Format.Format_ARGB32_Premultiplied)
    img.fill(QColor("#202024"))
    if project is None or project.screen(page_id) is None:
        p = QPainter(img)
        p.setPen(QColor("#9E9E9E"))
        p.drawText(img.rect(), Qt.AlignmentFlag.AlignCenter, tr("(la página no existe en esta versión)"))
        p.end()
        return img
    project = expand_project(project)
    screen = project.screen(page_id)
    ctx = rnd.RenderContext(project)
    boxes = compute_layout(project, screen, LayoutContext(project, ctx.measure_text, ctx.image_size_of, {}))
    p = QPainter(img)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.scale(scale, scale)
    p.setClipRect(QRectF(0, 0, w0, h0))
    p.fillRect(QRectF(0, 0, w0, h0), rnd.page_background(project, screen, ctx))
    rnd.paint_tree(p, screen.widgets, boxes, ctx)
    for wid, status in marks.items():
        b = boxes.get(wid)
        if b is None or not b.shown:
            continue
        c = COLORS[status]
        fill = QColor(c)
        fill.setAlpha(50)
        p.fillRect(QRectF(b.rect.x, b.rect.y, b.rect.w, b.rect.h), fill)
        p.setPen(QPen(c, 3 / scale))
        p.drawRect(QRectF(b.rect.x, b.rect.y, b.rect.w, b.rect.h))
    p.end()
    return img


class VersionsDialog(QDialog):
    def __init__(self, vm, parent=None):
        super().__init__(parent)
        self.vm = vm
        self.doc = vm.document_path
        self.store = VersionStore(self.doc)
        self.git = GitHistory(self.doc)
        self.setWindowTitle(tr("Versiones del proyecto"))
        self.resize(1180, 760)
        self.list = QTreeWidget()
        self.list.setHeaderLabels([tr("Versión"), tr("Autor"), tr("Fecha")])
        self.list.setRootIsDecorated(True)
        self.list.currentItemChanged.connect(lambda *_: self.compare())
        self.page = QComboBox()
        self.page.currentIndexChanged.connect(lambda _i: self.show_page())
        self.before = QLabel()
        self.after = QLabel()
        for lab in (self.before, self.after):
            lab.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lab.setMinimumSize(380, 240)
        self.before_title = QLabel(tr("Antes (versión elegida)"))
        self.after_title = QLabel(tr("Después (ahora)"))
        legend = QLabel("<span style='color:#43A047'>■</span> " + tr("añadido") + "  "
                        "<span style='color:#E53935'>■</span> " + tr("eliminado") + "  "
                        "<span style='color:#FFB300'>■</span> " + tr("cambiado"))
        self.changes = QPlainTextEdit()
        self.changes.setReadOnly(True)
        self.changes.setFont(mono_font(9))
        b_save = QPushButton(tr("Guardar versión…"))
        b_save.clicked.connect(lambda: self.save_version())
        self.b_restore = QPushButton(tr("Restaurar esta versión"))
        self.b_restore.clicked.connect(lambda: self.restore())
        self.b_delete = QPushButton(tr("Eliminar"))
        self.b_delete.clicked.connect(lambda: self.delete())
        left = QWidget()
        ll = QVBoxLayout(left)
        ll.setContentsMargins(0, 0, 0, 0)
        ll.addWidget(self.list, 1)
        row = QHBoxLayout()
        for b in (b_save, self.b_restore, self.b_delete):
            row.addWidget(b)
        ll.addLayout(row)
        if not self.doc:
            note = QLabel(tr("Guarda el proyecto para que sus versiones viajen con él."))
            note.setWordWrap(True)
            note.setStyleSheet("color:#9E9E9E")
            ll.addWidget(note)
        right = QWidget()
        rl = QVBoxLayout(right)
        rl.setContentsMargins(0, 0, 0, 0)
        top = QHBoxLayout()
        top.addWidget(QLabel(tr("Página:")))
        top.addWidget(self.page, 1)
        top.addWidget(legend)
        rl.addLayout(top)
        imgs = QHBoxLayout()
        for title, lab in ((self.before_title, self.before), (self.after_title, self.after)):
            col = QVBoxLayout()
            col.addWidget(title)
            col.addWidget(lab, 1)
            imgs.addLayout(col)
        rl.addLayout(imgs, 3)
        rl.addWidget(self.changes, 2)
        split = QSplitter()
        split.addWidget(left)
        split.addWidget(right)
        split.setSizes([330, 850])
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        lay = QVBoxLayout(self)
        lay.addWidget(split, 1)
        lay.addWidget(buttons)
        self.diff: ProjectDiff | None = None
        self.old: Project | None = None
        self.fill()

    # ------------------------------------------------ lista
    def fill(self, select: str | None = None) -> None:
        self.list.clear()
        now = QTreeWidgetItem([tr("Ahora (sin guardar)"), default_author(), ""])
        now.setData(0, Qt.ItemDataRole.UserRole, NOW)
        self.list.addTopLevelItem(now)
        groups = [(tr("Versiones guardadas"), self.store.list())]
        if self.git.available:
            groups.append((trf("Historial de Git ({file})", file=self.git.rel()), self.git.log()))
        target = None
        for title, versions in groups:
            g = QTreeWidgetItem([f"{title} · {len(versions)}"])
            g.setFlags(Qt.ItemFlag.ItemIsEnabled)          # cabecera de grupo: no se selecciona
            self.list.addTopLevelItem(g)
            for v in versions:
                it = QTreeWidgetItem([v.label + (f"  [{v.detail}]" if v.source == "git" else ""), v.author, v.when])
                it.setData(0, Qt.ItemDataRole.UserRole, v)
                it.setToolTip(0, v.detail)
                g.addChild(it)
                if select and v.id == select:
                    target = it
            g.setExpanded(True)
        self.list.resizeColumnToContents(0)
        if target is None:
            target = next((self.list.topLevelItem(i).child(0) for i in range(1, self.list.topLevelItemCount())
                           if self.list.topLevelItem(i).childCount()), None)
        self.list.setCurrentItem(target or now)

    def current(self) -> VersionInfo | None:
        it = self.list.currentItem()
        v = it.data(0, Qt.ItemDataRole.UserRole) if it else None
        return v if isinstance(v, VersionInfo) else None

    def load(self, v: VersionInfo) -> Project | None:
        if v.source == "git":
            return self.git.project_at(v.id, self.vm.project.display)
        return self.store.load(v.id)

    # ------------------------------------------------ comparación
    def compare(self) -> None:
        v = self.current()
        self.b_restore.setEnabled(v is not None)
        self.b_delete.setEnabled(v is not None and v.source == "local")
        try:
            self.old = self.load(v) if v else None
        except Exception as exc:              # versión dañada o Git que falla: se informa
            self.old = None
            self.changes.setPlainText(trf("No se pudo leer la versión: {error}", error=exc))
            return
        if self.old is None:
            self.diff = None
            self.changes.setPlainText(tr("Elige una versión para compararla con el proyecto actual."))
            self.page.clear()
            self.before.clear()
            self.after.setPixmap(QPixmap.fromImage(render_with_marks(
                self.vm.project, self.vm.current_screen_id, {})))
            return
        self.diff = diff_projects(self.old, self.vm.project)
        c = self.diff.counts()
        head = trf("{a} añadidos, {r} eliminados, {c} cambiados", a=c["added"], r=c["removed"], c=c["changed"])
        self.changes.setPlainText(head + "\n\n" + ("\n".join(self.diff.summary()) or tr("Sin cambios")))
        keep = self.page.currentData()
        self.page.blockSignals(True)
        self.page.clear()
        for pd in sorted(self.diff.pages, key=lambda x: not x.changed):
            mark = {"added": "+ ", "removed": "− ", "changed": "~ ", "same": "   "}[pd.status]
            self.page.addItem(f"{mark}{pd.name} ({pd.id})", pd.id)
        idx = self.page.findData(keep)
        self.page.setCurrentIndex(idx if idx >= 0 else 0)
        self.page.blockSignals(False)
        self.show_page()

    def show_page(self) -> None:
        pid = self.page.currentData()
        if self.diff is None or pid is None:
            return
        pd = self.diff.page(pid)
        before_marks = {w.id: w.status for w in pd.widgets if w.status in ("removed", "changed")}
        after_marks = {w.id: w.status for w in pd.widgets if w.status in ("added", "changed")}
        w = max(360, (self.width() - 420) // 2)
        self.before.setPixmap(QPixmap.fromImage(render_with_marks(self.old, pid, before_marks, w)))
        self.after.setPixmap(QPixmap.fromImage(render_with_marks(self.vm.project, pid, after_marks, w)))

    # ------------------------------------------------ acciones
    def save_version(self, label: str | None = None) -> VersionInfo | None:
        if label is None:
            label, ok = QInputDialog.getText(self, tr("Guardar versión"), tr("Descripción de la versión:"))
            if not ok:
                return None
        info = self.store.save(self.vm.project, label)
        self.fill(select=info.id)
        return info

    def restore(self, confirm: bool = True) -> bool:
        v = self.current()
        if v is None or self.old is None:
            return False
        if confirm and QMessageBox.question(
                self, tr("Restaurar versión"),
                trf("¿Sustituir el proyecto por «{label}»? Se puede deshacer con Ctrl+Z.", label=v.label)
        ) != QMessageBox.StandardButton.Yes:
            return False
        old = self.old.clone()
        old.source = dict(self.vm.project.source)
        ok = self.vm.apply_project(trf("Restaurar «{label}»", label=v.label), old)
        self.compare()
        return ok

    def delete(self, confirm: bool = True) -> bool:
        v = self.current()
        if v is None or v.source != "local":
            return False
        if confirm and QMessageBox.question(self, tr("Eliminar"), trf("¿Eliminar la versión «{label}»?",
                                                                      label=v.label)) != QMessageBox.StandardButton.Yes:
            return False
        self.store.delete(v.id)
        self.fill()
        return True
