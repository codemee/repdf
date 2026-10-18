import io
import json
from pathlib import Path

import pytest
from PIL import Image
from pypdf import PdfWriter
from pypdf.generic import (
    ArrayObject, DecodedStreamObject, DictionaryObject, FloatObject,
    NameObject, NumberObject,
)

from repdf.images import extract_clicked_image


def image_pdf(path, *, rotation=0, crop=False, form=False, alpha=False, matrix="100 0 0 80 40 60", overlap=False):
    writer = PdfWriter()
    page = writer.add_blank_page(240, 240)
    stream = DecodedStreamObject()
    stream.update({NameObject('/Type'): NameObject('/XObject'), NameObject('/Subtype'): NameObject('/Image'),
                   NameObject('/Width'): NumberObject(4), NameObject('/Height'): NumberObject(2),
                   NameObject('/BitsPerComponent'): NumberObject(8), NameObject('/ColorSpace'): NameObject('/DeviceRGB')})
    pixels = bytes([255, 0, 0] * 4 + [0, 0, 255] * 4)
    stream.set_data(pixels)
    if alpha:
        mask = DecodedStreamObject()
        mask.update({NameObject('/Type'): NameObject('/XObject'), NameObject('/Subtype'): NameObject('/Image'),
                     NameObject('/Width'): NumberObject(4), NameObject('/Height'): NumberObject(2),
                     NameObject('/BitsPerComponent'): NumberObject(8), NameObject('/ColorSpace'): NameObject('/DeviceGray')})
        mask.set_data(bytes([0, 255, 255, 255] * 2))
        stream[NameObject('/SMask')] = writer._add_object(mask)
    resources = DictionaryObject({NameObject('/XObject'): DictionaryObject({NameObject('/Im'): writer._add_object(stream)})})
    content = f'q {matrix} cm /Im Do Q'.encode()
    if overlap:
        other = DecodedStreamObject()
        other.update(stream)
        other.set_data(bytes([0, 255, 0] * 8))
        resources['/XObject'][NameObject('/Top')] = writer._add_object(other)
        content += b' q 50 0 0 40 60 80 cm /Top Do Q'
    if form:
        container = DecodedStreamObject()
        container.update({NameObject('/Type'): NameObject('/XObject'), NameObject('/Subtype'): NameObject('/Form'),
                          NameObject('/BBox'): ArrayObject([NumberObject(0), NumberObject(0), NumberObject(240), NumberObject(240)]),
                          NameObject('/Matrix'): ArrayObject([FloatObject(v) for v in (0.5, 0, 0, 0.5, 80, 40)]),
                          NameObject('/Resources'): resources})
        container.set_data(content)
        resources = DictionaryObject({NameObject('/XObject'): DictionaryObject({NameObject('/Fm'): writer._add_object(container)})})
        content = b'/Fm Do'
    contents = DecodedStreamObject()
    contents.set_data(content)
    page[NameObject('/Resources')] = resources
    page[NameObject('/Contents')] = writer._add_object(contents)
    if rotation:
        page.rotate(rotation)
    if crop:
        page.cropbox.lower_left = (20, 20)
        page.cropbox.upper_right = (220, 220)
    writer.write(path)


@pytest.mark.parametrize('rotation,point', [(0, (90/240, 140/240)), (90, (100/240, 90/240)),
                                           (180, (150/240, 100/240)), (270, (140/240, 150/240))])
def test_extract_native_pixels_with_page_rotation(tmp_path, rotation, point):
    source, output = tmp_path / 'source.pdf', tmp_path / 'image.png'
    image_pdf(source, rotation=rotation)
    before = source.read_bytes()
    result = extract_clicked_image(source, 0, point, output)
    assert (result['width'], result['height']) == (4, 2)
    with Image.open(output) as image:
        assert image.size == (4, 2)
        assert image.getpixel((1, 0))[:3] == (255, 0, 0)
        assert image.getpixel((1, 1))[:3] == (0, 0, 255)
    assert source.read_bytes() == before


@pytest.mark.parametrize('options,point', [({'crop': True}, (70/200, 120/200)),
                                         ({'form': True}, (125/240, 150/240)),
                                         ({'matrix': '80 40 -40 80 100 40'}, (120/240, 140/240))])
def test_hit_test_crop_nested_form_and_image_transform(tmp_path, options, point):
    source, output = tmp_path / 'source.pdf', tmp_path / 'image.png'
    image_pdf(source, **options)
    assert extract_clicked_image(source, 0, point, output) is not None
    # Outside the embedded image (including its rotated bounding rectangle).
    assert extract_clicked_image(source, 0, (0.05, 0.05), tmp_path / 'none.png') is None
    assert not (tmp_path / 'none.png').exists()
    if 'matrix' in options:
        assert extract_clicked_image(source, 0, (70/240, 190/240), tmp_path / 'corner.png') is None


def test_extract_applies_soft_mask_and_chooses_last_painted_image(tmp_path):
    source, output = tmp_path / 'source.pdf', tmp_path / 'image.png'
    image_pdf(source, alpha=True)
    extract_clicked_image(source, 0, (90/240, 140/240), output)
    with Image.open(output) as image:
        assert image.mode == 'RGBA'
        assert image.getpixel((0, 0))[3] == 0
        assert image.getpixel((1, 0)) == (255, 0, 0, 255)
    image_pdf(source, overlap=True)
    extract_clicked_image(source, 0, (90/240, 140/240), output)
    with Image.open(output) as image:
        assert image.getpixel((1, 0))[:3] == (0, 255, 0)


