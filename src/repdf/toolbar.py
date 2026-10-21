"""Toolbar overflow that stays usable with a fixed, single-row height."""

from PySide6.QtCore import QEvent, QSize, Qt, QTimer
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QHBoxLayout, QLabel, QMenu, QSlider,
    QProxyStyle, QStyle, QStyleFactory, QToolBar, QToolButton, QWidget, QWidgetAction,
)

from repdf.icons import toolbar_icon
from repdf.strings import tr


class _ToolbarStyle(QProxyStyle):
    def pixelMetric(self, metric, option=None, widget=None):
        if metric == QStyle.PixelMetric.PM_ToolBarExtensionExtent:
            return 34
        return super().pixelMetric(metric, option, widget)


class OverflowToolBar(QToolBar):
    def __init__(self, title, parent=None):
        super().__init__(title, parent)
        app = QApplication.instance()
        self._toolbar_style = app.findChild(_ToolbarStyle, "overflowToolbarStyle")
        if self._toolbar_style is None:
            self._toolbar_style = _ToolbarStyle(QStyleFactory.create("Fusion"))
            self._toolbar_style.setObjectName("overflowToolbarStyle")
            self._toolbar_style.setParent(app)
        self.setStyle(self._toolbar_style)
        self._extension = self.findChild(QToolButton, "qt_toolbar_ext_button")
        self._extension.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        # Keep Qt's overflow layout, with our own single-row popup trigger above
        # its extension button. Qt otherwise replaces its menu during relayout.
        self.overflow_button = QToolButton(self)
        self.overflow_button.setObjectName("moreToolsButton")
        self.overflow_button.setStyleSheet("QToolButton::menu-indicator { image: none; }")
        self.overflow_button.hide()
        self.overflow_button.setIconSize(QSize(20, 20))
        self.overflow_button.setToolTip(tr("更多工具"))
        self.overflow_button.setAccessibleName(tr("更多工具"))
        self.overflow_menu = QMenu(self)
        self._overflow_controls = {}
        self._action_groups = {}
        self._group_buttons = {}
        self.overflow_button.setMenu(self.overflow_menu)
        self.overflow_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.overflow_menu.aboutToShow.connect(self._populate_overflow)
        self._extension.installEventFilter(self)
        self.overflow_button.installEventFilter(self)
        self._configure_overflow()

    def eventFilter(self, watched, event):
        if watched is self._extension and event.type() == QEvent.Type.Paint:
            return True
        if watched is self._extension and event.type() in (
            QEvent.Type.Show, QEvent.Type.Hide, QEvent.Type.Resize, QEvent.Type.Move,
        ):
            QTimer.singleShot(0, self._position_overflow)
        if watched is self.overflow_button and event.type() == QEvent.Type.PaletteChange:
            self.overflow_button.setIcon(toolbar_icon("more"))
        return super().eventFilter(watched, event)

    def _position_overflow(self):
        self.overflow_button.setGeometry(self._extension.geometry())
        self.overflow_button.setVisible(not self._extension.isHidden())
        self.overflow_button.raise_()

    def _configure_overflow(self):
        self.overflow_button.setIcon(toolbar_icon("more"))
        self.overflow_button.setMenu(self.overflow_menu)
        self.overflow_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)

    def add_overflow_controls(self, widget, controls):
        action = self.addWidget(widget)
        self._overflow_controls[action] = controls
        return action

    def widgetForAction(self, action):
        return self._group_buttons.get(action) or super().widgetForAction(action)

    def add_action_menu_group(self, action, menu):
        group = QWidget()
        layout = QHBoxLayout(group)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)
        button = QToolButton(group)
        button.setDefaultAction(action)
        button.setFixedSize(34, 34)
        button.setIconSize(QSize(20, 20))
        button.setProperty('stateButton', action.isCheckable())
        button.setAttribute(Qt.WidgetAttribute.WA_Hover, True)
        arrow = QToolButton(group)
        arrow.setObjectName('ocrLanguageMenu')
        arrow.setFixedSize(14, 34)
        arrow.setIconSize(QSize(12, 12))
        arrow.setIcon(toolbar_icon('chevron_down'))
        arrow.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        arrow.setMenu(menu)
        arrow.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        arrow.setStyleSheet('QToolButton { border: none; padding: 0; } '
                            'QToolButton::menu-indicator { image: none; }')
        layout.addWidget(button)
        layout.addWidget(arrow)
        group_action = self.addWidget(group)
        self._action_groups[group_action] = (action, menu)
        self._group_buttons[action] = button
        return arrow

    def _control_row(self, controls):
        row = QWidget()
        layout = QHBoxLayout(row)
        layout.setContentsMargins(12, 6, 12, 6)
        for source in controls:
            if isinstance(source, QCheckBox):
                control = QCheckBox(source.text())
                control.setTristate(source.isTristate())
                control.setCheckState(source.checkState())
                def toggle(_checked=False, source=source, control=control):
                    source.click()
                    # MainWindow synchronizes parity with signals blocked.
                    control.setCheckState(source.checkState())
                control.clicked.connect(toggle)
                source.checkStateChanged.connect(control.setCheckState)
            else:
                control = QSlider(source.orientation())
                control.setRange(source.minimum(), source.maximum())
                control.setValue(source.value())
                control.setFixedWidth(source.width())
                label = QLabel(f"{source.value()}%")
                control.valueChanged.connect(lambda value, label=label: label.setText(f"{value}%"))
                source.valueChanged.connect(control.setValue)
                control.valueChanged.connect(source.setValue)
                layout.addWidget(label)
            control.setEnabled(source.isEnabled())
            control.setToolTip(source.toolTip())
            control.setAccessibleName(source.accessibleName())
            layout.addWidget(control)
        action = QWidgetAction(self.overflow_menu)
        action.setDefaultWidget(row)
        return action

    def _populate_overflow(self):
        self.overflow_menu.clear()
        for action in self.actions():
            widget = self.widgetForAction(action)
            if action.isVisible() and widget is not None and not widget.isVisible():
                if action.isSeparator():
                    if self.overflow_menu.actions():
                        self.overflow_menu.addSeparator()
                elif action in self._overflow_controls:
                    self.overflow_menu.addAction(self._control_row(self._overflow_controls[action]))
                elif action in self._action_groups:
                    primary, menu = self._action_groups[action]
                    self.overflow_menu.addAction(primary)
                    self.overflow_menu.addMenu(menu)
                elif not isinstance(action, QWidgetAction):
                    self.overflow_menu.addAction(action)
                    if isinstance(widget, QToolButton) and widget.menu() is not None:
                        self.overflow_menu.addMenu(widget.menu())
        actions = self.overflow_menu.actions()
        if actions and actions[-1].isSeparator():
            self.overflow_menu.removeAction(actions[-1])
