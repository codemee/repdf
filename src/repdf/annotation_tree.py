"""Compact annotation rows with an in-place copy action."""

from PySide6.QtCore import QEvent, QPersistentModelIndex, QRect, Qt, Signal
from PySide6.QtGui import QIcon, QKeySequence
from PySide6.QtWidgets import (
    QApplication,
    QStyledItemDelegate,
    QStyle,
    QStyleOptionViewItem,
    QToolTip,
    QTreeWidget,
)

from repdf.icons import toolbar_icon
from repdf.strings import tr
from repdf.shortcut_hints import shortcut_tooltip

TEXT_ROLE = Qt.ItemDataRole.UserRole + 2


def copy_rect(rect):
    return QRect(rect.right() - 33, rect.center().y() - 16, 34, 34)


def copy_tooltip():
    return shortcut_tooltip(tr('複製註解文字'), QKeySequence.keyBindings(QKeySequence.StandardKey.Copy))


class AnnotationDelegate(QStyledItemDelegate):
    def __init__(self, parent):
        super().__init__(parent)
        self.copy_icon = None
        self.palette_key = None

    def paint(self, painter, option, index):
        if not (index.data(TEXT_ROLE) or "").strip():
            super().paint(painter, option, index)
            return
        button = copy_rect(option.rect)
        selected = bool(option.state & QStyle.StateFlag.State_Selected)
        painter.save()
        tail = QRect(button.left() - 3, option.rect.top(), 37, option.rect.height())
        painter.fillRect(
            tail, option.palette.highlight() if selected else option.palette.base()
        )
        body = QStyleOptionViewItem(option)
        body.rect.setRight(button.left() - 4)
        super().paint(painter, body, index)
        hovered = self.parent().copy_hover == index
        if hovered:
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(option.palette.button())
            painter.drawRoundedRect(button.adjusted(1, 1, -1, -1), 4, 4)
        mode = QIcon.Mode.Selected if selected and not hovered else QIcon.Mode.Normal
        if self.palette_key != option.palette.cacheKey():
            self.palette_key = option.palette.cacheKey()
            self.copy_icon = toolbar_icon("copy")
        self.copy_icon.paint(
            painter, button.adjusted(7, 7, -7, -7), Qt.AlignmentFlag.AlignCenter, mode
        )
        painter.restore()

    def sizeHint(self, option, index):
        size = super().sizeHint(option, index)
        if (index.data(TEXT_ROLE) or "").strip():
            size.setHeight(max(34, size.height()))
        return size


class AnnotationTree(QTreeWidget):
    textCopied = Signal(str)

    def __init__(self):
        super().__init__()
        self.copy_hover = None
        self.copy_press = None
        self.setMouseTracking(True)
        self.setItemDelegate(AnnotationDelegate(self))

    def copy_index(self, position):
        index = self.indexAt(position)
        if (
            index.isValid()
            and (index.data(TEXT_ROLE) or "").strip()
            and copy_rect(self.visualRect(index)).contains(position)
        ):
            return index
        return None

    def mouseMoveEvent(self, event):
        super().mouseMoveEvent(event)
        index = self.copy_index(event.position().toPoint())
        self.copy_hover = QPersistentModelIndex(index) if index is not None else None
        self.viewport().setCursor(
            Qt.CursorShape.PointingHandCursor
            if index is not None
            else Qt.CursorShape.ArrowCursor
        )
        self.viewport().update()

    def mousePressEvent(self, event):
        index = self.copy_index(event.position().toPoint())
        if event.button() == Qt.MouseButton.LeftButton and index is not None:
            self.copy_press = QPersistentModelIndex(index)
            event.accept()
            return
        self.copy_press = None
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        if self.copy_press is not None and event.button() == Qt.MouseButton.LeftButton:
            pressed, self.copy_press = self.copy_press, None
            index = self.copy_index(event.position().toPoint())
            if index is not None and pressed == index:
                self.copy_text(index.data(TEXT_ROLE))
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event):
        if self.copy_index(event.position().toPoint()) is not None:
            event.accept()
            return
        super().mouseDoubleClickEvent(event)

    def keyPressEvent(self, event):
        if event.matches(QKeySequence.StandardKey.Copy):
            text = self.currentIndex().data(TEXT_ROLE) or ""
            if text.strip():
                self.copy_text(text)
                event.accept()
                return
        super().keyPressEvent(event)

    def copy_text(self, text):
        QApplication.clipboard().setText(text)
        self.textCopied.emit(text)

    def viewportEvent(self, event):
        if (
            event.type() == QEvent.Type.ToolTip
            and self.copy_index(event.pos()) is not None
        ):
            QToolTip.showText(event.globalPos(), copy_tooltip(), self.viewport())
            return True
        if event.type() == QEvent.Type.Leave:
            self.copy_hover = None
            self.viewport().update()
        return super().viewportEvent(event)
