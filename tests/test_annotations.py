import io
import json
from contextlib import closing

import pytest
import pypdfium2 as pdfium
from pypdf import PdfWriter
from pypdf.annotations import FreeText, Highlight, Link, Popup, Rectangle, Text
from pypdf.generic import ArrayObject, DecodedStreamObject, DictionaryObject, FloatObject, NameObject, TextStringObject
from PySide6.QtCore import QPoint, Qt
from PySide6.QtWidgets import QApplication

from repdf.pdf_annotations import read_annotations
from repdf.pdf_navigation import resolve_destination
from repdf.render_worker import serve
from test_navigation import load_window
from test_page_view import settled


def annotations_pdf(path, *, rotation=0, crop=False, password=None):
    writer = PdfWriter()
    for _ in range(3):
        writer.add_blank_page(300, 400)
    font = writer._add_object(DictionaryObject({NameObject('/Type'): NameObject('/Font'),
        NameObject('/Subtype'): NameObject('/Type1'), NameObject('/BaseFont'): NameObject('/Helvetica')}))
    page = writer.pages[2]
    page[NameObject('/Resources')] = DictionaryObject({NameObject('/Font'): DictionaryObject({NameObject('/F1'): font})})
    stream = DecodedStreamObject()
    stream.set_data(b'BT /F1 14 Tf 40 300 Td (Marked text) Tj ET')
    page[NameObject('/Contents')] = writer._add_object(stream)
    note = Text(rect=(80, 200, 140, 250), text='中文註解 <b>內容</b>')
    note[NameObject('/T')] = TextStringObject('Alice 作者')
    note[NameObject('/Subj')] = TextStringObject('Review')
    note[NameObject('/M')] = TextStringObject('D:20261023090000+08\'00\'')
    writer.add_annotation(0, note)
    writer.add_annotation(0, Popup(rect=(150, 150, 250, 250)))
    writer.add_annotation(0, Link(rect=(20, 20, 80, 40), target_page_index=2))
    writer.add_annotation(1, FreeText(text='Review this', rect=(40, 200, 200, 250)))
    writer.add_annotation(1, Rectangle(rect=(40, 100, 120, 150)))
    quad = ArrayObject([FloatObject(value) for value in (40, 316, 150, 316, 40, 298, 150, 298)])
    writer.add_annotation(2, Highlight(rect=(40, 298, 150, 316), quad_points=quad))
    writer.add_outline_item('Chapter', 0)
    for page in writer.pages:
        if crop:
            page.cropbox.lower_left, page.cropbox.upper_right = (20, 20), (280, 380)
        if rotation:
            page.rotate(rotation)
    if password:
        writer.encrypt(password, algorithm='AES-256')
    writer.write(path)


@pytest.mark.parametrize('rotation', [0, 90, 180, 270])
def test_read_comments_highlight_text_and_rotated_positions(tmp_path, rotation):
    path = tmp_path / 'annotations.pdf'
    annotations_pdf(path, rotation=rotation, crop=True, password='secret')
    with closing(pdfium.PdfDocument(path, password='secret')) as document:
        comments = read_annotations(document)
        assert len(comments) == 4  # Popup containers and links are not comment rows.
        assert [c['page'] for c in comments] == [0, 1, 1, 2]
        assert comments[0]['contents'] == '中文註解 <b>內容</b>'
        assert comments[0]['author'] == 'Alice 作者'
        assert comments[0]['subject'] == 'Review'
        assert comments[2]['kind'] == '矩形' and comments[2]['contents'] == ''
        assert comments[3]['kind'] == '螢光標示' and comments[3]['contents'] == 'Marked text'
        target = resolve_destination(document, comments[0]['destination'])
        expected = {0: [60/260, 130/360, 120/260, 180/360],
                    90: [180/360, 60/260, 230/360, 120/260],
                    180: [140/260, 180/360, 200/260, 230/360],
                    270: [130/360, 140/260, 180/360, 200/260]}
        assert target['annotation_rect'] == pytest.approx(expected[rotation])
        assert target['point'] == pytest.approx(expected[rotation][:2])
        assert read_annotations(document) == comments
        page_comments = read_annotations(document, [1], include_text=False)
        assert len(page_comments) == 2
        assert [(c['page'], c['index'], c['destination']) for c in page_comments] == [
            (c['page'], c['index'], c['destination']) for c in comments if c['page'] == 1]
        assert all(c['contents'] == '' for c in page_comments)


