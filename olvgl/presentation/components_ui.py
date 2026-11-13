"""Equipo › Componentes: biblioteca, catálogo (marketplace) y guardar la selección como componente."""
from __future__ import annotations

import os

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtWidgets import (QDialog, QDialogButtonBox, QFileDialog, QFormLayout, QHBoxLayout, QLabel, QLineEdit,
                               QListWidget, QListWidgetItem, QMessageBox, QPlainTextEdit, QPushButton, QTabWidget,
                               QVBoxLayout, QWidget)

from olvgl.i18n import tr, trf
from olvgl.infrastructure.components import (Catalog, CatalogEntry, ComponentError, Library, Package,
                                             extract_component, insert_component, make_manifest, preview_project,
                                             read_package, write_package)
from olvgl.infrastructure.versions import default_author


def package_preview(pkg: Package, size: int = 220) -> QPixmap:
    data = pkg.files.get("preview.png")
    if data:
        pm = QPixmap()
        if pm.loadFromData(data):
            return pm.scaled(size, size, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
    from olvgl.presentation.ai_ui import render_page
    proj = preview_project(pkg)
    return QPixmap.fromImage(render_page(proj, "preview", size))


def _project_images_dir(vm) -> str:
    doc = vm.document_path
    if doc:
        return os.path.join(os.path.dirname(os.path.abspath(doc)), "images")
    from olvgl.infrastructure.settings_db import app_data_dir
    return os.path.join(app_data_dir(), "images")


class ComponentsDialog(QDialog):
    def __init__(self, vm, settings, parent=None):
        super().__init__(parent)
        self.vm = vm
        self.settings = settings
        self.library = Library(settings.get("components_dir", "") or None)
        self.catalog = Catalog(settings.get("market_url", "") or None)
        self.setWindowTitle(tr("Componentes"))
        self.resize(980, 640)
        self.tabs = QTabWidget()
        # ---------- biblioteca
        self.lib_list = self._list()
        self.lib_list.currentItemChanged.connect(lambda *_: self._show_lib())
        self.lib_info = self._info()
        b_insert = QPushButton(tr("Insertar en la página"))
        b_insert.clicked.connect(lambda: self.insert_selected())
        b_import = QPushButton(tr("Instalar desde fichero…"))
        b_import.clicked.connect(lambda: self.install_file())
        b_export = QPushButton(tr("Exportar…"))
        b_export.clicked.connect(lambda: self.export_selected())
        b_remove = QPushButton(tr("Desinstalar"))
        b_remove.clicked.connect(lambda: self.remove_selected())
        lib = QWidget()
        ll = QHBoxLayout(lib)
        ll.addWidget(self.lib_list, 3)
        right = QVBoxLayout()
        right.addWidget(self.lib_info, 1)
        for b in (b_insert, b_import, b_export, b_remove):
            right.addWidget(b)
        ll.addLayout(right, 2)
        self.tabs.addTab(lib, tr("Biblioteca"))
        # ---------- catálogo
        self.url = QLineEdit(self.catalog.location)
        b_load = QPushButton(tr("Cargar"))
        b_load.clicked.connect(lambda: self.load_catalog(self.url.text().strip()))
        self.search = QLineEdit()
        self.search.setPlaceholderText(tr("Buscar (nombre, descripción, etiquetas)…"))
        self.search.textChanged.connect(lambda _t: self._fill_catalog())
        self.cat_list = self._list()
        self.cat_list.currentItemChanged.connect(lambda *_: self._show_cat())
        self.cat_info = self._info()
        b_install = QPushButton(tr("Instalar"))
        b_install.clicked.connect(lambda: self.install_selected())
        cat = QWidget()
        cl = QVBoxLayout(cat)
        row = QHBoxLayout()
        row.addWidget(QLabel(tr("Catálogo:")))
        row.addWidget(self.url, 1)
        row.addWidget(b_load)
        cl.addLayout(row)
        cl.addWidget(self.search)
        body = QHBoxLayout()
        body.addWidget(self.cat_list, 3)
        r2 = QVBoxLayout()
        r2.addWidget(self.cat_info, 1)
        r2.addWidget(b_install)
        body.addLayout(r2, 2)
        cl.addLayout(body, 1)
        note = QLabel(tr("Cada componente se comprueba con su SHA-256 antes de instalarlo. Para publicar los tuyos, "
                         "sube sus .olvglc y un index.json a cualquier web (ver docs/13_enterprise.md)."))
        note.setWordWrap(True)
        note.setStyleSheet("color:#9E9E9E")
        cl.addWidget(note)
        self.tabs.addTab(cat, tr("Catálogo"))
        self.status = QLabel()
        self.status.setWordWrap(True)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        lay = QVBoxLayout(self)
        lay.addWidget(self.tabs, 1)
        lay.addWidget(self.status)
        lay.addWidget(buttons)
        self.inserted: list[str] = []
        self.fill_library()
        self.load_catalog(self.catalog.location, quiet=True)

    @staticmethod
    def _list() -> QListWidget:
        lst = QListWidget()
        lst.setViewMode(QListWidget.ViewMode.IconMode)
        lst.setIconSize(QSize(150, 110))
        lst.setGridSize(QSize(180, 160))
        lst.setResizeMode(QListWidget.ResizeMode.Adjust)
        lst.setMovement(QListWidget.Movement.Static)
        lst.setWordWrap(True)
        return lst

    @staticmethod
    def _info() -> QPlainTextEdit:
        t = QPlainTextEdit()
        t.setReadOnly(True)
        return t

    # ------------------------------------------------ biblioteca
    def fill_library(self, select: str | None = None) -> None:
        self.lib_list.clear()
        for pkg in self.library.list():
            it = QListWidgetItem(QIcon(package_preview(pkg, 150)), pkg.name)
            it.setData(Qt.ItemDataRole.UserRole, pkg.id)
            self.lib_list.addItem(it)
            if pkg.id == select:
                self.lib_list.setCurrentItem(it)
        if self.lib_list.currentItem() is None and self.lib_list.count():
            self.lib_list.setCurrentRow(0)
        if not self.lib_list.count():
            self.lib_info.setPlainText(tr("Aún no hay componentes instalados. Instálalos desde la pestaña Catálogo "
                                          "o guarda una selección con Equipo › Guardar selección como componente."))

    def current_package(self) -> Package | None:
        it = self.lib_list.currentItem()
        return self.library.get(it.data(Qt.ItemDataRole.UserRole)) if it else None

    def _describe(self, m: dict) -> str:
        lines = [f"{m.get('name')}  ·  v{m.get('version', '')}", ""]
        if m.get("description"):
            lines += [m["description"], ""]
        for k, label in (("author", tr("Autor")), ("license", tr("Licencia")), ("widgets", tr("Widgets")),
                         ("tags", tr("Etiquetas"))):
            v = m.get(k)
            if v:
                lines.append(f"{label}: {', '.join(v) if isinstance(v, list) else v}")
        return "\n".join(lines)

    def _show_lib(self) -> None:
        pkg = self.current_package()
        if pkg:
            self.lib_info.setPlainText(self._describe(pkg.manifest))

    def insert_selected(self, x: int = 20, y: int = 20) -> list[str]:
        pkg = self.current_package()
        if pkg is None:
            return []
        sel = self.vm.selected_widgets()
        parent = sel[0].id if len(sel) == 1 and sel[0].type in ("obj", "tab", "tile") else None
        try:
            new, tops = insert_component(self.vm.project, pkg, self.vm.current_screen_id, parent, x, y,
                                         _project_images_dir(self.vm))
        except (ComponentError, OSError) as exc:
            self.status.setText(f"<span style='color:#EF5350'>{exc}</span>")
            return []
        self.vm.apply_project(trf("Insertar componente «{name}»", name=pkg.name), new)
        self.vm.set_selection(tops)
        self.inserted = tops
        self.status.setText(trf("«{name}» insertado ({n} widgets)", name=pkg.name,
                                n=sum(1 for t in tops for _ in self.vm.project.widget(t).walk())))
        return tops

    def install_file(self, path: str | None = None) -> Package | None:
        if path is None:
            path, _f = QFileDialog.getOpenFileName(self, tr("Instalar componente"), os.path.expanduser("~"),
                                                   tr("Componentes (*.olvglc)"))
            if not path:
                return None
        try:
            pkg = self.library.install(path)
        except (ComponentError, OSError) as exc:
            self.status.setText(f"<span style='color:#EF5350'>{exc}</span>")
            return None
        self.fill_library(pkg.id)
        self.status.setText(trf("«{name}» instalado", name=pkg.name))
        return pkg

    def export_selected(self, path: str | None = None) -> str | None:
        pkg = self.current_package()
        if pkg is None or not pkg.path:
            return None
        if path is None:
            path, _f = QFileDialog.getSaveFileName(self, tr("Exportar componente"),
                                                   os.path.join(os.path.expanduser("~"), f"{pkg.id}.olvglc"),
                                                   tr("Componentes (*.olvglc)"))
            if not path:
                return None
        with open(pkg.path, "rb") as src, open(path, "wb") as dst:
            dst.write(src.read())
        return path

    def remove_selected(self, confirm: bool = True) -> bool:
        pkg = self.current_package()
        if pkg is None:
            return False
        if confirm and QMessageBox.question(self, tr("Desinstalar"), trf("¿Desinstalar «{name}»?", name=pkg.name)
                                            ) != QMessageBox.StandardButton.Yes:
            return False
        self.library.remove(pkg.id)
        self.fill_library()
        return True

    # ------------------------------------------------ catálogo
    def load_catalog(self, location: str, quiet: bool = False) -> bool:
        self.catalog = Catalog(location or None)
        try:
            self.catalog.load()
        except ComponentError as exc:
            self.cat_list.clear()
            if not quiet:
                self.status.setText(f"<span style='color:#EF5350'>{exc}</span>")
            return False
        if location and location != self.settings.get("market_url", ""):
            self.settings.set("market_url", location)
        self._fill_catalog()
        self.status.setText(trf("{title}: {n} componentes", title=self.catalog.title or self.catalog.location,
                                n=len(self.catalog.entries)))
        return True

    def _fill_catalog(self) -> None:
        installed = {p.id: p.version for p in self.library.list()}
        self.cat_list.clear()
        for e in self.catalog.search(self.search.text()):
            mark = " ✓" if installed.get(e.id) == e.version else ""
            it = QListWidgetItem(e.name + mark)
            it.setData(Qt.ItemDataRole.UserRole, e.id)
            it.setToolTip(e.description)
            self.cat_list.addItem(it)
        if self.cat_list.count():
            self.cat_list.setCurrentRow(0)

    def current_entry(self) -> CatalogEntry | None:
        it = self.cat_list.currentItem()
        cid = it.data(Qt.ItemDataRole.UserRole) if it else None
        return next((e for e in self.catalog.entries if e.id == cid), None)

    def _show_cat(self) -> None:
        e = self.current_entry()
        if e:
            self.cat_info.setPlainText(self._describe(e.__dict__) + f"\n\nSHA-256: {e.sha256[:16]}…")

    def install_selected(self) -> Package | None:
        e = self.current_entry()
        if e is None:
            return None
        try:
            pkg = self.library.install(self.catalog.download(e), e.sha256)
        except (ComponentError, OSError) as exc:
            self.status.setText(f"<span style='color:#EF5350'>{exc}</span>")
            return None
        self.fill_library(pkg.id)
        self._fill_catalog()
        self.status.setText(trf("«{name}» instalado", name=pkg.name))
        return pkg

    def install_all(self) -> int:
        n = 0
        for i in range(self.cat_list.count()):
            self.cat_list.setCurrentRow(i)
            n += self.install_selected() is not None
        return n


class SaveComponentDialog(QDialog):
    """Guardar la selección como componente (en la biblioteca y, si se quiere, como fichero)."""

    def __init__(self, vm, settings, parent=None):
        super().__init__(parent)
        self.vm = vm
        self.library = Library(settings.get("components_dir", "") or None)
        self.setWindowTitle(tr("Guardar selección como componente"))
        self.resize(520, 420)
        ids = [w.id for w in vm.selected_widgets()]
        self.comp = extract_component(vm.project, ids)
        first = vm.project.widget(ids[0])
        self.name = QLineEdit(str(first.props.get("text") or first.id).replace("_", " ").capitalize()[:40])
        self.author = QLineEdit(default_author())
        self.description = QLineEdit()
        self.tags = QLineEdit()
        self.tags.setPlaceholderText(tr("separadas por comas"))
        self.license = QLineEdit("")
        self.license.setPlaceholderText("MIT, CC-BY-4.0…")
        self.preview = QLabel()
        self.preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        try:
            pkg = Package(make_manifest(self.name.text() or "x", self.comp), self.comp)
            self.preview.setPixmap(package_preview(pkg, 240))
        except ComponentError:
            pass
        form = QFormLayout()
        form.addRow(tr("Nombre:"), self.name)
        form.addRow(tr("Autor:"), self.author)
        form.addRow(tr("Descripción:"), self.description)
        form.addRow(tr("Etiquetas:"), self.tags)
        form.addRow(tr("Licencia:"), self.license)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(lambda: self.save() and self.accept())
        buttons.rejected.connect(self.reject)
        from olvgl.infrastructure.components import _walk_dicts
        self.status = QLabel(trf("{n} widgets", n=sum(1 for d in self.comp["widgets"] for _ in _walk_dicts(d))))
        lay = QVBoxLayout(self)
        lay.addWidget(self.preview)
        lay.addLayout(form)
        lay.addWidget(self.status)
        lay.addWidget(buttons)

    def save(self, file_path: str | None = None) -> Package | None:
        try:
            m = make_manifest(self.name.text(), self.comp, self.author.text().strip(),
                              self.description.text().strip(),
                              [t.strip() for t in self.tags.text().split(",") if t.strip()], "1.0.0",
                              self.license.text().strip())
        except ComponentError as exc:
            self.status.setText(str(exc))
            return None
        import tempfile
        tmp = file_path or os.path.join(tempfile.mkdtemp(), f"{m['id']}.olvglc")
        write_package(tmp, m, self.comp)
        pkg = self.library.install(tmp)
        self.saved = pkg
        return pkg if read_package(pkg.path) else None