def test_image_worker_protocol_and_no_hit(tmp_path):
    from repdf.render_worker import serve

    source = tmp_path / 'source.pdf'
    image_pdf(source)
    requests = [{'type': 'extract_image', 'source': str(source), 'page': 0,
                 'point': point, 'output_dir': str(tmp_path), 'generation': generation}
                for generation, point in ((1, (90/240, 140/240)), (2, (0.05, 0.05)))]
    output = io.StringIO()
    serve(io.StringIO('\n'.join(json.dumps(request) for request in requests)), output)
    messages = [json.loads(line) for line in output.getvalue().splitlines()]
    assert [message['type'] for message in messages] == ['ready', 'image', 'done', 'image', 'done']
    assert Path(messages[1]['image']['path']).is_file()
    assert messages[3]['image'] is None


@pytest.mark.parametrize('password', [None, 'image-secret'])
def test_click_image_saves_native_png_and_supports_fullscreen(qtbot, monkeypatch, tmp_path, password):
    from PySide6.QtCore import QPoint, Qt
    from PySide6.QtGui import QImage
    from PySide6.QtWidgets import QFileDialog
    from repdf.app import DocumentView, MainWindow

    source, output = tmp_path / 'source.pdf', tmp_path / 'saved.png'
    image_pdf(source, alpha=True)
    if password:
        writer = PdfWriter(clone_from=source)
        writer.encrypt(password, algorithm='AES-256')
        source = tmp_path / 'locked-image.pdf'
        writer.write(source)
    original = source.read_bytes()
    monkeypatch.setattr(DocumentView, '_queue_all_renders', lambda self: None)
    window = MainWindow()
    qtbot.addWidget(window)
    assert not window.extract_image_action.isEnabled()
    doc = window._new_document(source)
    doc.password = password
    doc.loaded(1)
    doc.page_sizes[0] = (240, 240)
    image = QImage(240, 240, QImage.Format.Format_RGB32)
    image.fill(Qt.GlobalColor.white)
    doc.page_cards[0].set_image(image)
    window._sync_controls()
    window.show()
    qtbot.waitExposed(window)
    assert window.extract_image_action.isEnabled()
    window.copy_text_action.setChecked(True)
    window.extract_image_action.setChecked(True)
    assert not window.copy_text_action.isChecked()
    assert not window.region_ocr_action.isChecked()
    label = doc.page_cards[0].preview
    assert label.image_mode
    parents = []

    def save_dialog(parent, *_args):
        parents.append(parent)
        return str(output), ''

    monkeypatch.setattr(QFileDialog, 'getSaveFileName', save_dialog)
    from PySide6.QtWidgets import QApplication
    QApplication.clipboard().setText('keep clipboard')
    qtbot.mouseClick(label, Qt.MouseButton.LeftButton, pos=QPoint(10, 10))
    qtbot.waitUntil(lambda: '此位置沒有' in window.statusBar().currentMessage(), timeout=5000)
    assert parents == []
    assert QApplication.clipboard().text() == 'keep clipboard'
    qtbot.mouseClick(label, Qt.MouseButton.LeftButton, pos=QPoint(90, 140))
    qtbot.waitUntil(output.exists, timeout=5000)
    with Image.open(output) as saved:
        assert saved.size == (4, 2)
        assert saved.getpixel((0, 0))[3] == 0
    assert parents == [window]
    output = tmp_path / 'fullscreen.png'
    window._show_fullscreen_preview()
    viewer = window._fullscreen_preview
    qtbot.waitExposed(viewer)
    label = viewer.label
    assert label.image_mode
    qtbot.mouseClick(label, Qt.MouseButton.LeftButton,
                    pos=QPoint(round(label.width() * 90/240), round(label.height() * 140/240)))
    qtbot.waitUntil(output.exists, timeout=5000)
    assert parents[-1] is viewer
    with Image.open(output) as saved:
        assert saved.size == (4, 2)
    viewer.close()
    window.region_ocr_action.setChecked(True)
    assert not window.extract_image_action.isChecked()
    assert not doc.page_cards[0].preview.image_mode
    assert source.read_bytes() == original


def test_late_image_result_is_discarded_after_mode_change_or_tab_close(qtbot, monkeypatch, tmp_path):
    from PySide6.QtCore import QPoint, Qt
    from PySide6.QtGui import QImage
    from PySide6.QtWidgets import QFileDialog
    from repdf.app import DocumentView, MainWindow

    monkeypatch.setattr(DocumentView, '_queue_all_renders', lambda self: None)
    window = MainWindow()
    qtbot.addWidget(window)
    doc = window._new_document(tmp_path / 'source.pdf')
    doc.loaded(1)
    image = QImage(240, 240, QImage.Format.Format_RGB32)
    image.fill(Qt.GlobalColor.white)
    doc.page_cards[0].set_image(image)
    doc.page_sizes[0] = (240, 240)
    window._sync_controls()
    window.show()
    monkeypatch.setattr(window.render_service, 'request_image', lambda *_args, **_kwargs: None)
    dialogs = []
    monkeypatch.setattr(QFileDialog, 'getSaveFileName', lambda *_args: (dialogs.append(True), ''))
    for close in (False, True):
        window.extract_image_action.setChecked(True)
        label = doc.page_cards[0].preview
        window._copy_text_selection(doc, 0, label, QPoint(90, 140), QPoint(90, 140))
        generation = window._next_generation
        path = Path(window.preview_temp.name) / f'g{generation}-image.png'
        image.save(str(path))
        if close:
            window.close_tab(0)
        else:
            window.copy_text_action.setChecked(True)
        window._handle_render_message({'type': 'image', 'generation': generation,
                                      'image': {'path': str(path), 'width': 240, 'height': 240}})
        assert not path.exists()
    assert dialogs == []
