import io
import json
from contextlib import closing

import pytest
import pypdfium2 as pdfium
from pypdf import PdfWriter
from pypdf.annotations import Link
from pypdf.generic import DecodedStreamObject, DictionaryObject, Fit, NameObject
from PySide6.QtCore import QCoreApplication, QEvent, QPoint, QPointF, Qt
from PySide6.QtGui import QMouseEvent

from repdf.app import MainWindow
from repdf.pdf_navigation import read_bookmarks, read_page_links, resolve_destination
from test_page_view import settled


def navigation_pdf(path, *, rotation=0, crop=False, password=None, count=4):
    writer = PdfWriter()
    for _ in range(count):
        writer.add_blank_page(300, 400)
    font = writer._add_object(DictionaryObject({NameObject('/Type'): NameObject('/Font'),
                                               NameObject('/Subtype'): NameObject('/Type1'),
                                               NameObject('/BaseFont'): NameObject('/Helvetica')}))
    for index, page in enumerate(writer.pages):
        page[NameObject('/Resources')] = DictionaryObject({NameObject('/Font'): DictionaryObject({NameObject('/F1'): font})})
        stream = DecodedStreamObject()
        text = (f'BT /F1 16 Tf 30 360 Td (Page {index + 1}) Tj ET\n'
                + ('BT /F1 14 Tf 30 300 Td (Chapter 2 - click to jump) Tj ET\n' if index == 0 else '')
                + 'BT /F1 10 Tf 30 30 Td (Bottom of complete page) Tj ET')
        stream.set_data(text.encode())
        page[NameObject('/Contents')] = writer._add_object(stream)
    parent = writer.add_outline_item('Chapter 1', 0, is_open=True)
    writer.add_outline_item('Section 1.1', 2, parent=parent, fit=Fit.xyz(left=40, top=220))
    writer.add_outline_item('Chapter 2', count - 1)
    writer.add_annotation(0, Link(rect=(30, 280, 200, 320), target_page_index=count - 1,
                                  fit=Fit.xyz(left=40, top=220)))
    writer.add_annotation(0, Link(rect=(30, 220, 200, 250), url='https://example.com/'))
    if rotation:
        writer.pages[0].rotate(rotation)
        writer.pages[count - 1].rotate(rotation)
    if crop:
        for page in writer.pages:
            page.cropbox.lower_left = (20, 20)
            page.cropbox.upper_right = (280, 380)
    if password:
        writer.encrypt(password, algorithm='AES-256')
    writer.write(path)


@pytest.mark.parametrize('rotation', [0, 90, 180, 270])
def test_outline_and_internal_links_resolve_positions(tmp_path, rotation):
    path = tmp_path / 'navigation.pdf'
    navigation_pdf(path, rotation=rotation, crop=True, password='secret')
    with closing(pdfium.PdfDocument(str(path), password='secret')) as document:
        bookmarks = read_bookmarks(document)
        assert [b['title'] for b in bookmarks] == ['Chapter 1', 'Section 1.1', 'Chapter 2']
        assert [b['level'] for b in bookmarks] == [0, 1, 0]
        assert bookmarks[1]['destination']['page'] == 2
        with closing(document[0]) as page:
            links = read_page_links(document, page)
        assert len(links) == 2
        assert links[1]['destination'] == {'url': 'https://example.com/'}
        link = links[0]
        assert link['destination']['page'] == 3
        assert all(0 <= v <= 1 for v in link['rect'])
        result = resolve_destination(document, link['destination'])
        expected = {0: [20 / 260, 160 / 360], 90: [200 / 360, 20 / 260],
                    180: [240 / 260, 200 / 360], 270: [160 / 360, 240 / 260]}
        assert result['point'] == pytest.approx(expected[rotation])


def load_window(qtbot, path):
    window = MainWindow()
    qtbot.addWidget(window)
    window.show()
    window.load_pdf(path)
    qtbot.waitUntil(lambda: window.current_document().ready, timeout=10000)
    doc = window.current_document()
    qtbot.waitUntil(lambda: settled(doc), timeout=15000)
    return window, doc


