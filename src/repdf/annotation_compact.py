"""Single-row annotation review controls, synchronized with the full tree."""
from html import escape

from PySide6.QtCore import QEvent, QSignalBlocker, QSize, Qt
from PySide6.QtWidgets import QComboBox, QFrame, QHBoxLayout, QLabel, QSizePolicy, QToolButton, QWidget

from repdf.icons import annotation_icon, toolbar_icon
from repdf.strings import tr
from repdf.shortcut_hints import shortcut_tooltip


class AnnotationSummary(QLabel):
    def __init__(self):
        super().__init__()
        self.contents = ''
        self.setTextFormat(Qt.TextFormat.PlainText)
        self.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self.setMinimumWidth(100)
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)

    def set_contents(self, text):
        self.contents = text
        normalized = text.replace('\r\n', '\n').replace('\r', '\n')
        self.setToolTip('<qt>' + escape(normalized).replace('\n', '<br>') + '</qt>' if text else '')
        self._elide()

    def _elide(self):
        self.setText(self.fontMetrics().elidedText(' '.join(self.contents.splitlines()),
                                                 Qt.TextElideMode.ElideRight, self.contentsRect().width()))

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._elide()

    def changeEvent(self, event):
        super().changeEvent(event)
        if event.type() == QEvent.Type.FontChange and hasattr(self, 'contents'):
            self._elide()


