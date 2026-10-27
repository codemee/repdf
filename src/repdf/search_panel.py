"""Search sidebar and its cancellable, independent background service."""

from html import escape
from dataclasses import dataclass, field
from pathlib import Path

from PySide6.QtCore import QEvent, QObject, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QAction, QActionGroup, QColor, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView, QColorDialog, QComboBox, QGroupBox, QHeaderView, QHBoxLayout, QLabel, QLayout, QLineEdit,
    QTreeWidget, QTreeWidgetItem, QMenu, QSplitter, QStyle, QStyledItemDelegate, QStyleOptionViewItem,
    QToolButton, QVBoxLayout, QWidget,
)

from repdf.icons import toolbar_icon
from repdf.renderer import RenderService, start_render_backend
from repdf.search import compile_query
from repdf.strings import tr


@dataclass
class SearchTarget:
    source_path: Path
    page_order: list[int] | None
    password: str | None = field(default=None, repr=False)
    stamp: tuple[int, int] | None = field(init=False, default=None)

    def __post_init__(self):
        try:
            stat = self.source_path.stat()
            self.stamp = stat.st_mtime_ns, stat.st_size
        except OSError:
            pass


class SearchStatus(QLabel):
    def __init__(self, text):
        super().__init__()
        self.setText(text)

    def setText(self, text):
        super().setText(text)
        self.setToolTip('<qt>' + escape(text).replace('\n', '<br>') + '</qt>')


class ResultRowDelegate(QStyledItemDelegate):
    def sizeHint(self, option, index):
        hint = super().sizeHint(option, index)
        return QSize(hint.width(), option.fontMetrics.height() + 4)


class ParagraphDelegate(ResultRowDelegate):
    """Keep complete result text in the model, but paint one elided line."""

    @staticmethod
    def elided_text(text, metrics, width):
        text = ' '.join(text.split())
        if metrics.horizontalAdvance(text) <= width:
            return text
        # Qt normally uses a single ellipsis glyph; the sidebar uses three dots.
        budget = width - max(0, metrics.horizontalAdvance('...') - metrics.horizontalAdvance('…'))
        elided = metrics.elidedText(text, Qt.TextElideMode.ElideRight, max(0, budget))
        return elided[:-1] + '...' if elided.endswith('…') else ''

    def paint(self, painter, option, index):
        opt = QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)
        style = opt.widget.style()
        rect = style.subElementRect(QStyle.SubElement.SE_ItemViewItemText, opt, opt.widget)
        opt.text = self.elided_text(opt.text, opt.fontMetrics, rect.width())
        opt.textElideMode = Qt.TextElideMode.ElideNone
        style.drawControl(QStyle.ControlElement.CE_ItemViewItem, opt, painter, opt.widget)

    def sizeHint(self, option, index):
        return QSize(0, option.fontMetrics.height() + 4)


