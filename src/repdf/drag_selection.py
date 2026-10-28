"""Extend a text drag through the reading viewport's page boundaries."""
from PySide6.QtCore import QEvent, QObject, Qt, QTimer
from PySide6.QtGui import QCursor
from PySide6.QtWidgets import QWidget
from repdf.widgets import PagePreviewLabel
from shiboken6 import isValid


class DragTextSelection(QObject):
    def __init__(self, copier):
        super().__init__(copier)
        self.copier = copier
        self.owner = copier.owner
        self.start = None
        self.crossed = False
        self.last = None
        self.timer = QTimer(self)
        self.timer.setInterval(150)
        self.timer.timeout.connect(self.advance)

    def labels(self):
        viewer = self.owner._fullscreen_preview
        if viewer is not None:
            return viewer.document, viewer.labels
        doc = self.owner.current_document()
        return doc, ({card.page_index: card.preview for card in doc.page_cards} if doc else {})

    def handle_event(self, watched, event, window):
        if not isinstance(watched, QWidget) or watched.window() is not window:
            return False
        if not self.owner.copy_text_action.isChecked() or self.owner._closing:
            self.timer.stop()
            self.start = None
            return False
        kind = event.type()
        if kind == QEvent.Type.MouseButtonPress and event.button() == Qt.MouseButton.LeftButton:
            if not isinstance(watched, PagePreviewLabel):
                return False
            doc, labels = self.labels()
            page = next((page for page, label in labels.items() if label is watched), None)
            if page is None:
                return False
            self.copier.cancel()
            self.doc = doc
            self.start = (page, [event.position().x() / watched.width(), event.position().y() / watched.height()])
            self.origin = watched
            self.crossed = False
            self.last = None
            self.timer.start()
        elif self.start is not None and kind == QEvent.Type.MouseMove:
            self.advance()
            return self.crossed
        elif self.start is not None and kind == QEvent.Type.MouseButtonRelease:
            self.timer.stop()
            crossed = self.crossed
            if crossed and self.last is not None:
                self.copier.select_range(self.doc, self.start, self.last, copy=True)
            self.start = None
            return crossed
        return False

    def advance(self):
        if self.start is None or self.owner._closing or self.doc.document_id not in self.owner.documents:
            self.timer.stop()
            return
        if not self.owner.copy_text_action.isChecked() or self.owner.current_document() is not self.doc:
            self.start = None
            self.timer.stop()
            return
        position = QCursor.pos()
        doc, labels = self.labels()
        viewer = self.owner._fullscreen_preview
        if not self.crossed:
            if not isValid(self.origin):
                self.start = None
                self.timer.stop()
                return
            point = self.origin.mapFromGlobal(position)
            if 0 <= point.y() < self.origin.height():
                return
            self.crossed = True
            self.origin._selecting = False
            self.origin._preview_timer.stop()
            self.owner._text_requests.clear()
            self.doc._search_navigation = None
        if viewer is None:
            viewport = doc.scroll_area.viewport()
            point = viewport.mapFromGlobal(position)
            bar = doc.scroll_area.verticalScrollBar()
            if point.y() < 24 or point.y() >= viewport.height() - 24:
                doc.fit_mode = False
                bar.setValue(bar.value() + (-40 if point.y() < 24 else 40))
            point = doc.grid_host.mapFromGlobal(position)
            page = min(doc.page_order, key=lambda page: max(doc.pages.rect(page).top() - point.y(),
                                                           0, point.y() - doc.pages.rect(page).bottom()))
            label = doc.pages.ensure_page(page).preview
        else:
            point = viewer.mapFromGlobal(position)
            direction = -1 if point.y() < 24 else 1 if point.y() >= viewer.height() - 24 else 0
            group = viewer.group_index + direction
            if direction and 0 <= group < len(viewer.groups):
                viewer.show_page(viewer.groups[group][0])
            page, label = min(viewer.labels.items(), key=lambda item:
                abs(item[1].mapFromGlobal(position).x() - item[1].width() / 2))
        point = label.mapFromGlobal(position)
        endpoint = (page, [max(0, min(1, point.x() / label.width())),
                           max(0, min(1, point.y() / label.height()))])
        if endpoint != self.last:
            self.last = endpoint
            self.copier.select_range(doc, self.start, endpoint)
