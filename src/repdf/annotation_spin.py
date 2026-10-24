"""Annotation-panel spin controls using the toolbar's chevron icons."""

from PySide6.QtCore import QEvent, QSize, Qt
from PySide6.QtWidgets import QAbstractSpinBox, QDoubleSpinBox, QSpinBox, QToolButton
from repdf.icons import toolbar_icon
from repdf.strings import tr


class _ChevronSteps:
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setProperty("annotationSpin", True)
        self.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)
        self.setMinimumHeight(30)
        self.setMinimumWidth(84)
        self.lineEdit().setTextMargins(0, 0, 20, 0)
        self.up_button = QToolButton(self)
        self.down_button = QToolButton(self)
        for button, label in [
            (self.up_button, "增加數值"),
            (self.down_button, "減少數值"),
        ]:
            button.setIconSize(QSize(12, 12))
            button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            button.setAutoRepeat(True)
            button.setAutoRepeatDelay(350)
            button.setAutoRepeatInterval(80)
            button.setToolTip(tr(label))
            button.setAccessibleName(tr(label))
            button.setStyleSheet(
                "QToolButton { padding: 0; border: none; border-radius: 3px; }"
            )
        self.up_button.clicked.connect(self.stepUp)
        self.down_button.clicked.connect(self.stepDown)
        self.valueChanged.connect(self._update_steps)
        self._refresh_step_icons()
        self._update_steps()
        self.style().unpolish(self)
        self.style().polish(self)

    def _sync_steps(self):
        if hasattr(self, "down_button"):
            self._update_steps()

    def setValue(self, value):
        super().setValue(value)
        self._sync_steps()

    def setRange(self, minimum, maximum):
        super().setRange(minimum, maximum)
        self._sync_steps()

    def setMinimum(self, value):
        super().setMinimum(value)
        self._sync_steps()

    def setMaximum(self, value):
        super().setMaximum(value)
        self._sync_steps()

    def setReadOnly(self, value):
        super().setReadOnly(value)
        self._sync_steps()

    def _refresh_step_icons(self):
        self.up_button.setIcon(toolbar_icon("chevron_up"))
        self.down_button.setIcon(toolbar_icon("chevron_down"))

    def _update_steps(self, *_):
        enabled = not self.isReadOnly()
        self.up_button.setEnabled(
            enabled and (self.wrapping() or self.value() < self.maximum())
        )
        self.down_button.setEnabled(
            enabled and (self.wrapping() or self.value() > self.minimum())
        )

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, "up_button"):
            half = (self.height() - 2) // 2
            self.up_button.setGeometry(self.width() - 18, 1, 16, half)
            self.down_button.setGeometry(
                self.width() - 18, half + 1, 16, self.height() - half - 2
            )
            self.up_button.raise_()
            self.down_button.raise_()

    def changeEvent(self, event):
        super().changeEvent(event)
        if event.type() == QEvent.Type.PaletteChange and hasattr(self, "up_button"):
            self._refresh_step_icons()


class AnnotationSpinBox(_ChevronSteps, QSpinBox):
    pass


class AnnotationDoubleSpinBox(_ChevronSteps, QDoubleSpinBox):
    pass
