"""Bookmark/annotation sidebar, internal navigation and web links."""

from html import escape

from PySide6.QtCore import QEvent, QObject, QSize, Qt, QUrl
from repdf.shortcut_hints import shortcut_tooltip

from PySide6.QtGui import QKeySequence, QDesktopServices
from PySide6.QtWidgets import (QApplication, QHBoxLayout, QLabel, QLayout, QSplitter, QToolButton,
                               QTreeWidgetItem, QVBoxLayout, QWidget, QPlainTextEdit)

from repdf.icons import toolbar_icon, annotation_icon
from repdf.annotation_tree import AnnotationTree, copy_tooltip
from repdf.strings import tr, localize_text
from repdf.renderer import RenderService, start_render_backend


class BookmarkPanel(QWidget):
    def __init__(self):
        super().__init__()
        self.setMinimumSize(0, 0)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)
        layout.setSizeConstraint(QLayout.SizeConstraint.SetNoConstraint)
        row = QHBoxLayout()
        self.title = QLabel(tr('書籤'))
        row.addWidget(self.title, 1)
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
        self.tree = AnnotationTree()
        self.tree.setHeaderHidden(True)
        self.tree.setAccessibleName(tr('PDF 書籤'))
        self.tree.setMinimumSize(0, 0)
        self.tree.setIndentation(16)
        self.tree.setIconSize(QSize(20, 20))
        self.tree.setTextElideMode(Qt.TextElideMode.ElideRight)
        self.tree.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        layout.addWidget(self.tree, 1)
        self.text_panel = QWidget()
        text_layout = QVBoxLayout(self.text_panel)
        text_layout.setContentsMargins(0, 0, 0, 0)
        text_layout.setSpacing(4)
        header = QHBoxLayout()
        self.annotation_text_title = QLabel(tr('註解文字'))
        header.addWidget(self.annotation_text_title, 1)
        self.select_text_button = QToolButton()
        self.copy_text_button = QToolButton()
        for button, label, icon in [(self.select_text_button, '全選註解文字', 'select_all_text'),
                                     (self.copy_text_button, '複製註解文字', 'copy')]:
            button.setFixedSize(34, 34)
            button.setIconSize(QSize(20, 20))
            button.setIcon(toolbar_icon(icon))
            button.setToolTip(copy_tooltip() if icon == 'copy' else shortcut_tooltip(tr(label), QKeySequence.keyBindings(QKeySequence.StandardKey.SelectAll)))
            button.setAccessibleName(tr(label))
            header.addWidget(button)
        text_layout.addLayout(header)
        self.annotation_text = QPlainTextEdit()
        self.annotation_text.setObjectName('annotationText')
        self.annotation_text.setAccessibleName(tr('註解文字'))
        self.annotation_text.setReadOnly(True)
        self.annotation_text.setMinimumHeight(0)
        self.annotation_text.setMaximumHeight(140)
        text_layout.addWidget(self.annotation_text)
        layout.addWidget(self.text_panel)
        self.text_panel.hide()
        self.select_text_button.clicked.connect(self.select_annotation_text)
        self.copy_text_button.clicked.connect(self.copy_annotation_text)
        self.tree.currentItemChanged.connect(self.show_annotation_text)

    def show_annotation_text(self, item, _previous=None):
        if item is not None and item.childCount():
            item = item.child(0)
        text = item.data(0, Qt.ItemDataRole.UserRole + 2) if item is not None else ''
        text = text or ''
        if self.annotation_text.toPlainText() != text:
            self.annotation_text.setPlainText(text)
        self.text_panel.setVisible(bool(text.strip()))

    def select_annotation_text(self):
        self.annotation_text.setFocus()
        self.annotation_text.selectAll()

    def copy_annotation_text(self):
        cursor = self.annotation_text.textCursor()
        text = cursor.selectedText().replace('\u2029', '\n') if cursor.hasSelection() else self.annotation_text.toPlainText()
        if text:
            QApplication.clipboard().setText(text)

    def changeEvent(self, event):
        super().changeEvent(event)
        if event.type() == QEvent.Type.PaletteChange and hasattr(self, 'close_button'):
            self.close_button.setIcon(toolbar_icon('close'))
            if hasattr(self, 'copy_text_button'):
                self.copy_text_button.setIcon(toolbar_icon('copy'))
                self.select_text_button.setIcon(toolbar_icon('select_all_text'))
                for index in range(self.tree.topLevelItemCount()):
                    group = self.tree.topLevelItem(index)
                    for child_index in range(group.childCount()):
                        item = group.child(child_index)
                        kind = item.data(0, Qt.ItemDataRole.UserRole + 1)
                        if kind:
                            item.setIcon(0, annotation_icon(kind))


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
        self.kind = 'bookmarks'
        self.displayed_kind = None
        self.annotation_service = None
        self.items = []
        self.annotation_groups = {}
        self.states = {}
        self.requests = {}
        self.latest_jump = None
        self.annotation_selection = None
        self.pending_annotation_copy = None
        self._layout_state = None
        self.panel.close_button.clicked.connect(self.close)
        self.panel.tree.textCopied.connect(lambda text: self.owner.statusBar().showMessage(tr('已複製 {p0} 個字元到剪貼簿', p0=len(text))))
        self.panel.tree.itemClicked.connect(self._clicked)
        self.panel.tree.itemActivated.connect(self._clicked)

    def toggle(self, kind='bookmarks'):
        if self.panel.isVisible() and self.kind == kind:
            self.close()
        else:
            self.open(kind)

    def open(self, kind='bookmarks', *, keep_fullscreen=False):
        if kind != self.kind:
            if self.kind == 'annotations':
                self._clear_annotation_selection()
            self._cancel_annotations()
        self.kind = kind
        if self.owner._fullscreen_preview is not None and not keep_fullscreen:
            self.owner._fullscreen_preview.close()
        self.owner.search_controller.close()
        self.opened = True
        self.narrow_results = True
        self.layout()
        self.show_document()
        self.panel.tree.setFocus()

    def close(self):
        if self.kind == 'annotations':
            self._clear_annotation_selection()
        self._cancel_annotations()
        self.opened = False
        self.layout()

    def _clear_annotation_selection(self):
        self.owner.annotation_editor.finish_text(True)
        self.owner.annotation_editor.clear()
        self.annotation_selection = None
        self.pending_annotation_copy = None
        self.latest_jump = None
        for doc in self.owner.documents.values():
            doc.pages.set_annotation_highlight(None, None)

    def layout(self):
        narrow = self.owner.width() < 640
        state = narrow, self.opened, self.narrow_results, self.kind
        if state == self._layout_state:
            return
        self._layout_state = state
        visible = self.opened and (not narrow or self.narrow_results)
        self.content.setVisible(not (narrow and visible))
        self.panel.setVisible(visible)
        self.owner.bookmark_action.setChecked(visible and self.kind == 'bookmarks')
        self.owner.annotation_action.setChecked(visible and self.kind == 'annotations')
        if visible and not narrow:
            self.workspace.setSizes([260, max(1, self.owner.width() - 260)])

    def show_document(self):
        doc = self.owner.current_document()
        document_id = doc.document_id if doc is not None else None
        if self.pending_annotation_copy is not None and self.pending_annotation_copy[0] != document_id:
            self.pending_annotation_copy = None
        if (self.displayed_id, self.displayed_kind) != (document_id, self.kind):
            self._cancel_annotations()
            self._remember_state()
            self.latest_jump = None
            self.displayed_id = document_id
            self.displayed_kind = self.kind
            self.panel.tree.clear()
            self.items = []
            self.annotation_groups = {}
        annotations = self.kind == 'annotations'
        self.panel.title.setText(tr('註解' if annotations else '書籤'))
        self.panel.annotation_text_title.setText(tr('註解文字'))
        self.panel.annotation_text.setAccessibleName(tr('註解文字'))
        for button, label in [(self.panel.select_text_button, '全選註解文字'), (self.panel.copy_text_button, '複製註解文字')]:
            button.setToolTip(copy_tooltip() if button is self.panel.copy_text_button else shortcut_tooltip(tr(label), QKeySequence.keyBindings(QKeySequence.StandardKey.SelectAll)))
            button.setAccessibleName(tr(label))
        close_label = tr('關閉註解窗格' if annotations else '關閉書籤窗格')
        self.panel.close_button.setText(close_label)
        self.panel.close_button.setToolTip(close_label)
        self.panel.close_button.setAccessibleName(close_label)
        self.panel.tree.setAccessibleName(tr('PDF 註解' if annotations else 'PDF 書籤'))
        self.panel.tree.setRootIsDecorated(True)
        self.panel.tree.setIndentation(16)
        if not self.opened:
            return
        if doc is None or not doc.ready:
            self.panel.status.setText(tr('請先開啟 PDF 檔案'))
            self.panel.status.show()
            return
        if getattr(doc, self.kind) is not None:
            self.populate(doc)
            return
        self.panel.status.setText(tr('正在載入註解…' if annotations else '正在載入書籤…'))
        self.panel.status.show()
        if not any(value == (doc.document_id, self.kind, False) for value in self.requests.values()):
            self._request(doc, self.kind)

    def _request(self, doc, kind, destination=None, fullscreen=False):
        self.owner._next_generation += 1
        generation = self.owner._next_generation
        self.requests = {key: value for key, value in self.requests.items()
                         if value[:2] != (doc.document_id, kind)}
        self.requests[generation] = doc.document_id, kind, fullscreen
        if kind == 'navigate':
            self.latest_jump = generation
        service = self.owner.render_service
        if kind == 'annotations':
            try:
                if self.annotation_service is None:
                    self.annotation_service = RenderService(start_render_backend(), self)
                    self.annotation_service.message.connect(self.receive, Qt.ConnectionType.QueuedConnection)
                service = self.annotation_service
            except (OSError, RuntimeError) as exc:
                self.receive({'type': 'error', 'generation': generation, 'message': str(exc)})
                return generation
        service.request_navigation(doc.source_path, doc.document_id, generation, kind,
                                                     destination=destination, password=doc.password)
        return generation

    def populate(self, doc):
        if self.items:
            return
        self.panel.tree.clear()
        if self.kind == 'annotations':
            self.populate_annotations(doc)
            return
        parents = []
        remembered = self.states.get((doc.document_id, self.kind))
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

    def populate_annotations(self, doc):
        counts = {}
        first_destinations = {}
        for annotation in doc.annotations:
            page = annotation['page']
            counts[page] = counts.get(page, 0) + 1
            first_destinations.setdefault(page, annotation['destination'])
        for page, count in counts.items():
            title = tr('第 {page} 頁（{count} 則註解）', page=page + 1, count=count)
            group = QTreeWidgetItem(self.panel.tree, [title])
            group.setToolTip(0, title)
            group.setData(0, Qt.ItemDataRole.UserRole, first_destinations[page])
            self.annotation_groups[page] = group
        for annotation in doc.annotations:
            summary = ' '.join((annotation['contents'] or annotation['subject'] or tr('沒有文字內容')).split())
            item = QTreeWidgetItem(self.annotation_groups[annotation['page']], [summary])
            item.setIcon(0, annotation_icon(annotation['kind']))
            item.setData(0, Qt.ItemDataRole.UserRole + 1, annotation['kind'])
            item.setData(0, Qt.ItemDataRole.UserRole + 2, annotation['contents'])
            item.setData(0, Qt.ItemDataRole.AccessibleTextRole, tr(annotation['kind']) + ' · ' + summary)
            item.setData(0, Qt.ItemDataRole.UserRole, annotation['destination'])
            item.setToolTip(0,self.annotation_tooltip(doc,annotation))
            self.items.append(item)
        remembered = self.states.get((doc.document_id, self.kind))
        if remembered and 0 <= remembered[1] < len(self.items):
            self.panel.tree.setCurrentItem(self.items[remembered[1]])
        for page, group in self.annotation_groups.items():
            group.setExpanded(remembered is not None and page in remembered[0])
        self._select_annotation_item(doc)
        self.panel.status.setText(tr('共 {count} 則註解', count=len(doc.annotations)) if doc.annotations else tr('此 PDF 沒有註解'))
        self.panel.status.show()

    def annotation_tooltip(self, doc, annotation):
        details=[tr(annotation['kind']),annotation['contents'] or tr('沒有文字內容')]
        reasons=doc.annotation_store.reasons.get(annotation['page'],{})
        reason=reasons.get(annotation['index']) or reasons.get(str(annotation['index'])) or reasons.get(-1) or reasons.get('-1')
        if reason:
            details.append(tr('此註解僅供檢視：{reason}',reason=localize_text(reason)))
        for key,label in [('author','作者：{value}'),('subject','主旨：{value}'),('modified','修改時間：{value}')]:
            if annotation.get(key): details.append(tr(label,value=annotation[key]))
        return '<qt>'+'<br>'.join(escape(line).replace('\n','<br>') for line in details)+'</qt>'

    def refresh_annotation_tooltips(self,doc):
        if self.kind=='annotations' and self.displayed_id==doc.document_id:
            for item,annotation in zip(self.items,doc.annotations or []):
                item.setToolTip(0,self.annotation_tooltip(doc,annotation))

    def _remember_state(self):
        selected = self.panel.tree.currentItem()
        expanded = ([page for page, group in self.annotation_groups.items() if group.isExpanded()]
                    if self.displayed_kind == 'annotations'
                    else [i for i, item in enumerate(self.items) if item.isExpanded()])
        self.states[self.displayed_id, self.displayed_kind] = (
            expanded, self.items.index(selected) if selected in self.items else -1)

    def _clicked(self, item, _column=0):
        if self.kind=="bookmarks":
            self.owner.annotation_editor.clear()
        self.annotation_selection = None
        destination = item.data(0, Qt.ItemDataRole.UserRole)
        doc = self.owner.current_document()
        if destination is not None and doc is not None:
            self.activate(doc, destination)
            if self.kind == 'annotations':
                target = item if item in self.items else item.child(0)
                if target in self.items:
                    annotation = doc.annotations[self.items.index(target)]
                    self.pending_annotation_copy = doc.document_id, annotation['page'], annotation['index']
                    if annotation.get('annotation_id'):
                        self.owner.annotation_editor.select(doc,annotation['annotation_id'])
                    else:
                        self.owner.annotation_editor.select_target(doc,annotation['page'],annotation['index'])

    def activate(self, doc, destination, fullscreen=False):
        if doc.ready and doc is self.owner.current_document():
            self.pending_annotation_copy = None
            if 'annotation_index' in destination:
                self.latest_jump = None
                doc._search_navigation = None
                self.annotation_selection = doc.document_id, destination['page'], destination['annotation_index']
                self.pending_annotation_copy = self.annotation_selection
                self.open('annotations', keep_fullscreen=fullscreen)
                self.narrow_results = False
                self.layout()
                self._select_annotation_item(doc)
                self.owner.search_controller.clear_highlights()
                doc.pages.set_annotation_highlight(destination['page'], destination.get('annotation_rect'))
                self.owner.annotation_editor.select_target(doc,destination['page'],destination['annotation_index'])
                doc._focus_page(destination['page'])
                return
            if 'url' in destination:
                url = QUrl(destination['url'], QUrl.ParsingMode.StrictMode)
                if (url.isValid() and url.scheme().lower() in ('http', 'https') and url.host()
                        and not any(ord(c) < 32 or ord(c) == 127 for c in destination['url'])):
                    if not QDesktopServices.openUrl(url):
                        self.owner.statusBar().showMessage(tr('無法開啟連結：{p0}', p0=destination['url']))
                return
            self._request(doc, 'navigate', destination, fullscreen)

    def _select_annotation_item(self, doc):
        if (self.annotation_selection is None or self.kind != 'annotations'
                or self.displayed_id != doc.document_id or doc.annotations is None):
            return
        for annotation, item in zip(doc.annotations, self.items):
            if self.annotation_selection == (doc.document_id, annotation['page'], annotation['index']):
                item.parent().setExpanded(True)
                self.panel.tree.setCurrentItem(item)
                self.panel.tree.scrollToItem(item)
                self._copy_pending_annotation(doc)
                break

    def _copy_pending_annotation(self, doc):
        if doc.annotations is None or doc is not self.owner.current_document():
            return
        for annotation in doc.annotations:
            if self.pending_annotation_copy == (doc.document_id, annotation['page'], annotation['index']):
                self.pending_annotation_copy = None
                text = annotation['contents']
                if text.strip():
                    QApplication.clipboard().setText(text)
                    self.owner.statusBar().showMessage(tr('已複製 {p0} 個字元到剪貼簿', p0=len(text)))
                break

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
        if message_type in ('bookmarks', 'annotations'):
            setattr(doc, message_type, payload[message_type])
            if message_type == "annotations":
                doc._annotation_base = payload[message_type]
                self.owner.annotation_editor.merge_list(doc)
            if doc.document_id == self.displayed_id and self.kind == message_type:
                self.populate(doc)
        elif message_type == 'navigate' and generation == self.latest_jump and doc is self.owner.current_document():
            page = payload['page']
            doc.page_labels[page] = payload.get('page_label')
            doc.page_sizes[page] = payload['width_points'], payload['height_points']
            doc._reflow_grid()
            self.owner.search_controller.clear_highlights()
            doc.pages.set_annotation_highlight(page, payload.get('annotation_rect'))
            editable=self.owner.annotation_editor.current()
            if editable is not None and editable['page']==page:
                doc.pages.set_annotation_highlight(None,None)
            self._copy_pending_annotation(doc)
            viewer = self.owner._fullscreen_preview
            if fullscreen and viewer is not None and viewer.document is doc:
                viewer.show_page(page)
            else:
                self.narrow_results = False
                self.layout()
                doc.jump_to_page(page, payload['point'])
        elif message_type == 'error':
            message = tr('無法載入註解：{p0}' if kind == 'annotations' else '無法載入 PDF 導航：{p0}',
                         p0=payload.get('message', ''))
            if doc.document_id == self.displayed_id and kind == self.kind:
                self.panel.status.setText(message)
                self.panel.status.show()
            self.owner.statusBar().showMessage(message)
        return True

    def remove_document(self, doc):
        if self.annotation_selection is not None and self.annotation_selection[0] == doc.document_id:
            self.annotation_selection = None
        if self.pending_annotation_copy is not None and self.pending_annotation_copy[0] == doc.document_id:
            self.pending_annotation_copy = None
        if self.displayed_id == doc.document_id or any(
                value[:2] == (doc.document_id, 'annotations') for value in self.requests.values()):
            self._cancel_annotations()
        for kind in ('bookmarks', 'annotations'):
            self.states.pop((doc.document_id, kind), None)
        self.requests = {key: value for key, value in self.requests.items() if value[0] != doc.document_id}
        if self.displayed_id == doc.document_id:
            self.displayed_id = None
            self.items = []
            self.annotation_groups = {}
            self.panel.tree.clear()
        for prefix in (-3_000_000, -4_000_000):
            self.owner.render_service.cancel_pending(prefix - doc.document_id)

    def retranslate(self):
        if self.kind == 'annotations':
            self._remember_state()
            self.panel.tree.clear()
            self.items = []
            self.annotation_groups = {}
        if self.opened:
            self.show_document()

    def _cancel_annotations(self):
        self.requests = {key: value for key, value in self.requests.items() if value[1] != 'annotations'}
        service, self.annotation_service = self.annotation_service, None
        if service is not None:
            service.close(terminate_tree=True)
            service.deleteLater()

    def shutdown(self):
        self._cancel_annotations()
