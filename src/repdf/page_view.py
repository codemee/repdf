"""Viewport driven page layout, bounded image cache and small render batches."""

from collections import OrderedDict
from math import ceil
from pathlib import Path

from PySide6.QtCore import QRect, QSize, Qt, QTimer
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import QLayout

from repdf.strings import tr


class PreviewCache:
    def __init__(self, limit=128 * 1024 * 1024):
        self.limit = limit
        self.bytes = 0
        self.items = OrderedDict()

    def get(self, key):
        image = self.items.get(key)
        if image is not None:
            self.items.move_to_end(key)
        return image

    def put(self, key, image):
        old = self.items.pop(key, None)
        if old is not None:
            self.bytes -= old.sizeInBytes()
        if image.sizeInBytes() <= self.limit:
            self.items[key] = image
            self.bytes += image.sizeInBytes()
        while self.bytes > self.limit:
            _, old = self.items.popitem(last=False)
            self.bytes -= old.sizeInBytes()

    def remove_document(self, document_id):
        for key in list(self.items):
            if key[0] == document_id:
                self.bytes -= self.items.pop(key).sizeInBytes()


class PageCards:
    """Index by stable PDF page number; iteration only visits existing widgets."""

    def __init__(self, document):
        self.document = document
        self.realized = {}

    def __len__(self):
        return self.document.page_count

    def __iter__(self):
        return iter(list(self.realized.values()))

    def __getitem__(self, index):
        if not 0 <= index < len(self):
            raise IndexError(index)
        if index not in self.realized:
            self.realized[index] = self.document._make_page_card(index)
        return self.realized[index]


