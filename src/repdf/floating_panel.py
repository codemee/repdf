"""Themed, draggable floating sidebars shared by fullscreen panels."""
from PySide6.QtCore import QEvent, Qt
from PySide6.QtWidgets import QDialog, QFrame, QSizeGrip, QVBoxLayout


class FloatingPanel(QDialog):
    def __init__(self, controller, viewer, title):
        super().__init__(viewer, Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint)
        self.controller = controller
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setWindowTitle(title)
        self.resize(320, 550)
        self.setModal(False)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        self.frame = QFrame()
        self.frame.setObjectName('floatingNavigationFrame')
        outer.addWidget(self.frame)
        self.box = QVBoxLayout(self.frame)
        self.box.setContentsMargins(1, 1, 1, 1)
        self.size_grip = QSizeGrip(self)
        self.size_grip.setFixedSize(16, 16)
        self._drag_offset = None
        self._drag_widgets = []
        self.set_drag_widgets((controller.panel.header, controller.panel.title))
        controller.panel.close_button.setCursor(Qt.CursorShape.ArrowCursor)

    def set_drag_widgets(self, widgets):
        for widget in self._drag_widgets:
            widget.removeEventFilter(self)
            widget.unsetCursor()
        self._drag_widgets = list(widgets)
        for widget in self._drag_widgets:
            widget.installEventFilter(self)
            widget.setCursor(Qt.CursorShape.OpenHandCursor)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.size_grip.move(self.width() - 18, self.height() - 18)
        self.size_grip.raise_()

    def eventFilter(self, watched, event):
        if watched in self._drag_widgets:
            if event.type() == QEvent.Type.MouseButtonPress and event.button() == Qt.MouseButton.LeftButton:
                self._drag_offset = event.globalPosition().toPoint() - self.pos()
                return True
            if event.type() == QEvent.Type.MouseMove and self._drag_offset is not None:
                if event.buttons() & Qt.MouseButton.LeftButton:
                    self.move(event.globalPosition().toPoint() - self._drag_offset)
                    return True
            if event.type() == QEvent.Type.MouseButtonRelease and event.button() == Qt.MouseButton.LeftButton:
                self._drag_offset = None
                return True
        return super().eventFilter(watched, event)

    def detach_panel(self):
        self.set_drag_widgets(())
        self._drag_offset = None

    def closeEvent(self, event):
        self.controller.close()
        event.ignore()

    def reject(self):
        self.controller.close()