class SearchPanel(QWidget):
    highlight_color_changed = Signal(str)

    def _button(self, kind, label):
        button = QToolButton()
        button.setText(tr(label))
        button.setToolTip(tr(label))
        button.setAccessibleName(tr(label))
        button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
        button.setFixedSize(34, 34)
        button.setIconSize(QSize(20, 20))
        self._icon_buttons.append((button, kind))
        return button

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName('searchPanel')
        self.setMinimumSize(0, 0)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(6)
        layout.setSizeConstraint(QLayout.SizeConstraint.SetNoConstraint)
        self._icon_buttons = []
        self.highlight_color = '#ffe13c'
        self.close_button = self._button('close', '關閉搜尋窗格')
        row = QHBoxLayout()
        self.query = QLineEdit()
        self.query.setPlaceholderText(tr('輸入文字或規則表達式'))
        self.query.setAccessibleName(tr('搜尋文字'))
        self.query.setClearButtonEnabled(True)
        self.query.setMinimumWidth(0)
        self.search_button = self._button('search', '搜尋')
        self.search_button.setToolTip(tr('搜尋（搜尋欄中按 Enter）'))
        self.stop_button = self._button('stop', '停止')
        self.stop_button.setEnabled(False)
        row.addWidget(self.query, 1)
        row.addWidget(self.search_button)
        row.addWidget(self.stop_button)
        row.addWidget(self.close_button)
        layout.addLayout(row)
        self.scope = QComboBox()
        self.scope.setAccessibleName(tr('搜尋範圍'))
        self.scope.addItems([tr('目前標籤頁'), tr('勾選的標籤頁'), tr('所有標籤頁'), tr('目前標籤所在的資料夾')])
        self.scope.setToolTip(self.scope.currentText())
        self.scope.currentTextChanged.connect(self.scope.setToolTip)
        self.scope.setMinimumWidth(0)
        self.options_box = QWidget()
        options = QHBoxLayout(self.options_box)
        options.setContentsMargins(0, 0, 0, 0)
        options.setSpacing(4)
        options.addWidget(self.scope, 1)
        self.regular_expression = self._button('regex', '規則表達式')
        self.case_sensitive = self._button('case_sensitive', '區分大小寫')
        self.whole_word = self._button('whole_word', '僅限單字')
        for button in (self.regular_expression, self.case_sensitive, self.whole_word):
            button.setObjectName('searchOptionButton')
            button.setCheckable(True)
            button.setProperty('stateButton', True)
            button.setAttribute(Qt.WidgetAttribute.WA_Hover, True)
        options.addWidget(self.regular_expression)
        options.addWidget(self.case_sensitive)
        options.addWidget(self.whole_word)
        self.highlight_color_button = self._button('highlight_color', '命中標示顏色')
        self.highlight_color_button.clicked.connect(self.choose_highlight_color)
        options.addWidget(self.highlight_color_button)
        layout.addWidget(self.options_box)
        status_row = QHBoxLayout()
        self.compact_options = self._button('more', '選項')
        self.compact_options.setStyleSheet('QToolButton::menu-indicator { image: none; }')
        self.compact_options.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        menu = QMenu(self.compact_options)
        self.scope_menu = menu.addMenu(tr('搜尋範圍'))
        scope_group = QActionGroup(menu)
        self.scope_actions = []
        for i in range(self.scope.count()):
            action = self.scope_menu.addAction(self.scope.itemText(i))
            action.setCheckable(True)
            action.setChecked(i == self.scope.currentIndex())
            scope_group.addAction(action)
            action.triggered.connect(lambda _checked=False, index=i: self.scope.setCurrentIndex(index))
            self.scope_actions.append(action)
        self.scope.currentIndexChanged.connect(lambda index: self.scope_actions[index].setChecked(True))
        for button in (self.regular_expression, self.case_sensitive, self.whole_word):
            action = QAction(button.text(), menu)
            action.setCheckable(True)
            action.toggled.connect(button.setChecked)
            button.toggled.connect(action.setChecked)
            menu.addAction(action)
        self.highlight_color_action = menu.addAction(tr('命中標示顏色'))
        self.highlight_color_action.triggered.connect(self.choose_highlight_color)
        self.compact_options.setMenu(menu)
        self.compact_options.hide()
        status_row.addWidget(self.compact_options)
        self.status = SearchStatus(tr('輸入條件後按 Enter 或搜尋鈕'))
        self.status.setTextFormat(Qt.TextFormat.PlainText)
        self.status.setMaximumHeight(36)
        self.status.setWordWrap(True)
        status_row.addWidget(self.status, 1)
        layout.addLayout(status_row)
        self.results_splitter = QSplitter(Qt.Orientation.Vertical)
        self.files = QTreeWidget()
        self.files.setAccessibleName(tr('有命中的檔案'))
        self.files.setHeaderLabels([tr('檔名'), tr('筆數')])
        self.files.headerItem().setTextAlignment(1, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.files.header().setStretchLastSection(False)
        self.files.header().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.files.header().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.files.setTextElideMode(Qt.TextElideMode.ElideMiddle)
        self.files.setItemDelegate(ResultRowDelegate(self.files))
        self.paragraphs = QTreeWidget()
        self.paragraphs.setAccessibleName(tr('命中段落'))
        self.paragraphs.setHeaderLabels([tr('頁碼'), tr('段落')])
        self.paragraphs.headerItem().setTextAlignment(0, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.paragraphs.header().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.paragraphs.header().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.paragraphs.setItemDelegate(ResultRowDelegate(self.paragraphs))
        self.paragraphs.setItemDelegateForColumn(1, ParagraphDelegate(self.paragraphs))
        self.paragraphs.setAlternatingRowColors(True)
        self.result_groups = []
        for table, title in ((self.files, '檔案'), (self.paragraphs, '命中項目')):
            table.setRootIsDecorated(False)
            table.setItemsExpandable(False)
            table.setUniformRowHeights(True)
            table.setWordWrap(False)
            table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
            table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
            table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
            table.setMinimumSize(0, 0)
            table.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
            table.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
            table.header().setMinimumSectionSize(40)
            table.header().setSectionsMovable(False)
            header_font = table.header().font()
            header_font.setBold(True)
            table.header().setFont(header_font)
            group = QGroupBox(tr(title))
            group.setMinimumSize(0, 0)
            group_layout = QVBoxLayout(group)
            group_layout.setContentsMargins(6, 8, 6, 6)
            group_layout.addWidget(table)
            self.result_groups.append(group)
            self.results_splitter.addWidget(group)
        self.results_splitter.setSizes([140, 260])
        layout.addWidget(self.results_splitter, 1)
        self.refresh_icons()

    def refresh_icons(self):
        for button, kind in self._icon_buttons:
            button.setIcon(self._highlight_icon() if kind == 'highlight_color' else toolbar_icon(kind))
        if hasattr(self, 'highlight_color_action'):
            self.highlight_color_action.setIcon(self._highlight_icon())

    def _highlight_icon(self):
        pixmap = QPixmap(48, 48)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        painter.scale(2, 2)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(self.palette().buttonText().color())
        painter.setBrush(QColor(self.highlight_color))
        painter.drawRoundedRect(4, 4, 16, 16, 2, 2)
        painter.end()
        return QIcon(pixmap)

    def set_highlight_color(self, color):
        color = QColor(str(color))
        if not color.isValid():
            color = QColor('#ffe13c')
        value = color.name()
        changed = value != self.highlight_color
        self.highlight_color = value
        self.refresh_icons()
        if changed:
            self.highlight_color_changed.emit(value)

    def choose_highlight_color(self):
        color = QColorDialog.getColor(QColor(self.highlight_color), self, tr('命中標示顏色'),
                                     QColorDialog.ColorDialogOption.DontUseNativeDialog)
        if color.isValid():
            self.set_highlight_color(color.name())

    def changeEvent(self, event):
        super().changeEvent(event)
        if event.type() == QEvent.Type.PaletteChange and hasattr(self, '_icon_buttons'):
            self.refresh_icons()

    def retranslate(self):
        index = self.scope.currentIndex()
        for i, label in enumerate(('目前標籤頁', '勾選的標籤頁', '所有標籤頁', '目前標籤所在的資料夾')):
            self.scope.setItemText(i, tr(label))
            self.scope_actions[i].setText(tr(label))
        self.scope_menu.setTitle(tr('搜尋範圍'))
        self.highlight_color_action.setText(tr('命中標示顏色'))
        self.scope.setCurrentIndex(index)
        self.query.setPlaceholderText(tr('輸入文字或規則表達式'))
        self.files.setHeaderLabels([tr('檔名'), tr('筆數')])
        self.paragraphs.setHeaderLabels([tr('頁碼'), tr('段落')])
        for group, title in zip(self.result_groups, ('檔案', '命中項目')):
            group.setTitle(tr(title))

    def set_compact(self, compact):
        self.options_box.setVisible(not compact)
        self.compact_options.setVisible(compact)
        self.status.setMaximumHeight(24 if compact else 36)


class SearchController(QObject):
    def __init__(self, owner, content):
        super().__init__(owner)
        self.owner = owner
        self.content = content
        self.panel = SearchPanel()
        self.workspace = QSplitter(Qt.Orientation.Horizontal)
        self.workspace.setChildrenCollapsible(False)
        self.workspace.addWidget(content)
        self.workspace.addWidget(self.panel)
        self.workspace.setStretchFactor(0, 1)
        self.workspace.setStretchFactor(1, 0)
        self.panel.hide()
        self.opened = False
        self.narrow_results = True
        self._layout_state = None
        self.service = None
        self.generation = 0
        self.results = {}
        self.targets = {}
        self.folder_search = False
        self.pending_activation = None
        self.order = []
        self.page_orders = {}
        self.pending = set()
        self.failures = {}
        self.zero_width = {}
        self.params = {}
        self.selected = None
        self._refresh_timer = QTimer(self)
        self._refresh_timer.setSingleShot(True)
        self._refresh_timer.setInterval(100)
        self._refresh_timer.timeout.connect(self._refresh_files)
        p = self.panel
        p.set_highlight_color(owner.settings.value('search/highlight_color', '#ffe13c'))
        self.highlight_color = p.highlight_color
        p.highlight_color_changed.connect(self._set_highlight_color)
        p.query.returnPressed.connect(self.start)
        p.search_button.clicked.connect(self.start)
        p.stop_button.clicked.connect(self.stop)
        p.close_button.clicked.connect(self.close)
        p.files.currentItemChanged.connect(self._show_paragraphs)
        p.files.currentItemChanged.connect(self._activate_file)
        p.files.itemClicked.connect(self._activate_file)
        p.files.itemActivated.connect(self._activate_file)
        p.paragraphs.itemClicked.connect(self._activate_item)
        p.paragraphs.itemActivated.connect(self._activate_item)

    def _set_highlight_color(self, color):
        self.highlight_color = color
        self.owner.settings.setValue('search/highlight_color', color)
        for doc in self.owner.documents.values():
            for card in doc.page_cards:
                card.preview.set_search_highlight_color(color)
        viewer = self.owner._fullscreen_preview
        if viewer is not None:
            for label in viewer.labels.values():
                label.set_search_highlight_color(color)

    def open(self):
        self.owner.navigation.close()
        if self.owner._fullscreen_preview is not None:
            self.owner._fullscreen_preview.close()
        self.opened = True
        self.narrow_results = True
        self.layout()
        self.panel.query.setFocus()
        self.panel.query.selectAll()
        QTimer.singleShot(0, self._focus_query)

    def _focus_query(self):
        if not self.owner._closing and self.opened and self.panel.isVisible():
            # A popup can retain the active-window state after its action runs,
            # especially on macOS. Return activation before assigning focus.
            self.owner.activateWindow()
            self.panel.query.setFocus()
            self.panel.query.selectAll()

    def close(self):
        self.stop()
        self.opened = False
        self.clear_highlights()
        self.layout()

    def layout(self):
        narrow = self.owner.width() < 640
        self.panel.set_compact(self.owner.height() < 360)
        state = (narrow, self.opened, self.narrow_results)
        if state == self._layout_state:
            return
        self._layout_state = state
        self.content.setVisible(not (narrow and self.opened and self.narrow_results))
        self.panel.setVisible(self.opened and (not narrow or self.narrow_results))
        if not narrow and self.opened:
            self.workspace.setSizes([max(1, self.owner.width() - 320), 320])

    def _end_service(self):
        if self.service is not None:
            service, self.service = self.service, None
            service.message.disconnect(self._receive)
            service.close(terminate_tree=True)
            service.deleteLater()

    def stop(self):
        self.pending_activation = None
        running = bool(self.pending)
        refresh = self._refresh_timer.isActive()
        self._refresh_timer.stop()
        self.generation += 1
        self.pending.clear()
        self._end_service()
        self.panel.stop_button.setEnabled(False)
        if (running or refresh) and not self.owner._closing:
            self._refresh_files()
        if running:
            self.panel.status.setText(tr('搜尋已停止；保留已找到的結果'))

    def clear_highlights(self):
        self.selected = None
        for doc in self.owner.documents.values():
            doc._search_navigation = None
            doc.pages.clear_highlights()
        viewer = self.owner._fullscreen_preview
        if viewer is not None:
            for label in viewer.labels.values():
                label.set_search_highlights([], [])

    def _reset_results(self):
        self.clear_highlights()
        self.results.clear()
        self.targets.clear()
        self.pending_activation = None
        self.order.clear()
        self.page_orders.clear()
        self.failures.clear()
        self.zero_width.clear()
        self.panel.files.clear()
        self.panel.paragraphs.clear()

    def start(self):
        p = self.panel
        self.stop()
        query = p.query.text()
        if not query:
            p.status.setText(tr('請輸入搜尋文字'))
            return
        try:
            compile_query(query, p.regular_expression.isChecked(), p.case_sensitive.isChecked(),
                          p.whole_word.isChecked())
        except Exception as exc:
            p.status.setText(tr('規則表達式無效：{p0}', p0=exc))
            return
        documents = self.owner.ordered_documents()
        if p.scope.currentIndex() == 0:
            current = self.owner.current_document()
            documents = [current] if current is not None else []
        elif p.scope.currentIndex() == 1:
            documents = [doc for doc in documents if doc.include_checkbox.isChecked()]
        documents = [doc for doc in documents if doc.ready]
        self._reset_results()
        self.folder_search = p.scope.currentIndex() == 3
        if self.folder_search:
            current = self.owner.current_document()
            if current is None or not current.ready:
                p.status.setText(tr('請先開啟資料夾中的 PDF 檔案'))
                return
            opened = {doc.source_path.resolve(): doc for doc in documents}
            try:
                paths = sorted((path.resolve() for path in current.source_path.parent.iterdir()
                                if path.is_file() and path.suffix.lower() == '.pdf'), key=lambda path: path.name.casefold())
            except OSError as exc:
                p.status.setText(tr('無法讀取資料夾：{message}', message=str(exc)))
                return
            for index, path in enumerate(dict.fromkeys(paths), 1):
                doc = opened.get(path)
                key = doc.document_id if doc is not None else -index
                self.targets[key] = SearchTarget(path, list(doc.page_order) if doc else None, doc.password if doc else None)
        else:
            self.targets = {doc.document_id: SearchTarget(doc.source_path, list(doc.page_order), doc.password) for doc in documents}
        if not self.targets:
            p.status.setText(tr('此範圍沒有已載入的檔案；請先開啟或勾選標籤頁'))
            return
        self.order = list(self.targets)
        self.page_orders = {key: target.page_order for key, target in self.targets.items()}
        self.params = {'query': query, 'regular_expression': p.regular_expression.isChecked(),
                       'case_sensitive': p.case_sensitive.isChecked(), 'whole_word': p.whole_word.isChecked()}
        self.pending = set(self.order)
        self._launch()

    def _launch(self):
        try:
            self.service = RenderService(start_render_backend(), self)
            self.service.message.connect(self._receive, Qt.ConnectionType.QueuedConnection)
            self.panel.stop_button.setEnabled(True)
            self.panel.status.setText(tr('正在搜尋文字層…'))
            for document_id in self.order:
                if document_id not in self.pending:
                    continue
                doc = self.targets.get(document_id)
                if doc is None:
                    continue
                self.service.request_search({
                    'type': 'search', 'document_id': document_id, 'generation': self.generation,
                    'source': str(doc.source_path), 'pages': self.page_orders[document_id],
                    'password': doc.password, **self.params,
                })
        except Exception as exc:
            self.stop()
            self.panel.status.setText(tr('搜尋失敗：{p0}', p0=exc))

    def _receive(self, payload):
        if (self.owner._closing or not isinstance(payload, dict)
                or payload.get('generation') != self.generation):
            return
        document_id = payload.get('document_id')
        if document_id not in self.pending or document_id not in self.targets:
            return
        kind = payload.get('type')
        if kind == 'search_page':
            self.zero_width[(document_id, payload['page'])] = payload.get('zero_width', 0)
            self.results.setdefault(document_id, {})[payload['page']] = payload['paragraphs']
            self.panel.status.setText(tr('搜尋 {p0}：第 {p1} / {p2} 頁',
                p0=self.targets[document_id].source_path.name, p1=payload['position'], p2=payload['total']))
            if not self._refresh_timer.isActive():
                self._refresh_timer.start()
        elif kind in ('done', 'error'):
            self.pending.discard(document_id)
            if kind == 'error':
                self.failures[document_id] = str(payload.get('message', ''))
                if payload.get('timeout'):
                    self.stop()
                    self.panel.status.setText(tr('規則表達式執行逾時；搜尋未完成，保留已找到的結果'))
                    return
            if not self.pending:
                self._refresh_timer.stop()
                self._refresh_files()
                self.panel.stop_button.setEnabled(False)
                self._summary()

    def _summary(self):
        paragraphs = [item for pages in self.results.values() for values in pages.values() for item in values]
        if not paragraphs and any(self.zero_width.values()):
            text = tr('只找到零長度位置，沒有可標示的文字')
        else:
            text = tr('找到 {p0} 個段落、{p1} 處命中', p0=len(paragraphs), p1=sum(p['count'] for p in paragraphs))
        if self.failures:
            text += '\n' + tr('有 {p0} 個檔案搜尋失敗；結果不完整', p0=len(self.failures))
        self.panel.status.setText(text)
        if self.failures:
            details = '\n'.join(f'{self.targets[key].source_path}\n{message}'
                                for key, message in self.failures.items() if key in self.targets)
            self.panel.status.setToolTip('<qt>' + escape(details).replace('\n', '<br>') + '</qt>')

    def _refresh_files(self):
        p = self.panel
        current = p.files.currentItem()
        selected_id = current.data(0, Qt.ItemDataRole.UserRole) if current else None
        p.files.blockSignals(True)
        p.files.clear()
        for document_id in self.order:
            if document_id not in self.targets:
                continue
            paragraphs = [item for items in self.results.get(document_id, {}).values() for item in items]
            if not paragraphs:
                continue
            doc = self.targets[document_id]
            item = QTreeWidgetItem([doc.source_path.name, str(len(paragraphs))])
            item.setData(0, Qt.ItemDataRole.UserRole, document_id)
            item.setTextAlignment(1, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            item.setToolTip(0, str(doc.source_path))
            item.setToolTip(1, tr('找到 {p0} 個段落、{p1} 處命中', p0=len(paragraphs), p1=sum(p['count'] for p in paragraphs)))
            p.files.addTopLevelItem(item)
            if document_id == selected_id:
                p.files.setCurrentItem(item)
        if p.files.currentItem() is None and p.files.topLevelItemCount():
            p.files.setCurrentItem(p.files.topLevelItem(0))
        p.files.blockSignals(False)
        self._show_paragraphs()

    def _show_paragraphs(self, *_args):
        p = self.panel
        selected = p.paragraphs.currentItem()
        previous = selected.data(0, Qt.ItemDataRole.UserRole) if selected else None
        p.paragraphs.clear()
        file_item = p.files.currentItem()
        if file_item is None:
            return
        document_id = file_item.data(0, Qt.ItemDataRole.UserRole)
        target = self.targets.get(document_id)
        if target is None:
            return
        doc = self._open_document(target.source_path)
        pages = doc.page_order if doc is not None and doc.ready else (target.page_order or sorted(self.results.get(document_id, {})))
        for page in pages:
            for result in self.results.get(document_id, {}).get(page, []):
                key = (document_id, page, result['paragraph_id'])
                item = QTreeWidgetItem([str(page + 1), result['text']])
                item.setTextAlignment(0, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                item.setData(0, Qt.ItemDataRole.UserRole, key)
                tooltip = '<qt>' + escape(tr('第 {p0} 頁 · {p1} 處命中 · {p2}', p0=page + 1, p1=result['count'], p2=result['text'])).replace('\n', '<br>') + '</qt>'
                item.setToolTip(0, tooltip)
                item.setToolTip(1, tooltip)
                p.paragraphs.addTopLevelItem(item)
                if key == previous:
                    p.paragraphs.setCurrentItem(item)

    def _open_document(self, path):
        return next((doc for doc in self.owner.documents.values() if doc.source_path == path), None)

    def _target_unchanged(self, key):
        target = self.targets.get(key)
        if target is None:
            return False
        try:
            stat = target.source_path.stat()
            unchanged = target.stamp is None or target.stamp == (stat.st_mtime_ns, stat.st_size)
        except OSError:
            unchanged = False
        if not unchanged:
            self.panel.status.setText(tr('搜尋結果的檔案已變更或無法讀取，請重新搜尋'))
        return unchanged

    def _activate_file(self, item, _column=0):
        if item is None:
            self.pending_activation = None
            return
        first = self.panel.paragraphs.topLevelItem(0)
        if first is not None:
            self._activate_item(first)

    def _activate_item(self, item, _column=0):
        key = tuple(item.data(0, Qt.ItemDataRole.UserRole))
        self.pending_activation = None
        target = self.targets.get(key[0])
        if target is None or not self._target_unchanged(key[0]):
            return
        doc = self._open_document(target.source_path)
        if doc is None:
            self.owner.load_pdf(target.source_path)
            doc = self._open_document(target.source_path)
        if doc is None:
            return
        if not doc.ready:
            self.owner.tabs.setCurrentWidget(doc)
            self.pending_activation = (self.generation, doc.document_id, key)
            return
        self._activate_result(doc, key)

    def document_loaded(self, doc):
        pending = self.pending_activation
        if pending is not None and pending[:2] == (self.generation, doc.document_id):
            self.pending_activation = None
            if self.owner.current_document() is doc:
                self._activate_result(doc, pending[2])

    def _activate_result(self, doc, key):
        document_id, page, paragraph_id = key
        if not self._target_unchanged(document_id):
            return
        if not 0 <= page < doc.page_count:
            self.panel.status.setText(tr('檔案頁面已變更，請重新搜尋'))
            return
        results = self.results.get(document_id, {}).get(page, [])
        result = next((p for p in results if p['paragraph_id'] == paragraph_id), None)
        if result is None:
            return
        self.clear_highlights()
        self.selected = (document_id, page, paragraph_id)
        doc.pages.set_highlights(page,
            [box for p in results for box in p['rects']], result['rects'])
        self.owner.tabs.setCurrentWidget(doc)
        if self.owner.width() < 640:
            self.narrow_results = False
            self.layout()
        doc.jump_to_search_result(page, result['rects'][0])

    def remove_document(self, document_id):
        if self.pending_activation is not None and self.pending_activation[1] == document_id:
            self.pending_activation = None
        if document_id not in self.order:
            return
        if self.folder_search:
            self.targets[document_id].password = None
            return
        was_pending = document_id in self.pending
        self.pending.discard(document_id)
        self.results.pop(document_id, None)
        self.targets.pop(document_id, None)
        self.failures.pop(document_id, None)
        self.page_orders.pop(document_id, None)
        self.zero_width = {key: value for key, value in self.zero_width.items() if key[0] != document_id}
        self.order = [key for key in self.order if key != document_id]
        if self.selected and self.selected[0] == document_id:
            self.clear_highlights()
        if was_pending:
            self.generation += 1
            self._end_service()
            if self.pending:
                self._launch()
            else:
                self.panel.stop_button.setEnabled(False)
        self._refresh_files()
        if not self.pending:
            self._summary()

    def retranslate(self):
        self.panel.retranslate()
        self._refresh_files()
        if self.order and not self.pending:
            self._summary()