def test_annotation_protocol_supports_empty_and_encrypted_documents(tmp_path):
    empty, locked = tmp_path / 'empty.pdf', tmp_path / 'locked.pdf'
    writer = PdfWriter()
    writer.add_blank_page(300, 400)
    writer.write(empty)
    annotations_pdf(locked, password='secret')
    requests = [{'type': 'annotations', 'source': str(empty), 'generation': 1},
                {'type': 'annotations', 'source': str(locked), 'generation': 2, 'password': 'secret'}]
    output = io.StringIO()
    serve(io.StringIO('\n'.join(json.dumps(r) for r in requests)), output)
    messages = [json.loads(line) for line in output.getvalue().splitlines()]
    assert not any(m['type'] == 'error' for m in messages)
    results = [m for m in messages if m['type'] == 'annotations']
    assert results[0]['annotations'] == []
    assert len(results[1]['annotations']) == 4
    assert 'secret' not in output.getvalue()


@pytest.mark.parametrize('virtual', [False, True])
def test_annotation_sidebar_is_lazy_and_jumps_after_reordering(qtbot, tmp_path, monkeypatch, virtual):
    if virtual:
        monkeypatch.setattr('repdf.page_view.PageViewport.VIRTUAL_THRESHOLD', 0)
    path = tmp_path / 'comments.pdf'
    annotations_pdf(path)
    window, doc = load_window(qtbot, path)
    nav = window.navigation
    clipboard = QApplication.clipboard()
    clipboard.setText('keep until selecting')
    assert doc.annotations is None and nav.annotation_service is None
    window.annotation_action.trigger()
    qtbot.waitUntil(lambda: len(nav.items) == 4, timeout=10000)
    assert nav.kind == 'annotations' and nav.panel.isVisible()
    assert nav.panel.title.text() == '註解'
    assert clipboard.text() == 'keep until selecting'
    assert '共 4' in nav.panel.status.text()
    assert '&lt;b&gt;' in nav.items[0].toolTip(0)
    assert 'Alice 作者' in nav.items[0].toolTip(0)
    assert 'Marked text' in nav.items[3].text(0)
    assert nav.panel.tree.topLevelItemCount() == 3
    assert nav.items[1].parent() is nav.items[2].parent()
    group = nav.items[1].parent()
    assert group.text(0) == '第 2 頁（2 則註解）'
    assert group.childCount() == 2 and not group.isExpanded()
    assert group.data(0, Qt.ItemDataRole.UserRole) == nav.items[1].data(0, Qt.ItemDataRole.UserRole)
    group.setExpanded(True)
    nav._clicked(group)
    qtbot.waitUntil(lambda: doc.focused_page == 1 and settled(doc), timeout=15000)
    first_rect = doc.annotations[1]['destination']['annotation_rect']
    assert doc.pages.annotation_highlights == {1: first_rect}
    assert doc._search_navigation == (1, first_rect[:2] * 2)
    assert clipboard.text() == 'Review this'
    doc._move_page(2, 0)
    nav._clicked(nav.items[3])
    qtbot.waitUntil(lambda: doc.focused_page == 2 and settled(doc), timeout=15000)
    assert window.page_number_input.text() == '3' and doc.page_order[0] == 2
    rect = doc.annotations[3]['destination']['annotation_rect']
    # Supported highlights now use editable annotation handles rather than the
    # read-only navigation overlay.
    selected = window.annotation_editor.current()
    assert selected and selected['kind'] == 'highlight' and selected['page'] == 2
    assert not doc.pages.annotation_highlights
    assert clipboard.text() == 'Marked text'
    assert doc.page_cards[2].preview._annotation_rect is None
    assert window.annotation_editor.current()["id"] == selected["id"]
    if virtual:
        old_card = doc.page_cards.realized.pop(2)
        old_card.hide()
        old_card.deleteLater()
        doc.pages.ensure_page(2)
    doc.pages.prepare_card(doc.page_cards[2])
    assert doc.page_cards[2].preview._annotation_rect is None
    assert window.annotation_editor.current()["id"] == selected["id"]
    window._show_fullscreen_preview()
    viewer = window._fullscreen_preview
    assert viewer.labels[2]._annotation_rect is None
    assert window.annotation_editor.current()["id"] == selected["id"]
    viewer.close()
    # Fullscreen metadata can refresh the tree and replace its Qt items.
    group = nav.items[1].parent()
    nav._clicked(group)
    qtbot.waitUntil(lambda: doc.focused_page == 1 and settled(doc), timeout=15000)
    assert doc.pages.annotation_highlights == {1: first_rect}
    assert doc.page_cards[2].preview._annotation_rect is None
    window.bookmark_action.trigger()
    qtbot.waitUntil(lambda: nav.kind == 'bookmarks' and len(nav.items) == 1)
    assert window.bookmark_action.isChecked() and not window.annotation_action.isChecked()
    window.annotation_action.trigger()
    assert len(nav.items) == 4 and not window.bookmark_action.isChecked()
    assert nav.items[1].parent().isExpanded()
    window.resize(320, 240)
    qtbot.waitUntil(lambda: window.width() == 320)
    nav.open('annotations')
    assert nav.panel.isVisible() and not nav.content.isVisible()
    nav._clicked(nav.items[0])
    qtbot.waitUntil(lambda: doc.focused_page == 0 and not nav.panel.isVisible(), timeout=10000)
    assert nav.content.isVisible()
    assert doc.page_cards[0].preview._annotation_rect is not None
    doc.pages.set_highlights(0, [[0.1, 0.1, 0.2, 0.2]], [])
    assert not doc.pages.annotation_highlights
    assert doc.page_cards[0].preview._annotation_rect is None
    nav.open('annotations')
    window.search_action.trigger()
    assert not nav.panel.isVisible() and window.search_controller.panel.isVisible()
    assert nav.annotation_service is None


