"""Panel de comentarios de revisión (colaboración, Fase 10)."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QCheckBox, QHBoxLayout, QLabel, QLineEdit, QPushButton, QTreeWidget,
                               QTreeWidgetItem, QVBoxLayout, QWidget)

from olvgl.i18n import tr, trf
from olvgl.infrastructure.collab import Comment, CommentStore


class CommentsPanel(QWidget):
    """Comentarios de la página actual: añadir (al widget seleccionado o a la
    página), responder, resolver y eliminar. Se guardan junto al proyecto y se
    fusionan con los de las demás personas."""

    def __init__(self, vm, on_changed=None, parent=None):
        super().__init__(parent)
        self.vm = vm
        self.on_changed = on_changed or (lambda: None)
        self.store = CommentStore(vm.document_path)
        self.list = QTreeWidget()
        self.list.setHeaderLabels([tr("Comentario"), tr("Autor"), tr("Widget")])
        self.list.setRootIsDecorated(True)
        self.list.currentItemChanged.connect(lambda *_: self._select_widget())
        self.show_resolved = QCheckBox(tr("Mostrar resueltos"))
        self.show_resolved.toggled.connect(lambda _v: self.refresh())
        self.text = QLineEdit()
        self.text.setPlaceholderText(tr("Escribe un comentario…"))
        self.text.returnPressed.connect(lambda: self.add())
        b_add = QPushButton(tr("Comentar"))
        b_add.setToolTip(tr("Sobre el widget seleccionado (o sobre la página)"))
        b_add.clicked.connect(lambda: self.add())
        self.b_reply = QPushButton(tr("Responder"))
        self.b_reply.clicked.connect(lambda: self.reply())
        self.b_resolve = QPushButton(tr("Resolver"))
        self.b_resolve.clicked.connect(lambda: self.toggle_resolved())
        self.b_delete = QPushButton(tr("Eliminar"))
        self.b_delete.clicked.connect(lambda: self.delete())
        self.info = QLabel()
        self.info.setWordWrap(True)
        self.info.setStyleSheet("color:#9E9E9E")
        row = QHBoxLayout()
        row.addWidget(self.text, 1)
        row.addWidget(b_add)
        row2 = QHBoxLayout()
        for b in (self.b_reply, self.b_resolve, self.b_delete):
            row2.addWidget(b)
        row2.addStretch(1)
        row2.addWidget(self.show_resolved)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(4, 4, 4, 4)
        lay.addWidget(self.list, 1)
        lay.addLayout(row)
        lay.addLayout(row2)
        lay.addWidget(self.info)
        vm.screen_changed.connect(lambda _id: self.refresh())
        vm.path_changed.connect(lambda _p: self.set_document())
        vm.project_replaced.connect(self.set_document)
        self.refresh()

    # ------------------------------------------------ datos
    def set_document(self) -> None:
        if self.store.path != (self.vm.document_path + ".comentarios.json" if self.vm.document_path else None):
            old = self.store
            self.store = CommentStore(self.vm.document_path)
            if old.path is None and old.comments:          # comentarios hechos antes de guardar
                self.store.comments.update(old.comments)
                self.store.save()
        self.refresh()

    def reload(self) -> None:
        self.store.reload()
        self.refresh()

    def counts(self) -> dict[str, int]:
        return self.store.open_by_widget(self.vm.current_screen_id)

    def refresh(self) -> None:
        keep = self.current_id()
        self.list.clear()
        comments = self.store.for_page(self.vm.current_screen_id, self.show_resolved.isChecked())
        target = None
        for c in comments:
            it = QTreeWidgetItem([("✓ " if c.resolved else "") + c.text, c.author, c.widget or tr("(página)")])
            it.setData(0, Qt.ItemDataRole.UserRole, c.id)
            it.setToolTip(0, f"{c.text}\n{c.author} · {c.created}")
            for r in c.replies:
                ch = QTreeWidgetItem(["↳ " + r.text, r.author, ""])
                ch.setData(0, Qt.ItemDataRole.UserRole, c.id)
                it.addChild(ch)
            self.list.addTopLevelItem(it)
            it.setExpanded(True)
            if c.id == keep:
                target = it
        self.list.resizeColumnToContents(1)
        if target:
            self.list.setCurrentItem(target)
        open_n = sum(1 for c in comments if not c.resolved)
        where = self.store.path or tr("(se guardarán junto al proyecto al guardarlo)")
        self.info.setText(trf("{n} abiertos en esta página · {where}", n=open_n, where=where))
        self.on_changed()

    def current_id(self) -> str | None:
        it = self.list.currentItem()
        return it.data(0, Qt.ItemDataRole.UserRole) if it else None

    def current(self) -> Comment | None:
        cid = self.current_id()
        return self.store.comments.get(cid) if cid else None

    def _select_widget(self) -> None:
        c = self.current()
        self.b_resolve.setText(tr("Reabrir") if c and c.resolved else tr("Resolver"))
        if c and c.widget and self.vm.project.widget(c.widget) is not None:
            self.vm.set_selection([c.widget])

    # ------------------------------------------------ acciones
    def add(self, text: str | None = None) -> Comment | None:
        text = (text if text is not None else self.text.text()).strip()
        if not text:
            return None
        sel = self.vm.selection
        c = self.store.add(self.vm.current_screen_id, sel[0] if sel else None, text)
        self.text.clear()
        self.refresh()
        return c

    def reply(self, text: str | None = None) -> bool:
        c = self.current()
        text = (text if text is not None else self.text.text()).strip()
        if c is None or not text:
            return False
        self.store.reply(c.id, text)
        self.text.clear()
        self.refresh()
        return True

    def toggle_resolved(self) -> bool:
        c = self.current()
        if c is None:
            return False
        self.store.set_resolved(c.id, not c.resolved)
        self.refresh()
        return True

    def delete(self) -> bool:
        c = self.current()
        if c is None:
            return False
        self.store.delete(c.id)
        self.refresh()
        return True
