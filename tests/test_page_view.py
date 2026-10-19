import io
import json
from pathlib import Path

from pypdf import PdfWriter
from PySide6.QtCore import Qt
from PySide6.QtGui import QImage

from repdf.app import MainWindow
from repdf.core import inspect_pdf
from repdf.page_view import PreviewCache


def make_document(path, count):
    writer = PdfWriter()
    for _ in range(count):
        writer.add_blank_page(300, 400)
    writer.write(path)


def settled(doc):
    return (not doc.render_timer.isActive() and not doc.fit_timer.isActive()
            and not doc.pages.scroll_timer.isActive() and not doc.pages.batch
            and all(getattr(doc.page_cards.realized.get(page), 'render_scale', None) == doc.pages.scale()
                    for page in doc.pages.targets()))


def test_large_document_only_renders_nearby_pages_and_reuses_cache(qtbot, tmp_path, monkeypatch):
    path = tmp_path / '800-pages.pdf'
    make_document(path, 800)
    window = MainWindow()
    qtbot.addWidget(window)
    window.show()
    batches = []
    request = window.render_service.request
    def record(*args, **kwargs):
        batches.append(list(kwargs['pages']))
        return request(*args, **kwargs)
    monkeypatch.setattr(window.render_service, 'request', record)
    window.load_pdf(path)
    qtbot.waitUntil(lambda: window.current_document().ready, timeout=10000)
    doc = window.current_document()
    qtbot.waitUntil(lambda: settled(doc), timeout=15000)
    assert doc.pages.virtual and len(doc.page_cards) == 800
    assert len(doc.page_cards.realized) < 20
    assert batches and all(1 <= len(batch) <= 2 for batch in batches)
    assert max(page for batch in batches for page in batch) < 20
    doc.page_cards[0].checkbox.click()
    first_requests = sum(0 in batch for batch in batches)
    window._navigate_preview(Qt.Key.Key_End)
    qtbot.waitUntil(lambda: 799 in doc.page_cards.realized and settled(doc), timeout=15000)
    assert not doc.page_cards[799].preview.pixmap().isNull()
    assert 0 not in doc.page_cards.realized
    assert len(doc.page_cards.realized) < 20
    assert not any(100 <= page <= 700 for batch in batches for page in batch)
    window._navigate_preview(Qt.Key.Key_Home)
    qtbot.waitUntil(lambda: 0 in doc.page_cards.realized and settled(doc), timeout=15000)
    assert doc.page_cards[0].checkbox.isChecked()
    assert sum(0 in batch for batch in batches) == first_requests
    assert window.preview_cache.bytes <= window.preview_cache.limit
    window._set_manual_zoom(50)
    qtbot.waitUntil(lambda: settled(doc), timeout=15000)
    assert len(doc.page_cards.realized) < 30
    assert sum(len(batch) for batch in batches) < 40
    window.fit_action.trigger()
    qtbot.waitUntil(lambda: settled(doc), timeout=15000)
    assert doc.pages.rect(doc.fit_page_index).height() <= doc.scroll_area.viewport().height()
    window._navigate_preview(Qt.Key.Key_End)
    qtbot.waitUntil(lambda: doc.fit_page_index == 799 and settled(doc), timeout=15000)
    viewport = doc.scroll_area.viewport()
    card = doc.page_cards[799]
    assert card.height() <= viewport.height()
    assert card.preview.mapTo(card, card.preview.rect().bottomLeft()).y() < card.height()
    boxes = [(0.1, 0.1, 0.2, 0.2)]
    doc.pages.set_highlights(400, boxes, boxes)
    doc.jump_to_search_result(400, boxes[0])
    qtbot.waitUntil(lambda: 400 in doc.page_cards.realized and settled(doc), timeout=15000)
    assert doc.page_cards[400].preview._active_search_rects == boxes


def test_virtual_drag_uses_global_order_and_preserves_selection(qtbot, tmp_path, monkeypatch):
    from PySide6.QtCore import QMimeData, QPointF
    from repdf.app import DocumentView
    from repdf.widgets import PageCard
    monkeypatch.setattr(DocumentView, '_queue_all_renders', lambda self: None)
    window = MainWindow()
    qtbot.addWidget(window)
    window.show()
    doc = window._new_document(tmp_path / 'virtual.pdf')
    doc.loaded(100)
    doc.selected_pages.add(99)
    window._navigate_preview(Qt.Key.Key_End)
    qtbot.waitUntil(lambda: 99 in doc.page_cards.realized and len(doc.page_cards.realized) >= 2)
    host = doc.grid_host
    source = doc.page_cards[99]
    host.begin_drag(source)
    destination = host._slots[0]
    expected = host._insertion_offset
    mime = QMimeData()
    mime.setData(PageCard.DRAG_MIME_TYPE, b'99')
    class Drop:
        def source(self):
            return source
        def mimeData(self):
            return mime
        def position(self):
            return QPointF(destination.left(), destination.center().y())
        def acceptProposedAction(self):
            pass
    host.dropEvent(Drop())
    host.finish_drag()
    assert doc.page_order[expected] == 99
    assert doc.selected_pages == {99}
    assert len(doc.page_cards.realized) < 20


def test_preview_cache_is_shared_bounded_and_released():
    image = QImage(64, 64, QImage.Format.Format_RGB32)
    cache = PreviewCache(limit=image.sizeInBytes() * 2)
    cache.put((1, 0, 1), image)
    cache.put((2, 0, 1), image)
    assert cache.get((1, 0, 1)) is image
    cache.put((1, 1, 1), image)
    assert cache.get((2, 0, 1)) is None
    assert cache.bytes == cache.limit
    cache.remove_document(1)
    assert not cache.items and cache.bytes == 0


def test_small_render_batches_reuse_one_pdf_handle(tmp_path, monkeypatch):
    from repdf import render_worker
    path = tmp_path / 'two.pdf'
    make_document(path, 2)
    constructor = render_worker.pdfium.PdfDocument
    opened = []
    def open_pdf(*args, **kwargs):
        opened.append(args[0])
        return constructor(*args, **kwargs)
    monkeypatch.setattr(render_worker.pdfium, 'PdfDocument', open_pdf)
    requests = [dict(source=str(path), scale=1, output_dir=str(tmp_path), generation=i + 1,
                     pages=[i]) for i in range(2)]
    output = io.StringIO()
    render_worker.serve(io.StringIO('\n'.join(json.dumps(r) for r in requests)), output)
    messages = [json.loads(line) for line in output.getvalue().splitlines()]
    assert len(opened) == 1
    assert [m['page'] for m in messages if m['type'] == 'page'] == [0, 1]
    assert not any(m['type'] == 'error' for m in messages)


def test_quick_inspection_does_not_flatten_all_pages(tmp_path, monkeypatch):
    from pypdf import PdfReader
    path = tmp_path / 'many.pdf'
    make_document(path, 800)
    def fail(*args, **kwargs):
        raise AssertionError('All pages were traversed')
    monkeypatch.setattr(PdfReader, '_flatten', fail)
    assert inspect_pdf(path, quick=True).page_count == 800