class PageViewport:
    VIRTUAL_THRESHOLD = 64
    BATCH_SIZE = 2

    def __init__(self, document):
        self.doc = document
        self.virtual = False
        self.rects = {}
        self.order_positions = {}
        self.batch = []
        self.batch_scale = None
        self.failed = set()
        self.highlights = {}
        self.chrome = 48
        self._in_layout = False
        self.scroll_timer = QTimer(document)
        self.scroll_timer.setSingleShot(True)
        self.scroll_timer.setInterval(40)
        self.scroll_timer.timeout.connect(self.refresh)
        document.scroll_area.verticalScrollBar().valueChanged.connect(self.schedule)
        document.scroll_area.horizontalScrollBar().valueChanged.connect(self.schedule)

    def initialize(self):
        d = self.doc
        self.virtual = d.page_count > self.VIRTUAL_THRESHOLD
        d.page_cards = PageCards(d)
        d.page_order = list(range(d.page_count))
        if self.virtual:
            d.grid.setSizeConstraint(QLayout.SizeConstraint.SetNoConstraint)
            d.grid.setEnabled(False)
            d.grid_host.virtual_document = d
        else:
            for index in d.page_order:
                d.page_cards[index]
        self.reflow()

    def scale(self):
        return self.doc._preview_scale()

    def key(self, page, scale=None):
        return self.doc.document_id, page, self.scale() if scale is None else scale

    def page_size(self, page):
        return self.doc.page_sizes.get(page, (595, 842))

    def dimensions(self, page):
        width, height = self.page_size(page)
        return max(1, ceil(width * self.scale())), max(1, ceil(height * self.scale()))

    def schedule(self, *_args):
        if not self.doc.owner._closing and self.doc.ready:
            self.scroll_timer.start()

    def visible_rect(self):
        d = self.doc
        return d.scroll_area.viewport().rect().translated(
            d.scroll_area.horizontalScrollBar().value(), d.scroll_area.verticalScrollBar().value())

    def rect(self, page):
        if self.virtual:
            return self.rects[page]
        return self.doc.page_cards[page].geometry()

    def current_page(self, prefer_focused=True):
        d = self.doc
        visible = self.visible_rect()
        if prefer_focused and d.focused_page is not None and self.rect(d.focused_page).intersects(visible):
            return d.focused_page
        return min(d.page_order, key=lambda page: (self.rect(page).center() - visible.center()).manhattanLength())

    def targets(self):
        d = self.doc
        view = self.visible_rect()
        nearby = view.adjusted(0, -view.height(), 0, view.height())
        candidates = [page for page in d.page_order if self.rect(page).intersects(nearby)]
        candidates.sort(key=lambda page: (not self.rect(page).intersects(view),
                                         abs(self.rect(page).center().y() - view.center().y())))
        return candidates

    def prepare_card(self, card):
        d = self.doc
        width, height = self.dimensions(card.page_index)
        card.set_preview_size(width, height)
        card.set_selected(card.page_index in d.selected_pages)
        if self.virtual and card.page_index in self.rects:
            card.setParent(d.grid_host)
            card.setGeometry(self.rects[card.page_index])
            card.show()
        cached = d.owner.preview_cache.get(self.key(card.page_index))
        if cached is not None:
            card.set_image(cached)
            card.render_scale = self.scale()
        if card.page_index in self.highlights:
            card.preview.set_search_highlights(*self.highlights[card.page_index])

    def reflow(self):
        d = self.doc
        if not d.ready or not d.page_order or self._in_layout or d.grid_host.drag_source is not None:
            return
        self._in_layout = True
        try:
            if self.virtual:
                self._layout_virtual()
            else:
                while d.grid.count():
                    d.grid.takeAt(0)
                # Preserve externally supplied images until their page metadata is known.
                for card in d.page_cards:
                    if card.page_index in d.page_sizes or card.preview.pixmap().isNull():
                        card.set_preview_size(*self.dimensions(card.page_index))
                width = max(card.width() for card in d.page_cards)
                available = max(1, d.scroll_area.viewport().width() - 24)
                columns = 1 if d.fit_mode else max(1, (available + 12) // (width + 12))
                for position, page in enumerate(d.page_order):
                    d.grid.addWidget(d.page_cards[page], position // columns, position % columns,
                                     Qt.AlignmentFlag.AlignHCenter)
                d.grid.activate()
        finally:
            self._in_layout = False
        self.schedule()

    def _layout_virtual(self):
        d = self.doc
        anchor = self.current_page(False) if self.rects else None
        old_y = self.rects[anchor].y() if anchor is not None else 0
        old_scroll = d.scroll_area.verticalScrollBar().value()
        widths = [self.dimensions(page)[0] + 24 for page in d.page_order]
        column_width = max(widths)
        available = max(1, d.scroll_area.viewport().width() - 24)
        columns = 1 if d.fit_mode else max(1, (available + 12) // (column_width + 12))
        content_width = max(d.scroll_area.viewport().width(), columns * (column_width + 12) + 12)
        left = (content_width - columns * (column_width + 12) + 12) // 2
        rects = {}
        y = 12
        for offset in range(0, d.page_count, columns):
            pages = d.page_order[offset:offset + columns]
            row_height = max(self.dimensions(page)[1] + self.chrome for page in pages)
            for column, page in enumerate(pages):
                width, height = self.dimensions(page)
                x = left + column * (column_width + 12) + (column_width - width - 24) // 2
                rects[page] = QRect(x, y, width + 24, height + self.chrome)
            y += row_height + 12
        self.rects = rects
        self.order_positions = {page: pos for pos, page in enumerate(d.page_order)}
        d.grid_host.virtual_size = QSize(content_width, y)
        d.grid_host.setMinimumSize(content_width, y)
        d.grid_host.resize(content_width, max(y, d.scroll_area.viewport().height()))
        for page, card in d.page_cards.realized.items():
            card.set_preview_size(*self.dimensions(page))
            card.setGeometry(rects[page])
        if anchor is not None and not d._fit_navigation_pending:
            d.scroll_area.verticalScrollBar().setValue(old_scroll + rects[anchor].y() - old_y)

    def refresh(self):
        d = self.doc
        if d.owner._closing or not d.ready or d.grid_host.drag_source is not None:
            return
        d.owner._update_page_indicator()
        if d.owner.current_document() is not d:
            d.owner.render_service.cancel_pending(d.document_id)
            return
        targets = self.targets()
        if self.virtual:
            keep = set(targets)
            for page in targets:
                card = d.page_cards[page]
                card.setGeometry(self.rects[page])
            for page in set(d.page_cards.realized) - keep:
                card = d.page_cards.realized.pop(page)
                card.hide()
                card.deleteLater()
        else:
            for card in d.page_cards:
                if card.page_index not in targets:
                    card.preview.setPixmap(QPixmap())
                    card.render_scale = None
        if not d.render_timer.isActive():
            d._queue_all_renders()

    def request_visible(self):
        d = self.doc
        if not d.ready or d.owner._closing or d.owner.current_document() is not d:
            return
        targets = self.targets()
        scale = self.scale()
        needed = []
        for page in targets:
            card = d.page_cards[page]
            cached = d.owner.preview_cache.get(self.key(page))
            if cached is not None and getattr(card, 'render_scale', None) != scale:
                card.set_image(cached)
                card.render_scale = scale
            if getattr(card, 'render_scale', None) != scale and self.key(page) not in self.failed:
                needed.append(page)
        # A small active batch can finish; a new viewport replaces queued work.
        if self.batch and self.batch_scale == scale and any(page in targets for page in self.batch):
            return
        if not needed:
            return
        for generation, document_id in list(d.owner._render_documents.items()):
            if document_id == d.document_id:
                d.owner._render_documents.pop(generation)
        d.owner._next_generation += 1
        d.render_generation = d.owner._next_generation
        d.owner._render_documents[d.render_generation] = d.document_id
        d.render_timer.stop()
        self.batch = needed[:self.BATCH_SIZE]
        self.batch_scale = scale
        d._render_pending = len(self.batch)
        d._render_received.clear()
        d.owner.render_service.request(d.source_path, scale, Path(d.owner.preview_temp.name),
                                       d.render_generation, document_id=d.document_id,
                                       pages=self.batch, password=d.password)

    def receive(self, payload):
        d = self.doc
        kind = payload.get('type')
        if kind == 'page':
            self.accept(payload)
        elif kind in ('done', 'error'):
            if kind == 'error':
                for page in self.batch:
                    if page not in d._render_received:
                        self.failed.add(self.key(page, self.batch_scale))
                        card = d.page_cards.realized.get(page)
                        if card is not None:
                            card.set_render_error()
                d.show_status(tr('部分頁面無法產生預覽'))
            d._render_done_generation = d.render_generation
            d._render_pending = 0
            self.batch = []
            self.schedule()

    def accept(self, payload):
        d = self.doc
        page = int(payload['page'])
        path = Path(payload['path'])
        image = QImage(str(path))
        path.unlink(missing_ok=True)
        if not 0 <= page < d.page_count or image.isNull():
            return
        scale = self.batch_scale or self.scale()
        old_size = d.page_sizes.get(page)
        d.page_links[page] = payload.get('links', [])
        d.page_labels[page] = payload.get('page_label')
        d.page_sizes[page] = (float(payload.get('width_points', image.width() / scale)),
                              float(payload.get('height_points', image.height() / scale)))
        d.owner.preview_cache.put(self.key(page, scale), image)
        card = d.page_cards.realized.get(page)
        if card is not None:
            card.set_image(image)
            card.preview.set_links(d.page_links[page])
            card.render_scale = scale
        if page not in d._render_received:
            d._render_received.add(page)
            d._render_pending = max(0, d._render_pending - 1)
        if old_size != d.page_sizes[page]:
            self.reflow()
        if d.fit_mode and page == d.fit_page_index:
            d.fit_timer.start()
            QTimer.singleShot(0, d._scroll_to_fit_page)
        if d._search_navigation and page == d._search_navigation[0]:
            QTimer.singleShot(0, d._scroll_to_search_result)
        d.owner._sync_controls()

    def ensure_page(self, page):
        card = self.doc.page_cards[page]
        if self.virtual:
            card.setGeometry(self.rects[page])
            card.show()
        return card

    def suspend(self):
        d = self.doc
        self.scroll_timer.stop()
        d.render_timer.stop()
        d.owner.render_service.cancel_pending(d.document_id)
        self.batch = []
        d._render_pending = 0
        d.render_generation = -1
        for generation, document_id in list(d.owner._render_documents.items()):
            if document_id == d.document_id:
                d.owner._render_documents.pop(generation)
        if self.virtual:
            for card in d.page_cards:
                card.hide()
                card.deleteLater()
            d.page_cards.realized.clear()
        else:
            for card in d.page_cards:
                card.preview.setPixmap(QPixmap())
                card.render_scale = None

    def set_highlights(self, page, all_rects, active_rects):
        self.highlights[page] = (all_rects, active_rects)
        self.ensure_page(page).preview.set_search_highlights(all_rects, active_rects)

    def clear_highlights(self):
        self.highlights.clear()
        for card in self.doc.page_cards:
            card.preview.set_search_highlights([], [])