class CompactAnnotations(QWidget):
    def __init__(self, controller):
        super().__init__(controller.panel)
        self.controller = controller
        self.page = None
        self.document_id = None
        self.pages = []
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(4)
        self.grip = QToolButton()
        self.grip.setFixedSize(18, 34)
        self.grip.setIconSize(QSize(16, 20))
        self.grip.setStyleSheet('QToolButton { padding: 0; border: none; }')
        self.grip.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.mode = QToolButton()
        self.mode.setDefaultAction(controller.compact_action)
        self.mode.setProperty('stateButton', True)
        self.page_label = QLabel()
        self.page_label.setTextFormat(Qt.TextFormat.PlainText)
        self.annotations = QComboBox()
        self.annotations.setMinimumWidth(120)
        self.annotations.setMaximumWidth(220)
        self.annotations.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.annotations.setMinimumContentsLength(12)
        self.annotations.setObjectName('compactAnnotationChoice')
        self.choice_arrow = QToolButton(self.annotations)
        self.choice_arrow.setFixedWidth(24)
        self.choice_arrow.setIconSize(QSize(12, 12))
        self.choice_arrow.setStyleSheet('QToolButton { padding: 0; border: none; }')
        self.choice_arrow.clicked.connect(self.annotations.showPopup)
        self.annotations.installEventFilter(self)
        self.text = AnnotationSummary()
        self.previous = QToolButton()
        self.next = QToolButton()
        self.previous.setDefaultAction(controller.previous_annotation_page)
        self.next.setDefaultAction(controller.next_annotation_page)
        for button in (self.mode, self.previous, self.next):
            button.setFixedSize(34, 34)
            button.setIconSize(QSize(20, 20))
        self.mode_separator = QFrame()
        self.content_separator = QFrame()
        for separator in (self.mode_separator, self.content_separator):
            separator.setObjectName('compactAnnotationSeparator')
            separator.setFixedSize(1, 24)
        for widget in (self.grip, self.mode, self.previous, self.page_label, self.next, self.annotations):
            row.addWidget(widget, 0, Qt.AlignmentFlag.AlignVCenter)
            if widget is self.mode or widget is self.annotations:
                row.addWidget(self.mode_separator if widget is self.mode else self.content_separator,
                              0, Qt.AlignmentFlag.AlignVCenter)
        row.addWidget(self.text, 1, Qt.AlignmentFlag.AlignVCenter)
        self.annotations.activated.connect(self.select_annotation)
        self.hide()
        self.retranslate()

    def eventFilter(self, watched, event):
        if watched is self.annotations and event.type() == QEvent.Type.Resize:
            self.choice_arrow.setGeometry(self.annotations.width() - 24, 0, 24, self.annotations.height())
        return super().eventFilter(watched, event)

    def retranslate(self):
        self.grip.setIcon(toolbar_icon('drag_handle'))
        self.grip.setToolTip(tr('拖曳移動註解工具列'))
        self.grip.setAccessibleName(tr('拖曳移動註解工具列'))
        self.choice_arrow.setIcon(toolbar_icon('chevron_down'))
        self.choice_arrow.setToolTip(tr('目前頁面的註解'))
        self.annotations.setAccessibleName(tr('目前頁面的註解'))
        self.text.setAccessibleName(tr('註解文字'))
        self.page_label.setToolTip(tr('拖曳移動註解工具列'))
        for button, label, icon in ((self.previous, '上一個有註解的頁面', 'previous'),
                                     (self.next, '下一個有註解的頁面', 'next')):
            action = button.defaultAction()
            action.setText(tr(label))
            action.setIcon(toolbar_icon(icon))
            action.setToolTip(shortcut_tooltip(tr(label), action.shortcuts()))
            button.setAccessibleName(tr(label))
            button.setIcon(toolbar_icon(icon))

    def changeEvent(self, event):
        super().changeEvent(event)
        if event.type() == QEvent.Type.PaletteChange and hasattr(self, 'previous'):
            self.retranslate()
            self.controller.compact_action.setIcon(toolbar_icon(
                'panel_full' if self.controller.compact else 'panel_compact'))

    def sync(self, *_args):
        nav = self.controller
        doc = nav.owner.current_document()
        annotations = doc.annotations if doc is not None else None
        annotations = annotations or []
        selected = nav.panel.tree.currentItem()
        if selected is not None and selected.childCount():
            selected = selected.child(0)
        selected_index = nav.items.index(selected) if selected in nav.items else None
        self.pages = list(dict.fromkeys(annotation['page'] for annotation in annotations))
        if doc is None or self.document_id != doc.document_id:
            self.page = None
            self.document_id = doc.document_id if doc else None
        if selected_index is not None and selected_index < len(annotations):
            self.page = annotations[selected_index]['page']
        elif self.page not in self.pages:
            current = doc.preview_page_index() if doc is not None and doc.ready else 0
            self.page = next((page for page in self.pages if page >= current), self.pages[-1] if self.pages else None)
        blocker = QSignalBlocker(self.annotations)
        self.annotations.clear()
        current_index = 0
        for index, annotation in enumerate(annotations):
            if annotation['page'] != self.page:
                continue
            summary = ' '.join((annotation['contents'] or annotation['subject'] or tr('沒有文字內容')).split())
            self.annotations.addItem(annotation_icon(annotation['kind']),
                                     summary[:80], index)
            if index == selected_index:
                current_index = self.annotations.count() - 1
        self.annotations.setCurrentIndex(current_index if self.annotations.count() else -1)
        del blocker
        index = self.annotations.currentData()
        text = annotations[index]['contents'] if index is not None else ''
        self.text.set_contents(text)
        self.annotations.setToolTip(self.annotations.currentText())
        self.page_label.setText(tr('第 {page} 頁', page=self.page + 1) if self.page is not None else tr('沒有註解頁面'))
        self.annotations.setEnabled(bool(self.pages))
        position = self.pages.index(self.page) if self.page in self.pages else -1
        self.previous.defaultAction().setEnabled(position > 0)
        self.next.defaultAction().setEnabled(0 <= position < len(self.pages) - 1)

    def select_annotation(self, index):
        global_index = self.annotations.itemData(index)
        if global_index is not None:
            self.controller.select_compact_annotation(global_index)

    def step_page(self, delta):
        if self.controller.kind != 'annotations' or not self.controller.opened:
            return
        if self.page not in self.pages:
            return
        target = self.pages.index(self.page) + delta
        if not 0 <= target < len(self.pages):
            return
        doc = self.controller.owner.current_document()
        if doc is None or doc.annotations is None:
            return
        page = self.pages[target]
        index = next((i for i, annotation in enumerate(doc.annotations) if annotation['page'] == page), None)
        if index is not None:
            self.controller.select_compact_annotation(index)
