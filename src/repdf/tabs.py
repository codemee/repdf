"""A document tab strip with scrolling controls at opposite ends."""

from PySide6.QtCore import QEvent, QSize, Qt, QTimer
from PySide6.QtWidgets import QMenu, QTabWidget, QToolButton

from repdf.strings import tr
from repdf.icons import toolbar_icon


class DocumentTabs(QTabWidget):
    CONTROL_WIDTH = 26

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setUsesScrollButtons(True)
        self._native_scroll = {}
        self._arrow_buttons = {}
        self._arrow_palettes = {}
        self._layout_timer = QTimer(self)
        self._layout_timer.setSingleShot(True)
        self._layout_timer.timeout.connect(self._align_controls)
        self.tabBar().setStyleSheet('QTabBar::scroller { width: 0px; } '
                                   'QTabBar::tear { width: 0px; border: none; image: none; }')
        self.tabBar().installEventFilter(self)
        for button in self.tabBar().findChildren(QToolButton):
            kind = 'previous' if button.objectName() == 'ScrollLeftButton' else 'next'
            self._native_scroll[kind] = button
            button.setFixedSize(0, 0)
            button.installEventFilter(self)
        self.scroll_left_button = self._make_arrow('previous', tr('向左捲動標籤'))
        self.scroll_right_button = self._make_arrow('next', tr('向右捲動標籤'))
        self.scroll_left_button.clicked.connect(self._native_scroll['previous'].click)
        self.scroll_right_button.clicked.connect(self._native_scroll['next'].click)
        for button in (self.scroll_left_button, self.scroll_right_button):
            button.setAutoRepeat(True)
        self.tab_list_button = self._make_arrow('chevron_down', tr('選擇標籤頁'))
        self.tab_list_button.setObjectName('documentTabList')
        self.tab_list_menu = QMenu(self)
        self.tab_list_menu.setToolTipsVisible(True)
        self.tab_list_menu.aboutToShow.connect(self.populate_tab_list)
        self.tab_list_button.setMenu(self.tab_list_menu)
        self.tab_list_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)

    def _make_arrow(self, kind, label):
        button = QToolButton(self)
        button.setIcon(toolbar_icon(kind))
        button.setIconSize(QSize(16, 16))
        button.setAutoRaise(True)
        button.setFixedWidth(self.CONTROL_WIDTH)
        button.setToolTip(label)
        button.setAccessibleName(label)
        button.setStyleSheet('QToolButton { padding: 0; border: none; border-radius: 0; } '
                            'QToolButton::menu-indicator { image: none; }')
        self._arrow_buttons[button] = kind
        button.installEventFilter(self)
        return button

    def eventFilter(self, watched, event):
        if watched in self._native_scroll.values():
            if event.type() == QEvent.Type.Paint:
                return True
            if event.type() in (QEvent.Type.EnabledChange, QEvent.Type.Show, QEvent.Type.Hide):
                self._layout_timer.start(0)
        if watched in self._arrow_buttons and event.type() == QEvent.Type.Paint:
            palette = watched.palette().cacheKey()
            if self._arrow_palettes.get(watched) != palette:
                self._arrow_palettes[watched] = palette
                watched.setIcon(toolbar_icon(self._arrow_buttons[watched]))
        if watched is self.tabBar() and event.type() in (QEvent.Type.Resize, QEvent.Type.Move, QEvent.Type.LayoutRequest):
            self._layout_timer.start(0)
        return super().eventFilter(watched, event)

    def _align_controls(self):
        if not hasattr(self, 'tab_list_button'):
            return
        bar = self.tabBar()
        width = self.CONTROL_WIDTH
        bar.setMaximumWidth(max(1, self.width() - width * 3))
        bar.move(width, bar.y())
        for button, x in ((self.scroll_left_button, 0),
                          (self.scroll_right_button, self.width() - width * 2),
                          (self.tab_list_button, self.width() - width)):
            button.setGeometry(x, bar.y(), width, bar.height())
            button.raise_()
        for kind, button in (('previous', self.scroll_left_button), ('next', self.scroll_right_button)):
            native = self._native_scroll[kind]
            button.setEnabled(native.isVisible() and native.isEnabled())

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._align_controls()

    def showEvent(self, event):
        super().showEvent(event)
        self._align_controls()

    def paintEvent(self, event):
        super().paintEvent(event)
        # QTabWidget can lazily restore its standard tab-bar position while
        # painting. Reapply the reserved left strip before children are drawn.
        self._align_controls()

    def populate_tab_list(self):
        self.tab_list_menu.clear()
        for index in range(self.count()):
            document = self.widget(index)
            path = document.source_path
            label = path.name + (' *' if document.modified else '')
            action = self.tab_list_menu.addAction(label.replace('&', '&&'))
            action.setToolTip(str(path))
            action.setData(document.document_id)
            action.setCheckable(True)
            action.setChecked(document is self.currentWidget())
            action.triggered.connect(lambda _checked, doc=document: self._select_document(doc))

    def _select_document(self, document):
        for index in range(self.count()):
            if self.widget(index) is document:
                self.setCurrentIndex(index)
                break
