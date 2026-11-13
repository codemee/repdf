"""Compact original-page navigation for the fullscreen floating toolbar."""
from PySide6.QtCore import QEvent, QPoint, QTimer, Qt
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QLineEdit, QToolTip, QWidget

from repdf.strings import tr


class FullscreenPageNavigation(QWidget):
    def __init__(self, viewer, parent):
        super().__init__(parent)
        self.viewer = viewer
        self.document_id = None
        self.dirty = False
        row = QHBoxLayout(self)
        row.setContentsMargins(4, 0, 4, 0)
        row.setSpacing(5)
        separator = QFrame(self)
        separator.setObjectName('toolbarSeparator')
        separator.setFixedSize(1, 24)
        row.addWidget(separator, 0, Qt.AlignmentFlag.AlignVCenter)
        self.input = QLineEdit(self)
        self.input.setObjectName('fullscreenPageNumberInput')
        self.input.setAccessibleName(tr('目前頁碼，輸入後按 Enter 跳頁'))
        self.input.setInputMethodHints(Qt.InputMethodHint.ImhDigitsOnly)
        self.input.setMaxLength(10)
        self.input.setAlignment(Qt.AlignmentFlag.AlignRight)
        self.input.setFixedHeight(28)
        self.input.setStyleSheet('QLineEdit { border: 1px solid palette(mid); border-radius: 4px; '
                                 'padding: 2px 4px; background: palette(base); }')
        self.input.textEdited.connect(self.edited)
        self.input.returnPressed.connect(self.jump)
        self.input.installEventFilter(self)
        row.addWidget(self.input)
        self.total = QLabel(self)
        row.addWidget(self.total)
        self.refresh()

    def edited(self):
        self.dirty = True

    def refresh(self):
        if self.viewer.closed:
            return
        doc = self.viewer.document
        if doc.document_id != self.document_id:
            self.dirty = False
            self.document_id = doc.document_id
        self.input.setEnabled(doc.ready and not self.viewer.owner._export_running)
        self.total.setText(f'/ {doc.page_count}')
        width = self.input.fontMetrics().horizontalAdvance('9' * max(3, len(str(doc.page_count)))) + 18
        self.input.setFixedWidth(max(44, min(88, width)))
        self.input.setToolTip(tr('目前原始頁碼；輸入 1–{p0} 後按 Enter 跳頁，Esc 取消', p0=doc.page_count))
        if not (self.input.hasFocus() and self.dirty):
            self.input.setText(str(self.viewer.page_index + 1))

    def jump(self):
        doc = self.viewer.document
        text = self.input.text().strip()
        if not text.isdecimal() or not 1 <= int(text) <= doc.page_count:
            QToolTip.showText(self.input.mapToGlobal(QPoint(0, self.input.height())),
                             tr('請輸入 1–{p0} 的頁碼', p0=doc.page_count), self.input)
            self.input.selectAll()
            return
        page = int(text) - 1
        if not self.viewer.owner.proofreading.allow_page(doc, page):
            self.dirty = False
            self.refresh()
            self.input.selectAll()
            return
        self.viewer.owner.annotation_editor.finish_text(True)
        self.dirty = False
        self.viewer.show_page(page)
        self.input.clearFocus()
        self.viewer.setFocus()
        self.refresh()

    def eventFilter(self, watched, event):
        if watched is self.input:
            if event.type() == QEvent.Type.FocusIn:
                QTimer.singleShot(0, self.input.selectAll)
            elif event.type() == QEvent.Type.FocusOut:
                self.dirty = False
                QTimer.singleShot(0, self.refresh)
            elif event.type() == QEvent.Type.KeyPress and event.key() == Qt.Key.Key_Escape:
                self.dirty = False
                self.input.clearFocus()
                self.viewer.setFocus()
                self.refresh()
                return True
        return super().eventFilter(watched, event)
