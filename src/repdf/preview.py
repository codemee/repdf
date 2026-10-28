from pathlib import Path

from PySide6.QtCore import QEvent, Qt, QTimer
from PySide6.QtGui import QImage, QKeySequence, QPixmap
from PySide6.QtWidgets import QApplication, QCheckBox, QHBoxLayout, QWidget

from repdf.strings import tr
from repdf.widgets import PagePreviewLabel, ParityCheckBox
from repdf.core import parity_state, SelectionState
from repdf.floating_tools import FloatingAnnotationTools


class FullscreenPreview(QWidget):
    """Display ordered pages at a common scale and share document selection."""

    HEADER_HEIGHT = 30
    PAGE_GAP = 12

    def __init__(self, owner, document, page_index, mode="single"):
        super().__init__(owner, Qt.WindowType.Window)
        self.owner = owner
        self.document = document
        self.mode = mode
        self.groups = self.page_groups(mode)
        self.render_generation = -1
        self.images = {}
        self.labels = {}
        self.page_frames = {}
        self.checkboxes = {}
        self.parity_buttons = {}
        self.page_headers = {}
        self.closed = False
        self.setWindowModality(Qt.WindowModality.ApplicationModal)
        self.setObjectName('fullscreenPreview')
        self.setStyleSheet("QWidget#fullscreenPreview { background: palette(window); }")
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.setInterval(120)
        self.timer.timeout.connect(self.request_render)
        QApplication.instance().installEventFilter(self)
        self.show_page(page_index)
        self.floating_tools = FloatingAnnotationTools(self)

    def page_groups(self, mode):
        order = self.document.page_order
        if mode == 'single':
            return [[page] for page in order]
        if mode == 'spread':
            return [order[i:i + 2] for i in range(0, len(order), 2)]
        if mode == 'cover':
            return [order[:1]] + [order[i:i + 2] for i in range(1, len(order), 2)]
        raise ValueError(f'Unknown preview mode: {mode}')

    def set_mode(self, mode):
        groups = self.page_groups(mode)
        if mode == self.mode:
            return
        self.owner.annotation_editor.finish_text(True)
        self.owner.annotation_editor.clear()
        page = self.page_index
        self.mode = mode
        self.groups = groups
        self.owner.fullscreen_mode = mode
        action = {'single': self.owner.single_action, 'spread': self.owner.spread_action,
                  'cover': self.owner.cover_action}[mode]
        action.setChecked(True)
        self.owner.fullscreen_action.setToolTip(tr('全螢幕模式：{mode}', mode=action.text()))
        self.owner._refresh_toolbar_icons()
        self.show_page(page)

    @property
    def image(self):
        return self.images.get(self.page_index, QImage())

    @property
    def label(self):
        return self.labels[self.page_index]

    def show_page(self, page_index):
        self.render_generation = -1
        self.owner.render_service.cancel_pending(-self.document.document_id)
        self.group_index = next(i for i, group in enumerate(self.groups) if page_index in group)
        self.visible_pages = self.groups[self.group_index]
        self.page_index = self.visible_pages[0]
        for widget in list(self.labels.values()) + list(self.page_frames.values()) + list(self.page_headers.values()):
            widget.hide()
            widget.deleteLater()
        self.images = {}
        self.labels = {}
        self.page_frames = {}
        self.checkboxes = {}
        self.parity_buttons = {}
        self.page_headers = {}
        for index in self.visible_pages:
            self.images[index] = self.document.page_cards[index].preview.pixmap().toImage()
            label = PagePreviewLabel('', draggable=False)
            frame = QWidget(self)
            self.page_frames[index] = frame
            frame.show()
            label.set_search_highlight_color(self.owner.search_controller.highlight_color)
            label.setParent(frame)
            self.owner.annotation_editor.attach(label,self.document,index)
            source_label = self.document.page_cards[index].preview
            label.set_links(self.document.page_links.get(index, []))
            label.set_annotations(self.document.page_annotations.get(index, []))
            label.link_activated.connect(lambda destination: self.owner.navigation.activate(
                self.document, destination, fullscreen=True))
            label.set_search_highlights(source_label._search_rects, source_label._active_search_rects)
            label.set_annotation_highlight(self.document.pages.annotation_highlights.get(index))
            label.set_text_mode(self.owner._selection_active(), region=self.owner.region_ocr_action.isChecked(),
                                image=self.owner.extract_image_action.isChecked())
            label.text_selected.connect(
                lambda start, end, page=index, preview=label:
                self.owner._copy_text_selection(self.document, page, preview, start, end))
            label.selection_preview.connect(
                lambda start, end, page=index, preview=label:
                self.owner._copy_text_selection(self.document, page, preview, start, end, copy=False))
            self.owner.document_text.apply_label(label, self.document, index)
            label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            if self.images[index].isNull():
                label.setText(tr("正在產生頁面預覽…"))
            label.show()
            self.labels[index] = label
            header = QWidget(self)
            header_layout = QHBoxLayout(header)
            header_layout.setContentsMargins(0, 0, 0, 0)
            header_layout.setSpacing(6)
            self.page_headers[index] = header
            checkbox = QCheckBox(tr("第 {p0} 頁", p0=index + 1), header)
            header_layout.addWidget(checkbox, 0, Qt.AlignmentFlag.AlignVCenter)
            checkbox.setChecked(index in self.document.selected_pages)
            checkbox.setEnabled(not self.owner._export_running)
            checkbox.toggled.connect(lambda checked, page=index: self._select_page(page, checked))
            checkbox.show()
            self.checkboxes[index] = checkbox
            parity = ParityCheckBox(index, header)
            header_layout.addWidget(parity, 0, Qt.AlignmentFlag.AlignVCenter)
            parity.set_selection_state(parity_state(self.document.selected_pages, self.document.page_count, parity.odd))
            parity.setEnabled(not self.owner._export_running)
            parity.clicked.connect(lambda _checked, odd=parity.odd:
                self.document._toggle_parity(odd, parity_state(self.document.selected_pages, self.document.page_count, odd) != SelectionState.ALL)
                if not self.owner._export_running else None)
            parity.show()
            self.parity_buttons[index] = parity
            header.show()
        self.update_image()
        self.timer.start()

    def _select_page(self, index, checked):
        self.document.page_cards[index].set_selected(checked)
        self.document._page_selection_changed(index, checked)

    def _page_sizes(self):
        result = {}
        for index in self.visible_pages:
            size = self.document.page_sizes.get(index)
            if size is None:
                image = self.images[index]
                size = (image.width(), image.height()) if not image.isNull() else (595, 842)
            trim = self.document.trim_boxes.get(index) if self.document.trim_view else None
            result[index] = (size[0] * (trim[2] - trim[0]), size[1] * (trim[3] - trim[1])) if trim else size
        return result

    def _fit_scale(self, sizes):
        width = sum(size[0] for size in sizes.values())
        height = max(size[1] for size in sizes.values())
        gap = self.PAGE_GAP * (len(sizes) - 1)
        return max(.001, min(max(1, self.width() - gap) / width,
                             max(1, self.height() - self.HEADER_HEIGHT) / height))

    def request_render(self):
        if self.closed:
            return
        sizes = self._page_sizes()
        scale = self._fit_scale(sizes) * self.devicePixelRatioF()
        area = sum(self.document.page_sizes.get(index, size)[0] *
                   self.document.page_sizes.get(index, size)[1] for index, size in sizes.items())
        scale = min(scale, (30_000_000 / area) ** .5)
        self.owner._next_generation += 1
        self.render_generation = self.owner._next_generation
        self.owner.render_service.request(self.document.source_path, scale,
                                         Path(self.owner.preview_temp.name), self.render_generation,
                                         document_id=-self.document.document_id, pages=self.visible_pages,
                                         password=self.document.password)
        self.owner.render_service.prioritize(-self.document.document_id)

    def accept_render(self, payload):
        if payload.get("type") == "page":
            index = int(payload["page"])
            path = Path(payload["path"])
            image = QImage(str(path)).copy()
            path.unlink(missing_ok=True)
            if index not in self.visible_pages:
                return
            self.owner.annotation_editor.loaded(self.document,index,payload)
            self.images[index] = image
            self.document.page_links[index] = payload.get('links', [])
            self.document.page_annotations[index] = payload.get('annotation_hits', [])
            self.document.page_labels[index] = payload.get('page_label')
            self.labels[index].set_links(self.document.page_links[index])
            self.labels[index].set_annotations(self.document.page_annotations[index])
            unknown_size = index not in self.document.page_sizes
            if payload.get('trim_rect') is not None:
                self.document.trim_boxes[index] = payload['trim_rect']
            else:
                self.document.trim_boxes.pop(index, None)
            self.document.page_sizes[index] = (
                float(payload["width_points"]), float(payload["height_points"]))
            self.update_image()
            if unknown_size:
                self.timer.start()
        elif payload.get("type") == "error":
            for index, image in self.images.items():
                if image.isNull():
                    self.labels[index].setText(tr("無法產生預覽"))

    def update_image(self):
        sizes = self._page_sizes()
        scale = self._fit_scale(sizes)
        spread_width = sum(width * scale for width, _ in sizes.values()) + self.PAGE_GAP * (len(sizes) - 1)
        spread_height = max(height * scale for _, height in sizes.values())
        x = (self.width() - spread_width) / 2
        y = self.HEADER_HEIGHT + (self.height() - self.HEADER_HEIGHT - spread_height) / 2
        ratio = self.devicePixelRatioF()
        for index, (width, height) in sizes.items():
            label = self.labels[index]
            trim = self.document.trim_boxes.get(index) if self.document.trim_view else None
            frame = self.page_frames[index]
            frame.setGeometry(round(x), round(y), max(1, round(width * scale)), max(1, round(height * scale)))
            parent = frame if trim else self
            if label.parentWidget() is not parent:
                label.setParent(parent)
                label.show()
            frame.setVisible(trim is not None)
            full_width = width / (trim[2] - trim[0]) if trim else width
            full_height = height / (trim[3] - trim[1]) if trim else height
            label.setGeometry(-round(trim[0] * full_width * scale) if trim else round(x),
                              -round(trim[1] * full_height * scale) if trim else round(y),
                              max(1, round(full_width * scale)), max(1, round(full_height * scale)))
            header = self.page_headers[index]
            header.adjustSize()
            header.move(round(x) + 6, round(y) - self.HEADER_HEIGHT +
                        (self.HEADER_HEIGHT - header.height()) // 2)
            image = self.images[index]
            if not image.isNull():
                pixmap = QPixmap.fromImage(image).scaled(
                    label.size() * ratio, Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation)
                pixmap.setDevicePixelRatio(ratio)
                label.setPixmap(pixmap)
            x += width * scale + self.PAGE_GAP
        if hasattr(self,'floating_tools'):
            self.floating_tools.reposition()
        self.owner._update_page_indicator()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, "timer"):
            self.update_image()
            self.timer.start()

    def eventFilter(self, watched, event):
        editor=self.owner.annotation_editor
        if editor.text_edit is not None and isinstance(watched,QWidget) and (watched is editor.text_edit or editor.text_edit.isAncestorOf(watched)):
            return False
        if event.type()==QEvent.Type.KeyPress and event.key()==Qt.Key.Key_Escape and (editor.anchor is not None or editor.drag is not None):
            return False
        if self.owner.document_text.handle_event(watched, event, self):
            return True
        if (not self.closed and isinstance(watched,QWidget) and watched.window() is self
                and event.type() in (QEvent.Type.ShortcutOverride,QEvent.Type.KeyPress)
                and (event.matches(QKeySequence.StandardKey.Save) or event.matches(QKeySequence.StandardKey.SaveAs))):
            if event.type() == QEvent.Type.ShortcutOverride: event.accept()
            else: self.owner.saving.choose(save_as=event.matches(QKeySequence.StandardKey.SaveAs))
            return True
        if (not self.closed and isinstance(watched, QWidget) and watched.window() is self
                and event.type() in (QEvent.Type.ShortcutOverride, QEvent.Type.KeyPress)
                and event.matches(QKeySequence.StandardKey.Print)):
            if event.type() == QEvent.Type.ShortcutOverride:
                event.accept()
            else:
                self.owner.print_controller.open()
            return True
        if (not self.closed and isinstance(watched, QWidget) and watched.window() is self
                and event.type() in (QEvent.Type.ShortcutOverride, QEvent.Type.KeyPress)
                and event.matches(QKeySequence.StandardKey.Find)):
            if event.type() == QEvent.Type.ShortcutOverride:
                event.accept()
            else:
                self.owner.search_controller.open()
            return True
        if (not self.closed and isinstance(watched, QWidget) and watched.window() is self
                and event.type() == QEvent.Type.KeyPress and not event.modifiers()):
            return self._handle_key(event.key())
        return super().eventFilter(watched, event)

    def _handle_key(self, key):
        if key in (Qt.Key.Key_Escape, Qt.Key.Key_F11):
            self.close()
            return True
        if key in (Qt.Key.Key_Home, Qt.Key.Key_End):
            position = 0 if key == Qt.Key.Key_Home else len(self.groups) - 1
            if position != self.group_index:
                self.show_page(self.groups[position][0])
            return True
        previous = (Qt.Key.Key_Left, Qt.Key.Key_Up, Qt.Key.Key_PageUp)
        following = (Qt.Key.Key_Right, Qt.Key.Key_Down, Qt.Key.Key_PageDown)
        if key in previous + following:
            position = self.group_index + (-1 if key in previous else 1)
            if 0 <= position < len(self.groups):
                self.show_page(self.groups[position][0])
            return True
        return False

    def closeEvent(self, event):
        self.owner.annotation_editor.finish_text(True)
        self.closed = True
        self.floating_tools.restore_menus()
        self.timer.stop()
        QApplication.instance().removeEventFilter(self)
        self.owner.render_service.cancel_pending(-self.document.document_id)
        self.owner._fullscreen_preview = None
        self.owner.annotation_floating.setVisible(self.owner.annotation_tools_action.isChecked())
        self.owner.annotation_floating.reposition()
        self.owner.activateWindow()
        self.deleteLater()
        event.accept()
