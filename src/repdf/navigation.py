"""Bookmark sidebar, internal navigation and web links for the current document."""

from PySide6.QtCore import QEvent, QObject, QSize, Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (QHBoxLayout, QLabel, QLayout, QSplitter, QToolButton,
                               QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget)

from repdf.icons import toolbar_icon
from repdf.strings import tr


class BookmarkPanel(QWidget):
    def __init__(self):
        super().__init__()
        self.setMinimumSize(0, 0)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)
        layout.setSizeConstraint(QLayout.SizeConstraint.SetNoConstraint)
        row = QHBoxLayout()
        row.addWidget(QLabel(tr('書籤')), 1)
        self.close_button = QToolButton()
        self.close_button.setText(tr('關閉書籤窗格'))
        self.close_button.setAccessibleName(tr('關閉書籤窗格'))
        self.close_button.setToolTip(tr('關閉書籤窗格'))
        self.close_button.setFixedSize(34, 34)
        self.close_button.setIconSize(QSize(20, 20))
        self.close_button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
        self.close_button.setIcon(toolbar_icon('close'))
        row.addWidget(self.close_button)
        layout.addLayout(row)
        self.status = QLabel()
        self.status.setWordWrap(True)
        self.status.setTextFormat(Qt.TextFormat.PlainText)
        layout.addWidget(self.status)
        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.setAccessibleName(tr('PDF 書籤'))
        self.tree.setMinimumSize(0, 0)
        self.tree.setIndentation(16)
        self.tree.setTextElideMode(Qt.TextElideMode.ElideRight)
        self.tree.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        layout.addWidget(self.tree, 1)

    def changeEvent(self, event):
        super().changeEvent(event)
        if event.type() == QEvent.Type.PaletteChange and hasattr(self, 'close_button'):
            self.close_button.setIcon(toolbar_icon('close'))


