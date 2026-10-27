from math import ceil

import pytest
from PIL import Image, ImageChops
from pypdf import PdfReader, PdfWriter
from PySide6.QtWidgets import QFileDialog, QMessageBox

from repdf.png_export import png_output_paths, publish_png_pages, render_png_pages
from repdf.render_worker import PdfDocumentCache
from test_navigation import load_window, navigation_pdf
from test_printing import colored_pdf


def render(source, destination, stage, pages, **kwargs):
    stage.mkdir(exist_ok=True)
    messages = []
    render_png_pages({'destination': str(destination), 'staging_dir': str(stage),
        'generation': 1, 'documents': [{'source': str(source), 'pages': pages,
            'password': kwargs.pop('password', None),
            'annotation_changes': kwargs.pop('annotation_changes', ())}], **kwargs},
        PdfDocumentCache(), messages.append)
    return messages


@pytest.mark.parametrize('password', [None, 'secret'])
def test_png_pages_keep_order_dimensions_and_password(tmp_path, password):
    source, destination, stage = tmp_path / 'source.pdf', tmp_path / 'out.png', tmp_path / 'stage'
    colored_pdf(source, password)
    messages = render(source, destination, stage, [2, 1], password=password)
    outputs = png_output_paths(destination, 2)
    assert not any(p.exists() for p in outputs)
    publish_png_pages(stage, outputs)
    for path, size, color in zip(outputs, [(200, 300), (300, 200)], [(0, 255, 0), (0, 0, 255)]):
        with Image.open(path) as image:
            assert image.size == tuple(ceil(v * 300 / 72) for v in size)
            assert image.getpixel((100, 100)) == color
            assert image.info['dpi'][0] == pytest.approx(300, abs=.1)
    assert [m['count'] for m in messages] == [1, 2]
    assert outputs[0].name == 'out_01.png'


def test_png_rotation_crop_and_unsaved_annotation(qapp, tmp_path):
    from repdf.annotation_editor import DEFAULT_MARK
    from repdf.annotation_graphics import appearance

    source, destination, stage = tmp_path / 'source.pdf', tmp_path / 'out.png', tmp_path / 'stage'
    navigation_pdf(source, rotation=90, crop=True)
    source_bytes = source.read_bytes()
    render(source, destination, stage, [0])
    with Image.open(stage / 'out.png') as image:
        original = image.copy()
    assert original.size == (1500, 1084)  # Cropped 360 x 260 points, rotated.
    model = {**DEFAULT_MARK, 'id': 'repdf-test', 'page': 0, 'kind': 'underline',
        'geometry': {'box': [20, 20, 280, 380], 'rotation': 90},
        'quads': [[40, 300, 160, 300, 40, 280, 160, 280]], 'text': 'annotation'}
    model['appearance_pdf'] = appearance(model)
    render(source, destination, stage, [0], annotation_changes=[model])
    with Image.open(stage / 'out.png') as image:
        assert ImageChops.difference(original, image.convert('RGB')).getbbox()
    assert source.read_bytes() == source_bytes


def test_png_failure_and_existing_targets_are_safe(tmp_path):
    source, destination, stage = tmp_path / 'source.pdf', tmp_path / 'out.png', tmp_path / 'stage'
    colored_pdf(source)
    destination.write_bytes(b'original')
    with pytest.raises(FileExistsError):
        render(source, destination, stage, [0])
    assert destination.read_bytes() == b'original'
    with pytest.raises(IndexError):
        render(source, destination, stage, [0, 99], overwrite=True)
    assert destination.read_bytes() == b'original'
    render(source, destination, stage, [0], overwrite=True)
    with pytest.raises(OSError):
        publish_png_pages(stage, [destination])
    assert destination.read_bytes() == b'original'
    publish_png_pages(stage, [destination], overwrite=True)
    with Image.open(destination) as image:
        assert image.getpixel((50, 50)) == (255, 0, 0)


def test_png_protects_open_source_and_caps_large_pages(tmp_path):
    source, destination, stage = tmp_path / 'source.pdf', tmp_path / 'out.png', tmp_path / 'stage'
    writer = PdfWriter()
    writer.add_blank_page(3000, 3000)
    writer.write(source)
    with pytest.raises(ValueError):
        render(source, destination, stage, [0], protected_sources=[str(destination)])
    render(source, destination, stage, [0])
    with Image.open(stage / 'out.png') as image:
        assert image.width * image.height <= 30_000_000
        assert image.info['dpi'][0] < 300


