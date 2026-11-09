"""Independent, persistent sidebar text sizes with a menu and Ctrl+wheel."""
from PySide6.QtCore import QEvent, QObject, Qt, Signal
from PySide6.QtGui import QActionGroup, QFont
from PySide6.QtWidgets import QApplication, QMenu, QToolButton, QTreeWidget, QTreeWidgetItemIterator, QWidget

from repdf.strings import tr


class PanelTextSize(QObject):
    changed = Signal()
    SIZES = (8, 9, 10, 11, 12, 14, 16, 18, 20, 24)

    def __init__(self, panel, settings, key):
        super().__init__(panel)
        self.panel, self.settings, self.key = panel, settings, key
        self.button = QToolButton(panel.header)
        self.button.setText('Aa')
        self.button.setAccessibleName(tr('字級'))
        self.button.setFixedSize(34, 34)
        self.button.setFont(QApplication.font())
        self.button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.button.setStyleSheet('QToolButton::menu-indicator { image: none; }')
        menu = QMenu(self.button)
        self.button.setMenu(menu)
        group = QActionGroup(menu)
        group.setExclusive(True)
        self.actions = {}
        for size in self.SIZES:
            action = menu.addAction(f'{size} pt')
            action.setCheckable(True)
            group.addAction(action)
            action.triggered.connect(lambda _checked=False, size=size: self.set_size(size))
            self.actions[size] = action
        row = panel.header.layout()
        row.insertWidget(row.count() - 1, self.button)
        for widget in [panel, *panel.findChildren(QWidget)]:
            widget.installEventFilter(self)
        try:
            size = int(settings.value(key, 10))
        except (ValueError, TypeError):
            size = 10
        self.set_size(size, save=False)

    def set_size(self, size, *, save=True):
        size = min(self.SIZES, key=lambda candidate: abs(candidate - size))
        self.size = size
        # A scoped style survives application-wide theme repolishing, which
        # otherwise resets explicit QWidget fonts in Qt's stylesheet engine.
        control_size = max(1, QApplication.font().pointSize())
        self.panel.setStyleSheet(
            f'QWidget {{ font-size: {size}pt; }} '
            f'QToolButton, QMenu {{ font-size: {control_size}pt; }} '
            'QHeaderView { font-weight: bold; }')
        fonts = [(widget, QFont(widget.font())) for widget in [self.panel, *self.panel.findChildren(QWidget)]]
        for widget, font in fonts:
            if isinstance(widget, (QToolButton, QMenu)):
                continue
            font.setPointSize(size)
            widget.setFont(font)
            if isinstance(widget, QTreeWidget):
                iterator = QTreeWidgetItemIterator(widget)
                while iterator.value() is not None:
                    item = iterator.value()
                    for column in range(widget.columnCount()):
                        explicit = item.data(column, Qt.ItemDataRole.FontRole)
                        if isinstance(explicit, QFont):
                            explicit.setPointSize(size)
                            item.setFont(column, explicit)
                    iterator += 1
        for table in self.panel.findChildren(QTreeWidget):
            if not table.isHeaderHidden():
                font = table.header().font()
                font.setPointSize(size)
                font.setBold(True)
                table.header().setFont(font)
        self.actions[size].setChecked(True)
        self.retranslate()
        if save:
            self.settings.setValue(self.key, size)
        self.changed.emit()

    def retranslate(self):
        self.button.setAccessibleName(tr('字級'))
        self.button.setToolTip(tr('字級：{size} pt（Ctrl＋滾輪調整）', size=self.size))

    def eventFilter(self, watched, event):
        if event.type() == QEvent.Type.Wheel and event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            delta = event.angleDelta().y()
            if delta:
                index = self.SIZES.index(self.size) + (1 if delta > 0 else -1)
                self.set_size(self.SIZES[max(0, min(len(self.SIZES) - 1, index))])
                event.accept()
                return True
        return super().eventFilter(watched, event)