class NavigationController(QObject):
    def __init__(self, owner, content):
        super().__init__(owner)
        self.owner, self.content = owner, content
        self.panel = BookmarkPanel()
        self.workspace = QSplitter(Qt.Orientation.Horizontal)
        self.workspace.setChildrenCollapsible(False)
        self.workspace.addWidget(self.panel)
        self.workspace.addWidget(content)
        self.workspace.setStretchFactor(0, 0)
        self.workspace.setStretchFactor(1, 1)
        self.panel.hide()
        self.opened = False
        self.narrow_results = True
        self.displayed_id = None
        self.items = []
        self.states = {}
        self.requests = {}
        self.latest_jump = None
        self._layout_state = None
        self.panel.close_button.clicked.connect(self.close)
        self.panel.tree.itemClicked.connect(self._clicked)
        self.panel.tree.itemActivated.connect(self._clicked)

    def toggle(self):
        if self.panel.isVisible():
            self.close()
        else:
            self.open()

    def open(self):
        if self.owner._fullscreen_preview is not None:
            self.owner._fullscreen_preview.close()
        self.owner.search_controller.close()
        self.opened = True
        self.narrow_results = True
        self.layout()
        self.show_document()
        self.panel.tree.setFocus()

    def close(self):
        self.opened = False
        self.layout()

    def layout(self):
        narrow = self.owner.width() < 640
        state = narrow, self.opened, self.narrow_results
        if state == self._layout_state:
            return
        self._layout_state = state
        visible = self.opened and (not narrow or self.narrow_results)
        self.content.setVisible(not (narrow and visible))
        self.panel.setVisible(visible)
        self.owner.bookmark_action.setChecked(visible)
        if visible and not narrow:
            self.workspace.setSizes([260, max(1, self.owner.width() - 260)])

    def show_document(self):
        doc = self.owner.current_document()
        document_id = doc.document_id if doc is not None else None
        if self.displayed_id != document_id:
            selected = self.panel.tree.currentItem()
            self.states[self.displayed_id] = ([i for i, item in enumerate(self.items) if item.isExpanded()],
                                             self.items.index(selected) if selected in self.items else -1)
            self.latest_jump = None
            self.displayed_id = document_id
            self.panel.tree.clear()
            self.items = []
        if not self.opened:
            return
        if doc is None or not doc.ready:
            self.panel.status.setText(tr('請先開啟 PDF 檔案'))
            self.panel.status.show()
            return
        if doc.bookmarks is not None:
            self.populate(doc)
            return
        self.panel.status.setText(tr('正在載入書籤…'))
        self.panel.status.show()
        if not any(value == (doc.document_id, 'bookmarks', False) for value in self.requests.values()):
            self._request(doc, 'bookmarks')

    def _request(self, doc, kind, destination=None, fullscreen=False):
        self.owner._next_generation += 1
        generation = self.owner._next_generation
        self.requests = {key: value for key, value in self.requests.items()
                         if value[:2] != (doc.document_id, kind)}
        self.requests[generation] = doc.document_id, kind, fullscreen
        if kind == 'navigate':
            self.latest_jump = generation
        self.owner.render_service.request_navigation(doc.source_path, doc.document_id, generation, kind,
                                                     destination=destination, password=doc.password)
        return generation

    def populate(self, doc):
        if self.items:
            return
        self.panel.tree.clear()
        parents = []
        remembered = self.states.get(doc.document_id)
        for index, bookmark in enumerate(doc.bookmarks):
            level = min(bookmark['level'], len(parents))
            parents = parents[:level]
            parent = parents[-1] if parents else self.panel.tree
            title = bookmark['title'] or tr('未命名書籤')
            item = QTreeWidgetItem(parent, [title])
            item.setData(0, Qt.ItemDataRole.UserRole, bookmark['destination'])
            item.setToolTip(0, title)
            self.items.append(item)
            parents.append(item)
        if remembered and 0 <= remembered[1] < len(self.items):
            self.panel.tree.setCurrentItem(self.items[remembered[1]])
        for index, (item, bookmark) in enumerate(zip(self.items, doc.bookmarks)):
            item.setExpanded(index in remembered[0] if remembered else bookmark['expanded'])
        self.panel.status.setText(tr('此 PDF 沒有內建書籤'))
        self.panel.status.setVisible(not bool(doc.bookmarks))

    def _clicked(self, item, _column=0):
        destination = item.data(0, Qt.ItemDataRole.UserRole)
        doc = self.owner.current_document()
        if destination is not None and doc is not None:
            self.activate(doc, destination)

    def activate(self, doc, destination, fullscreen=False):
        if doc.ready and doc is self.owner.current_document():
            if 'url' in destination:
                url = QUrl(destination['url'], QUrl.ParsingMode.StrictMode)
                if (url.isValid() and url.scheme().lower() in ('http', 'https') and url.host()
                        and not any(ord(c) < 32 or ord(c) == 127 for c in destination['url'])):
                    if not QDesktopServices.openUrl(url):
                        self.owner.statusBar().showMessage(tr('無法開啟連結：{p0}', p0=destination['url']))
                return
            self._request(doc, 'navigate', destination, fullscreen)

    def receive(self, payload):
        generation = payload.get('generation')
        request = self.requests.get(generation)
        if request is None:
            return False
        document_id, kind, fullscreen = request
        doc = self.owner.documents.get(document_id)
        message_type = payload.get('type')
        if message_type in ('done', 'error'):
            self.requests.pop(generation, None)
        if doc is None or self.owner._closing:
            return True
        if message_type == 'bookmarks':
            doc.bookmarks = payload['bookmarks']
            if doc.document_id == self.displayed_id:
                self.populate(doc)
        elif message_type == 'navigate' and generation == self.latest_jump and doc is self.owner.current_document():
            page = payload['page']
            doc.page_labels[page] = payload.get('page_label')
            doc.page_sizes[page] = payload['width_points'], payload['height_points']
            doc._reflow_grid()
            self.owner.search_controller.clear_highlights()
            viewer = self.owner._fullscreen_preview
            if fullscreen and viewer is not None and viewer.document is doc:
                viewer.show_page(page)
            else:
                self.narrow_results = False
                self.layout()
                doc.jump_to_page(page, payload['point'])
        elif message_type == 'error':
            message = tr('無法載入 PDF 導航：{p0}', p0=payload.get('message', ''))
            if doc.document_id == self.displayed_id and kind == 'bookmarks':
                self.panel.status.setText(message)
                self.panel.status.show()
            self.owner.statusBar().showMessage(message)
        return True

    def remove_document(self, doc):
        self.states.pop(doc.document_id, None)
        self.requests = {key: value for key, value in self.requests.items() if value[0] != doc.document_id}
        if self.displayed_id == doc.document_id:
            self.displayed_id = None
            self.items = []
            self.panel.tree.clear()
        for prefix in (-3_000_000, -4_000_000):
            self.owner.render_service.cancel_pending(prefix - doc.document_id)

    def retranslate(self):
        self.panel.tree.setAccessibleName(tr('PDF 書籤'))
        if self.opened:
            self.show_document()
