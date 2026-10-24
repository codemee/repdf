"""Qt message dialogs with a clear heading, explanation and action hierarchy."""

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QBoxLayout, QDialogButtonBox, QLabel, QMessageBox

from repdf.strings import tr


def unsaved_changes_message(parent, filename):
    message = QMessageBox(parent)
    message.setOption(QMessageBox.Option.DontUseNativeDialog, True)
    message.setTextFormat(Qt.TextFormat.PlainText)
    message.setWindowTitle(tr('尚未儲存的變更'))
    message.setText(tr('有尚未儲存的變更'))
    message.setInformativeText(tr('「{name}」尚未儲存。\n\n請先儲存，或選擇不儲存並關閉；未儲存的變更將會捨棄。', name=filename))
    buttons = QMessageBox.StandardButton
    message.setStandardButtons(buttons.Save | buttons.Discard | buttons.Cancel)
    message.setDefaultButton(buttons.Save)
    message.setEscapeButton(buttons.Cancel)
    for standard, label, name in ((buttons.Cancel, '取消', 'messageCancel'),
                                  (buttons.Discard, '不儲存', 'messageDiscard'),
                                  (buttons.Save, '儲存', 'messageSave')):
        button = message.button(standard)
        button.setText(tr(label))
        button.setObjectName(name)
        button.setFixedSize(88, 34)
    box = message.findChild(QDialogButtonBox)
    box.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
    box.layout().setSpacing(8)
    message.layout().setContentsMargins(24, 24, 24, 18)
    message.layout().setHorizontalSpacing(14)
    message.layout().setVerticalSpacing(14)
    palette = message.palette()
    dark = palette.window().color().lightness() < 128
    warning = '#ffad59' if dark else '#c65300'
    background = palette.window().color().name() if dark else '#ffffff'
    accent = palette.highlight().color().name()
    foreground = palette.highlightedText().color().name()
    message.setStyleSheet(f'''
        QMessageBox {{ background: {background}; }}
        QLabel#qt_msgbox_label {{ font-size: 14pt; font-weight: 500; padding: 0; }}
        QLabel#qt_msgbox_informativelabel {{ font-size: 10pt; padding: 4px 0 14px; }}
        QLabel#qt_msgboxex_icon_label {{ padding: 0; }}
        QMessageBox QPushButton {{ font-size: 10pt; padding: 0; border-radius: 5px;
            min-width: 86px; max-width: 86px; min-height: 32px; max-height: 32px; }}
        QPushButton#messageCancel {{ background: transparent; border: 1px solid {accent}; }}
        QPushButton#messageDiscard {{ background: transparent; border: 1px solid transparent; color: {warning}; }}
        QPushButton#messageSave {{ background: {accent}; border: 1px solid {accent}; color: {foreground}; }}
    ''')
    pixmap = QPixmap(56, 56)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.scale(2, 2)
    pen = QPen(QColor(warning), 1.4)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    painter.setPen(pen)
    painter.drawEllipse(1, 1, 26, 26)
    painter.drawLine(14, 7, 14, 16)
    painter.drawPoint(14, 21)
    painter.end()
    pixmap.setDevicePixelRatio(2)
    message.setIconPixmap(pixmap)
    message.ensurePolished()
    grid = message.layout()
    grid.setContentsMargins(24, 24, 24, 18)
    grid.setHorizontalSpacing(14)
    grid.setVerticalSpacing(14)
    title = message.findChild(QLabel, 'qt_msgbox_label')
    detail = message.findChild(QLabel, 'qt_msgbox_informativelabel')
    icon = message.findChild(QLabel, 'qt_msgboxex_icon_label')
    for widget in (title, detail, icon):
        grid.removeWidget(widget)
    grid.addWidget(icon, 0, 0, Qt.AlignmentFlag.AlignVCenter)
    grid.addWidget(title, 0, 1, 1, 2, Qt.AlignmentFlag.AlignVCenter)
    detail.setFixedWidth(372)
    grid.addWidget(detail, 1, 0, 1, 3)
    button_layout = box.layout()
    while button_layout.count():
        button_layout.takeAt(0)
    button_layout.setDirection(QBoxLayout.Direction.LeftToRight)
    button_layout.addStretch()
    for standard in (buttons.Cancel, buttons.Discard, buttons.Save):
        button_layout.addWidget(message.button(standard))
    return message
