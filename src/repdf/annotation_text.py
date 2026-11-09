"""Annotation text views and platform-native clipboard line endings."""
import os

from PySide6.QtGui import QKeySequence
from PySide6.QtWidgets import QApplication, QMenu, QPlainTextEdit

from repdf.strings import tr


def platform_text(text):
    return text.replace('\r\n', '\n').replace('\r', '\n').replace('\u2029', '\n').replace('\u2028', '\n').replace('\n', os.linesep)


def copy_annotation_text(text):
    QApplication.clipboard().setText(platform_text(text))


class AnnotationTextEdit(QPlainTextEdit):
    def copy(self):
        if self.textCursor().hasSelection():
            copy_annotation_text(self.textCursor().selectedText())

    def keyPressEvent(self, event):
        if event.matches(QKeySequence.StandardKey.Copy):
            self.copy()
            event.accept()
            return
        super().keyPressEvent(event)

    def contextMenuEvent(self, event):
        menu = QMenu(self)
        action = menu.addAction(tr('複製註解文字'), self.copy)
        action.setEnabled(self.textCursor().hasSelection())
        menu.addAction(tr('全選註解文字'), self.selectAll)
        menu.exec(event.globalPos())