@pytest.mark.parametrize('split', [False, True])
def test_current_page_pdf_and_png_dialog(qtbot, monkeypatch, tmp_path, split):
    source = tmp_path / 'source.pdf'
    colored_pdf(source)
    window, doc = load_window(qtbot, source)
    monkeypatch.setattr(QMessageBox, 'information', lambda *a: None)
    errors = []
    monkeypatch.setattr(QMessageBox, 'critical', lambda *a: errors.append(a[-1]))
    doc.jump_to_page(1)
    qtbot.waitUntil(lambda: doc.preview_page_index() == 1)
    assert window.output_selection() == []
    assert window.output_selection(fallback_current=True)[0].pages == (1,)
    output = tmp_path / 'current.pdf'
    def choose_pdf(*args):
        assert '*.pdf' in args[3]
        assert ('*.png' in args[3]) == split
        return str(output), 'PDF (*.pdf)'
    monkeypatch.setattr(QFileDialog, 'getSaveFileName', choose_pdf)
    choose = window.choose_split_output if split else window.choose_output
    choose()
    qtbot.waitUntil(lambda: not window._export_running, timeout=15000)
    assert not errors
    reader = PdfReader(tmp_path / 'current_01.pdf' if split else output)
    assert len(reader.pages) == 1
    assert reader.pages[0].mediabox.width == 300
    if not split:
        return
    image_output = tmp_path / 'current.png'
    monkeypatch.setattr(QFileDialog, 'getSaveFileName', lambda *a: (str(image_output), 'PNG (*.png)'))
    choose()
    qtbot.waitUntil(lambda: not window._export_running, timeout=20000)
    assert not errors
    with Image.open(image_output) as image:
        assert image.getpixel((50, 50)) == (0, 0, 255)


def test_png_controller_cancel_and_checked_page_order(qtbot, monkeypatch, tmp_path):
    source, destination = tmp_path / 'source.pdf', tmp_path / 'out.png'
    colored_pdf(source)
    window, doc = load_window(qtbot, source)
    monkeypatch.setattr(QMessageBox, 'information', lambda *a: None)
    doc.page_order = [2, 0, 1]
    doc.selected_pages = {0, 2}
    window._start_export(destination, image=True)
    window.png_export.cancel()
    assert not window._export_running
    assert not list(tmp_path.glob('out*.png'))
    assert not list(tmp_path.glob('.repdf-png-*'))
    errors = []
    monkeypatch.setattr(QMessageBox, 'critical', lambda *a: errors.append(a[-1]))
    monkeypatch.setattr(QFileDialog, 'getSaveFileName', lambda *a: (str(destination), 'PNG (*.png)'))
    window.choose_split_output()
    qtbot.waitUntil(lambda: not window._export_running, timeout=20000)
    assert not errors
    for output, color in zip(png_output_paths(destination, 2), [(0, 255, 0), (255, 0, 0)]):
        with Image.open(output) as image:
            assert image.getpixel((50, 50)) == color
    assert not list(tmp_path.glob('.repdf-png-*'))


def test_fullscreen_current_page_and_png_error_cleanup(qtbot, monkeypatch, tmp_path):
    source, destination = tmp_path / 'source.pdf', tmp_path / 'out.png'
    colored_pdf(source)
    window, doc = load_window(qtbot, source)
    doc.jump_to_page(1)
    qtbot.waitUntil(lambda: doc.preview_page_index() == 1)
    window._show_fullscreen_preview()
    viewer = window._fullscreen_preview
    qtbot.waitUntil(viewer.isVisible)
    assert window.output_selection(fallback_current=True)[0].pages == (viewer.page_index,)
    viewer.close()
    errors = []
    monkeypatch.setattr(QMessageBox, 'critical', lambda *a: errors.append(a[-1]))
    destination.write_bytes(b'keep me')
    window._start_export(destination, image=True)
    qtbot.waitUntil(lambda: not window._export_running, timeout=15000)
    assert errors
    assert destination.read_bytes() == b'keep me'
    assert window.png_export.service is None
    assert not list(tmp_path.glob('.repdf-png-*'))