def test_annotation_tabs_empty_state_translation_and_stale_response(qtbot, tmp_path):
    comments, empty = tmp_path / 'comments.pdf', tmp_path / 'empty.pdf'
    annotations_pdf(comments)
    writer = PdfWriter()
    writer.add_blank_page(300, 400)
    writer.write(empty)
    window, doc = load_window(qtbot, comments)
    window.annotation_action.trigger()
    nav = window.navigation
    qtbot.waitUntil(lambda: len(nav.items) == 4, timeout=10000)
    nav.panel.tree.setCurrentItem(nav.items[2])
    nav.items[2].parent().setExpanded(True)
    nav.pending_annotation_copy = doc.document_id, 0, doc.annotations[0]['index']
    QApplication.clipboard().setText('keep across tabs')
    window.load_pdf(empty)
    qtbot.waitUntil(lambda: window.current_document().annotations == [], timeout=10000)
    assert nav.items == [] and nav.panel.status.text() == '此 PDF 沒有註解'
    assert nav.pending_annotation_copy is None
    window.tabs.setCurrentWidget(doc)
    assert nav.panel.tree.currentItem() is nav.items[2]
    assert nav.items[2].parent().isExpanded()
    assert QApplication.clipboard().text() == 'keep across tabs'
    window.language_controller.set_mode('en')
    assert nav.panel.title.text() == 'Annotations'
    assert not nav.items[3].icon(0).isNull()
    assert 'Highlight' in nav.items[3].toolTip(0)
    assert nav.items[2].parent().isExpanded()
    doc.annotations = None
    nav.panel.tree.clear()
    nav.items = []
    nav.annotation_groups = {}
    nav.show_document()
    generation = next(g for g, value in nav.requests.items() if value[1] == 'annotations')
    nav.close()
    assert nav.annotation_service is None
    assert not nav.receive({'type': 'annotations', 'generation': generation, 'annotations': []})
    assert doc.annotations is None


