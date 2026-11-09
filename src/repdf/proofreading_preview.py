"""Two selected PDFs in a clearly framed left/right fullscreen comparison."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QFrame, QLabel, QSizePolicy, QSplitter, QVBoxLayout, QWidget

from repdf.floating_tools import FloatingAnnotationTools
from repdf.preview import FullscreenPreview


class ComparisonPane(QFrame):
    def __init__(self, document, parent):
        super().__init__(parent)
        self.document = document
        self.setObjectName('comparisonPane')
        self.title = QLabel(self)
        self.title.setTextFormat(Qt.TextFormat.PlainText)
        self.title.setFixedHeight(24)
        self.title.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
        self.title.setToolTip(str(document.source_path))
        row = QVBoxLayout(self)
        row.setContentsMargins(2, 2, 2, 2)
        row.setSpacing(0)
        row.addWidget(self.title)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.title.setText(self.title.fontMetrics().elidedText(self.document.source_path.name,
                           Qt.TextElideMode.ElideRight, max(0, self.width() - 8)))


class ComparisonPreview(FullscreenPreview):
    def __init__(self, owner, documents, mode='single'):
        QWidget.__init__(self, owner, Qt.WindowType.Window)
        self.owner, self.mode = owner, mode
        self.closed = False
        self.views = {}
        self.frames = {}
        self.setWindowModality(Qt.WindowModality.ApplicationModal)
        self.setObjectName('fullscreenPreview')
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 76)
        controller = owner.proofreading
        controller.busy = True
        try:
            self.splitter = QSplitter(Qt.Orientation.Horizontal, self)
            self.splitter.setChildrenCollapsible(False)
            self.splitter.setHandleWidth(16)
            for doc in documents:
                self.splitter.addWidget(self._make_view(doc))
            self.splitter.setSizes([1, 1])
            layout.addWidget(self.splitter)
        finally:
            controller.busy = False
        self.floating_tools = FloatingAnnotationTools(self)
        QApplication.instance().installEventFilter(self)
        # Focus must switch the active document before the annotation editor
        # handles the same mouse press in either embedded preview.
        QApplication.instance().removeEventFilter(controller)
        QApplication.instance().installEventFilter(controller)
        self.mark_active()

    def _make_view(self, doc):
        frame = ComparisonPane(doc, self)
        page = (doc._search_navigation[0] if doc._search_navigation is not None else
                doc.fit_page_index if doc._fit_navigation_pending else doc.preview_page_index())
        view = FullscreenPreview(self.owner, doc, page, self.mode, embedded_parent=frame)
        frame.layout().addWidget(view)
        self.views[doc.document_id] = view
        self.frames[doc.document_id] = frame
        return frame

    @property
    def document(self):
        current = self.owner.current_document()
        return current if current is not None and current.document_id in self.views else next(iter(self.views.values())).document

    @property
    def active_view(self):
        return self.views[self.document.document_id]

    @property
    def page_index(self):
        return self.active_view.page_index

    @property
    def visible_pages(self):
        return self.active_view.visible_pages

    @property
    def labels(self):
        return self.active_view.labels

    @property
    def images(self):
        return self.active_view.images

    @property
    def parity_buttons(self):
        return self.active_view.parity_buttons

    @property
    def groups(self):
        return self.active_view.groups

    @property
    def group_index(self):
        return self.active_view.group_index

    @property
    def checkboxes(self):
        return self.active_view.checkboxes

    @property
    def timer(self):
        return self.active_view.timer

    @property
    def render_generation(self):
        return -1

    def accept_comparison_render(self, payload):
        view = next((v for v in self.views.values()
                     if v.render_generation == payload.get('generation')), None)
        if view is None:
            return False
        view.accept_render(payload)
        return True

    def mark_active(self):
        for document_id, frame in self.frames.items():
            active = document_id == self.document.document_id
            if frame.property('activePane') != active:
                frame.setProperty('activePane', active)
                frame.style().unpolish(frame)
                frame.style().polish(frame)
                frame.update()

    def show_page(self, page):
        self.active_view.show_page(page)

    def _handle_key(self, key):
        if key in (Qt.Key.Key_Escape, Qt.Key.Key_F11):
            self.close()
            return True
        return self.active_view._handle_key(key)

    def set_mode(self, mode):
        if mode == self.mode:
            return
        controller = self.owner.proofreading
        active = self.active_view
        target = next(group[0] for group in active.page_groups(mode) if active.page_index in group)
        synchronized = controller.active_sync()
        if synchronized and not controller.allow_page(active.document, target):
            {'single': self.owner.single_action, 'spread': self.owner.spread_action,
             'cover': self.owner.cover_action}[self.mode].setChecked(True)
            return
        controller.busy = True
        try:
            self.mode = mode
            for view in self.views.values():
                view.set_mode(mode)
                if synchronized and view.page_index != target:
                    view.show_page(target)
        finally:
            controller.busy = False
        self.owner._sync_controls()

    def update_image(self):
        for view in self.views.values():
            view.update_image()

    def resizeEvent(self, event):
        QWidget.resizeEvent(self, event)
        if hasattr(self, 'floating_tools'):
            self.floating_tools.reposition()

    def closeEvent(self, event):
        self.owner.annotation_editor.finish_text(True)
        self.closed = True
        self.floating_tools.restore_menus()
        QApplication.instance().removeEventFilter(self)
        self.owner._fullscreen_preview = None
        self.owner.sync_views_action.setChecked(False)
        controller = self.owner.proofreading
        controller.busy = True
        try:
            for view in self.views.values():
                view.closed = True
                view.timer.stop()
                self.owner.render_service.cancel_pending(-view.document.document_id)
                if view.document.document_id in self.owner.documents:
                    view.document.jump_to_page(view.page_index)
        finally:
            controller.busy = False
        self.owner.navigation.layout()
        self.owner.search_controller.layout()
        self.owner.annotation_floating.setVisible(self.owner.annotation_tools_action.isChecked())
        self.owner.annotation_floating.reposition()
        self.owner._sync_controls()
        self.owner.activateWindow()
        self.deleteLater()
        event.accept()
