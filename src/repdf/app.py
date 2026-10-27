from __future__ import annotations

from repdf.strings import tr, localize_text

import sys
import shutil
import tempfile
from html import escape
from importlib.resources import files
from pathlib import Path
from shiboken6 import isValid

from PySide6.QtCore import QEvent, QPointF, QSettings, QSize, Qt, QThreadPool, QTimer, Slot
from PySide6.QtGui import (
    QCloseEvent,
    QAction,
    QActionGroup,
    QFont,
    QFontDatabase,
    QIcon,
    QImage,
    QKeySequence,
)
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QDialog,
    QAbstractButton,
    QAbstractSlider,
    QFileDialog,
    QHBoxLayout,
    QLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMenu,
    QMessageBox,
    QScrollArea,
    QSizePolicy,
    QSlider,
    QTabWidget,
    QTabBar,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from repdf.core import (
    SelectionState,
    default_output_path,
    parity_state,
    set_parity,
    split_output_paths,
    DocumentSelection,
)
from repdf import __version__
from repdf.icons import toolbar_icon
from repdf.theme import ThemeController
from repdf.preferences import LanguageController, migrate_preferences
from repdf.renderer import RenderService, start_render_backend
from repdf.widgets import PageCard, PageGrid, PageGridLayout, PdfPasswordDialog
from repdf.toolbar import OverflowToolBar
from repdf.shortcut_hints import ShortcutHints, native_shortcuts
from repdf.message_dialogs import unsaved_changes_message
from repdf.preview import FullscreenPreview
from repdf.floating_tools import FloatingAnnotationTools
from repdf.workers import ExportPdfTask, LoadPdfTask
from repdf.search_panel import SearchController
from repdf.document_text import DocumentTextCopy
from repdf.png_export import PngExportController, png_output_paths
from repdf.page_view import PageViewport, PreviewCache
from repdf.navigation import NavigationController
from repdf.printing import PrintController
from repdf.ocr_languages import OcrLanguageController
from repdf.saving import SaveController
from repdf.annotation_store import AnnotationStore
from repdf.annotation_editor import AnnotationEditor
from repdf.about import AboutDialog
from repdf.system_menu import WindowsSystemMenu


