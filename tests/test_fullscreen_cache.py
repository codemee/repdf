import pytest

from repdf.app import MainWindow
from repdf.renderer import RenderService
from test_preview import make_pdf, wait_for_preview
from test_renderer import FakeBackend


def test_background_render_never_overtakes_pending_navigation(qtbot, tmp_path, monkeypatch):
    service = RenderService(FakeBackend())
    service._reader.join()
    sent = []
    monkeypatch.setattr(service, '_write', lambda payload: (sent.append(payload), True)[1])
    try:
        service.request(tmp_path / 'a.pdf', 1, tmp_path, 1, document_id=1)
        service.request(tmp_path / 'a.pdf', 1, tmp_path, 2, document_id=('prefetch', 1), background=True)
        service.request_navigation(tmp_path / 'a.pdf', 1, 3, 'annotations')
        service._busy = False
        service._start_next()
        assert [p['generation'] for p in sent] == [1, 3]
        service._busy = False
        service._start_next()
        assert sent[-1]['generation'] == 2
    finally:
        service.close()


@pytest.mark.parametrize('mode', ['single', 'spread'])
def test_idle_prefetch_shows_next_group_immediately_without_rerender(qtbot, tmp_path, monkeypatch, mode):
    source = tmp_path / 'lookahead.pdf'
    make_pdf(source, [(300, 400), (600, 300), (300, 600), (450, 400), (300, 400), (300, 400), (300, 400)])
    window = MainWindow()
    qtbot.addWidget(window)
    window.show()
    window.load_pdf(source)
    doc = window.current_document()
    wait_for_preview(qtbot, doc)
    window.fullscreen_mode = mode
    window._show_fullscreen_preview()
    viewer = window._fullscreen_preview
    viewer.resize(900, 700)
    future = viewer.groups[1]
    qtbot.waitUntil(lambda: all(viewer.cache.get(page, viewer.cache.scale_for(future))
                               for page in future), timeout=25000)
    expected = {page: viewer.cache.entries[page][1] for page in future}
    calls = []
    request = window.render_service.request
    def capture(*args, **kwargs):
        calls.append(kwargs)
        return request(*args, **kwargs)
    monkeypatch.setattr(window.render_service, 'request', capture)
    viewer.show_page(future[0])
    assert all(viewer.images[page] == expected[page] for page in future)
    viewer.timer.stop()
    viewer.request_render()
    assert not [call for call in calls if not call.get('background')]
    assert viewer.render_generation == -1
    assert len(viewer.cache.entries) <= viewer.cache.MAX_PAGES
    assert sum(entry[1].sizeInBytes() for entry in viewer.cache.entries.values()) <= viewer.cache.MAX_BYTES
    doc.annotation_store.revision += 1
    assert viewer.cache.get(future[0]) is None
    assert not viewer.cache.entries
    viewer.close()
    assert not viewer.cache.timer.isActive()