def test_click_annotation_on_page_syncs_sidebar_and_preserves_fullscreen(qtbot, tmp_path):
    path = tmp_path / 'click-comments.pdf'
    annotations_pdf(path)
    window, doc = load_window(qtbot, path)
    nav = window.navigation
    clipboard = QApplication.clipboard()
    clipboard.setText('before page click')
    assert doc.annotations is None  # Hit targets require only the rendered page.
    label = doc.page_cards[0].preview
    assert len(label.annotations) == 1  # Popup and link are excluded.

    def center(preview, hit):
        left, top, right, bottom = hit['rect']
        return QPoint(round((left + right) / 2 * preview.width()),
                      round((top + bottom) / 2 * preview.height()))

    point = center(label, label.annotations[0])
    window.copy_text_action.setChecked(True)
    assert label._link_at(point) is None
    window.copy_text_action.setChecked(False)
    qtbot.mouseClick(label, Qt.MouseButton.LeftButton, pos=point)
    qtbot.waitUntil(lambda: len(nav.items) == 4, timeout=10000)
    assert nav.kind == 'annotations' and nav.panel.isVisible()
    assert nav.panel.tree.currentItem() is nav.items[0]
    assert nav.items[0].parent().isExpanded()
    assert doc.pages.annotation_highlights == {0: label.annotations[0]['rect']}
    assert clipboard.text() == '中文註解 <b>內容</b>'
    assert not doc.selected_pages

    # Select a different annotation on a page with several comments in fullscreen.
    window._show_fullscreen_preview()
    viewer = window._fullscreen_preview
    viewer.show_page(1)
    qtbot.waitUntil(lambda: len(viewer.labels[1].annotations) == 2, timeout=10000)
    fullscreen_label = viewer.labels[1]
    hit = fullscreen_label.annotations[1]
    qtbot.mouseClick(fullscreen_label, Qt.MouseButton.LeftButton, pos=center(fullscreen_label, hit))
    assert window._fullscreen_preview is viewer and not viewer.closed
    assert viewer.labels[1]._annotation_rect == hit['rect']
    assert nav.panel.tree.currentItem() is nav.items[2]
    assert nav.items[2].parent().isExpanded()
    assert clipboard.text() == '中文註解 <b>內容</b>'  # Empty shape leaves clipboard unchanged.
    viewer.close()

    # Narrow windows retain the PDF after a page click instead of obscuring it.
    window.resize(320, 240)
    nav.activate(doc, hit['destination'])
    assert nav.content.isVisible() and not nav.panel.isVisible()
    nav.open('annotations')
    assert nav.panel.tree.currentItem() is nav.items[2]


@pytest.mark.parametrize('close_with', ['button', 'toolbar', 'bookmarks', 'search'])
def test_closing_annotations_clears_markers_and_pending_copy(qtbot, tmp_path, close_with):
    path = tmp_path / 'close-comments.pdf'
    annotations_pdf(path)
    window, doc = load_window(qtbot, path)
    nav = window.navigation
    nav.open('annotations')
    qtbot.waitUntil(lambda: len(nav.items) == 4, timeout=10000)
    nav._clicked(nav.items[1])
    qtbot.waitUntil(lambda: doc.focused_page == 1 and settled(doc), timeout=15000)
    assert QApplication.clipboard().text() == 'Review this'
    window._show_fullscreen_preview()
    viewer = window._fullscreen_preview
    assert viewer.labels[1]._annotation_rect is not None
    if close_with == 'button':
        nav.panel.close_button.click()
    elif close_with == 'toolbar':
        window.annotation_action.trigger()
    elif close_with == 'bookmarks':
        window.bookmark_action.trigger()
    else:
        window.search_action.trigger()
    assert not doc.pages.annotation_highlights
    assert all(card.preview._annotation_rect is None for card in doc.page_cards)
    if not viewer.closed:
        assert all(label._annotation_rect is None for label in viewer.labels.values())
        viewer.close()

    clipboard = QApplication.clipboard()
    clipboard.setText('unchanged on reopen')
    nav.open('annotations')
    assert clipboard.text() == 'unchanged on reopen'
    assert not doc.pages.annotation_highlights
    nav._clicked(nav.items[0])
    generation = nav.latest_jump
    nav.close()
    # A late navigation result must not restore the frame or copy text after closing.
    nav.receive({'type': 'navigate', 'generation': generation, 'page': 0,
                 'point': [0.2, 0.3], 'width_points': 300, 'height_points': 400,
                 'annotation_rect': [0.2, 0.3, 0.4, 0.5]})
    assert not doc.pages.annotation_highlights
    assert clipboard.text() == 'unchanged on reopen'



