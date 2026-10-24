"""Draggable annotation tools for the reading window and fullscreen preview."""

from PySide6.QtCore import QEvent, QPoint, QSize, Qt
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLayout, QToolButton
from repdf.icons import toolbar_icon
from repdf.strings import tr
from repdf.toolbar import OverflowToolBar


class FloatingAnnotationTools(QFrame):
    def __init__(self, viewer, *, owner=None):
        super().__init__(viewer)
        self.viewer = viewer
        self.fullscreen = owner is None
        self.owner = viewer.owner if self.fullscreen else owner
        self.bounds_widget = viewer if self.fullscreen else owner.centralWidget()
        self.setObjectName("fullscreenAnnotationTools")
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.manual_position = False
        self.drag_origin = None
        self.saved_menus = []
        self.arrows = []
        self.buttons = {}
        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 0, 4, 0)
        layout.setSpacing(2)
        layout.setSizeConstraint(QLayout.SizeConstraint.SetNoConstraint)
        self.grip = QToolButton(self)
        self.grip.setFixedSize(18, 34)
        self.grip.setIconSize(QSize(16, 20))
        self.grip.setStyleSheet("QToolButton { padding: 0; border: none; }")
        self.grip.setToolTip(tr("拖曳移動工具列"))
        self.grip.setAccessibleName(tr("拖曳移動工具列"))
        self.grip.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.grip.setCursor(Qt.CursorShape.OpenHandCursor)
        self.grip.installEventFilter(self)
        layout.addWidget(self.grip)
        self.toggle = QToolButton(self)
        self.toggle.setCheckable(True)
        self.toggle.setProperty("stateButton", True)
        self.toggle.setFixedSize(34, 34)
        self.toggle.setIconSize(QSize(20, 20))
        self.toggle.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        layout.addWidget(self.toggle)
        self.toolbar = (OverflowToolBar(tr("註解與擷取"), self) if self.fullscreen
                        else self.owner.annotation_toolbar)
        self.toolbar.setObjectName("floatingAnnotationBar")
        self.toolbar.setMovable(False)
        self.toolbar.setFloatable(False)
        self.toolbar.setOrientation(Qt.Orientation.Horizontal)
        self.toolbar.setMinimumWidth(0)
        self.toolbar.setMaximumWidth(16777215)
        self.toolbar.setFixedHeight(42)
        self.toolbar.setIconSize(QSize(20, 20))
        self.toolbar.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
        layout.addWidget(self.toolbar)
        editor = self.owner.annotation_editor
        groups = [
            (editor.mark_action, editor.mark_menu),
            (editor.callout_action, editor.callout_menu),
            (editor.draw_action, editor.draw_menu),
        ]
        actions = [action for action, _menu in groups]
        if self.fullscreen:
            for action, menu in groups:
                self.add_group(action, menu)
            self.toolbar.addSeparator()
            self.toolbar.addAction(self.owner.copy_text_action)
            self.add_group(self.owner.region_ocr_action, self.owner.ocr_languages.menu)
            self.toolbar.addAction(self.owner.extract_image_action)
            actions.extend((self.owner.copy_text_action, self.owner.region_ocr_action,
                            self.owner.extract_image_action))
        for action in actions:
            button = self.toolbar.widgetForAction(action)
            button.setFixedSize(34, 34)
            button.setIconSize(QSize(20, 20))
            button.setProperty("stateButton", True)
            button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            button.setAttribute(Qt.WidgetAttribute.WA_Hover, True)
            self.buttons[action] = button
        if self.fullscreen:
            self.mode_toolbar = OverflowToolBar(tr('全螢幕模式'), self)
            self.mode_toolbar.setObjectName('floatingAnnotationBar')
            self.mode_toolbar.setMovable(False)
            self.mode_toolbar.setFloatable(False)
            self.mode_toolbar.setFixedSize(60, 42)
            self.mode_toolbar.setIconSize(QSize(20, 20))
            self.mode_toolbar.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
            layout.addWidget(self.mode_toolbar)
            self.add_group(self.owner.fullscreen_action, self.owner.fullscreen_menu, toolbar=self.mode_toolbar)
            mode_button = self.mode_toolbar.widgetForAction(self.owner.fullscreen_action)
            mode_button.setFixedSize(34, 34)
            mode_button.setIconSize(QSize(20, 20))
            mode_button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            self.buttons[self.owner.fullscreen_action] = mode_button
        else:
            self.toggle.hide()
        self.toolbar.group_sections()
        for action in actions:
            self.buttons[action] = self.toolbar.widgetForAction(action)
        active = bool(editor.mode() or self.owner._selection_active())
        expanded = self.owner.settings.value(
            "view/fullscreen_tools_expanded",
            self.owner.annotation_tools_action.isChecked(),
            type=bool,
        )
        self.toggle.setChecked(expanded or active if self.fullscreen else True)
        self.toolbar.setVisible(self.toggle.isChecked())
        self.toggle.toggled.connect(self.set_expanded)
        self.refresh_icons()
        self.setVisible(self.fullscreen or self.owner.annotation_tools_action.isChecked())
        self.bounds_widget.installEventFilter(self)
        self.reposition()

    def add_group(self, action, menu, *, toolbar=None):
        self.saved_menus.append((menu, menu.parentWidget(), menu.windowFlags()))
        menu.setParent(self.viewer, menu.windowFlags())
        arrow = (toolbar or self.toolbar).add_action_menu_group(
            action, menu, arrow_name="fullscreenAnnotationMenu"
        )
        arrow.setToolTip(menu.title() or action.text())
        self.arrows.append(arrow)

    def restore_menus(self):
        for menu, parent, flags in self.saved_menus:
            menu.hide()
            menu.setParent(parent, flags)
        self.saved_menus.clear()

    def refresh_icons(self):
        self.toolbar.setWindowTitle(tr("註解與擷取" if self.fullscreen else "註解工具"))
        self.grip.setIcon(toolbar_icon("drag_handle"))
        self.toggle.setIcon(toolbar_icon("edit_tools"))
        label = tr("收合註解工具" if self.toggle.isChecked() else "展開註解工具")
        self.toggle.setToolTip(label)
        self.toggle.setAccessibleName(label)
        for arrow in self.arrows:
            arrow.setIcon(toolbar_icon("chevron_down"))

    def set_expanded(self, expanded):
        self.toolbar.setVisible(expanded)
        if not expanded:
            self.owner._finish_annotation_modes(include_extraction=self.fullscreen)
        self.owner.settings.setValue("view/fullscreen_tools_expanded", expanded)
        self.refresh_icons()
        self.reposition()

    def reposition(self):
        bounds = self.available_rect()
        self.setMaximumWidth(max(1, bounds.width() - 16))
        self.setMaximumHeight(max(1, bounds.height() - 16))
        self.layout().activate()
        self.adjustSize()
        if not self.manual_position:
            self.move(
                bounds.left() + max(8, (bounds.width() - self.width()) // 2),
                max(bounds.top() + 8, bounds.bottom() + 1 - self.height() - 16),
            )
        self.move(self.clamped(self.pos()))
        self.raise_()

    def available_rect(self):
        return self.viewer.rect() if self.fullscreen else self.bounds_widget.geometry()

    def clamped(self, point):
        bounds = self.available_rect()
        return QPoint(
            max(bounds.left() + 8, min(max(bounds.left() + 8, bounds.right() + 1 - self.width() - 8), point.x())),
            max(bounds.top() + 8, min(max(bounds.top() + 8, bounds.bottom() + 1 - self.height() - 8), point.y())),
        )

    def eventFilter(self, watched, event):
        if watched is self.bounds_widget and event.type() in (QEvent.Type.Resize, QEvent.Type.Show):
            self.reposition()
        if watched is self.grip:
            if (
                event.type() == QEvent.Type.MouseButtonPress
                and event.button() == Qt.MouseButton.LeftButton
            ):
                self.drag_origin = event.globalPosition().toPoint()
                self.start_position = self.pos()
                self.grip.setCursor(Qt.CursorShape.ClosedHandCursor)
                return True
            if event.type() == QEvent.Type.MouseMove and self.drag_origin is not None:
                self.manual_position = True
                self.move(
                    self.clamped(
                        self.start_position
                        + event.globalPosition().toPoint()
                        - self.drag_origin
                    )
                )
                return True
            if (
                event.type() == QEvent.Type.MouseButtonRelease
                and event.button() == Qt.MouseButton.LeftButton
            ):
                self.drag_origin = None
                self.grip.setCursor(Qt.CursorShape.OpenHandCursor)
                return True
        return super().eventFilter(watched, event)

    def changeEvent(self, event):
        super().changeEvent(event)
        if (
            event.type() == QEvent.Type.PaletteChange
            and hasattr(self, "arrows")
            and hasattr(self, "toggle")
        ):
            self.refresh_icons()
