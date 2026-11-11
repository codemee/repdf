from types import SimpleNamespace

import pytest
from PySide6.QtCore import QPointF, QRectF

from repdf.annotation_editor import AnnotationEditor
from repdf.annotation_graphics import transform
from repdf.widgets import PagePreviewLabel


@pytest.mark.parametrize('kind', ['strikeout', 'underline', 'squiggly', 'highlight'])
@pytest.mark.parametrize('rotation', [0, 90, 180, 270])
@pytest.mark.parametrize('zoom', [.5, 2])
def test_wrapped_markup_does_not_capture_note_or_interline_space(qtbot, kind, rotation, zoom):
    # F6791_CH08(38).pdf, page 9: the two runs straddle a read-only sticky note.
    geometry = {'box': [0, 0, 561.259, 731.338], 'rotation': rotation}
    markup = {'id': 'mark', 'kind': kind, 'page': 8, 'width': 1,
              'quads': [[406.352, 419.491, 439.373, 419.491, 406.352, 409.461, 439.373, 409.461],
                        [104.882, 400.991, 121.069, 400.991, 104.882, 390.961, 121.069, 390.961]]}
    models = [markup]
    store = SimpleNamespace(geometries={8: geometry}, page=lambda page: models)
    doc = SimpleNamespace(annotation_store=store)
    label = PagePreviewLabel('')
    qtbot.addWidget(label)
    width, height = (731, 561) if rotation in (90, 270) else (561, 731)
    label.resize(round(width * zoom), round(height * zoom))
    label.annotation_document, label.annotation_page = doc, 8
    tx = transform(geometry, label.width(), label.height())
    editor = SimpleNamespace(selected=None)
    hit = lambda x, y: AnnotationEditor.hit(editor, label, tx.map(QPointF(x, y)))[0]
    assert hit(431.466, 402.879) is None  # Visible note center, inside combined bounds.
    note_rect = tx.mapRect(QRectF(421.466, 392.879, 20, 20))
    fallback = {'rect': [note_rect.left() / label.width(), note_rect.top() / label.height(),
                         note_rect.right() / label.width(), note_rect.bottom() / label.height()],
                'destination': {'annotation_index': 1, 'contents': 'speech_stream'}}
    label.set_annotations([fallback])
    assert label._link_at(tx.map(QPointF(431.466, 402.879))) is fallback
    assert hit(250, 405) is None
    for q in markup['quads']:
        y = q[5] if kind in ('underline', 'squiggly') else (q[1] + q[5]) / 2
        assert hit((q[0] + q[2]) / 2, y) is markup
    # An editable note beneath the markup in stacking order is accessible too.
    note = {'id': 'note', 'kind': 'note', 'page': 8, 'rect': [421.466, 392.879, 441.466, 412.879]}
    models.insert(0, note)
    assert hit(431.466, 402.879) is note