class DocumentView(QWidget):
    REFERENCE_PAGE_WIDTH_POINTS = 595
    SCREEN_DPI = 96
    PDF_DPI = 72

    def __init__(self, owner, document_id: int, path: Path) -> None:
        super().__init__()
        self.owner = owner
        self.document_id = document_id
        self.source_path = path.resolve()
        self.page_count = 0
        self.selected_pages = set()
        self.page_order = []
        self.page_cards = []
        self.zoom = 100
        self.fit_mode = False
        self.fit_page_index = 0
        self._fit_navigation_pending = False
        self.focused_page = None
        self.page_sizes = {}
        self.page_links = {}
        self.page_annotations = {}
        self.page_labels = {}
        self.bookmarks = None
        self.annotations = None
        self.annotation_store = AnnotationStore(self)
        self.annotation_store.changed.connect(lambda: self.owner.annotation_editor.changed(self))
        self.ready = False
        self._search_navigation = None
        self.password: str | None = None
        self.render_generation = -1
        self._render_received = set()
        self._render_pending = 0
        self._render_done_generation = -1
        self.include_checkbox = QCheckBox()
        self.include_checkbox.setObjectName('tabIncludeCheckbox')
        self.include_checkbox.setToolTip(tr('勾選此檔案以加入重組或拆分；未勾選任何標籤時僅輸出目前檔案'))
        self.include_checkbox.setEnabled(False)
        self.include_checkbox.toggled.connect(owner._sync_controls)
        self.close_button = QToolButton()
        self.close_button.setText("×")
        self.close_button.setToolTip(tr('關閉此檔案（{p0}）', p0=owner.close_shortcut_text))
        self.close_button.setFixedSize(22, 22)
        self.close_button.clicked.connect(lambda: owner.close_tab(owner.tabs.indexOf(self)))
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        horizontal = self.scroll_area.horizontalScrollBar()
        horizontal.rangeChanged.connect(lambda minimum, maximum:
                                        horizontal.setValue((minimum + maximum) // 2))
        self.scroll_area.viewport().installEventFilter(self)
        self.grid_host = PageGrid()
        self.grid_host.insertion_requested.connect(self._insert_page)
        self.grid_host.drag_finished.connect(self._reflow_grid)
        self.grid = PageGridLayout(self.grid_host)
        self.grid.setContentsMargins(12, 12, 12, 12)
        self.grid.setSpacing(12)
        self.grid.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignHCenter)
        self.empty_label = QLabel(tr('正在讀取 PDF…'))
        self.empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.grid.addWidget(self.empty_label, 0, 0)
        self.scroll_area.setWidget(self.grid_host)
        root.addWidget(self.scroll_area)
        self.render_timer = QTimer(self)
        self.render_timer.setSingleShot(True)
        self.render_timer.setInterval(250)
        self.render_timer.timeout.connect(self._queue_all_renders)
        self.fit_timer = QTimer(self)
        self.fit_timer.setSingleShot(True)
        self.fit_timer.setInterval(150)
        self.fit_timer.timeout.connect(self._apply_fit)
        self.pages = PageViewport(self)

    def loaded(self, page_count: int) -> None:
        self.page_count = page_count
        self.ready = True
        self.empty_label.hide()
        self.grid.removeWidget(self.empty_label)
        self._create_page_cards()
        for card in self.page_cards:
            card.checkbox.setEnabled(not self.owner._export_running)
        self.include_checkbox.setEnabled(not self.owner._export_running)
        if self.fit_mode:
            self.fit_timer.start()

    @property
    def modified(self):
        return self.ready and (self.page_order != list(range(self.page_count)) or self.annotation_store.modified)

    def eventFilter(self, watched, event) -> bool:
        if watched is self.scroll_area.viewport() and event.type() == QEvent.Type.Resize:
            QTimer.singleShot(0, self._reflow_grid)
            if self.fit_mode:
                self.fit_timer.start()
        return super().eventFilter(watched, event)

    def show_status(self, message: str) -> None:
        if self.owner.current_document() is self and not self.owner._export_running:
            self.owner.statusBar().showMessage(message)

    def _create_page_cards(self) -> None:
        self.pages.initialize()

    def _make_page_card(self, page_index):
        card = PageCard(page_index, self._target_preview_width())
        card.setParent(self.grid_host)
        card.set_text_copy_mode(self.owner._selection_active(), region=self.owner.region_ocr_action.isChecked(),
                                image=self.owner.extract_image_action.isChecked())
        card.checkbox.setEnabled(not self.owner._export_running)
        card.selection_changed.connect(self._page_selection_changed)
        card.reorder_requested.connect(self._move_page)
        card.focused.connect(self._focus_page)
        card.text_selected.connect(lambda index, start, end, preview=card.preview:
                                  self.owner._copy_text_selection(self, index, preview, start, end))
        card.selection_preview.connect(lambda index, start, end, preview=card.preview:
                                      self.owner._copy_text_selection(self, index, preview, start, end, copy=False))
        self.pages.prepare_card(card)
        self.owner.annotation_editor.attach(card.preview,self,page_index)
        card.preview.set_links(self.page_links.get(page_index, []))
        card.preview.set_annotations(self.page_annotations.get(page_index, []))
        card.preview.link_activated.connect(lambda destination: self.owner.navigation.activate(self, destination))
        self.pages.chrome = max(1, card.sizeHint().height() - card.preview.height())
        return card

    def _target_preview_width(self) -> int:
        return max(
            55,
            round(self.REFERENCE_PAGE_WIDTH_POINTS * self._preview_scale()),
        )

    def _preview_scale(self) -> float:
        return self.zoom / 100 * self.SCREEN_DPI / self.PDF_DPI

    def _reflow_grid(self) -> None:
        self.pages.reflow()

    @Slot(int, int)
    def _insert_page(self, source_index: int, insertion: int) -> None:
        if self.owner._export_running or self.owner._selection_active() or source_index not in self.page_order:
            return
        self.page_order.remove(source_index)
        self.page_order.insert(insertion, source_index)
        self._reflow_grid()
        self.owner._sync_controls()
        self.show_status(
            tr('已調整第 {p0} 頁的預覽與輸出順序', p0=source_index + 1)
        )

    @Slot(int, int)
    def _move_page(self, source_index: int, target_index: int) -> None:
        if self.owner._export_running or self.owner._selection_active() or source_index == target_index:
            return
        if source_index not in self.page_order or target_index not in self.page_order:
            return
        source_position = self.page_order.index(source_index)
        target_position = self.page_order.index(target_index)
        self.page_order.pop(source_position)
        insertion = self.page_order.index(target_index)
        if source_position < target_position:
            insertion += 1
        self.page_order.insert(insertion, source_index)
        self._reflow_grid()
        self.owner._sync_controls()
        self.show_status(
            tr('已調整第 {p0} 頁的預覽與輸出順序', p0=source_index + 1)
        )

    @Slot(int, bool)
    def _page_selection_changed(self, page_index: int, selected: bool) -> None:
        if selected:
            self.selected_pages.add(page_index)
        else:
            self.selected_pages.discard(page_index)
        self._selection_updated()

    def _toggle_parity(self, odd: bool, checked: bool) -> None:
        if self.owner._syncing_bulk:
            return
        self.selected_pages = set_parity(
            self.selected_pages, self.page_count, odd, checked
        )
        for card in self.page_cards:
            card.set_selected(card.page_index in self.selected_pages)
        self._selection_updated()

    def _selection_updated(self) -> None:
        self.owner._sync_controls()

    def set_zoom(self, value: int) -> None:
        was_fit = self.fit_mode
        self.fit_mode = False
        self._fit_navigation_pending = False
        self.fit_timer.stop()
        if was_fit:
            self._reflow_grid()
        if self.zoom == value:
            return
        self.zoom = value
        self.pages.batch = []
        self._render_pending = 0
        self.owner.render_service.cancel_pending(self.document_id)
        self.render_generation = -1
        for generation, document_id in list(self.owner._render_documents.items()):
            if document_id == self.document_id:
                self.owner._render_documents.pop(generation)
        if self.page_cards:
            self._reflow_grid()
            self.render_timer.start()

    def _focus_page(self, page_index: int) -> None:
        self.focused_page = page_index
        self.owner._update_page_indicator()

    def preview_page_index(self, *, prefer_focused=True) -> int:
        return self.pages.current_page(prefer_focused)

    def fit_page(self) -> None:
        index = self.preview_page_index()
        self.fit_page_index = index
        self.fit_mode = True
        self._apply_fit()

    def _apply_fit(self) -> None:
        if not self.fit_mode or not self.ready or self.owner._closing:
            return
        card = self.page_cards[self.fit_page_index]
        points = self.pages.page_size(self.fit_page_index)
        width, height = points
        margins = self.grid.contentsMargins()
        chrome = max(0, card.sizeHint().height() - card.preview.height())
        available_width = max(1, self.scroll_area.viewport().width() - margins.left() - margins.right() - 26)
        # Grid margins surround the entire document, not each fitted page.
        # Fit the card to the viewport and scroll it into alignment separately.
        available_height = max(1, self.scroll_area.viewport().height() - chrome - 2)
        zoom = round(min(available_width / width, available_height / height) * self.PDF_DPI / self.SCREEN_DPI * 100, 2)
        if abs(zoom - self.zoom) > 0.05:
            self.zoom = zoom
            self.render_timer.start()
        self._reflow_grid()
        self.owner._sync_controls()
        QTimer.singleShot(0, self._scroll_to_fit_page)

    def _scroll_to_fit_page(self) -> None:
        if not self.fit_mode or self.owner._closing:
            return
        if self._search_navigation and self._search_navigation[0] == self.fit_page_index:
            self._scroll_to_search_result()
            return
        card = self.pages.rect(self.fit_page_index)
        viewport = self.scroll_area.viewport()
        self.scroll_area.verticalScrollBar().setValue(
            card.y() + (card.height() - viewport.height()) // 2)
        self.scroll_area.horizontalScrollBar().setValue(
            card.x() + (card.width() - viewport.width()) // 2)
        self._fit_navigation_pending = False

        self.owner._update_page_indicator()

    def jump_to_search_result(self, page, rect):
        self.focused_page = page
        self._search_navigation = (page, rect)
        if self.fit_mode:
            self.fit_page_index = page
            self._fit_navigation_pending = True
            self._apply_fit()
        QTimer.singleShot(0, self._scroll_to_search_result)
        self.owner._update_page_indicator()

    def jump_to_page(self, page, point=(0, 0)):
        x, y = point
        self.jump_to_search_result(page, [x, y, x, y])

    def _scroll_to_search_result(self):
        if self.owner._closing or self._search_navigation is None:
            return
        page, rect = self._search_navigation
        label = self.pages.ensure_page(page).preview
        # Scroll using the placeholder geometry before its image is available.
        # On-demand rendering only starts once the target enters the viewport;
        # the render callback then refines this position with the actual size.
        from PySide6.QtCore import QPoint
        point = label.mapTo(self.grid_host, QPoint(round((rect[0] + rect[2]) / 2 * label.width()),
                                                   round((rect[1] + rect[3]) / 2 * label.height())))
        self.scroll_area.ensureVisible(point.x(), point.y(), 40, 40)
        self._fit_navigation_pending = False
        self.owner._update_page_indicator()

    @Slot()
    def _queue_all_renders(self) -> None:
        # Keep this entry point for toolbar/tab callers; work is now viewport-only.
        self.pages.request_visible()

    @Slot(object)
    def _handle_render_message(self, payload: object) -> None:
        if isinstance(payload, dict) and payload.get('generation') == self.render_generation:
            self.pages.receive(payload)

    def _accept_render_page(self, payload) -> None:
        self.pages.accept(payload)

    def _reset_render_state(self) -> None:
        self._render_received.clear()



class MainWindow(QMainWindow):
    def __init__(self, render_backend=None) -> None:
        super().__init__()
        self.settings = QSettings("repdf", "repdf")
        migrate_preferences(self.settings, QSettings("PDFPick", "PDFPick"))
        self.language_controller = LanguageController(self.settings.value("ui/language", "system"), self)
        self._theme_controller = ThemeController(QApplication.instance(), self.settings.value("ui/theme", "system"), self)
        self._update_window_title()
        self.setWindowIcon(load_app_icon())
        self.resize(1040, 760)
        self.setMinimumSize(320, 240)
        self.setAcceptDrops(True)
        self.thread_pool = QThreadPool(self)
        self.thread_pool.setMaxThreadCount(4)
        self.preview_temp = tempfile.TemporaryDirectory(prefix="repdf-preview-")
        self.preview_cache = PreviewCache()
        self.render_service = RenderService(render_backend if render_backend is not None else start_render_backend(), self)
        self.render_service.message.connect(self._handle_render_message, Qt.ConnectionType.QueuedConnection)
        self.documents = {}
        self._next_document_id = 0
        self._next_generation = 0
        self._render_documents = {}
        self._text_requests = {}
        self._ocr_generations = {}
        self._image_requests = {}
        self._active_tasks = set()
        self._load_batches = {}
        self._password_queue = []
        self._password_dialog = None
        self._password_document_id = None
        self._document_batches = {}
        self._next_batch = 0
        self._export_running = False
        self._export_id = 0
        self._syncing_bulk = False
        self._closing = False
        self._discard_on_close = set()
        self._fullscreen_preview = None
        self._build_toolbar()
        central = QWidget()
        root = QVBoxLayout(central)
        root.setContentsMargins(12, 10, 12, 12)
        self.empty_label = QLabel(tr('請先開啟 PDF 檔案，或將多個 PDF 拖曳到視窗'))
        self.empty_label.setWordWrap(True)
        self.empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        root.addWidget(self.empty_label)
        self.tabs = QTabWidget()
        self.tabs.setDocumentMode(True)
        self.tabs.setMovable(True)
        self.tabs.setElideMode(Qt.TextElideMode.ElideRight)
        self.tabs.tabBar().setExpanding(False)
        self.tabs.tabBar().setDrawBase(False)
        self.tabs.currentChanged.connect(self._tab_changed)
        self.tabs.tabBar().tabMoved.connect(self._sync_controls)
        self.tabs.hide()
        root.addWidget(self.tabs)
        self.navigation = NavigationController(self, central)
        self.search_controller = SearchController(self, self.navigation.workspace)
        self.setCentralWidget(self.search_controller.workspace)
        self.annotation_floating = FloatingAnnotationTools(self, owner=self)
        self.statusBar().setSizeGripEnabled(False)
        self.statusBar().showMessage(tr('就緒'))
        self._build_page_navigation()
        self.print_controller = PrintController(self)
        self.saving = SaveController(self)
        self.document_text = DocumentTextCopy(self)
        self.png_export = PngExportController(self)
        self.language_controller.changed.connect(self._retranslate)
        self._update_preference_actions()

        QApplication.instance().installEventFilter(self)
        self._sync_controls()

        self._about_dialog = None
        self.about_action = QAction(tr('關於 RePDF'), self)
        self.about_action.setMenuRole(QAction.MenuRole.AboutRole)
        self.about_action.triggered.connect(self.show_about)
        self.addAction(self.about_action)
        if sys.platform != 'win32':
            self.menuBar().setNativeMenuBar(True)
            self.menuBar().addMenu(tr('說明')).addAction(self.about_action)
        self._windows_system_menu = WindowsSystemMenu(self)

    def show_about(self):
        if self._about_dialog is None or not isValid(self._about_dialog):
            self._about_dialog = AboutDialog(self._fullscreen_preview or self)
        self._about_dialog.show()
        self._about_dialog.raise_()
        self._about_dialog.activateWindow()

    def showEvent(self, event):
        super().showEvent(event)
        menu = getattr(self, '_windows_system_menu', None)
        if menu is not None:
            menu.refresh()

    def event(self, event):
        result = super().event(event)
        if event.type() == QEvent.Type.WinIdChange:
            menu = getattr(self, '_windows_system_menu', None)
            if menu is not None and menu.api is not None:
                QTimer.singleShot(0, menu.refresh)
        return result

    def nativeEvent(self, event_type, message):
        menu = getattr(self, '_windows_system_menu', None)
        if menu is not None and menu.native_event(event_type, message):
            return True, 0
        return super().nativeEvent(event_type, message)

    def _build_page_navigation(self):
        self._page_edit_dirty = False
        self._page_edit_document = None
        self.page_controls = QWidget()
        self.page_controls.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
        row = QHBoxLayout(self.page_controls)
        row.setContentsMargins(8, 0, 4, 0)
        row.setSpacing(4)
        self.book_page_label = QLabel()
        self.book_page_label.setTextFormat(Qt.TextFormat.PlainText)
        self.book_page_label.setMinimumWidth(0)
        self.book_page_label.hide()
        row.addWidget(self.book_page_label)
        self.page_number_caption = QLabel(tr('頁碼'))
        row.addWidget(self.page_number_caption)
        self.page_number_input = QLineEdit()
        self.page_number_input.setObjectName('pageNumberInput')
        self.page_number_input.setAccessibleName(tr('目前頁碼，輸入後按 Enter 跳頁'))
        self.page_number_input.setInputMethodHints(Qt.InputMethodHint.ImhDigitsOnly)
        self.page_number_input.setMaxLength(10)
        self.page_number_input.setAlignment(Qt.AlignmentFlag.AlignRight)
        self.page_number_input.setFixedSize(48, 22)
        self.page_number_input.textEdited.connect(lambda: setattr(self, '_page_edit_dirty', True))
        self.page_number_input.returnPressed.connect(self._jump_from_page_field)
        row.addWidget(self.page_number_input)
        self.page_total = QLabel('/ 0')
        row.addWidget(self.page_total)
        self.statusBar().addPermanentWidget(self.page_controls)
        self._update_page_indicator()

    def _update_page_indicator(self):
        if not hasattr(self, 'page_number_input') or self._closing:
            return
        doc = self.current_document()
        ready = doc is not None and doc.ready and bool(doc.page_order)
        document_id = doc.document_id if ready else None
        if self._page_edit_document != document_id:
            self._page_edit_dirty = False
            self._page_edit_document = document_id
        self.page_number_input.setEnabled(ready)
        total = doc.page_count if ready else 0
        self.page_total.setText(f'/ {total}')
        digits = max(3, len(str(total)))
        width = self.page_number_input.fontMetrics().horizontalAdvance('9' * digits) + 18
        self.page_number_input.setFixedWidth(max(44, min(88, width)))
        self.page_number_input.setToolTip(
            tr('目前原始頁碼；輸入 1–{p0} 後按 Enter 跳頁，Esc 取消', p0=total)
            if ready else tr('請先開啟 PDF 檔案'))
        current = doc.preview_page_index() if ready else None
        label = doc.page_labels.get(current) if ready else None
        self.book_page_label.setVisible(bool(label))
        self.page_number_caption.setText('PDF' if label else tr('頁碼'))
        if label:
            text = tr('書頁 {p0}｜', p0=' '.join(label.split()))
            metrics = self.book_page_label.fontMetrics()
            fixed = (self.page_number_input.width() + metrics.horizontalAdvance('PDF')
                     + metrics.horizontalAdvance(self.page_total.text()) + 40)
            available = min(180, max(24, self.width() - fixed - 24))
            self.book_page_label.setMaximumWidth(available)
            self.book_page_label.setText(metrics.elidedText(text, Qt.TextElideMode.ElideRight, available))
            self.book_page_label.setAccessibleName(tr('書頁 {p0}', p0=label))
            self.book_page_label.setToolTip('<qt>' + escape(tr('PDF 內建頁碼標籤：{p0}', p0=label)) + '</qt>')
        else:
            self.book_page_label.clear()
            self.book_page_label.setToolTip('')
            self.book_page_label.setAccessibleName('')
        if not (self.page_number_input.hasFocus() and self._page_edit_dirty):
            page = current + 1 if ready else '-'
            self.page_number_input.setText(str(page))

    def _jump_from_page_field(self):
        doc = self.current_document()
        if doc is None or not doc.ready:
            return
        try:
            text = self.page_number_input.text().strip()
            if not text.isdecimal():
                raise ValueError
            number = int(text)
            if not 1 <= number <= doc.page_count:
                raise ValueError
        except ValueError:
            self.statusBar().showMessage(tr('請輸入 1–{p0} 的頁碼', p0=doc.page_count), 3000)
            self.page_number_input.selectAll()
            return
        self._page_edit_dirty = False
        page = number - 1
        doc.focused_page = page
        doc._search_navigation = None
        if doc.fit_mode:
            doc.fit_page_index = page
            doc._fit_navigation_pending = True
            doc._apply_fit()
        else:
            rect = doc.pages.rect(page)
            doc.scroll_area.verticalScrollBar().setValue(rect.y())
            doc.scroll_area.horizontalScrollBar().setValue(
                rect.x() + (rect.width() - doc.scroll_area.viewport().width()) // 2)
            doc.pages.schedule()
        self.page_number_input.clearFocus()
        doc.scroll_area.setFocus()
        self._update_page_indicator()

    def eventFilter(self, watched, event) -> bool:
        editor=getattr(self,'annotation_editor',None)
        text_editor=editor.text_edit if editor is not None else None
        if text_editor is not None and isinstance(watched,QWidget) and (watched is text_editor or text_editor.isAncestorOf(watched)):
            return False
        if watched is getattr(self, 'page_number_input', None):
            if event.type() == QEvent.Type.FocusIn:
                QTimer.singleShot(0, self.page_number_input.selectAll)
            elif event.type() == QEvent.Type.FocusOut:
                self._page_edit_dirty = False
                QTimer.singleShot(0, self._update_page_indicator)
        controller = getattr(self, 'search_controller', None)
        if (controller is not None and not self._closing and isinstance(watched, QWidget)
                and watched.window() is self
                and event.type() in (QEvent.Type.ShortcutOverride, QEvent.Type.KeyPress)
                and event.matches(QKeySequence.StandardKey.Find)):
            if event.type() == QEvent.Type.ShortcutOverride:
                event.accept()
            else:
                controller.open()
            return True
        if controller is not None and isinstance(watched, QWidget) and (
                watched is controller.panel or controller.panel.isAncestorOf(watched)):
            return super().eventFilter(watched, event)
        navigation = getattr(self, 'navigation', None)
        if navigation is not None and isinstance(watched, QWidget) and (
                watched is navigation.panel or navigation.panel.isAncestorOf(watched)):
            return super().eventFilter(watched, event)
        copier = getattr(self, 'document_text', None)
        if copier is not None and copier.handle_event(watched, event, self):
            return True
        if (not self._closing and isinstance(watched, QWidget) and watched.window() is self
                and event.type() in (QEvent.Type.ShortcutOverride, QEvent.Type.KeyPress)):
            control = Qt.KeyboardModifier.MetaModifier if sys.platform == 'darwin' else Qt.KeyboardModifier.ControlModifier
            modifiers = event.modifiers()
            if (event.key() in (Qt.Key.Key_Tab, Qt.Key.Key_Backtab)
                    and modifiers in (control, control | Qt.KeyboardModifier.ShiftModifier)):
                # Claim both native representations before child widgets use
                # Shift+Tab for focus traversal or Qt's shortcut normalization.
                if event.type() == QEvent.Type.ShortcutOverride:
                    event.accept()
                else:
                    reverse = event.key() == Qt.Key.Key_Backtab or bool(modifiers & Qt.KeyboardModifier.ShiftModifier)
                    self._cycle_tab(-1 if reverse else 1)
                return True
        if watched is getattr(self, 'page_number_input', None) and event.type() == QEvent.Type.KeyPress:
            if event.key() == Qt.Key.Key_Escape:
                self._page_edit_dirty = False
                self.page_number_input.clearFocus()
                self._update_page_indicator()
                return True
            return super().eventFilter(watched, event)
        keys = (Qt.Key.Key_Left, Qt.Key.Key_Right, Qt.Key.Key_Up, Qt.Key.Key_Down,
                Qt.Key.Key_PageUp, Qt.Key.Key_PageDown, Qt.Key.Key_Home, Qt.Key.Key_End)
        if (not self._closing and isinstance(watched, QWidget) and watched.window() is self
                and event.type() == QEvent.Type.KeyPress and not event.modifiers()
                and event.key() in keys):
            self._navigate_preview(event.key())
            return True
        return super().eventFilter(watched, event)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, 'search_controller'):
            self.search_controller.layout()
            self.navigation.layout()
            self._update_page_indicator()

    def _navigate_preview(self, key) -> None:
        if self._export_running:
            return
        doc = self.current_document()
        if doc is None or not doc.ready or not doc.page_order:
            return
        if key in (Qt.Key.Key_Home, Qt.Key.Key_End):
            first = key == Qt.Key.Key_Home
            index = doc.page_order[0 if first else -1]
            doc.focused_page = index
            if doc.fit_mode:
                doc.fit_page_index = index
                doc._fit_navigation_pending = True
                doc._apply_fit()
            else:
                vertical = doc.scroll_area.verticalScrollBar()
                card = doc.page_cards[index]
                vertical.setValue(vertical.minimum() if first else card.y())
                viewport = doc.scroll_area.viewport()
                doc.scroll_area.horizontalScrollBar().setValue(
                    card.x() + (card.width() - viewport.width()) // 2)
            return
        previous = key in (Qt.Key.Key_Left, Qt.Key.Key_Up, Qt.Key.Key_PageUp)
        if doc.fit_mode:
            pending = doc._fit_navigation_pending or doc.render_timer.isActive() or doc._render_pending > 0
            current = doc.fit_page_index if pending else doc.preview_page_index(prefer_focused=False)
            doc.fit_page_index = current
            doc.focused_page = current
            position = doc.page_order.index(current) + (-1 if previous else 1)
            if 0 <= position < len(doc.page_order):
                doc.fit_page_index = doc.page_order[position]
                doc.focused_page = doc.fit_page_index
                doc._fit_navigation_pending = True
                doc._apply_fit()
            return
        horizontal = key in (Qt.Key.Key_Left, Qt.Key.Key_Right)
        scrollbar = doc.scroll_area.horizontalScrollBar() if horizontal else doc.scroll_area.verticalScrollBar()
        paging = key in (Qt.Key.Key_PageUp, Qt.Key.Key_PageDown)
        action = (QAbstractSlider.SliderAction.SliderPageStepSub if previous else QAbstractSlider.SliderAction.SliderPageStepAdd) if paging else (
            QAbstractSlider.SliderAction.SliderSingleStepSub if previous else QAbstractSlider.SliderAction.SliderSingleStepAdd)
        scrollbar.triggerAction(action)

    def _build_toolbar(self) -> None:
        self.next_tab_action = QAction(tr('下一個標籤頁'), self)
        self.next_tab_action.setShortcuts(QKeySequence.keyBindings(QKeySequence.StandardKey.NextChild))
        self.next_tab_action.triggered.connect(lambda: self._cycle_tab(1))
        self.addAction(self.next_tab_action)
        self.previous_tab_action = QAction(tr('上一個標籤頁'), self)
        previous_tab_keys = QKeySequence.keyBindings(QKeySequence.StandardKey.PreviousChild)
        # Qt's Windows standard binding uses Backtab, while native keyboards can
        # deliver Ctrl+Shift+Tab. Register both representations outside QTabWidget.
        reverse_tab = QKeySequence('Ctrl+Shift+Tab')
        if reverse_tab not in previous_tab_keys:
            previous_tab_keys.append(reverse_tab)
        self.previous_tab_action.setShortcuts(previous_tab_keys)
        self.previous_tab_action.triggered.connect(lambda: self._cycle_tab(-1))
        self.addAction(self.previous_tab_action)
        close_keys = QKeySequence.keyBindings(QKeySequence.StandardKey.Close)
        names = [sequence.toString(QKeySequence.SequenceFormat.NativeText) for sequence in close_keys]
        names = sorted((name for name in names if name and name != "Close"),
                       key=lambda name: "W" not in name.upper())
        self.close_shortcut_text = " / ".join(names)
        self.close_tab_action = QAction(tr('關閉目前標籤頁'), self)
        self.close_tab_action.setShortcuts(close_keys)
        self.close_tab_action.setToolTip(tr('關閉目前標籤頁'))
        self.close_tab_action.triggered.connect(lambda: self.close_tab(self.tabs.currentIndex()))
        self.addAction(self.close_tab_action)
        self.toolbar = OverflowToolBar(tr('檔案與顯示'), self)
        self.toolbar.setMovable(False)
        self.toolbar.setFloatable(False)
        self.toolbar.setContextMenuPolicy(Qt.ContextMenuPolicy.PreventContextMenu)
        self.toolbar.setFixedHeight(42)
        self.toolbar.setIconSize(QSize(20, 20))
        self.toolbar.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
        self.addToolBar(self.toolbar)
        self.annotation_tools_action = QAction(tr('註解工具'), self)
        self.annotation_tools_action.setCheckable(True)
        self.annotation_tools_action.setToolTip(tr('註解工具：顯示或隱藏懸浮工具列'))
        self.annotation_toolbar = OverflowToolBar(tr('註解與擷取'), self)
        self.annotation_toolbar.setObjectName('annotationToolbar')
        self.annotation_toolbar.setMovable(False)
        self.annotation_toolbar.setFloatable(False)
        self.annotation_toolbar.setContextMenuPolicy(Qt.ContextMenuPolicy.PreventContextMenu)
        self.annotation_toolbar.setFixedHeight(42)
        self.annotation_toolbar.setIconSize(QSize(20,20))
        self.annotation_toolbar.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
        self.annotation_toolbar.hide()
        self.annotation_tools_action.toggled.connect(self._toggle_annotation_toolbar)

        self.open_action = QAction(tr('開啟 PDF'), self)
        self.open_action.setShortcut(QKeySequence.StandardKey.Open)
        self.open_action.setToolTip(tr('開啟 PDF'))
        self.open_action.triggered.connect(self.choose_pdf)
        self.toolbar.addAction(self.open_action)
        self.save_action = QAction(tr('存檔'), self)
        self.save_action.setShortcuts(QKeySequence.keyBindings(QKeySequence.StandardKey.Save))
        self.save_action.setToolTip(tr('存檔：將目前檔案的完整頁面順序儲存至原 PDF'))
        self.save_action.triggered.connect(lambda: self.saving.choose())
        self.addAction(self.save_action)
        self.save_as_action = QAction(tr('另存新檔'), self)
        self.save_as_action.setShortcuts(QKeySequence.keyBindings(QKeySequence.StandardKey.SaveAs))
        self.save_as_action.setToolTip(tr('另存新檔：將目前檔案的完整頁面順序儲存為另一份 PDF'))
        self.save_as_action.triggered.connect(lambda: self.saving.choose(save_as=True))
        self.addAction(self.save_as_action)
        self.toolbar.addAction(self.save_action)
        self.toolbar.addAction(self.save_as_action)
        self.print_action = QAction(tr('列印'), self)
        self.print_action.setShortcuts(QKeySequence.keyBindings(QKeySequence.StandardKey.Print))
        self.print_action.setToolTip(tr('列印：設定範圍、印表機並即時預覽'))
        self.print_action.setEnabled(False)
        self.print_action.triggered.connect(lambda: self.print_controller.open())
        self.toolbar.addAction(self.print_action)
        self.export_action = QAction(tr('重組輸出'), self)
        self.export_action.setToolTip(tr('合併選取頁面為單一 PDF；未勾選時輸出目前檢視頁面'))
        self.export_action.setEnabled(False)
        self.export_action.triggered.connect(self.choose_output)
        self.split_action = QAction(tr('拆分選取頁面'), self)
        self.split_action.setToolTip(tr('拆分頁面為獨立 PDF 或 PNG；未勾選時輸出目前檢視頁面'))
        self.split_action.setEnabled(False)
        self.split_action.triggered.connect(self.choose_split_output)
        self.toolbar.addSeparator()

        self.copy_text_action = QAction(tr('複製文字'), self)
        self.copy_text_action.setCheckable(True)
        self.copy_text_action.setToolTip(tr('複製文字：拖曳選字並複製；{keys} 全選整份 PDF 的文字並複製。掃描影像需使用 OCR。', keys=native_shortcuts(QKeySequence.keyBindings(QKeySequence.StandardKey.SelectAll))))
        self.copy_text_action.toggled.connect(self._set_copy_text_mode)
        self.region_ocr_action = QAction(tr('區域 OCR'), self)
        self.region_ocr_action.setCheckable(True)
        self.region_ocr_action.setToolTip(tr('區域 OCR：框選頁面或圖片中的區域，放開滑鼠後辨識並複製文字。'))
        self.region_ocr_action.toggled.connect(self._set_region_ocr_mode)
        self.ocr_languages = OcrLanguageController(self)
        self.extract_image_action = QAction(tr('擷取圖片'), self)
        self.extract_image_action.setCheckable(True)
        self.extract_image_action.setEnabled(False)
        self.extract_image_action.setToolTip(tr('擷取圖片：點選頁面中的內嵌點陣圖片，另存為 PNG。'))
        self.extract_image_action.toggled.connect(self._set_image_mode)
        self.bookmark_action = QAction(tr('書籤'), self)
        self.bookmark_action.setCheckable(True)
        self.bookmark_action.setToolTip(tr('書籤：開啟章節目錄，點選即可跳頁'))
        self.bookmark_action.triggered.connect(lambda: self.navigation.toggle())
        self.toolbar.addAction(self.bookmark_action)
        self.toolbar.widgetForAction(self.bookmark_action).setObjectName('bookmarksTool')
        self.annotation_action = QAction(tr('註解'), self)
        self.annotation_action.setCheckable(True)
        self.annotation_action.setToolTip(tr('註解：開啟註解清單，點選即可跳至對應頁面'))
        self.annotation_action.triggered.connect(lambda: self.navigation.toggle('annotations'))
        self.toolbar.addAction(self.annotation_action)
        self.toolbar.widgetForAction(self.annotation_action).setObjectName('annotationsTool')
        self.search_action = QAction(tr('搜尋文字'), self)
        self.search_action.setShortcuts(QKeySequence.keyBindings(QKeySequence.StandardKey.Find))
        self.search_action.setToolTip(tr('搜尋文字：搜尋目前、勾選、所有標籤頁或目前標籤所在資料夾'))
        self.search_action.triggered.connect(lambda: self.search_controller.open())
        self.toolbar.insertAction(self.bookmark_action,self.search_action)
        self.toolbar.addAction(self.annotation_tools_action)
        self.toolbar.addSeparator()
        self.annotation_editor = AnnotationEditor(self)
        self.toolbar.addAction(self.copy_text_action)
        self.toolbar.widgetForAction(self.copy_text_action).setObjectName('copyTextTool')
        self.ocr_language_button = self.toolbar.add_action_menu_group(self.region_ocr_action,self.ocr_languages.menu)
        self.toolbar.widgetForAction(self.region_ocr_action).setObjectName('regionOcrTool')
        self.ocr_language_button.setToolTip(tr('OCR 辨識語言'))
        self.ocr_language_button.setAccessibleName(tr('OCR 辨識語言'))
        self.toolbar.addAction(self.extract_image_action)
        self.toolbar.widgetForAction(self.extract_image_action).setObjectName('extractImageTool')

        self.toolbar.addSeparator()
        selection_controls = QWidget(self)
        bulk = QHBoxLayout(selection_controls)
        bulk.setContentsMargins(8, 0, 4, 0)
        bulk.setSpacing(8)
        bulk.setSizeConstraint(QLayout.SizeConstraint.SetFixedSize)
        self.odd_checkbox = QCheckBox(tr('單數頁'))
        self.even_checkbox = QCheckBox(tr('雙數頁'))
        for checkbox in (self.odd_checkbox, self.even_checkbox):
            checkbox.setTristate(True)
            checkbox.setEnabled(False)
            bulk.addWidget(checkbox)
        self.odd_checkbox.setToolTip(tr('選取或取消原始頁碼的單數頁'))
        self.even_checkbox.setToolTip(tr('選取或取消原始頁碼的雙數頁'))
        self.odd_checkbox.clicked.connect(lambda checked: self._toggle_parity(True, checked))
        self.even_checkbox.clicked.connect(lambda checked: self._toggle_parity(False, checked))
        self.toolbar.add_overflow_controls(selection_controls, (self.odd_checkbox, self.even_checkbox))
        self.toolbar.addAction(self.export_action)
        self.toolbar.addAction(self.split_action)
        self.toolbar.addSeparator()

        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.toolbar.addWidget(spacer)
        self.zoom_out_action = QAction(tr('縮小'), self)
        self.zoom_out_action.setShortcut(QKeySequence("Ctrl+-"))
        self.zoom_out_action.setToolTip(tr('縮小'))
        self.zoom_out_action.triggered.connect(lambda: self._adjust_zoom(-25))
        self.addAction(self.zoom_out_action)
        self.zoom_slider = QSlider(Qt.Orientation.Horizontal)
        self.zoom_slider.setRange(25, 200)
        self.zoom_slider.setValue(100)
        self.zoom_slider.setFixedWidth(150)
        self.zoom_slider.setAccessibleName(tr('頁面顯示比例'))
        self.zoom_slider.setToolTip(tr('100% 以 96 DPI 顯示 PDF 頁面'))
        self.zoom_slider.valueChanged.connect(self._zoom_changed)
        self.zoom_in_action = QAction(tr('放大'), self)
        self.zoom_in_action.setShortcuts([QKeySequence("Ctrl++"), QKeySequence("Ctrl+=")])
        self.zoom_in_action.setToolTip(tr('放大'))
        self.zoom_in_action.triggered.connect(lambda: self._adjust_zoom(25))
        self.addAction(self.zoom_in_action)
        self.zoom_reset_action = QAction("100%", self)
        self.zoom_reset_action.setShortcut(QKeySequence("Ctrl+0"))
        self.zoom_reset_action.setToolTip(
            tr('頁面顯示比例：25%–200%\n拖曳右側滑桿調整比例；點擊比例回到 100%。\n100% 以 96 DPI 顯示 PDF 頁面。')
        )
        self.zoom_reset_action.triggered.connect(lambda: self._set_manual_zoom(100))
        self.toolbar.addAction(self.zoom_reset_action)
        self.zoom_display = self.toolbar.widgetForAction(self.zoom_reset_action)
        self.zoom_display.setFixedWidth(64)
        self.zoom_display.setToolButtonStyle(
            Qt.ToolButtonStyle.ToolButtonTextOnly
        )
        self.toolbar.add_overflow_controls(self.zoom_slider, (self.zoom_slider,))
        self.fit_action = QAction("Fit", self)
        self.fit_action.setCheckable(True)
        self.fit_action.setToolTip(tr("Fit：將目前單頁等比例縮放至預覽區，視窗調整時自動適應"))
        self.fit_action.triggered.connect(self._fit_page)
        self.toolbar.addAction(self.fit_action)
        self.fullscreen_mode = 'single'
        self.fullscreen_action = QAction(tr('全螢幕'), self)
        self.fullscreen_action.setShortcut(QKeySequence("F11"))
        self.fullscreen_action.setToolTip(tr('全螢幕'))
        self.fullscreen_action.triggered.connect(self._toggle_fullscreen_preview)
        self.addAction(self.fullscreen_action)
        self.single_action = QAction(tr('全螢幕單頁'), self)
        self.single_action.setToolTip(tr('全螢幕單頁'))
        self.single_action.triggered.connect(lambda: self._show_fullscreen_preview('single'))
        self.spread_action = QAction(tr("全螢幕對頁"), self)
        self.spread_action.setToolTip(tr("全螢幕對頁：依目前順序兩頁並排；Esc 結束，方向鍵／Page Up／Page Down 切頁，可勾選頁面"))
        self.spread_action.triggered.connect(lambda: self._show_fullscreen_preview("spread"))
        self.cover_action = QAction(tr("全螢幕封面＋對頁"), self)
        self.cover_action.setToolTip(tr("全螢幕封面＋對頁：第一頁單獨顯示，其餘兩頁並排；Esc 結束，方向鍵／Page Up／Page Down 切頁，可勾選頁面"))
        self.cover_action.triggered.connect(lambda: self._show_fullscreen_preview("cover"))
        self.fullscreen_menu = QMenu(tr('全螢幕模式'), self)
        self.fullscreen_modes = QActionGroup(self)
        self.fullscreen_modes.setExclusive(True)
        for action in (self.single_action, self.spread_action, self.cover_action):
            action.setCheckable(True)
            self.fullscreen_modes.addAction(action)
            self.fullscreen_menu.addAction(action)
        self.single_action.setChecked(True)
        self.fullscreen_menu_button = self.toolbar.add_action_menu_group(
            self.fullscreen_action, self.fullscreen_menu, arrow_name='fullscreenModeMenu')
        self.fullscreen_menu_button.setToolTip(tr('全螢幕模式'))
        self.fullscreen_menu_button.setAccessibleName(tr('全螢幕模式'))
        self.toolbar.addSeparator()
        self.language_action = QAction(self)
        self.language_action.triggered.connect(self._cycle_language)
        self.theme_action = QAction(self)
        self.theme_action.triggered.connect(self._cycle_theme)
        self.toolbar.addAction(self.language_action)
        self.toolbar.addAction(self.theme_action)
        self._refresh_toolbar_icons()
        for toolbar in (self.toolbar,self.annotation_toolbar):
            for action in toolbar.actions():
                button = toolbar.widgetForAction(action)
                if isinstance(button,QToolButton):
                    if action.isCheckable():
                        button.setProperty('stateButton',True)
                        button.setAttribute(Qt.WidgetAttribute.WA_Hover,True)
                    if button is self.zoom_display: button.setFixedHeight(34)
                    else: button.setFixedSize(34,34)
        self.toolbar.group_sections()
        self.zoom_display = self.toolbar.widgetForAction(self.zoom_reset_action)
        self.shortcut_hints = ShortcutHints(self)
        self.annotation_tools_action.setChecked(self.settings.value('view/annotation_toolbar',False,type=bool))

    def _finish_annotation_modes(self, include_extraction=False):
        self.annotation_editor.finish_text(True)
        self.annotation_editor.clear()
        actions = [self.annotation_editor.mark_action, self.annotation_editor.callout_action, self.annotation_editor.draw_action]
        if include_extraction:
            actions.extend((self.copy_text_action, self.region_ocr_action, self.extract_image_action))
        for action in actions:
            action.setChecked(False)
        self._sync_selection_modes()

    def _toggle_annotation_toolbar(self, enabled):
        if not enabled and hasattr(self,'annotation_editor'):
            self._finish_annotation_modes()
        if hasattr(self, 'annotation_floating'):
            self.annotation_floating.setVisible(enabled and self._fullscreen_preview is None)
            if enabled:
                self.annotation_floating.reposition()
        self.settings.setValue('view/annotation_toolbar',enabled)

    def _refresh_toolbar_icons(self) -> None:
        if hasattr(self, 'ocr_language_button'):
            self.ocr_language_button.setIcon(toolbar_icon('chevron_down'))
        for action, kind in ((self.open_action, "open"), (self.export_action, "export"),
                             (self.save_action, 'save'), (self.save_as_action, 'save_as'),
                             (self.split_action, "split"), (self.copy_text_action, "copy_text"),
                             (self.region_ocr_action, "ocr_region"),
                             (self.extract_image_action, "extract_image"),
                             (self.search_action, "search"),
                             (self.print_action, "print"),
                             (self.bookmark_action, "bookmarks"),
                             (self.annotation_action, "annotations"),
                             (self.fit_action, "fit"),
                             (self.fullscreen_action, {'single': 'fullscreen', 'spread': 'fullscreen_spread', 'cover': 'fullscreen_cover'}[self.fullscreen_mode]),
                             (self.single_action, 'fullscreen'),
                             (self.spread_action, "fullscreen_spread"),
                             (self.cover_action, "fullscreen_cover")):
            action.setIcon(toolbar_icon(kind))
        if hasattr(self, "language_action"):
            self._update_preference_actions()
        if hasattr(self, "annotation_editor"):
            self.annotation_editor.refresh_icons()
        self.annotation_tools_action.setIcon(toolbar_icon('edit_tools'))
        for name in ('ocr_language_button', 'fullscreen_menu_button'):
            if hasattr(self, name):
                getattr(self, name).setIcon(toolbar_icon('chevron_down'))

    def _update_preference_actions(self) -> None:
        language = self.language_controller
        language_names = {"system": tr("跟隨系統"), "zh": tr("中文"), "en": "English"}
        theme_names = {"system": tr("跟隨系統"), "light": tr("淺色"), "dark": tr("深色")}
        self.language_action.setText(tr("介面語言：{mode}", mode=language_names[language.mode]))
        self.language_action.setIcon(toolbar_icon("language_" + language.mode))
        self.language_action.setToolTip(tr("介面語言：{mode}（目前：{language}）\n點擊依序切換：跟隨系統 → 中文 → English",
                                          mode=language_names[language.mode], language=language_names[language.language]))
        self.theme_action.setText(tr("介面配色：{mode}", mode=theme_names[self._theme_controller.mode]))
        self.theme_action.setIcon(toolbar_icon("theme_" + self._theme_controller.mode))
        self.theme_action.setToolTip(tr("介面配色：{mode}\n點擊依序切換：跟隨系統 → 淺色 → 深色",
                                      mode=theme_names[self._theme_controller.mode]))

    def _cycle_language(self) -> None:
        modes = ("system", "zh", "en")
        mode = modes[(modes.index(self.language_controller.mode) + 1) % 3]
        self.settings.setValue("ui/language", mode)
        self.language_controller.set_mode(mode)

    def _cycle_theme(self) -> None:
        modes = ("system", "light", "dark")
        mode = modes[(modes.index(self._theme_controller.mode) + 1) % 3]
        self.settings.setValue("ui/theme", mode)
        self._theme_controller.set_mode(mode)
        self._update_preference_actions()

    def _retranslate(self) -> None:
        status = localize_text(self.statusBar().currentMessage())
        for widget in self.findChildren(QLabel) + self.findChildren(QAbstractButton) + self.findChildren(QAction):
            if isinstance(widget, QLabel) and not widget.pixmap().isNull():
                continue
            text = localize_text(widget.text())
            if text != widget.text():
                widget.setText(text)
        for widget in self.findChildren(QWidget) + self.findChildren(QAction):
            widget.setToolTip(localize_text(widget.toolTip()))
            if isinstance(widget, QWidget):
                widget.setAccessibleName(localize_text(widget.accessibleName()))
        self.toolbar.setWindowTitle(localize_text(self.toolbar.windowTitle()))
        self.annotation_toolbar.setWindowTitle(localize_text(self.annotation_toolbar.windowTitle()))
        self._update_window_title()
        self._sync_controls()
        self.statusBar().showMessage(status)
        self._update_preference_actions()
        self.shortcut_hints.refresh()
        self.search_controller.retranslate()
        self.navigation.retranslate()
        self.ocr_languages.refresh()
        self.annotation_editor.mark_menu.refresh()
        self.annotation_editor.callout_menu.refresh()
        self.annotation_editor.draw_menu.refresh()
        self.annotation_floating.refresh_icons()
        if self._about_dialog is not None and isValid(self._about_dialog):
            self._about_dialog.retranslate()
        self._windows_system_menu.refresh()
        if self._fullscreen_preview is not None:
            self._fullscreen_preview.floating_tools.refresh_icons()

    def changeEvent(self, event: QEvent) -> None:
        super().changeEvent(event)
        if event.type() == QEvent.Type.PaletteChange and hasattr(self, "zoom_reset_action"):
            self._refresh_toolbar_icons()
        if event.type() == QEvent.Type.LocaleChange and hasattr(self, "language_controller"):
            if self.language_controller.mode == "system":
                self.language_controller.refresh()

    def _update_window_title(self) -> None:
        self.setWindowTitle(f"RePDF {__version__}")

    def _adjust_zoom(self, delta: int) -> None:
        doc = self.current_document()
        value = doc.zoom if doc is not None else self.zoom_slider.value()
        self._set_manual_zoom(max(25, min(200, round(value + delta))))

    def _set_manual_zoom(self, value: int) -> None:
        self.zoom_slider.blockSignals(True)
        self.zoom_slider.setValue(value)
        self.zoom_slider.blockSignals(False)
        self._zoom_changed(value)

    def _fit_page(self) -> None:
        doc = self.current_document()
        if doc is not None and doc.ready:
            doc.fit_page()

    def _selection_active(self) -> bool:
        return any(action.isChecked() for action in
                   (self.copy_text_action, self.region_ocr_action, self.extract_image_action))

    def _set_image_mode(self, enabled: bool) -> None:
        self._select_mode(self.extract_image_action, enabled)

    def _select_mode(self, active, enabled):
        if enabled:
            for action in (self.annotation_editor.mark_action,self.annotation_editor.callout_action,self.annotation_editor.draw_action):
                action.blockSignals(True); action.setChecked(False); action.blockSignals(False)
            self.annotation_editor.anchor = None
            for action in (self.copy_text_action, self.region_ocr_action, self.extract_image_action):
                if action is not active:
                    action.blockSignals(True)
                    action.setChecked(False)
                    action.blockSignals(False)
        self._sync_selection_modes()

    def _set_copy_text_mode(self, enabled: bool) -> None:
        self._select_mode(self.copy_text_action, enabled)

    def _set_region_ocr_mode(self, enabled: bool) -> None:
        self._select_mode(self.region_ocr_action, enabled)

    def _sync_selection_modes(self) -> None:
        if hasattr(self, 'document_text'):
            self.document_text.cancel()
        enabled = self._selection_active()
        region = self.region_ocr_action.isChecked()
        image = self.extract_image_action.isChecked()
        for doc in self.documents.values():
            doc.grid_host.finish_drag()
            for card in doc.page_cards:
                card.set_text_copy_mode(enabled, region=region, image=image)
        if self._fullscreen_preview is not None:
            for label in self._fullscreen_preview.labels.values():
                label.set_text_mode(enabled, region=region, image=image)
        self._text_requests.clear()
        self._ocr_generations.clear()
        self._image_requests.clear()

    def _copy_text_selection(self, doc, page_index, label, start, end, *, copy=True) -> None:
        self.document_text.cancel()
        if not self._selection_active() or doc.document_id not in self.documents:
            return
        if label.pixmap().isNull() or label.width() < 1 or label.height() < 1:
            return
        if self.extract_image_action.isChecked():
            if copy:
                self._request_image(doc, page_index, label, end)
            return
        region = self.region_ocr_action.isChecked()
        if region and not copy:
            return
        self._next_generation += 1
        generation = self._next_generation
        for previous, (document_id, _label, _copy) in list(self._text_requests.items()):
            if document_id == doc.document_id:
                self._text_requests.pop(previous)
        self._text_requests[generation] = (doc.document_id, label, copy)
        self._ocr_generations[doc.document_id] = generation
        self.render_service.request_text(
            doc.source_path, page_index,
            (start.x() / label.width(), start.y() / label.height()),
            (end.x() / label.width(), end.y() / label.height()),
            generation, -1_000_000 - doc.document_id,
            allow_ocr=copy, region_ocr=region, password=doc.password,
            ocr_profile=self.ocr_languages.profile,
        )
        if copy:
            self.statusBar().showMessage(tr('正在辨識選取區域…') if region else tr('正在擷取文字…'))

    def _request_image(self, doc, page_index, label, point):
        self._next_generation += 1
        generation = self._next_generation
        self._image_requests = {key: value for key, value in self._image_requests.items()
                                if value[0] != doc.document_id}
        self._image_requests[generation] = (doc.document_id, page_index, label)
        self.render_service.request_image(
            doc.source_path, page_index,
            (point.x() / label.width(), point.y() / label.height()),
            Path(self.preview_temp.name), generation, -1_000_000 - doc.document_id,
            password=doc.password)
        self.statusBar().showMessage(tr('正在擷取圖片…'))

    def _accept_image(self, generation, payload):
        request = self._image_requests.pop(generation, None)
        result = payload.get('image')
        path = Path(self.preview_temp.name) / f'g{generation}-image.png'
        try:
            if request is None or self._closing or not self.extract_image_action.isChecked():
                return
            document_id, page_index, label = request
            doc = self.documents.get(document_id)
            if doc is None or not isValid(label) or not label.isVisible():
                return
            if not result:
                self.statusBar().showMessage(tr('此位置沒有可擷取的內嵌點陣圖片'))
                return
            if Path(result['path']) != path or not path.is_file():
                raise ValueError(tr('圖片擷取結果無效'))
            parent = self._fullscreen_preview or self
            suggested = doc.source_path.with_name(f'{doc.source_path.stem}_p{page_index + 1}_image.png')
            filename, _ = QFileDialog.getSaveFileName(
                parent, tr('儲存擷取的圖片'), str(suggested), tr('PNG 圖片 (*.png)'), '',
                QFileDialog.Option.DontUseNativeDialog)
            if not filename:
                self.statusBar().showMessage(tr('已取消儲存圖片'))
                return
            destination = Path(filename)
            if destination.suffix.lower() != '.png':
                destination = Path(str(destination) + '.png')
                if destination.exists() and QMessageBox.question(
                    parent, tr('覆蓋圖片'), tr('檔案已存在，是否覆蓋？\n{p0}', p0=destination),
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                    QMessageBox.StandardButton.No) != QMessageBox.StandardButton.Yes:
                    return
            if destination.resolve() in {item.source_path.resolve() for item in self.documents.values()}:
                raise ValueError(tr('輸出檔案不可覆蓋來源 PDF。'))
            with tempfile.NamedTemporaryFile(prefix='.repdf-image-', suffix='.tmp',
                                             dir=destination.parent, delete=False) as temporary:
                pending = Path(temporary.name)
            try:
                shutil.copyfile(path, pending)
                pending.replace(destination)
            finally:
                pending.unlink(missing_ok=True)
            self.statusBar().showMessage(tr('已儲存圖片（{p0} × {p1}）：{p2}',
                                           p0=result['width'], p1=result['height'], p2=destination))
        except Exception as exc:
            self.statusBar().showMessage(tr('無法擷取圖片：{p0}', p0=exc))
            QMessageBox.warning(self._fullscreen_preview or self, tr('無法擷取圖片'), str(exc))
        finally:
            path.unlink(missing_ok=True)

    def _toggle_fullscreen_preview(self) -> None:
        if self._fullscreen_preview is not None:
            self._fullscreen_preview.close()
        else:
            self._show_fullscreen_preview()

    def _show_fullscreen_preview(self, mode=None) -> None:
        self.annotation_editor.finish_text(True)
        if self._export_running:
            return
        doc = self.current_document()
        if doc is None or not doc.ready or not doc.page_sizes:
            return
        mode = mode or self.fullscreen_mode
        if self._fullscreen_preview is not None:
            self._fullscreen_preview.set_mode(mode)
            return
        self.fullscreen_mode = mode
        action = {'single': self.single_action, 'spread': self.spread_action, 'cover': self.cover_action}[mode]
        action.setChecked(True)
        self.fullscreen_action.setToolTip(tr('全螢幕模式：{mode}', mode=action.text()))
        self._refresh_toolbar_icons()
        self.annotation_floating.hide()
        viewer = FullscreenPreview(self, doc, doc.preview_page_index(), mode)
        self._fullscreen_preview = viewer
        viewer.setGeometry(self.screen().geometry())
        viewer.showFullScreen()
        viewer.activateWindow()
        viewer.setFocus()

    def current_document(self):
        return self.tabs.currentWidget() if hasattr(self, "tabs") else None

    def _cycle_tab(self, step: int) -> None:
        count = self.tabs.count()
        if count > 1:
            self.tabs.setCurrentIndex((self.tabs.currentIndex() + step) % count)

    def ordered_documents(self):
        return [self.tabs.widget(i) for i in range(self.tabs.count())]

    def output_selection(self, *, fallback_current=False) -> list[DocumentSelection]:
        documents = self.ordered_documents()
        included = [doc for doc in documents if doc.include_checkbox.isChecked()]
        if not included:
            current = self.current_document()
            included = [current] if current is not None else []
        selections = [DocumentSelection(doc.source_path, tuple(page for page in doc.page_order if page in doc.selected_pages), doc.password, tuple(doc.annotation_store.changes()))
                      for doc in included if doc.ready and doc.selected_pages]
        if not selections and fallback_current:
            doc = self.current_document()
            if doc is not None and doc.ready and doc.page_count:
                viewer = self._fullscreen_preview
                page = viewer.page_index if viewer is not None and viewer.document is doc else doc.preview_page_index()
                selections = [DocumentSelection(doc.source_path, (page,), doc.password, tuple(doc.annotation_store.changes()))]
        return selections

    def _tab_changed(self, _index: int) -> None:
        if hasattr(self, 'document_text'):
            self.document_text.cancel()
        self.annotation_editor.finish_text(True)
        self.annotation_editor.clear()
        if self._closing:
            return
        doc = self.current_document()
        for other in self.documents.values():
            if other is not doc:
                other.pages.suspend()
        self._update_window_title()
        if doc is not None:
            self.zoom_slider.blockSignals(True)
            self.zoom_slider.setValue(round(doc.zoom))
            self.zoom_slider.blockSignals(False)
            self.render_service.prioritize(doc.document_id)
            if doc.ready and (doc.render_generation < 0 or doc.render_timer.isActive()):
                doc._queue_all_renders()
            doc._reflow_grid()
        self._sync_controls()
        if hasattr(self, 'navigation'):
            self.navigation.show_document()

    def _sync_controls(self, *_args) -> None:
        if not hasattr(self, "tabs") or self._closing:
            return
        self._update_page_indicator()
        doc = self.current_document()
        ready = doc is not None and doc.ready
        for action in (self.annotation_editor.mark_action,self.annotation_editor.callout_action,self.annotation_editor.draw_action):
            action.setEnabled(ready and bool(doc.page_sizes) and not self._export_running and not self.print_controller.busy)
        self.print_action.setEnabled(ready and not self.print_controller.busy and not self._export_running)
        self.save_action.setEnabled(ready and doc.modified and not self._export_running and not self.print_controller.busy)
        self.save_as_action.setEnabled(ready and not self._export_running and not self.print_controller.busy)
        for document in self.documents.values():
            index = self.tabs.indexOf(document)
            self.tabs.setTabText(index, document.source_path.stem + (' *' if document.modified else ''))
        self.close_tab_action.setEnabled(self.tabs.count() > 0 and not self._export_running)
        self._syncing_bulk = True
        for checkbox, odd in ((self.odd_checkbox, True), (self.even_checkbox, False)):
            checkbox.blockSignals(True)
            state = parity_state(doc.selected_pages, doc.page_count, odd) if ready else SelectionState.NONE
            checkbox.setCheckState({SelectionState.NONE: Qt.CheckState.Unchecked,
                                    SelectionState.PARTIAL: Qt.CheckState.PartiallyChecked,
                                    SelectionState.ALL: Qt.CheckState.Checked}[state])
            checkbox.setEnabled(ready and not self._export_running and (odd or doc.page_count >= 2))
            checkbox.blockSignals(False)
        self._syncing_bulk = False
        zoom = doc.zoom if ready else self.zoom_slider.value()
        if ready:
            self.zoom_slider.blockSignals(True)
            self.zoom_slider.setValue(round(zoom))
            self.zoom_slider.blockSignals(False)
        self.zoom_reset_action.setText(f"{int(zoom + 0.5)}%")
        self.fit_action.setChecked(ready and doc.fit_mode)
        available = ready and bool(doc.page_sizes)
        self.fit_action.setEnabled(available)
        self.fullscreen_action.setEnabled(available)
        self.single_action.setEnabled(available)
        self.fullscreen_menu_button.setEnabled(available)
        mode_action = {'single': self.single_action, 'spread': self.spread_action,
                       'cover': self.cover_action}[self.fullscreen_mode]
        self.fullscreen_action.setToolTip(tr('全螢幕模式：{mode}', mode=mode_action.text()))
        self.spread_action.setEnabled(available)
        self.cover_action.setEnabled(available)
        self.copy_text_action.setEnabled(available)
        self.region_ocr_action.setEnabled(available)
        self.extract_image_action.setEnabled(available)
        self.zoom_out_action.setEnabled(zoom > 25)
        self.zoom_in_action.setEnabled(zoom < 200)
        enabled = bool(self.output_selection(fallback_current=True)) and not self._export_running
        self.export_action.setEnabled(enabled)
        self.split_action.setEnabled(enabled)
        if not self._export_running:
            count = sum(len(item.pages) for item in self.output_selection())
            self.statusBar().showMessage(
                (tr('目前檔案：已選取 {p0} / {p1} 頁；輸出合計 {p2} 頁', p0=len(doc.selected_pages), p1=doc.page_count, p2=count)
                 if count else tr('目前檔案：已選取 {selected} / {total} 頁；預設輸出目前檢視頁面', selected=len(doc.selected_pages), total=doc.page_count))
                if ready else (tr('正在讀取 PDF…') if doc is not None else tr('就緒')))

    def _toggle_parity(self, odd: bool, checked: bool) -> None:
        doc = self.current_document()
        if doc is not None and doc.ready and not self._export_running:
            doc._toggle_parity(odd, checked)

    def _zoom_changed(self, value: int) -> None:
        doc = self.current_document()
        if doc is not None:
            doc.set_zoom(value)
        self._sync_controls()

    def _dropped_pdfs(self, event) -> list[Path]:
        if self._export_running:
            return []
        urls = event.mimeData().urls()
        if not urls or any(not url.isLocalFile() for url in urls):
            return []
        paths = [Path(url.toLocalFile()) for url in urls]
        return paths if all(path.suffix.lower() == ".pdf" and path.is_file() for path in paths) else []

    def dragEnterEvent(self, event) -> None:
        if self._dropped_pdfs(event):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragMoveEvent(self, event) -> None:
        self.dragEnterEvent(event)

    def dropEvent(self, event) -> None:
        paths = self._dropped_pdfs(event)
        if not paths:
            event.ignore()
            return
        event.acceptProposedAction()
        self.load_pdfs(paths)

    @Slot()
    def choose_pdf(self) -> None:
        filenames, _ = QFileDialog.getOpenFileNames(self, tr('開啟 PDF'), str(Path.home()), tr('PDF 檔案 (*.pdf)'), "", QFileDialog.Option.DontUseNativeDialog)
        if filenames:
            self.load_pdfs([Path(filename) for filename in filenames])

    def _new_document(self, path: Path):
        self._next_document_id += 1
        doc = DocumentView(self, self._next_document_id, path)
        self.documents[doc.document_id] = doc
        self.empty_label.hide()
        self.tabs.show()
        index = self.tabs.addTab(doc, path.stem)
        self.tabs.setTabToolTip(index, str(doc.source_path))
        self.tabs.tabBar().setTabButton(index, QTabBar.ButtonPosition.LeftSide, doc.include_checkbox)
        self.tabs.tabBar().setTabButton(index, QTabBar.ButtonPosition.RightSide, doc.close_button)
        self.tabs.setCurrentIndex(index)
        return doc

    def load_pdf(self, path: Path) -> None:
        self.load_pdfs([path])

    def load_pdfs(self, paths: list[Path]) -> None:
        if self._export_running:
            return
        self._next_batch += 1
        batch = self._next_batch
        self._load_batches[batch] = {"pending": set(), "errors": []}
        for path in paths:
            path = Path(path).resolve()
            existing = next((doc for doc in self.documents.values() if doc.source_path == path), None)
            if existing is not None:
                self.tabs.setCurrentWidget(existing)
                continue
            doc = self._new_document(path)
            self._document_batches[doc.document_id] = batch
            self._load_batches[batch]["pending"].add(doc.document_id)
            self._start_load(doc)
        if not self._load_batches[batch]["pending"]:
            self._load_batches.pop(batch)

    def _start_load(self, doc):
        task = LoadPdfTask(doc.source_path, doc.document_id, doc.password)
        self._active_tasks.add(task)
        task.signals.loaded.connect(self._pdf_loaded)
        task.signals.failed.connect(self._pdf_load_failed)
        task.signals.password_required.connect(self._pdf_password_required)
        for signal in (task.signals.loaded, task.signals.failed, task.signals.password_required):
            signal.connect(lambda *_args, job=task: self._active_tasks.discard(job))
        self.thread_pool.start(task)

    @Slot(int, bool)
    def _pdf_password_required(self, document_id, incorrect):
        if self._closing or document_id not in self.documents:
            return
        self.documents[document_id].password = None
        self._password_queue.append((document_id, incorrect))
        QTimer.singleShot(0, self._prompt_next_password)

    def _prompt_next_password(self):
        if self._closing or self._password_dialog is not None:
            return
        while self._password_queue:
            document_id, incorrect = self._password_queue.pop(0)
            doc = self.documents.get(document_id)
            if doc is not None:
                break
        else:
            return
        dialog = PdfPasswordDialog(doc.source_path, incorrect=incorrect, parent=self)
        self._password_dialog = dialog
        self._password_document_id = document_id
        try:
            accepted = dialog.exec() == QDialog.DialogCode.Accepted
            if document_id not in self.documents or self._closing:
                return
            if accepted:
                doc.password = dialog.password_edit.text()
                self._start_load(doc)
            else:
                self.close_tab(self.tabs.indexOf(doc), force=True)
                self._finish_load(document_id)
        finally:
            dialog.password_edit.clear()
            dialog.deleteLater()
            self._password_dialog = None
            self._password_document_id = None
            QTimer.singleShot(0, self._prompt_next_password)

    def _finish_load(self, document_id: int, error: str | None = None) -> None:
        batch = self._document_batches.pop(document_id, None)
        if batch is None:
            return
        state = self._load_batches[batch]
        state["pending"].discard(document_id)
        if error:
            state["errors"].append(error)
        if not state["pending"]:
            self._load_batches.pop(batch)
            if state["errors"] and not self._closing:
                QMessageBox.critical(self, tr('部分 PDF 無法開啟'), "\n\n".join(state["errors"]))

    @Slot(int, object, int)
    def _pdf_loaded(self, document_id: int, path: Path, page_count: int) -> None:
        doc = self.documents.get(document_id)
        if doc is not None and not self._closing:
            doc.fit_mode = True
            doc.loaded(page_count)
            if self.current_document() is doc:
                self._tab_changed(self.tabs.currentIndex())
            self._sync_controls()
        self._finish_load(document_id)
        if doc is not None and doc.ready:
            self.search_controller.document_loaded(doc)

    @Slot(int, str)
    def _pdf_load_failed(self, document_id: int, message: str) -> None:
        doc = self.documents.get(document_id)
        error = f"{doc.source_path}\n{message}" if doc is not None else None
        if doc is not None:
            self.close_tab(self.tabs.indexOf(doc), force=True)
        self._finish_load(document_id, error)

    def _confirm_close(self, doc, on_saved=None):
        if not doc.modified:
            return True
        message = unsaved_changes_message(self, doc.source_path.name)
        result = message.exec()
        if result == QMessageBox.StandardButton.Discard:
            return True
        if result == QMessageBox.StandardButton.Save:
            self.tabs.setCurrentWidget(doc)
            self.saving.choose(on_saved=on_saved)
        else:
            self._discard_on_close.clear()
        return False

    def close_tab(self, index: int, *, force: bool = False) -> None:
        if (self._export_running and not force) or index < 0:
            return
        doc = self.tabs.widget(index)
        if doc is None:
            return
        if not force:
            self.annotation_editor.finish_text(True)
            if not self._confirm_close(doc, lambda saved: self.close_tab(self.tabs.indexOf(saved), force=True)):
                return
        doc.password = None
        if self._password_document_id == doc.document_id and self._password_dialog is not None:
            self._password_dialog.reject()
        self._password_queue = [item for item in self._password_queue if item[0] != doc.document_id]
        if not force and not doc.ready:
            self._finish_load(doc.document_id)
        doc.render_timer.stop()
        doc.fit_timer.stop()
        doc.pages.scroll_timer.stop()
        self.preview_cache.remove_document(doc.document_id)
        doc.grid_host.finish_drag()
        self.render_service.cancel_pending(doc.document_id)
        self.render_service.cancel_pending(-1_000_000 - doc.document_id)
        self.render_service.release_document(doc.document_id, doc.source_path)
        self._text_requests = {generation: request for generation, request in self._text_requests.items()
                               if request[0] != doc.document_id}
        self._image_requests = {generation: request for generation, request in self._image_requests.items()
                                if request[0] != doc.document_id}
        for generation, document_id in list(self._render_documents.items()):
            if document_id == doc.document_id:
                self._render_documents.pop(generation)
        self.documents.pop(doc.document_id, None)
        self._ocr_generations.pop(doc.document_id, None)
        self.search_controller.remove_document(doc.document_id)
        self.navigation.remove_document(doc)
        self.tabs.removeTab(index)
        doc.deleteLater()
        if not self.tabs.count():
            self.tabs.hide()
            self.empty_label.show()
            self.zoom_slider.blockSignals(True)
            self.zoom_slider.setValue(100)
            self.zoom_slider.blockSignals(False)
        self._sync_controls()

    @Slot(object)
    def _handle_render_message(self, payload) -> None:
        if not isinstance(payload, dict):
            return
        if self.annotation_editor.receive(payload):
            return
        if self.navigation.receive(payload):
            return
        try:
            generation = int(payload.get("generation", -1))
        except (TypeError, ValueError):
            return
        viewer = self._fullscreen_preview
        if payload.get('type') == 'image':
            self._accept_image(generation, payload)
            return
        if generation in self._image_requests:
            if payload.get('type') in {'done', 'error'}:
                self._image_requests.pop(generation, None)
                if payload.get('type') == 'error':
                    self.statusBar().showMessage(tr('無法擷取圖片：{p0}', p0=payload.get('message', '')))
            return
        if generation in self._text_requests:
            document_id, label, copy = self._text_requests[generation]
            if document_id in self.documents and not self._closing:
                retry = payload.get('ocr_retry')
                if payload.get('ocr_model_missing') and copy and retry:
                    def retry_selection(document_id=document_id, label=label, retry=retry, generation=generation):
                        doc = self.documents.get(document_id)
                        if (doc is None or not isValid(label) or self._closing or not label.text_mode
                                or self._ocr_generations.get(document_id) != generation
                                or self.ocr_languages.profile != retry['ocr_profile']
                                or label.region_mode != (retry['type'] == 'ocr_region')):
                            return
                        self._copy_text_selection(doc, retry['page'], label,
                            QPointF(retry['start'][0] * label.width(), retry['start'][1] * label.height()),
                            QPointF(retry['end'][0] * label.width(), retry['end'][1] * label.height()))
                    self.ocr_languages.ensure(retry['ocr_profile'], retry_selection)
                if payload.get('type') == 'ocr' and copy:
                    self.statusBar().showMessage(tr('選取文字疑似損壞，正在進行 OCR…'))
                elif payload.get('type') == 'text':
                    extracted = str(payload.get('text', ''))
                    if isValid(label) and label.text_mode:
                        label.set_text_highlights(payload.get('rects', []))
                    if extracted and copy:
                        QApplication.clipboard().setText(extracted)
                        if payload.get('ocr_error'):
                            self.statusBar().showMessage(tr('OCR 未完成，已複製原始文字：{p0}', p0=payload['ocr_error']))
                        elif payload.get('ocr_used'):
                            self.statusBar().showMessage(tr('已透過 OCR 複製 {p0} 個字元，請確認辨識結果', p0=len(extracted)))
                        else:
                            self.statusBar().showMessage(tr('已複製 {p0} 個字元到剪貼簿', p0=len(extracted)))
                    elif copy:
                        self.statusBar().showMessage(tr('選取範圍沒有可複製的文字'))
                elif payload.get('type') == 'error':
                    if isValid(label):
                        label.set_text_highlights([])
                    if copy:
                        self.statusBar().showMessage(tr('無法擷取文字：{p0}', p0=payload.get('message', '')))
            if payload.get('type') in {'done', 'error'}:
                self._text_requests.pop(generation, None)
            return
        if viewer is not None and viewer.render_generation == generation:
            viewer.accept_render(payload)
            return
        doc = self.documents.get(self._render_documents.get(generation))
        if doc is not None and doc.render_generation == generation and not self._closing:
            doc._handle_render_message(payload)
        elif payload.get("type") == "page":
            path = Path(str(payload.get("path", "")))
            if path.parent == Path(self.preview_temp.name) and path.name.startswith(f"g{generation}-p"):
                path.unlink(missing_ok=True)
        if payload.get("type") in {"done", "error"}:
            self._render_documents.pop(generation, None)

    def _set_export_running(self, running: bool) -> None:
        self._export_running = running
        self.open_action.setEnabled(not running)
        self.tabs.setMovable(not running)
        for doc in self.documents.values():
            doc.include_checkbox.setEnabled(doc.ready and not running)
            doc.close_button.setEnabled(not running)
            for card in doc.page_cards:
                card.checkbox.setEnabled(not running)
        self._sync_controls()

    @Slot()
    def choose_output(self) -> None:
        self._choose_output(split=False)

    @Slot()
    def choose_split_output(self) -> None:
        self._choose_output(split=True)

    def _choose_output(self, *, split: bool) -> None:
        self.annotation_editor.finish_text(True)
        selections = self.output_selection(fallback_current=True)
        if not selections or self._export_running:
            return
        suggested = default_output_path(selections[0].source)
        filename, selected_filter = QFileDialog.getSaveFileName(
            self._fullscreen_preview or self,
            tr('拆分頁面（PDF／PNG；新 PDF 不加密）') if split else tr('重組輸出（單一 PDF；新 PDF 不加密）'),
            str(suggested), tr('PDF 檔案 (*.pdf)') + (';;' + tr('PNG 圖檔 (*.png)') if split else ''), '',
            QFileDialog.Option.DontUseNativeDialog | QFileDialog.Option.DontConfirmOverwrite,
        )
        if not filename:
            return
        image = split and ('*.png' in selected_filter or Path(filename).suffix.lower() == '.png')
        destination = Path(filename).with_suffix('.png' if image else '.pdf')
        count = sum(len(item.pages) for item in selections)
        outputs = (png_output_paths(destination, count) if image else
                   split_output_paths(destination, count) if split else [destination])
        if {doc.source_path for doc in self.documents.values()}.intersection(path.resolve() for path in outputs):
            QMessageBox.warning(self._fullscreen_preview or self, tr('無法輸出'), tr('輸出檔案不可覆蓋來源 PDF。'))
            return
        existing = [path for path in outputs if path.exists()]
        overwrite = False
        if existing:
            answer = QMessageBox.question(
                self._fullscreen_preview or self, tr('覆蓋輸出檔案'),
                tr('已有 {p0} 個同名輸出檔案，例如：\n{p1}\n\n是否覆蓋？', p0=len(existing), p1=existing[0]),
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No)
            if answer != QMessageBox.StandardButton.Yes:
                return
            overwrite = True
        self._start_export(destination, split=split, overwrite=overwrite, image=image, selections=selections)

    def _start_export(self, destination: Path, *, split: bool = False, overwrite: bool = False,
                      image: bool = False, selections=None) -> None:
        selections = selections if selections is not None else self.output_selection(fallback_current=True)
        if not selections or self._export_running:
            return
        self._export_id += 1
        self._set_export_running(True)
        self._export_split = split
        self._export_png = image
        if image:
            self.statusBar().showMessage(tr('正在輸出 PNG…'))
            self.png_export.start(selections, destination, self._export_id, overwrite)
            return
        self.statusBar().showMessage(tr('正在拆分單頁 PDF…') if split else tr('正在輸出 PDF…'))
        task = ExportPdfTask(
            selections,
            destination,
            self._export_id,
            split=split, overwrite=overwrite,
            protected_sources=tuple(doc.source_path for doc in self.documents.values()),
        )
        self._active_tasks.add(task)
        task.signals.completed.connect(self._export_completed)
        task.signals.failed.connect(self._export_failed)
        task.signals.completed.connect(lambda *_args, job=task: self._active_tasks.discard(job))
        task.signals.failed.connect(lambda *_args, job=task: self._active_tasks.discard(job))
        self.thread_pool.start(task)

    @Slot(int, object, int)
    def _export_completed(self, session: int, destination: Path, count: int) -> None:
        if session != self._export_id or self._closing:
            return
        self._set_export_running(False)
        self.statusBar().showMessage(tr('輸出完成：{p0}', p0=destination))
        if self._export_png:
            outputs = png_output_paths(destination, count)
            message = tr('已輸出 {count} 張 PNG：\n{path}', count=count, path=outputs[0])
            if count > 1:
                message += f'\n…\n{outputs[-1]}'
            QMessageBox.information(self._fullscreen_preview or self, tr('輸出完成'), message)
            return
        if self._export_split:
            outputs = split_output_paths(destination, count)
            message = tr('已拆分為 {p0} 個單頁 PDF：\n{p1}', p0=count, p1=outputs[0])
            if count > 1:
                message += f"\n…\n{outputs[-1]}"
        else:
            message = tr('已輸出 {p0} 頁至：\n{p1}', p0=count, p1=destination)
        message += '\n' + tr('新 PDF 不加密，原始檔案保持不變。')
        QMessageBox.information(self._fullscreen_preview or self, tr('輸出完成'), message)

    @Slot(int, str)
    def _export_failed(self, session: int, message: str) -> None:
        if session != self._export_id or self._closing:
            return
        self._set_export_running(False)
        self.statusBar().showMessage(tr('輸出失敗'))
        QMessageBox.critical(self._fullscreen_preview or self, tr('輸出失敗'), localize_text(message))

    def closeEvent(self, event: QCloseEvent) -> None:
        self.png_export.cancel()
        if self.saving.task is not None:
            event.ignore()
            self.statusBar().showMessage(tr('正在儲存 PDF…'))
            return
        self.annotation_editor.finish_text(True)
        for doc in self.ordered_documents():
            if doc.document_id not in self._discard_on_close and doc.modified:
                if not self._confirm_close(doc, lambda _saved: self.close()):
                    event.ignore()
                    return
                self._discard_on_close.add(doc.document_id)
        self._closing = True
        self.annotation_editor.finish_text(True)
        self.document_text.cancel()
        self.navigation.shutdown()
        self.ocr_languages.close()
        self.print_controller.close()
        self.search_controller.stop()
        self._password_queue.clear()
        if self._password_dialog is not None:
            self._password_dialog.reject()
        if self._fullscreen_preview is not None:
            self._fullscreen_preview.close()
        for doc in self.documents.values():
            doc.password = None
            doc.render_timer.stop()
            doc.fit_timer.stop()
            doc.pages.scroll_timer.stop()
            doc.grid_host.finish_drag()
        self.render_service.close()
        self.thread_pool.clear()
        self.thread_pool.waitForDone()
        self.preview_temp.cleanup()
        self.language_controller.close()
        event.accept()


def load_app_icon() -> QIcon:
    from repdf.icon_layout import fitted_icon
    import io
    from PySide6.QtGui import QPixmap
    buffer=io.BytesIO()
    fitted_icon(files('repdf').joinpath('assets','repdf.png')).save(buffer,format='PNG')
    image=QImage.fromData(buffer.getvalue())
    return QIcon(QPixmap.fromImage(image))


def configure_application(app: QApplication) -> None:
    app.setApplicationName("RePDF")
    app.setOrganizationName("repdf")
    app.setStyle("Fusion")
    app.setWindowIcon(load_app_icon())
    available = set(QFontDatabase.families())
    for family in (
        "Microsoft JhengHei UI",
        "Microsoft JhengHei",
        "Noto Sans TC",
        "Arial",
    ):
        if family in available:
            app.setFont(QFont(family, 10))
            break


def main() -> int:
    render_backend = start_render_backend()
    app = QApplication(sys.argv)
    configure_application(app)
    window = MainWindow(render_backend)
    window.show()
    return app.exec()
