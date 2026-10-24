import io
import json
from copy import deepcopy
from pathlib import Path

import pytest
from pypdf import PdfReader, PdfWriter
from pypdf.generic import (
    ArrayObject,
    DecodedStreamObject,
    DictionaryObject,
    FloatObject,
    NameObject,
    NumberObject,
    TextStringObject,
)
import pypdfium2 as pdfium
from PIL import ImageChops, Image
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QRectF, QPoint, QPointF, Qt

from repdf.annotation_data import read_models
from repdf.annotation_graphics import appearance, transform
from repdf.annotation_editor import DEFAULT_CALLOUT, DEFAULT_MARK
from repdf.core import (
    save_document,
    DocumentSelection,
    export_documents,
    split_documents,
)
from repdf.render_worker import render_document
from test_navigation import load_window
from test_page_view import settled


@pytest.fixture(autouse=True)
def usable_fonts(qapp):
    from PySide6.QtGui import QFontDatabase

    paths = [
        "C:/Windows/Fonts/msjh.ttc",
        "C:/Windows/Fonts/arial.ttf",
        "/System/Library/Fonts/PingFang.ttc",
        "/System/Library/Fonts/Supplemental/Arial.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ]
    ids = [
        QFontDatabase.addApplicationFont(path) for path in paths if Path(path).exists()
    ]
    yield
    for identifier in ids:
        if identifier >= 0:
            QFontDatabase.removeApplicationFont(identifier)


def source_pdf(path):
    w = PdfWriter()
    p = w.add_blank_page(400, 500)
    font = w._add_object(
        DictionaryObject(
            {
                NameObject("/Type"): NameObject("/Font"),
                NameObject("/Subtype"): NameObject("/Type1"),
                NameObject("/BaseFont"): NameObject("/Helvetica"),
            }
        )
    )
    p[NameObject("/Resources")] = DictionaryObject(
        {NameObject("/Font"): DictionaryObject({NameObject("/F1"): font})}
    )
    stream = DecodedStreamObject()
    stream.set_data(b"BT /F1 14 Tf 40 400 Td (hello world) Tj ET")
    p[NameObject("/Contents")] = w._add_object(stream)
    w.write(path)


def models():
    geom = {"box": [0, 0, 400, 500], "rotation": 0}
    result = []
    for i, kind in enumerate(("underline", "strikeout", "squiggly")):
        y = 350 - i * 35
        m = {
            **DEFAULT_MARK,
            "id": "repdf-" + kind,
            "page": 0,
            "geometry": geom,
            "kind": kind,
            "quads": [[40, y, 140, y, 40, y - 14, 140, y - 14]],
            "text": "hello world",
        }
        m["appearance_pdf"] = appearance(m)
        result.append(m)
    m = {
        **DEFAULT_CALLOUT,
        "id": "repdf-callout",
        "page": 0,
        "geometry": geom,
        "rect": [180, 160, 370, 240],
        "leader": [70, 100, 164, 200, 180, 200],
        "font": "Arial",
        "text": "這是註解\nhello world",
    }
    m["appearance_pdf"] = appearance(m)
    result.append(m)
    return result


def test_native_appearances_unicode_roundtrip_and_output_snapshots(qapp, tmp_path):
    source = tmp_path / "source.pdf"
    source_pdf(source)
    changes = models()
    saved = tmp_path / "saved.pdf"
    save_document(source, saved, [0], annotation_changes=changes)
    reader = PdfReader(saved)
    imported, reasons, geometry = read_models(reader, 0)
    assert not reasons and len(imported) == 4
    assert imported[-1]["text"] == "這是註解\nhello world"
    for a in reader.pages[0]["/Annots"]:
        assert a.get_object()["/AP"]["/N"].get_object().get_data()
    assert reader.pages[0]["/Annots"][-1].get_object()["/AP"]["/N"]["/Resources"][
        "/Font"
    ]
    document = pdfium.PdfDocument(saved)
    page = document[0]
    native = page.render(scale=1, draw_annots=True).to_pil().copy()
    plain = page.render(scale=1, draw_annots=False).to_pil().copy()
    assert ImageChops.difference(native, plain).getbbox() is not None
    page.close()
    document.close()
    output = io.StringIO()
    render_document(saved, 1, tmp_path, 20, output, interactive=True)
    payload = json.loads(output.getvalue().splitlines()[0])
    assert len(payload["editable_annotations"]) == 4
    hidden = Image.open(payload["path"]).convert("RGB")
    assert ImageChops.difference(hidden, plain.convert("RGB")).getbbox() is None
    selection = DocumentSelection(source, (0,), None, tuple(changes))
    exported = tmp_path / "export.pdf"
    export_documents([selection], exported)
    split = split_documents([selection], tmp_path / "split.pdf")
    assert len(PdfReader(exported).pages[0]["/Annots"]) == 4
    assert len(PdfReader(split[0]).pages[0]["/Annots"]) == 4
    # Reopened annotations retain editability, and deletion keeps source indices stable.
    update = deepcopy(imported[-1])
    update["text"] = "修改後"
    update["width"] = 3
    update["appearance_pdf"] = appearance(update)
    deleted = {"page": 0, "source_index": imported[0]["source_index"], "deleted": True}
    save_document(saved, saved, [0], annotation_changes=[deleted, update])
    imported, _, _ = read_models(PdfReader(saved), 0)
    assert len(imported) == 3 and imported[-1]["text"] == "修改後"


def test_import_external_standard_annotations_and_readonly_fallback(qapp, tmp_path):
    source = tmp_path / "external.pdf"
    source_pdf(source)
    w = PdfWriter(clone_from=source)
    p = w.pages[0]
    a = DictionaryObject(
        {
            NameObject("/Type"): NameObject("/Annot"),
            NameObject("/Subtype"): NameObject("/FreeText"),
            NameObject("/Rect"): ArrayObject(
                [FloatObject(v) for v in (80, 80, 300, 180)]
            ),
            NameObject("/RD"): ArrayObject([FloatObject(v) for v in (100, 20, 0, 0)]),
            NameObject("/CL"): ArrayObject(
                [FloatObject(v) for v in (80, 80, 164, 130, 180, 130)]
            ),
            NameObject("/IT"): NameObject("/FreeTextCallout"),
            NameObject("/LE"): NameObject("/OpenArrow"),
            NameObject("/Contents"): TextStringObject("External callout"),
            NameObject("/DA"): TextStringObject("/Helv 12 Tf 0 0 1 rg"),
        }
    )
    p[NameObject("/Annots")] = ArrayObject([w._add_object(a)])
    w.write(source)
    imported, reasons, _ = read_models(PdfReader(source), 0)
    assert (
        len(imported) == 1
        and not reasons
        and imported[0]["rect"] == [180, 100, 300, 180]
    )
    w = PdfWriter(clone_from=source)
    w.pages[0]["/Annots"][0].get_object()[NameObject("/RC")] = TextStringObject(
        "<p>rich</p>"
    )
    w.write(source)
    imported, reasons, _ = read_models(PdfReader(source), 0)
    assert not imported and 0 in reasons


def test_create_edit_move_undo_and_save_callout(qtbot, tmp_path, monkeypatch):
    source = tmp_path / "ui.pdf"
    source_pdf(source)
    window, doc = load_window(qtbot, source)
    editor = window.annotation_editor
    label = doc.page_cards[0].preview

    def point(x, y):
        return QPoint(round(label.width() * x), round(label.height() * y))

    editor.callout_action.trigger()
    qtbot.mouseClick(label, Qt.MouseButton.LeftButton, pos=point(0.2, 0.75))
    assert editor.text_edit is not None
    editor.text_edit.setPlainText("我的註解")
    qtbot.keyClick(
        editor.text_edit, Qt.Key.Key_Return, Qt.KeyboardModifier.ControlModifier
    )
    assert len(doc.annotation_store.items) == 1 and doc.modified
    model = deepcopy(next(iter(doc.annotation_store.items.values())))
    anchor = model["leader"][:2]
    editor.change_style(True, "color", "#00aa00")
    assert editor.current()["color"] == "#00aa00"
    doc.annotation_store.undo.undo()
    assert editor.current()["color"] == "#ff0000"
    doc.annotation_store.undo.redo()
    assert editor.current()["color"] == "#00aa00"
    editor.callout_action.setChecked(False)
    center = (
        transform(model["geometry"], label.width(), label.height())
        .mapRect(
            QRectF(
                model["rect"][0],
                model["rect"][1],
                model["rect"][2] - model["rect"][0],
                model["rect"][3] - model["rect"][1],
            )
        )
        .center()
        .toPoint()
    )
    painted_handles = []
    original_handles = editor.handles

    def capture_handles(model, tx):
        painted_handles.append(deepcopy(model))
        return original_handles(model, tx)

    monkeypatch.setattr(editor, "handles", capture_handles)
    qtbot.mousePress(label, Qt.MouseButton.LeftButton, pos=center)
    qtbot.mouseMove(label, center + QPoint(10, 12))
    assert editor.draft is not None
    painted_handles.clear()
    label.grab()
    assert painted_handles and painted_handles[-1]["rect"] == editor.draft["rect"]
    assert painted_handles[-1]["rect"] != model["rect"]
    qtbot.mouseRelease(label, Qt.MouseButton.LeftButton, pos=center + QPoint(10, 12))
    assert editor.current()["rect"] != model["rect"]
    assert editor.current()["leader"][:2] == anchor
    assert window.save_action.isEnabled()
    window.save_action.trigger()
    qtbot.waitUntil(lambda: window.saving.task is None, timeout=15000)
    current = window.current_document()
    qtbot.waitUntil(lambda: settled(current), timeout=15000)
    assert len(current.annotation_store.items) == 1 and not current.modified
    assert next(iter(current.annotation_store.items.values()))["text"] == "我的註解"
    editor.commit(
        current,
        deepcopy(next(iter(current.annotation_store.items.values()))),
        "Unchanged",
    )
    assert not current.modified


@pytest.mark.parametrize("kind", ["highlight", "underline", "strikeout", "squiggly"])
def test_markup_drag_uses_text_layer_and_undo(qtbot, tmp_path, kind):
    source = tmp_path / "markup.pdf"
    source_pdf(source)
    window, doc = load_window(qtbot, source)
    editor = window.annotation_editor
    label = doc.page_cards[0].preview
    tx = transform(doc.annotation_store.geometries[0], label.width(), label.height())
    a = tx.map(QPointF(42, 405)).toPoint()
    b = tx.map(QPointF(107, 405)).toPoint()
    editor.change_style(False, "kind", kind)
    editor.mark_action.trigger()
    qtbot.mousePress(label, Qt.MouseButton.LeftButton, pos=a)
    qtbot.mouseMove(label, b)
    qtbot.waitUntil(lambda: bool(editor.mark_highlights), timeout=10000)
    assert not doc.annotation_store.items and not doc.modified
    assert editor.mark_highlights[2]
    qtbot.mouseRelease(label, Qt.MouseButton.LeftButton, pos=b)
    qtbot.waitUntil(lambda: bool(doc.annotation_store.items), timeout=10000)
    model = next(iter(doc.annotation_store.items.values()))
    assert model["kind"] == kind and model["quads"] and "hello" in model["text"]
    assert doc.modified
    doc.annotation_store.undo.undo()
    assert not doc.modified
    doc.annotation_store.undo.redo()
    assert doc.modified


# Capture before the autouse fixture suppresses interactive teardown questions.
from repdf.app import MainWindow

CONFIRM_CLOSE = MainWindow._confirm_close


def test_close_with_unsaved_annotations_can_cancel_discard_and_save(
    qtbot, tmp_path, monkeypatch
):
    from PySide6.QtWidgets import QMessageBox

    source = tmp_path / "close.pdf"
    source_pdf(source)
    window, doc = load_window(qtbot, source)
    monkeypatch.setattr(
        window, "_confirm_close", CONFIRM_CLOSE.__get__(window, MainWindow)
    )
    editor = window.annotation_editor
    editor.commit(doc, models()[-1], "New callout")
    original = source.read_bytes()

    def cancel_message(message):
        assert message.testOption(QMessageBox.Option.DontUseNativeDialog)
        assert message.button(QMessageBox.StandardButton.Discard).text() == "不儲存"
        assert message.icon() == QMessageBox.Icon.NoIcon
        assert not message.iconPixmap().isNull()
        assert message.defaultButton() == message.button(
            QMessageBox.StandardButton.Save
        )
        return QMessageBox.StandardButton.Cancel

    monkeypatch.setattr(QMessageBox, "exec", cancel_message)
    window.close_tab(0)
    assert window.tabs.count() == 1 and doc.modified and source.read_bytes() == original
    monkeypatch.setattr(
        QMessageBox, "exec", lambda *a, **k: QMessageBox.StandardButton.Discard
    )
    window.close_tab(0)
    assert window.tabs.count() == 0 and source.read_bytes() == original
    window.load_pdf(source)
    qtbot.waitUntil(lambda: window.current_document().ready, timeout=10000)
    doc = window.current_document()
    qtbot.waitUntil(lambda: settled(doc), timeout=15000)
    editor.commit(doc, models()[-1], "New callout")
    monkeypatch.setattr(
        QMessageBox, "exec", lambda *a, **k: QMessageBox.StandardButton.Save
    )
    window.close_tab(0)
    qtbot.waitUntil(
        lambda: window.tabs.count() == 0 and window.saving.task is None, timeout=15000
    )
    assert len(PdfReader(source).pages[0]["/Annots"]) == 1


@pytest.mark.parametrize("rotation", [0, 90, 180, 270])
def test_annotation_coordinates_round_trip_with_crop(rotation):
    geom = {"box": [20, 30, 380, 480], "rotation": rotation}
    tx = transform(geom, 640, 800)
    inverse, ok = tx.inverted()
    assert ok
    for point in (QPointF(20, 30), QPointF(380, 480), QPointF(100, 200)):
        restored = inverse.map(tx.map(point))
        assert restored.x() == pytest.approx(
            point.x()
        ) and restored.y() == pytest.approx(point.y())


def test_application_icon_uses_consistent_visual_size():
    from repdf.icon_layout import fitted_icon

    image = fitted_icon(Path(__file__).parents[1] / "src/repdf/assets/repdf.png", 256)
    box = image.getchannel("A").point(lambda a: 255 if a >= 32 else 0).getbbox()
    assert 0.88 <= max(box[2] - box[0], box[3] - box[1]) / 256 <= 0.94


@pytest.mark.parametrize("rotation", [0, 90, 180, 270])
def test_new_callout_text_stays_upright_on_rotated_pages(qapp, tmp_path, rotation):
    source = tmp_path / "rotation.pdf"
    source_pdf(source)
    writer = PdfWriter(clone_from=source)
    writer.pages[0].rotate(rotation)
    writer.write(source)
    model = models()[-1]
    model["text"] = "HELLO"
    model["geometry"]["rotation"] = rotation
    model["text_rotation"] = rotation
    model["appearance_pdf"] = appearance(model)
    output = tmp_path / "annotated.pdf"
    save_document(source, output, [0], annotation_changes=[model])
    doc = pdfium.PdfDocument(output)
    page = doc[0]
    bitmap = page.render(scale=2)
    image = bitmap.to_pil().convert("RGB")
    red, green, blue = image.split()
    mask = ImageChops.multiply(
        blue.point(lambda v: 255 if v > 180 else 0),
        red.point(lambda v: 255 if v < 80 else 0),
    )
    mask = ImageChops.multiply(mask, green.point(lambda v: 255 if v < 80 else 0))
    box = mask.getbbox()
    assert box is not None and box[2] - box[0] > 2 * (box[3] - box[1])
    bitmap.close()
    page.close()
    doc.close()


def test_external_callout_with_standard_appearance_and_opacity_fallback(qapp, tmp_path):
    source = tmp_path / "external-appearance.pdf"
    source_pdf(source)
    writer = PdfWriter(clone_from=source)
    font = writer._add_object(
        DictionaryObject(
            {
                NameObject("/Type"): NameObject("/Font"),
                NameObject("/Subtype"): NameObject("/Type1"),
                NameObject("/BaseFont"): NameObject("/Helvetica"),
            }
        )
    )
    state = DictionaryObject(
        {
            NameObject("/Type"): NameObject("/ExtGState"),
            NameObject("/CA"): FloatObject(1),
            NameObject("/ca"): FloatObject(1),
        }
    )
    ap = DecodedStreamObject()
    ap.set_data(
        b"q /GS0 gs 1 0 0 RG 1 w 100 20 120 80 re S /Tx BMC BT /Helv 12 Tf 0 0 1 rg 104 64 Td (External) Tj ET EMC Q"
    )
    ap[NameObject("/Type")] = NameObject("/XObject")
    ap[NameObject("/Subtype")] = NameObject("/Form")
    ap[NameObject("/BBox")] = ArrayObject([NumberObject(v) for v in (0, 0, 220, 100)])
    ap[NameObject("/Resources")] = DictionaryObject(
        {
            NameObject("/Font"): DictionaryObject({NameObject("/Helv"): font}),
            NameObject("/ExtGState"): DictionaryObject({NameObject("/GS0"): state}),
        }
    )
    a = DictionaryObject(
        {
            NameObject("/Subtype"): NameObject("/FreeText"),
            NameObject("/Contents"): TextStringObject("External"),
            NameObject("/Rect"): ArrayObject(
                [NumberObject(v) for v in (80, 80, 300, 180)]
            ),
            NameObject("/RD"): ArrayObject([NumberObject(v) for v in (100, 20, 0, 0)]),
            NameObject("/CL"): ArrayObject(
                [NumberObject(v) for v in (80, 80, 164, 130, 180, 130)]
            ),
            NameObject("/DA"): TextStringObject("/Helv 12 Tf 0 0 1 rg"),
            NameObject("/AP"): DictionaryObject(
                {NameObject("/N"): writer._add_object(ap)}
            ),
        }
    )
    writer.pages[0][NameObject("/Annots")] = ArrayObject([writer._add_object(a)])
    writer.write(source)
    imported, reasons, _ = read_models(PdfReader(source), 0)
    assert len(imported) == 1 and not reasons and imported[0]["color"] == "#ff0000"
    changed = imported[0]
    changed["text"] = "Edited external"
    changed["appearance_pdf"] = appearance(changed)
    save_document(source, tmp_path / "edited.pdf", [0], annotation_changes=[changed])
    reopened, _, _ = read_models(PdfReader(tmp_path / "edited.pdf"), 0)
    assert reopened[0]["text"] == "Edited external"
    state[NameObject("/ca")] = FloatObject(0.5)
    writer.write(source)
    imported, reasons, _ = read_models(PdfReader(source), 0)
    assert not imported and reasons


def test_fullscreen_callout_text_keys_and_arrow_drag(qtbot, tmp_path):
    source = tmp_path / "fullscreen-edit.pdf"
    source_pdf(source)
    window, doc = load_window(qtbot, source)
    editor = window.annotation_editor
    editor.callout_action.trigger()
    window._show_fullscreen_preview()
    viewer = window._fullscreen_preview
    label = viewer.label

    def point(x, y):
        return QPoint(round(label.width() * x), round(label.height() * y))

    qtbot.mouseClick(label, Qt.MouseButton.LeftButton, pos=point(0.2, 0.75))
    assert editor.text_edit is not None
    editor.text_edit.setPlainText("Fullscreen text")
    qtbot.keyClick(editor.text_edit, Qt.Key.Key_Home)
    assert viewer.page_index == 0
    qtbot.keyClick(
        editor.text_edit, Qt.Key.Key_Return, Qt.KeyboardModifier.ControlModifier
    )
    assert (
        viewer is window._fullscreen_preview
        and editor.current()["text"] == "Fullscreen text"
    )
    model = deepcopy(editor.current())
    rect = model["rect"]
    center = (
        transform(model["geometry"], label.width(), label.height())
        .map(QPointF((rect[0] + rect[2]) / 2, (rect[1] + rect[3]) / 2))
        .toPoint()
    )
    qtbot.mouseDClick(label, Qt.MouseButton.LeftButton, pos=center)
    assert editor.text_edit is not None
    editor.text_edit.setPlainText("cancel me")
    qtbot.keyClick(editor.text_edit, Qt.Key.Key_Escape)
    assert (
        viewer is window._fullscreen_preview
        and editor.current()["text"] == "Fullscreen text"
    )
    tx = transform(model["geometry"], label.width(), label.height())
    start = tx.map(QPointF(*model["leader"][:2])).toPoint()
    qtbot.mousePress(label, Qt.MouseButton.LeftButton, pos=start)
    qtbot.mouseMove(label, start + QPoint(18, 8))
    qtbot.mouseRelease(label, Qt.MouseButton.LeftButton, pos=start + QPoint(18, 8))
    assert editor.current()["leader"][:2] != model["leader"][:2]
    qtbot.keyClick(label, Qt.Key.Key_Z, Qt.KeyboardModifier.ControlModifier)
    assert editor.current()["leader"][:2] == model["leader"][:2]
    viewer.close()


def test_save_shortcut_commits_active_text_editor(qtbot, tmp_path):
    source = tmp_path / "draft-save.pdf"
    source_pdf(source)
    window, doc = load_window(qtbot, source)
    editor = window.annotation_editor
    label = doc.page_cards[0].preview
    model = models()[-1]
    model["text"] = ""
    editor.begin_text(label, model)
    assert not window.save_action.isEnabled()
    editor.text_edit.setPlainText("Save active editor")
    qtbot.keyClick(editor.text_edit, Qt.Key.Key_S, Qt.KeyboardModifier.ControlModifier)
    qtbot.waitUntil(
        lambda: window.saving.task is None and window.current_document() is not doc,
        timeout=15000,
    )
    imported, _, _ = read_models(PdfReader(source), 0)
    assert imported[0]["text"] == "Save active editor"
    assert not window.current_document().modified


def test_external_edits_do_not_restore_stale_private_metadata(qapp, tmp_path):
    source = tmp_path / "original.pdf"
    source_pdf(source)
    saved = tmp_path / "saved.pdf"
    save_document(source, saved, [0], annotation_changes=[models()[-1]])
    writer = PdfWriter(clone_from=saved)
    writer.pages[0]["/Annots"][0].get_object()[NameObject("/Contents")] = (
        TextStringObject("Changed externally")
    )
    writer.write(saved)
    imported, reasons, _ = read_models(PdfReader(saved), 0)
    assert not imported and "inconsistent" in reasons[0]
    assert (
        PdfReader(saved).pages[0]["/Annots"][0].get_object()["/Contents"]
        == "Changed externally"
    )


def test_high_precision_geometry_remains_editable_after_serialization(qapp, tmp_path):
    source = tmp_path / "precision.pdf"
    source_pdf(source)
    model = models()[-1]
    model["rect"] = [180.123499999, 160.999500001, 370.123499999, 240.999500001]
    model["appearance_pdf"] = appearance(model)
    output = tmp_path / "saved.pdf"
    save_document(source, output, [0], annotation_changes=[model])
    imported, reasons, _ = read_models(PdfReader(output), 0)
    assert len(imported) == 1 and not reasons


@pytest.mark.parametrize("rotation", [0, 90, 180, 270])
@pytest.mark.parametrize("size", [8, 12, 72])
def test_auto_callout_keeps_target_and_fits_one_line(qapp, rotation, size):
    from types import SimpleNamespace
    from repdf.annotation_editor import AnnotationEditor

    geometry = {"box": [20, 30, 620, 830], "rotation": rotation}
    label = SimpleNamespace(
        annotation_page=0,
        annotation_document=SimpleNamespace(
            annotation_store=SimpleNamespace(geometries={0: geometry})
        ),
    )
    editor = SimpleNamespace(
        callout_style={**DEFAULT_CALLOUT, "size": size},
        minimum_text_height=AnnotationEditor.minimum_text_height,
    )
    for target in [QPointF(25, 35), QPointF(615, 825), QPointF(320, 430)]:
        model = AnnotationEditor.new_callout(editor, label, target)
        assert model["leader"][:2] == [target.x(), target.y()]
        l, b, r, t = model["rect"]
        assert 20 <= l < r <= 620 and 30 <= b < t <= 830
        height = r - l if rotation in (90, 270) else t - b
        assert height >= AnnotationEditor.minimum_text_height(model)
        assert not QRectF(l, b, r - l, t - b).contains(target)


def test_click_outside_callout_finishes_without_creating_another(qtbot, tmp_path):
    source = tmp_path / "outside-click.pdf"
    source_pdf(source)
    window, doc = load_window(qtbot, source)
    editor = window.annotation_editor
    label = doc.page_cards[0].preview
    editor.callout_action.trigger()
    qtbot.mouseClick(
        label,
        Qt.MouseButton.LeftButton,
        pos=QPoint(round(label.width() * 0.2), round(label.height() * 0.75)),
    )
    assert editor.text_edit is not None
    editor.text_edit.setPlainText("完成輸入")
    outside = QPoint(round(label.width() * 0.1), round(label.height() * 0.1))
    qtbot.mouseClick(label, Qt.MouseButton.LeftButton, pos=outside)
    qtbot.waitUntil(lambda: editor.text_edit is None)
    assert editor.drag is None and editor.draft is None
    assert len(doc.annotation_store.items) == 1
    assert editor.current()["text"] == "完成輸入"
    assert editor.callout_action.isChecked()
    qtbot.mouseClick(label, Qt.MouseButton.LeftButton, pos=outside)
    assert editor.text_edit is not None
    editor.text_edit.setPlainText("第二個註解")
    qtbot.keyClick(
        editor.text_edit, Qt.Key.Key_Return, Qt.KeyboardModifier.ControlModifier
    )
    assert len(doc.annotation_store.items) == 2


@pytest.mark.parametrize("rotation", [0, 90, 180, 270])
def test_callout_auto_sizes_text_wraps_and_stays_inside_page(qtbot, tmp_path, rotation):
    source = tmp_path / "auto-size.pdf"
    source_pdf(source)
    window, doc = load_window(qtbot, source)
    editor = window.annotation_editor
    label = doc.page_cards[0].preview
    model = deepcopy(models()[-1])
    model["geometry"]["rotation"] = rotation
    model["text_rotation"] = rotation
    target = model["leader"][:2]
    editor.begin_text(label, model)
    editor.text_edit.setPlainText("字")
    short_rect = list(editor.draft["rect"])

    def dimensions(rect):
        l, b, r, t = rect
        return (t - b, r - l) if rotation in (90, 270) else (r - l, t - b)

    short_width, short_height = dimensions(short_rect)
    editor.text_edit.setPlainText("第一行\n第二行\n第三行")
    assert dimensions(editor.draft["rect"])[1] > short_height
    editor.text_edit.setPlainText("長文字自動換行 " * 35)
    wrapped_rect = list(editor.draft["rect"])
    assert dimensions(wrapped_rect)[1] > short_height
    assert editor.draft["leader"][:2] == target
    l, b, r, t = wrapped_rect
    assert 0 <= l < r <= 400 and 0 <= b < t <= 500
    editor.text_edit.setPlainText("字")
    assert dimensions(editor.draft["rect"])[0] == pytest.approx(short_width)
    assert dimensions(editor.draft["rect"])[1] == pytest.approx(short_height)
    editor.finish_text(True)
    assert editor.current()["text"] == "字"
    assert dimensions(editor.current()["rect"])[1] == pytest.approx(short_height)
    committed = deepcopy(editor.current())
    editor.begin_text(label, deepcopy(committed))
    editor.text_edit.setPlainText("取消尺寸變更\n取消尺寸變更\n取消尺寸變更")
    editor.finish_text(False)
    assert editor.current()["rect"] == committed["rect"]
    assert editor.current()["text"] == "字"


def test_highlight_standard_pdf_roundtrip_and_transparent_appearance(qapp, tmp_path):
    source = tmp_path / "highlight-source.pdf"
    source_pdf(source)
    model = deepcopy(models()[0])
    model.update(
        kind="highlight",
        color="#ffe13c",
        text="hello world",
        quads=[[40, 412, 112, 412, 40, 397, 112, 397]],
    )
    model["appearance_pdf"] = appearance(model)
    saved = tmp_path / "highlight.pdf"
    save_document(source, saved, [0], annotation_changes=[model])
    reader = PdfReader(saved)
    annotation = reader.pages[0]["/Annots"][0].get_object()
    assert annotation["/Subtype"] == "/Highlight"
    assert annotation["/QuadPoints"] and annotation["/AP"]
    imported, reasons, _ = read_models(reader, 0)
    assert not reasons and imported[0]["kind"] == "highlight"
    assert imported[0]["color"] == "#ffe13c"
    document = pdfium.PdfDocument(saved)
    page = document[0]
    image = page.render(scale=1, draw_annots=True).to_pil().convert("RGB")
    # Blank part of the highlight retains the white page through its colour.
    red, green, blue = image.getpixel((110, 90))
    assert red > 240 and green > 200 and 100 < blue < 245
    # Glyphs remain visible through the translucent highlight.
    assert (
        min(sum(image.getpixel((x, y))) for x in range(42, 100) for y in range(90, 100))
        < 400
    )
    page.close()
    document.close()


def test_markup_selection_follows_text_across_lines(qtbot, tmp_path):
    source = tmp_path / "cross-line.pdf"
    source_pdf(source)
    writer = PdfWriter(clone_from=source)
    stream = DecodedStreamObject()
    stream.set_data(
        b"BT /F1 14 Tf 40 400 Td (hello world) Tj 0 -40 Td (next line) Tj ET"
    )
    writer.pages[0][NameObject("/Contents")] = writer._add_object(stream)
    writer.write(source)
    window, doc = load_window(qtbot, source)
    editor = window.annotation_editor
    label = doc.page_cards[0].preview
    tx = transform(doc.annotation_store.geometries[0], label.width(), label.height())
    start = tx.map(QPointF(74, 405)).toPoint()
    end = tx.map(QPointF(65, 365)).toPoint()
    editor.mark_action.trigger()
    qtbot.mousePress(label, Qt.MouseButton.LeftButton, pos=start)
    qtbot.mouseMove(label, end)
    qtbot.waitUntil(lambda: bool(editor.mark_highlights), timeout=10000)
    rects = editor.mark_highlights[2]
    assert len({round(rect[1], 2) for rect in rects}) >= 2
    assert not doc.modified
    qtbot.mouseRelease(label, Qt.MouseButton.LeftButton, pos=end)
    qtbot.waitUntil(lambda: bool(doc.annotation_store.items), timeout=10000)
    model = next(iter(doc.annotation_store.items.values()))
    assert "world" in model["text"] and "next" in model["text"]
    assert "hello" not in model["text"] and "line" not in model["text"]
    assert len(model["quads"]) == 2


@pytest.mark.parametrize("sidebar_open", [False, True])
def test_double_click_callout_edits_without_sidebar_relayout(
    qtbot, tmp_path, sidebar_open
):
    source = tmp_path / "double-click.pdf"
    source_pdf(source)
    window, doc = load_window(qtbot, source)
    editor = window.annotation_editor
    model = models()[-1]
    editor.commit(doc, model, "Callout")
    if sidebar_open:
        window.annotation_action.trigger()
        qtbot.waitUntil(
            lambda: window.navigation.panel.isVisible() and settled(doc), timeout=15000
        )
    label = doc.page_cards[0].preview
    tx = transform(model["geometry"], label.width(), label.height())
    l, b, r, t = model["rect"]
    center = tx.map(QPointF((l + r) / 2, (b + t) / 2)).toPoint()
    size_before = label.size()
    # Include the first click/release; mouseDClick alone misses the regression.
    qtbot.mouseClick(label, Qt.MouseButton.LeftButton, pos=center)
    assert window.navigation.panel.isVisible() == sidebar_open
    qtbot.mouseDClick(label, Qt.MouseButton.LeftButton, pos=center)
    assert editor.text_edit is not None
    assert editor.edit_model[1]["id"] == model["id"]
    qtbot.wait(QApplication.doubleClickInterval() + 30)
    assert editor.text_edit is not None
    assert window.navigation.panel.isVisible() == sidebar_open
    assert label.size() == size_before
    editor.text_edit.setPlainText("雙擊修改成功")
    qtbot.keyClick(
        editor.text_edit, Qt.Key.Key_Return, Qt.KeyboardModifier.ControlModifier
    )
    assert editor.current()["text"] == "雙擊修改成功"
    assert len(doc.annotation_store.items) == 1


def test_single_click_callout_still_opens_annotation_list(qtbot, tmp_path):
    source = tmp_path / "single-click.pdf"
    source_pdf(source)
    window, doc = load_window(qtbot, source)
    editor = window.annotation_editor
    model = models()[-1]
    editor.commit(doc, model, "Callout")
    label = doc.page_cards[0].preview
    tx = transform(model["geometry"], label.width(), label.height())
    l, b, r, t = model["rect"]
    center = tx.map(QPointF((l + r) / 2, (b + t) / 2)).toPoint()
    qtbot.mouseClick(label, Qt.MouseButton.LeftButton, pos=center)
    assert editor.current()["id"] == model["id"]
    qtbot.waitUntil(lambda: window.navigation.panel.isVisible(), timeout=3000)
    assert editor.text_edit is None
    assert editor.current()["id"] == model["id"]


@pytest.mark.parametrize("rotation", [0, 90, 180, 270])
def test_callout_hover_cursors_show_move_resize_and_arrow(qtbot, tmp_path, rotation):
    source = tmp_path / "hover.pdf"
    source_pdf(source)
    window, doc = load_window(qtbot, source)
    editor = window.annotation_editor
    label = doc.page_cards[0].preview
    model = deepcopy(models()[-1])
    model["geometry"]["rotation"] = rotation
    model["text_rotation"] = rotation
    editor.commit(doc, model, "Callout")
    editor.select(doc, model["id"])
    # Hit testing uses the page's rendered rotation as well.
    doc.annotation_store.geometries[0] = model["geometry"]
    editor.callout_action.setChecked(True)
    tx = transform(model["geometry"], label.width(), label.height())
    l, b, r, t = model["rect"]
    center = tx.map(QPointF((l + r) / 2, (b + t) / 2))
    qtbot.mouseMove(label, center.toPoint())
    assert label.cursor().shape() == Qt.CursorShape.SizeAllCursor
    for name, point in editor.handles(model, tx).items():
        qtbot.mouseMove(label, point.toPoint())
        if name == "anchor":
            expected = Qt.CursorShape.PointingHandCursor
        else:
            expected = (
                Qt.CursorShape.SizeFDiagCursor
                if (point.x() - center.x()) * (point.y() - center.y()) > 0
                else Qt.CursorShape.SizeBDiagCursor
            )
        assert label.cursor().shape() == expected


def test_rounded_callout_appearance_survives_save_and_reopen(qapp, tmp_path):
    source = tmp_path / "rounded-source.pdf"
    source_pdf(source)
    model = deepcopy(models()[-1])
    model["radius"] = 6
    model["appearance_pdf"] = appearance(model)
    saved = tmp_path / "rounded.pdf"
    save_document(source, saved, [0], annotation_changes=[model])
    reader = PdfReader(saved)
    annotation = reader.pages[0]["/Annots"][0].get_object()
    assert annotation["/Subtype"] == "/FreeText" and annotation["/CL"]
    assert b" c" in annotation["/AP"]["/N"].get_object().get_data()
    imported, reasons, _ = read_models(reader, 0)
    assert not reasons and imported[0]["radius"] == 6
    assert imported[0]["text"] == model["text"]
    imported[0]["radius"] = 0
    imported[0]["appearance_pdf"] = appearance(imported[0])
    save_document(saved, saved, [0], annotation_changes=imported)
    square, reasons, _ = read_models(PdfReader(saved), 0)
    assert not reasons and square[0]["radius"] == 0


def test_copy_shortcut_on_selected_page_annotation(qtbot, tmp_path):
    source = tmp_path / "copy-annotation.pdf"
    source_pdf(source)
    window, doc = load_window(qtbot, source)
    editor = window.annotation_editor
    model = models()[-1]
    editor.commit(doc, model, "Callout")
    editor.select(doc, model["id"])
    label = doc.page_cards[0].preview
    label.setFocus()
    QApplication.clipboard().setText("before copy")
    qtbot.keyClick(label, Qt.Key.Key_C, Qt.KeyboardModifier.ControlModifier)
    assert QApplication.clipboard().text() == model["text"]


def test_callout_retains_initial_width_and_grows_with_single_line(qtbot, tmp_path):
    from PySide6.QtGui import QInputMethodEvent

    source = tmp_path / "growing-input.pdf"
    source_pdf(source)
    window, doc = load_window(qtbot, source)
    editor = window.annotation_editor
    label = doc.page_cards[0].preview
    model = deepcopy(models()[-1])
    model.update(rect=[40, 200, 140, 250], text="")
    editor.begin_text(label, model)
    edit = editor.text_edit
    initial_width = edit.width()
    edit.setPlainText("字")
    assert edit.width() >= initial_width - 1
    short_height = edit.height()
    widths = []
    for length in [5, 10, 15, 20]:
        edit.setPlainText("字" * length)
        widths.append(edit.width())
        assert edit.height() == short_height
    assert widths == sorted(widths) and widths[-1] > initial_width
    edit.setPlainText("")
    assert edit.width() >= initial_width - 1
    QApplication.sendEvent(edit, QInputMethodEvent("中文輸入法正在組字測試文字", []))
    qtbot.waitUntil(lambda: edit.width() > initial_width)
    assert edit.toPlainText() == "" and editor.draft["text"] == ""
    assert edit.height() == short_height
    QApplication.sendEvent(edit, QInputMethodEvent("", []))
    edit.setPlainText("字" * 100)
    assert edit.height() > short_height
    assert editor.draft["rect"][2] <= 400
    assert editor.draft["leader"][:2] == model["leader"][:2]


def drawing_models():
    from repdf.annotation_editor import DEFAULT_DRAW
    from repdf.annotation_geometry import new_drawing

    geometry = {"box": [0, 0, 400, 500], "rotation": 0}
    result = []
    for index, kind in enumerate(("line", "arrow", "rectangle", "ellipse", "ink")):
        model = new_drawing(
            {**DEFAULT_DRAW, "kind": kind},
            0,
            geometry,
            (40 + index * 55, 200),
            (75 + index * 55, 260),
        )
        if kind in ("rectangle", "ellipse"):
            model["background"] = "#fff4cc"
        if kind == "ink":
            model["paths"][0][2:2] = [270, 280]
        result.append(model)
    result.append(
        {
            "id": "repdf-note",
            "kind": "note",
            "page": 0,
            "geometry": geometry,
            "rect": [300, 380, 324, 404],
            "text": "便利貼內容\n第二行",
            "color": "#c69214",
            "width": 1,
        }
    )
    for model in result:
        model["appearance_pdf"] = appearance(model)
    return result


@pytest.mark.parametrize("rotation", [0, 90, 180, 270])
def test_note_and_drawing_standard_pdf_save_export_reopen(qapp, tmp_path, rotation):
    source = tmp_path / "drawing.pdf"
    source_pdf(source)
    writer = PdfWriter(clone_from=source)
    writer.pages[0].rotate(rotation)
    writer.write(source)
    models = drawing_models()
    for model in models:
        model["geometry"]["rotation"] = rotation
    saved = tmp_path / "drawing-saved.pdf"
    save_document(source, saved, [0], annotation_changes=models)
    reader = PdfReader(saved)
    assert [a.get_object()["/Subtype"] for a in reader.pages[0]["/Annots"]] == [
        "/Line",
        "/Line",
        "/Square",
        "/Circle",
        "/Ink",
        "/Text",
    ]
    assert reader.pages[0]["/Annots"][1].get_object()["/LE"][1] == "/OpenArrow"
    assert reader.pages[0]["/Annots"][4].get_object()["/InkList"]
    imported, reasons, _ = read_models(reader, 0)
    assert not reasons and [m["kind"] for m in imported] == [m["kind"] for m in models]
    assert imported[-1]["text"] == "便利貼內容\n第二行"
    assert imported[2]["background"] == "#fff4cc"
    document = pdfium.PdfDocument(saved)
    page = document[0]
    annotated = page.render(scale=1, draw_annots=True).to_pil().copy()
    plain = page.render(scale=1, draw_annots=False).to_pil().copy()
    assert ImageChops.difference(annotated, plain).getbbox()
    page.close()
    document.close()
    exported = tmp_path / "drawing-export.pdf"
    export_documents([DocumentSelection(source, (0,), None, tuple(models))], exported)
    assert len(read_models(PdfReader(exported), 0)[0]) == 6


@pytest.mark.parametrize("kind", ["line", "arrow", "rectangle", "ellipse", "ink"])
def test_draw_tool_create_move_resize_undo_and_save(qtbot, tmp_path, kind):
    from repdf.annotation_geometry import rect_for

    source = tmp_path / "draw-ui.pdf"
    source_pdf(source)
    window, doc = load_window(qtbot, source)
    editor = window.annotation_editor
    label = doc.page_cards[0].preview
    tx = transform(doc.annotation_store.geometries[0], label.width(), label.height())
    start, middle, end = [
        tx.map(QPointF(x, y)).toPoint() for x, y in [(40, 300), (80, 350), (140, 360)]
    ]
    editor.change_style("draw", "kind", kind)
    editor.draw_action.trigger()
    assert editor.mode() == "draw" and not editor.callout_action.isChecked()
    qtbot.mousePress(label, Qt.MouseButton.LeftButton, pos=start)
    qtbot.mouseMove(label, middle)
    qtbot.mouseMove(label, end)
    assert editor.draft and editor.draft["kind"] == kind
    label.grab()
    qtbot.mouseRelease(label, Qt.MouseButton.LeftButton, pos=end)
    assert len(doc.annotation_store.items) == 1 and doc.modified
    original = deepcopy(editor.current())
    editor.draw_action.setChecked(False)
    if kind in ("line", "arrow"):
        center = tx.map(QPointF(90, 330)).toPoint()
    elif kind == "ink":
        center = middle
    else:
        center = tx.map(QPointF(90, 330)).toPoint()
    qtbot.mousePress(label, Qt.MouseButton.LeftButton, pos=center)
    qtbot.mouseMove(label, center + QPoint(16, 12))
    qtbot.mouseRelease(label, Qt.MouseButton.LeftButton, pos=center + QPoint(16, 12))
    moved_model = deepcopy(editor.current())
    assert rect_for(moved_model) != rect_for(original)
    doc.annotation_store.undo.undo()
    assert rect_for(editor.current()) == rect_for(original)
    doc.annotation_store.undo.redo()
    model = editor.current()
    handle = "end" if kind in ("line", "arrow") else "rt"
    corner = editor.handles(model, tx)[handle].toPoint()
    qtbot.mousePress(label, Qt.MouseButton.LeftButton, pos=corner)
    qtbot.mouseMove(label, corner + QPoint(14, -14))
    qtbot.mouseRelease(label, Qt.MouseButton.LeftButton, pos=corner + QPoint(14, -14))
    assert rect_for(editor.current()) != rect_for(moved_model)
    window.save_action.trigger()
    qtbot.waitUntil(lambda: window.saving.task is None, timeout=15000)
    current = window.current_document()
    qtbot.waitUntil(lambda: settled(current), timeout=15000)
    assert not current.modified
    assert next(iter(current.annotation_store.items.values()))["kind"] == kind


def test_note_tool_shared_panel_create_edit_cancel_move_and_copy(
    qtbot, tmp_path, monkeypatch
):
    from PySide6.QtWidgets import QDialog, QPlainTextEdit

    source = tmp_path / "note-ui.pdf"
    source_pdf(source)
    window, doc = load_window(qtbot, source)
    editor = window.annotation_editor
    label = doc.page_cards[0].preview
    tx = transform(doc.annotation_store.geometries[0], label.width(), label.height())

    def accept_note(dialog):
        dialog.findChild(QPlainTextEdit).setPlainText("便利貼文字")
        return QDialog.DialogCode.Accepted

    monkeypatch.setattr(QDialog, "exec", accept_note)
    editor.change_style(True, "kind", "note")
    editor.callout_menu.refresh()
    assert editor.callout_menu.style_buttons["note"].isChecked()
    assert not editor.callout_menu.size.isEnabled()
    editor.callout_action.trigger()
    qtbot.mouseClick(
        label, Qt.MouseButton.LeftButton, pos=tx.map(QPointF(100, 300)).toPoint()
    )
    assert len(doc.annotation_store.items) == 1
    note = deepcopy(editor.current())
    assert note["kind"] == "note" and note["text"] == "便利貼文字"
    center = tx.map(
        QPointF(
            (note["rect"][0] + note["rect"][2]) / 2,
            (note["rect"][1] + note["rect"][3]) / 2,
        )
    ).toPoint()

    def edit_note(dialog):
        field = dialog.findChild(QPlainTextEdit)
        assert field.toPlainText() == "便利貼文字"
        field.setPlainText("修改便利貼")
        return QDialog.DialogCode.Accepted

    monkeypatch.setattr(QDialog, "exec", edit_note)
    qtbot.mouseClick(label, Qt.MouseButton.LeftButton, pos=center)
    qtbot.mouseDClick(label, Qt.MouseButton.LeftButton, pos=center)
    assert editor.current()["text"] == "修改便利貼"
    monkeypatch.setattr(QDialog, "exec", lambda _: QDialog.DialogCode.Rejected)
    qtbot.mouseClick(
        label, Qt.MouseButton.LeftButton, pos=tx.map(QPointF(200, 300)).toPoint()
    )
    assert len(doc.annotation_store.items) == 1
    qtbot.mousePress(label, Qt.MouseButton.LeftButton, pos=center)
    qtbot.mouseMove(label, center + QPoint(20, 15))
    qtbot.mouseRelease(label, Qt.MouseButton.LeftButton, pos=center + QPoint(20, 15))
    assert editor.current()["rect"] != note["rect"]
    label.setFocus()
    qtbot.keyClick(label, Qt.Key.Key_C, Qt.KeyboardModifier.ControlModifier)
    assert QApplication.clipboard().text() == "修改便利貼"
    editor.change_style(True, "kind", "callout")
    assert (
        editor.callout_style["kind"] == "callout"
        and len(doc.annotation_store.items) == 1
    )


def test_annotation_menu_type_switch_resizes_and_activates_tool(qtbot, tmp_path):
    source = tmp_path / "menu-types.pdf"
    source_pdf(source)
    window, doc = load_window(qtbot, source)
    editor = window.annotation_editor
    menu = editor.callout_menu
    menu.popup(window.mapToGlobal(QPoint(200, 70)))
    qtbot.waitUntil(menu.isVisible)
    qtbot.mouseClick(menu.style_buttons["note"], Qt.MouseButton.LeftButton)
    assert editor.callout_action.isChecked() and editor.callout_style["kind"] == "note"
    assert editor.style(True)["color"] == "#c69214"
    note_height = menu.height()
    assert menu.size.isHidden() and menu.width.isHidden()
    qtbot.mouseClick(menu.style_buttons["callout"], Qt.MouseButton.LeftButton)
    assert editor.callout_style["kind"] == "callout"
    assert not menu.size.isHidden() and menu.height() > note_height
    assert menu.size.mapTo(menu, menu.size.rect().bottomRight()).y() < menu.height()
    assert (
        menu.background.mapTo(menu, menu.background.rect().bottomRight()).y()
        < menu.height()
    )
    menu.hide()
    drawing = editor.draw_menu
    drawing.popup(window.mapToGlobal(QPoint(250, 70)))
    qtbot.waitUntil(drawing.isVisible)
    qtbot.mouseClick(drawing.style_buttons["line"], Qt.MouseButton.LeftButton)
    assert editor.draw_action.isChecked() and not editor.callout_action.isChecked()
    line_height = drawing.height()
    qtbot.mouseClick(drawing.style_buttons["rectangle"], Qt.MouseButton.LeftButton)
    assert drawing.height() > line_height
    assert (
        drawing.background.mapTo(drawing, drawing.background.rect().bottomRight()).y()
        < drawing.height()
    )
    drawing.hide()


def test_drawing_escape_and_degenerate_drag_do_not_add_annotation(qtbot, tmp_path):
    source = tmp_path / "drawing-cancel.pdf"
    source_pdf(source)
    window, doc = load_window(qtbot, source)
    editor = window.annotation_editor
    label = doc.page_cards[0].preview
    editor.draw_action.trigger()
    start, end = QPoint(70, 150), QPoint(140, 210)
    qtbot.mouseClick(label, Qt.MouseButton.LeftButton, pos=start)
    assert not doc.annotation_store.items and not doc.modified
    qtbot.mousePress(label, Qt.MouseButton.LeftButton, pos=start)
    qtbot.mouseMove(label, end)
    assert editor.draft is not None
    qtbot.keyClick(label, Qt.Key.Key_Escape)
    qtbot.mouseRelease(label, Qt.MouseButton.LeftButton, pos=end)
    assert not doc.annotation_store.items and not doc.modified and editor.draft is None


@pytest.mark.parametrize("decimal", [False, True])
def test_annotation_spin_chevrons_step_type_and_obey_limits(qtbot, decimal):
    from repdf.annotation_spin import AnnotationSpinBox, AnnotationDoubleSpinBox

    field = AnnotationDoubleSpinBox() if decimal else AnnotationSpinBox()
    qtbot.addWidget(field)
    field.setRange(0.5, 6) if decimal else field.setRange(8, 72)
    field.setSingleStep(0.5 if decimal else 1)
    field.blockSignals(True)
    field.setValue(1 if decimal else 12)
    field.blockSignals(False)
    field.show()
    assert field.down_button.isEnabled() and field.up_button.isEnabled()
    from PySide6.QtCore import QSize

    assert field.up_button.iconSize() == QSize(12, 12)
    original = field.value()
    qtbot.mouseClick(field.up_button, Qt.MouseButton.LeftButton)
    assert field.value() == original + field.singleStep()
    qtbot.mouseClick(field.down_button, Qt.MouseButton.LeftButton)
    assert field.value() == original
    field.setValue(field.minimum())
    assert not field.down_button.isEnabled()
    field.setValue(field.maximum())
    assert not field.up_button.isEnabled()
    field.lineEdit().selectAll()
    qtbot.keyClicks(field.lineEdit(), "2" if decimal else "20")
    qtbot.keyClick(field.lineEdit(), Qt.Key.Key_Return)
    assert field.value() == (2 if decimal else 20)
    field.setReadOnly(True)
    assert not field.up_button.isEnabled() and not field.down_button.isEnabled()


@pytest.mark.parametrize("rotation", [0, 90, 180, 270])
@pytest.mark.parametrize("kind", ["callout", "note"])
def test_markup_companion_anchor_and_compound_undo(
    qtbot, tmp_path, monkeypatch, rotation, kind
):
    from PySide6.QtWidgets import QDialog, QPlainTextEdit
    from repdf.annotation_graphics import selection_top_center

    source = tmp_path / "linked-text.pdf"
    source_pdf(source)
    window, doc = load_window(qtbot, source)
    editor = window.annotation_editor
    geometry = {"box": [20, 30, 380, 480], "rotation": rotation}
    doc.annotation_store.geometries[0] = geometry
    editor.set_mark_companion(enabled=True, kind=kind)
    editor.mark_action.setChecked(True)
    if kind == "note":

        def accept(dialog):
            dialog.findChild(QPlainTextEdit).setPlainText("連帶便利貼")
            return QDialog.DialogCode.Accepted

        monkeypatch.setattr(QDialog, "exec", accept)
    quads = [
        [40, 410, 160, 410, 40, 397, 160, 397],
        [40, 380, 120, 380, 40, 367, 120, 367],
    ]
    generation = 999999
    editor.requests[generation] = (
        doc.document_id,
        0,
        deepcopy(DEFAULT_MARK),
        False,
        deepcopy(editor.mark_companion),
        deepcopy(editor.callout_style),
        editor.note_color,
    )
    editor.receive(
        {
            "type": "text",
            "generation": generation,
            "text": "hello world\nnext line",
            "quads": quads,
        }
    )
    assert any(m["kind"] == "underline" for m in doc.annotation_store.items.values())
    anchor = selection_top_center(quads, geometry)
    width, height = (450, 360) if rotation in (90, 270) else (360, 450)
    upright = transform(geometry, width, height)
    points = [
        upright.map(QPointF(q[i], q[i + 1])) for q in quads for i in range(0, 8, 2)
    ]
    target = upright.map(anchor)
    assert target.x() == pytest.approx(
        (min(p.x() for p in points) + max(p.x() for p in points)) / 2
    )
    assert target.y() == pytest.approx(min(p.y() for p in points))
    if kind == "callout":
        assert editor.text_edit is not None
        assert editor.draft["leader"][:2] == pytest.approx([anchor.x(), anchor.y()])
        editor.text_edit.setPlainText("連帶文字框")
        editor.finish_text(True)
    else:
        note = next(
            m for m in doc.annotation_store.items.values() if m["kind"] == "note"
        )
        l, b, r, t = note["rect"]
        box = upright.mapRect(QRectF(l, b, r - l, t - b))
        assert box.center().x() == pytest.approx(target.x())
        assert box.bottom() == pytest.approx(max(24, target.y() - 4))
        assert box.top() >= 0 and box.bottom() <= height
    assert len(doc.annotation_store.items) == 2 and editor.linked_store is None
    assert doc.annotation_store.undo.count() == 1
    doc.annotation_store.undo.undo()
    assert not doc.annotation_store.items and not doc.modified
    doc.annotation_store.undo.redo()
    assert len(doc.annotation_store.items) == 2


@pytest.mark.parametrize("kind", ["callout", "note"])
def test_cancelling_markup_companion_retains_only_markup(
    qtbot, tmp_path, monkeypatch, kind
):
    from PySide6.QtWidgets import QDialog

    source = tmp_path / "cancel-linked.pdf"
    source_pdf(source)
    window, doc = load_window(qtbot, source)
    editor = window.annotation_editor
    editor.set_mark_companion(enabled=True, kind=kind)
    editor.mark_action.setChecked(True)
    if kind == "note":
        monkeypatch.setattr(QDialog, "exec", lambda _: QDialog.DialogCode.Rejected)
    request = (
        doc.document_id,
        0,
        deepcopy(DEFAULT_MARK),
        False,
        deepcopy(editor.mark_companion),
        deepcopy(editor.callout_style),
        editor.note_color,
    )
    editor.requests[9000] = request
    editor.receive(
        {
            "type": "text",
            "generation": 9000,
            "text": "hello",
            "quads": [[40, 410, 90, 410, 40, 397, 90, 397]],
        }
    )
    if kind == "callout":
        editor.finish_text(False)
    assert len(doc.annotation_store.items) == 1 and editor.linked_store is None
    assert next(iter(doc.annotation_store.items.values()))["kind"] == "underline"
    doc.annotation_store.undo.undo()
    assert not doc.modified


def test_markup_companion_real_selection_saves_and_reopens_pair(qtbot, tmp_path):
    source = tmp_path / "linked-real.pdf"
    source_pdf(source)
    window, doc = load_window(qtbot, source)
    editor = window.annotation_editor
    editor.set_mark_companion(enabled=True, kind="callout")
    editor.change_style(True, "kind", "note")
    editor.mark_action.setChecked(True)
    label = doc.page_cards[0].preview
    tx = transform(doc.annotation_store.geometries[0], label.width(), label.height())
    start, end = tx.map(QPointF(42, 405)).toPoint(), tx.map(QPointF(107, 405)).toPoint()
    qtbot.mousePress(label, Qt.MouseButton.LeftButton, pos=start)
    qtbot.mouseMove(label, end)
    qtbot.mouseRelease(label, Qt.MouseButton.LeftButton, pos=end)
    qtbot.waitUntil(lambda: editor.text_edit is not None, timeout=10000)
    assert editor.draft["kind"] == "callout"
    l, b, r, t = editor.draft["rect"]
    rendered_box = tx.mapRect(QRectF(l, b, r - l, t - b))
    rendered_target = tx.map(QPointF(*editor.draft["leader"][:2]))
    assert rendered_box.bottom() < rendered_target.y()
    editor.text_edit.setPlainText("畫線註解說明")
    qtbot.keyClick(
        editor.text_edit, Qt.Key.Key_Return, Qt.KeyboardModifier.ControlModifier
    )
    assert (
        len(doc.annotation_store.items) == 2 and doc.annotation_store.undo.count() == 1
    )
    window.save_action.trigger()
    qtbot.waitUntil(lambda: window.saving.task is None, timeout=15000)
    current = window.current_document()
    qtbot.waitUntil(lambda: settled(current), timeout=15000)
    assert not current.modified and len(current.annotation_store.items) == 2
    assert {m["kind"] for m in current.annotation_store.items.values()} == {
        "underline",
        "callout",
    }
