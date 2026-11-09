"""Shared flat Qt message dialogs, including static QMessageBox helpers."""
from PySide6.QtCore import QEvent, QObject, QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import QApplication, QBoxLayout, QDialogButtonBox, QLabel, QMessageBox

from repdf.strings import tr


def _icon(kind, color):
    pixmap = QPixmap(48, 48)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.scale(2, 2)
    pen = QPen(QColor(color), 1.3)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    painter.setPen(pen)
    if kind == QMessageBox.Icon.Warning.value:
        path = QPainterPath()
        path.moveTo(12, 3)
        path.lineTo(22, 21)
        path.lineTo(2, 21)
        path.closeSubpath()
        painter.drawPath(path)
        painter.drawLine(12, 9, 12, 14)
        painter.drawPoint(12, 17)
    else:
        painter.drawEllipse(QRectF(2.5, 2.5, 19, 19))
        if kind == QMessageBox.Icon.Critical.value:
            painter.drawLine(8, 8, 16, 16)
            painter.drawLine(16, 8, 8, 16)
        elif kind == QMessageBox.Icon.Question.value:
            path = QPainterPath()
            path.moveTo(8.5, 9)
            path.cubicTo(8.5, 5, 16, 5, 15.5, 10)
            path.cubicTo(15.5, 12, 12, 12, 12, 14)
            painter.drawPath(path)
            painter.drawPoint(12, 17)
        else:
            painter.drawPoint(12, 7)
            painter.drawLine(12, 11, 12, 17)
    painter.end()
    pixmap.setDevicePixelRatio(2)
    return pixmap


def style_message(message):
    """Keep QMessageBox semantics, roles and detailed diagnostics intact."""
    message.setOption(QMessageBox.Option.DontUseNativeDialog, True)
    if message.property('modernMessageIcon') is None:
        message.setProperty('modernMessageIcon', message.icon().value)
    kind = message.property('modernMessageIcon')
    if not message.informativeText() and message.text() != message.windowTitle() and message.windowTitle():
        content = message.text()
        message.setText(message.windowTitle())
        message.setInformativeText(content)
    palette = QApplication.palette()
    dark = palette.window().color().lightness() < 128
    hover = '#3b2a56' if dark else '#e7ebf0'
    pressed = '#4d376e' if dark else '#d8e3f3'
    warning = '#ffad59' if dark else '#c65300'
    color = ('#ff8a80' if dark else '#c43b35') if kind == QMessageBox.Icon.Critical.value else (
        warning if kind == QMessageBox.Icon.Warning.value else palette.windowText().color().name())
    message.setStyleSheet(f"""
        QMessageBox {{ background: {palette.window().color().name()}; font-size: 10pt; }}
        QMessageBox QLabel {{ color: palette(window-text); padding: 0; }}
        QLabel#qt_msgbox_label {{ font-size: 12pt; font-weight: 500; }}
        QLabel#qt_msgbox_informativelabel {{ font-size: 10pt; font-weight: normal; }}
        QMessageBox QPushButton {{ color: palette(button-text); background: transparent;
            border: 1px solid transparent; border-radius: 4px; padding: 0 10px;
            min-width: 64px; min-height: 32px; max-height: 32px; font-size: 10pt; }}
        QMessageBox QPushButton:hover, QMessageBox QPushButton:focus {{ background: {hover}; }}
        QMessageBox QPushButton:pressed {{ background: {pressed}; }}
        QMessageBox QPushButton:default {{ background: {hover}; }}
        QMessageBox QPushButton[destructive="true"] {{ color: {warning}; }}
    """)
    if kind != QMessageBox.Icon.NoIcon.value:
        message.setIconPixmap(_icon(kind, color))
    message.ensurePolished()
    grid = message.layout()
    grid.setContentsMargins(20, 18, 20, 14)
    grid.setHorizontalSpacing(12)
    grid.setVerticalSpacing(14)
    title = message.findChild(QLabel, 'qt_msgbox_label')
    detail = message.findChild(QLabel, 'qt_msgbox_informativelabel')
    icon = message.findChild(QLabel, 'qt_msgboxex_icon_label')
    if title is not None:
        grid.removeWidget(title)
        title.setWordWrap(True)
        with_icon = kind != QMessageBox.Icon.NoIcon.value
        grid.addWidget(title, 0, 1 if with_icon else 0, 1, 2 if with_icon else 3, Qt.AlignmentFlag.AlignVCenter)
    if icon is not None and kind != QMessageBox.Icon.NoIcon.value:
        grid.removeWidget(icon)
        icon.setFixedSize(24, 24)
        grid.addWidget(icon, 0, 0, Qt.AlignmentFlag.AlignVCenter)
    if detail is not None and message.informativeText():
        grid.removeWidget(detail)
        detail.setWordWrap(True)
        detail.setFixedWidth(400)
        grid.addWidget(detail, 1, 0, 1, 3)
    box = message.findChild(QDialogButtonBox)
    if box is not None:
        buttons = box.buttons()
        for button in buttons:
            button.setMinimumWidth(88)
            button.setFixedHeight(34)
            button.setProperty('destructive', message.standardButton(button) == QMessageBox.StandardButton.Discard)
            button.style().unpolish(button)
            button.style().polish(button)
        # Destructive confirmations put Cancel first and the default Save last.
        if message.standardButtons() & QMessageBox.StandardButton.Save:
            row = box.layout()
            while row.count():
                row.takeAt(0)
            row.setDirection(QBoxLayout.Direction.LeftToRight)
            row.addStretch()
            order = (QMessageBox.StandardButton.Cancel, QMessageBox.StandardButton.Discard, QMessageBox.StandardButton.Save)
            ordered = [message.button(kind) for kind in order if message.button(kind) is not None]
            for button in [b for b in buttons if b not in ordered] + ordered:
                row.addWidget(button)
    message.setProperty('modernMessageReady', True)
    return message