def test_annotation_type_icons_and_selectable_text_details(qtbot, tmp_path):
    from PySide6.QtGui import QTextCursor
    source = tmp_path / 'details.pdf'
    annotations_pdf(source)
    window, doc = load_window(qtbot, source)
    window.annotation_action.trigger()
    nav = window.navigation
    qtbot.waitUntil(lambda: len(nav.items) == 4, timeout=10000)
    for item, annotation in zip(nav.items, doc.annotations):
        assert not item.icon(0).isNull()
        assert ' · ' not in item.text(0)
        assert annotation['kind'] in item.toolTip(0)
    item = nav.items[0]
    nav.panel.tree.setCurrentItem(item)
    text = doc.annotations[0]['contents']
    assert nav.panel.text_panel.isVisible()
    assert nav.panel.annotation_text.isReadOnly()
    assert nav.panel.annotation_text.toPlainText() == text
    cursor = nav.panel.annotation_text.textCursor()
    cursor.setPosition(0)
    cursor.setPosition(min(6, len(text)), QTextCursor.MoveMode.KeepAnchor)
    nav.panel.annotation_text.setTextCursor(cursor)
    qtbot.mouseClick(nav.panel.copy_text_button, Qt.MouseButton.LeftButton)
    assert QApplication.clipboard().text() == text[:6]
    qtbot.mouseClick(nav.panel.select_text_button, Qt.MouseButton.LeftButton)
    qtbot.keyClick(nav.panel.annotation_text, Qt.Key.Key_C, Qt.KeyboardModifier.ControlModifier)
    assert QApplication.clipboard().text() == text
    window.bookmark_action.trigger()
    assert not nav.panel.text_panel.isVisible()


@pytest.mark.parametrize('width', [320, 1000])
def test_copy_on_annotation_row_does_not_select_or_navigate(qtbot, tmp_path, width):
    from repdf.annotation_tree import copy_rect, TEXT_ROLE
    source = tmp_path / 'row-copy.pdf'
    annotations_pdf(source)
    window, doc = load_window(qtbot, source)
    window.resize(width, 700)
    window.annotation_action.trigger()
    nav = window.navigation
    qtbot.waitUntil(lambda: len(nav.items) == 4, timeout=10000)
    tree = nav.panel.tree
    tree.setCurrentItem(nav.items[0])
    target = nav.items[1]
    target.parent().setExpanded(True)
    tree.scrollToItem(target)
    focused = doc.focused_page
    current = tree.currentItem()
    old_text = nav.panel.annotation_text.toPlainText()
    clicks = []
    tree.itemClicked.connect(lambda *args: clicks.append(args))
    QApplication.clipboard().setText('before copy')
    rectangle = tree.visualItemRect(target)
    assert rectangle.height() >= 34
    position = copy_rect(rectangle).center()
    qtbot.mouseMove(tree.viewport(), position)
    assert tree.viewport().cursor().shape() == Qt.CursorShape.PointingHandCursor
    qtbot.mouseClick(tree.viewport(), Qt.MouseButton.LeftButton, pos=position)
    assert QApplication.clipboard().text() == target.data(0, TEXT_ROLE)
    assert tree.currentItem() is current and not clicks
    assert doc.focused_page == focused and not doc.modified
    assert nav.panel.annotation_text.toPlainText() == old_text
    tree.setFocus()
    qtbot.keyClick(tree, Qt.Key.Key_C, Qt.KeyboardModifier.ControlModifier)
    assert QApplication.clipboard().text() == current.data(0, TEXT_ROLE)