def test_bookmark_sidebar_switching_narrow_and_reordered_jump(qtbot, tmp_path):
    path = tmp_path / 'navigation.pdf'
    navigation_pdf(path, count=100)
    window, doc = load_window(qtbot, path)
    assert doc.bookmarks is None  # Opening a file does not scan its outline.
    window.bookmark_action.trigger()
    nav = window.navigation
    qtbot.waitUntil(lambda: len(nav.items) == 3)
    assert nav.items[1].parent() is nav.items[0]
    assert nav.panel.isVisible()
    doc._move_page(99, 0)
    nav._clicked(nav.items[2])
    qtbot.waitUntil(lambda: doc.focused_page == 99 and settled(doc), timeout=15000)
    assert doc.page_order[0] == 99
    assert doc.pages.current_page() == 99
    assert window.page_number_input.text() == '100'
    window.resize(320, 240)
    qtbot.waitUntil(lambda: window.width() == 320)
    nav.open()
    assert nav.panel.isVisible() and not nav.content.isVisible()
    nav._clicked(nav.items[1])
    qtbot.waitUntil(lambda: doc.focused_page == 2 and not nav.panel.isVisible(), timeout=10000)
    assert nav.content.isVisible()
    qtbot.waitUntil(lambda: window.page_number_input.text() == '3')
    nav.open()
    window.search_action.trigger()
    assert not nav.panel.isVisible()
    assert window.search_controller.panel.isVisible()


def test_click_page_link_and_fullscreen_preserve_selection_modes(qtbot, tmp_path):
    path = tmp_path / 'links.pdf'
    navigation_pdf(path)
    window, doc = load_window(qtbot, path)
    label = doc.page_cards[0].preview
    assert len(label.links) == 2
    rect = label.links[0]['rect']
    point = QPoint(round((rect[0] + rect[2]) / 2 * label.width()),
                   round((rect[1] + rect[3]) / 2 * label.height()))
    window.copy_text_action.setChecked(True)
    assert label._link_at(point) is None
    window.copy_text_action.setChecked(False)
    qtbot.mouseClick(label, Qt.MouseButton.LeftButton, pos=point)
    qtbot.waitUntil(lambda: doc.focused_page == 3, timeout=10000)
    assert not doc.selected_pages
    doc.focused_page = 0
    doc.scroll_area.ensureWidgetVisible(doc.page_cards[0])
    window._show_fullscreen_preview()
    viewer = window._fullscreen_preview
    qtbot.waitUntil(lambda: bool(viewer.labels[0].links), timeout=10000)
    fullscreen_label = viewer.labels[0]
    rect = fullscreen_label.links[0]['rect']
    point = QPoint(round((rect[0] + rect[2]) / 2 * fullscreen_label.width()),
                   round((rect[1] + rect[3]) / 2 * fullscreen_label.height()))
    qtbot.mouseClick(fullscreen_label, Qt.MouseButton.LeftButton, pos=point)
    qtbot.waitUntil(lambda: viewer.page_index == 3, timeout=10000)
    assert window._fullscreen_preview is viewer
    viewer.close()


def test_navigation_backend_protocol_empty_outline_and_invalid_target(tmp_path):
    from repdf.render_worker import serve
    path = tmp_path / 'empty.pdf'
    writer = PdfWriter()
    writer.add_blank_page(300, 400)
    writer.write(path)
    requests = [dict(type='bookmarks', source=str(path), generation=1),
                dict(type='navigate', source=str(path), generation=2, destination={'page': 99})]
    output = io.StringIO()
    serve(io.StringIO('\n'.join(json.dumps(r) for r in requests)), output)
    messages = [json.loads(line) for line in output.getvalue().splitlines()]
    assert messages[1]['type'] == 'bookmarks' and messages[1]['bookmarks'] == []
    assert messages[-1]['type'] == 'error'


def test_named_destinations_in_outline_and_page_link(tmp_path):
    from pypdf.generic import NameObject, TextStringObject
    path = tmp_path / 'named.pdf'
    writer = PdfWriter()
    for _ in range(2):
        writer.add_blank_page(300, 400)
    writer.add_named_destination('chapter', 1)
    bookmark = writer.add_outline_item('Named chapter', 1).get_object()
    del bookmark['/A']
    bookmark[NameObject('/Dest')] = TextStringObject('chapter')
    annotation = writer.add_annotation(0, Link(rect=(20, 20, 100, 50), target_page_index=1))
    annotation[NameObject('/Dest')] = TextStringObject('chapter')
    writer.write(path)
    with closing(pdfium.PdfDocument(str(path))) as document:
        assert read_bookmarks(document)[0]['destination']['page'] == 1
        with closing(document[0]) as page:
            assert read_page_links(document, page)[0]['destination']['page'] == 1


