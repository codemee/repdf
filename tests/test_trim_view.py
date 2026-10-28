"""Optional TrimBox viewing follows per-page metadata without editing PDFs."""

from pypdf import PdfWriter
import pytest
from contextlib import closing
import pypdfium2 as pdfium
from repdf.trim_view import viewing_box
from pypdf.generic import DecodedStreamObject, NameObject

from test_navigation import load_window
from test_page_view import settled


@pytest.mark.parametrize('rotation', [0, 90, 180, 270])
@pytest.mark.parametrize('marks', ['complete', 'incomplete', 'rectangle', 'trimbox'])
def test_vector_crop_marks_require_all_eight_strokes(qtbot, tmp_path, rotation, marks):
    source = tmp_path / 'marks.pdf'
    writer = PdfWriter()
    page = writer.add_blank_page(300, 400)
    lines = [f'{x0} {y0} m {x1} {y1} l' for x0, y0, x1, y1 in
             [(0,40,30,40),(270,40,300,40),(0,360,30,360),(270,360,300,360),
              (40,0,40,30),(260,0,260,30),(40,370,40,400),(260,370,260,400)]]
    if marks == 'incomplete':
        lines.pop()
    content = '0 G 0.5 w ' + ' '.join(lines) + ' S'
    if marks == 'rectangle':
        content = '0 G 0.5 w 40 40 220 320 re S'
    if marks == 'trimbox':
        page.trimbox.lower_left = (50,50)
        page.trimbox.upper_right = (250,350)
    stream = DecodedStreamObject()
    stream.set_data(content.encode())
    page[NameObject('/Contents')] = writer._add_object(stream)
    page.rotate(rotation)
    writer.write(source)
    with closing(pdfium.PdfDocument(str(source))) as document, closing(document[0]) as parsed:
        result = viewing_box(parsed)
        if marks in ('incomplete', 'rectangle'):
            assert result is None
        else:
            assert result == pytest.approx((50,50,250,350) if marks == 'trimbox' else (40,40,260,360))
    if marks == 'complete' and rotation == 0:
        window, doc = load_window(qtbot, source)
        assert window.trim_view_action.isEnabled()
        window.trim_view_action.trigger()
        assert doc.page_cards[0].preview._trim_mask is not None


def test_trimbox_tool_only_available_when_page_has_trim(qtbot, tmp_path):
    path = tmp_path / 'trim.pdf'
    writer = PdfWriter()
    trimmed = writer.add_blank_page(300, 400)
    trimmed.trimbox.lower_left = (40, 40)
    trimmed.trimbox.upper_right = (260, 360)
    stream = DecodedStreamObject()
    stream.set_data(b'0 0 0 rg 0 0 300 400 re f')
    trimmed[NameObject('/Contents')] = writer._add_object(stream)
    writer.add_blank_page(300, 400)
    writer.write(path)
    window, doc = load_window(qtbot, path)
    assert 0 in doc.trim_boxes
    assert window.trim_view_action.isEnabled()
    doc.fit_page()
    normal_zoom = doc.zoom
    window.trim_view_action.trigger()
    qtbot.waitUntil(lambda: settled(doc), timeout=15000)
    assert doc.trim_view and doc.fit_mode
    assert doc.zoom > normal_zoom
    assert doc.trim_boxes[0][0] > 0
    label = doc.page_cards[0].preview
    assert label._trim_mask == doc.trim_boxes[0]
    image = label.grab().toImage()
    assert image.pixelColor(2, 2).red() > 245
    assert image.pixelColor(label.width() // 2, label.height() // 2).red() < 30
    window.trim_view_action.trigger()
    assert not doc.trim_view
    assert label._trim_mask is None
    assert label.grab().toImage().pixelColor(2, 2).red() < 30
    window.trim_view_action.trigger()
    window.fullscreen_action.trigger()
    viewer = window._fullscreen_preview
    assert viewer is not None
    qtbot.waitUntil(lambda: not viewer.image.isNull(), timeout=15000)
    assert window.trim_view_action in viewer.floating_tools.buttons
    assert viewer.labels[0].x() < 0 and viewer.labels[0].y() < 0
    assert viewer._page_sizes()[0] == pytest.approx((220, 320))
    window.trim_view_action.trigger()
    assert not doc.trim_view
    assert viewer.labels[0].parentWidget() is viewer
    window.trim_view_action.trigger()
    for mode in ('spread', 'cover', 'single'):
        viewer.set_mode(mode)
        assert viewer.labels[0].x() < 0
        assert viewer.page_frames[0].width() < viewer.labels[0].width()
    viewer.close()
    qtbot.waitUntil(lambda: window._fullscreen_preview is None)
    doc.jump_to_page(1)
    qtbot.waitUntil(lambda: doc.preview_page_index() == 1 and settled(doc), timeout=15000)
    assert not window.trim_view_action.isEnabled()
    assert doc.trim_view
    assert path.exists()