class _MessageStyle(QObject):
    def __init__(self, app):
        super().__init__(app)
        self.busy = False

    def eventFilter(self, watched, event):
        if self.busy or not isinstance(watched, QMessageBox):
            return False
        if ((event.type() == QEvent.Type.Show and not watched.property('modernMessageReady'))
                or (event.type() == QEvent.Type.ApplicationPaletteChange and watched.isVisible())):
            self.busy = True
            try:
                style_message(watched)
            finally:
                self.busy = False
        return False


def install_message_style(app):
    QApplication.setAttribute(Qt.ApplicationAttribute.AA_DontUseNativeDialogs, True)
    if not hasattr(app, '_repdf_message_style'):
        app._repdf_message_style = _MessageStyle(app)
        app.installEventFilter(app._repdf_message_style)


def unsaved_changes_message(parent, filename):
    message = QMessageBox(parent)
    message.setWindowTitle(tr('尚未儲存的變更'))
    message.setTextFormat(Qt.TextFormat.PlainText)
    message.setIcon(QMessageBox.Icon.Warning)
    message.setText(tr('有尚未儲存的變更'))
    message.setInformativeText(tr('「{name}」尚未儲存。\n\n請先儲存，或選擇不儲存並關閉；未儲存的變更將會捨棄。', name=filename))
    buttons = QMessageBox.StandardButton
    message.setStandardButtons(buttons.Save | buttons.Discard | buttons.Cancel)
    message.setDefaultButton(buttons.Save)
    message.setEscapeButton(buttons.Cancel)
    for standard, label in ((buttons.Cancel, '取消'), (buttons.Discard, '不儲存'), (buttons.Save, '儲存')):
        message.button(standard).setText(tr(label))
    return style_message(message)


def proofreading_range_message(parent, page, filename, total):
    message = QMessageBox(parent)
    message.setWindowTitle(tr('同步校對'))
    message.setTextFormat(Qt.TextFormat.PlainText)
    message.setIcon(QMessageBox.Icon.Information)
    message.setText(tr('無法跳至第 {page} 頁', page=page))
    message.setInformativeText(tr('「{name}」只有 {total} 頁。\n\n兩邊頁次維持不變。', name=filename, total=total))
    message.setStandardButtons(QMessageBox.StandardButton.Ok)
    message.setDefaultButton(QMessageBox.StandardButton.Ok)
    message.setEscapeButton(QMessageBox.StandardButton.Ok)
    return style_message(message)