@pytest.mark.parametrize('url,accepted', [
    ('http://example.com/path?q=1&x=2#section', True),
    ('HTTPS://example.com/', True),
    ('https://example.com/章節', True),
    ('mailto:reader@example.com', False),
    ('file:///C:/temp/test.pdf', False),
    ('javascript:alert(1)', False),
    ('https:///missing-host', False),
    ('https://example.com/\ninvalid', False),
])
def test_only_http_https_annotation_actions_are_read(tmp_path, url, accepted):
    path = tmp_path / 'web-link.pdf'
    writer = PdfWriter()
    writer.add_blank_page(300, 400)
    writer.add_annotation(0, Link(rect=(20, 20, 100, 50), url=url))
    writer.write(path)
    with closing(pdfium.PdfDocument(str(path))) as document, closing(document[0]) as page:
        links = read_page_links(document, page)
    assert bool(links) is accepted
    if accepted:
        assert links[0]['destination'] == {'url': url}


def test_web_links_open_browser_in_preview_and_fullscreen(qtbot, tmp_path, monkeypatch):
    from repdf.navigation import QDesktopServices
    path = tmp_path / 'web-links.pdf'
    navigation_pdf(path)
    window, doc = load_window(qtbot, path)
    opened = []
    monkeypatch.setattr(QDesktopServices, 'openUrl', lambda url: opened.append(url.toString()) or True)
    def click_web(label):
        link = next(link for link in label.links if 'url' in link['destination'])
        left, top, right, bottom = link['rect']
        point = QPoint(round((left + right) / 2 * label.width()),
                       round((top + bottom) / 2 * label.height()))
        QCoreApplication.sendEvent(label, QMouseEvent(
            QEvent.Type.MouseMove, QPointF(point), QPointF(label.mapToGlobal(point)),
            Qt.MouseButton.NoButton, Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier))
        assert 'https://example.com/' in label.toolTip()
        assert label.cursor().shape() == Qt.CursorShape.PointingHandCursor
        qtbot.mouseClick(label, Qt.MouseButton.LeftButton, pos=point)
        return point
    label = doc.page_cards[0].preview
    point = click_web(label)
    assert opened == ['https://example.com/']
    assert doc.focused_page == 0
    window.copy_text_action.setChecked(True)
    qtbot.mouseClick(label, Qt.MouseButton.LeftButton, pos=point)
    assert len(opened) == 1
    window.copy_text_action.setChecked(False)
    window._show_fullscreen_preview()
    viewer = window._fullscreen_preview
    qtbot.waitUntil(lambda: bool(viewer.labels[0].links), timeout=10000)
    qtbot.waitUntil(viewer.isActiveWindow)
    click_web(viewer.labels[0])
    assert opened == ['https://example.com/'] * 2
    assert viewer.page_index == 0
    viewer.close()
    for url in ('file:///C:/temp/test.pdf', 'javascript:alert(1)', 'https:///missing-host'):
        window.navigation.activate(doc, {'url': url})
    assert len(opened) == 2
    monkeypatch.setattr(QDesktopServices, 'openUrl', lambda url: False)
    window.navigation.activate(doc, {'url': 'https://example.com/'})
    assert 'https://example.com/' in window.statusBar().currentMessage()


def test_sidebar_states_empty_document_and_stale_navigation(qtbot, tmp_path, monkeypatch):
    path, empty = tmp_path / 'chapters.pdf', tmp_path / 'empty.pdf'
    navigation_pdf(path)
    writer = PdfWriter()
    writer.add_blank_page(300, 400)
    writer.write(empty)
    window, doc = load_window(qtbot, path)
    nav = window.navigation
    nav.open()
    qtbot.waitUntil(lambda: len(nav.items) == 3)
    nav.panel.tree.setCurrentItem(nav.items[1])
    nav.items[0].setExpanded(False)
    window.load_pdf(empty)
    qtbot.waitUntil(lambda: window.current_document().ready and window.current_document().bookmarks == [], timeout=10000)
    other = window.current_document()
    assert nav.panel.status.isVisible()
    window.tabs.setCurrentWidget(doc)
    assert not nav.items[0].isExpanded()
    assert nav.panel.tree.currentItem() is nav.items[1]
    monkeypatch.setattr(window.render_service, 'request_navigation', lambda *args, **kwargs: None)
    old = nav._request(doc, 'navigate', {'page': 2})
    latest = nav._request(doc, 'navigate', {'page': 3})
    assert old not in nav.requests
    window._handle_render_message({'type': 'navigate', 'generation': old, 'page': 2,
                                  'point': [0, 0], 'width_points': 300, 'height_points': 400})
    assert doc.focused_page is None
    window.close_tab(window.tabs.indexOf(doc))
    window._handle_render_message({'type': 'navigate', 'generation': latest, 'page': 3,
                                  'point': [0, 0], 'width_points': 300, 'height_points': 400})
    assert window.current_document() is other
    assert other.focused_page is None
    assert not nav.requests
