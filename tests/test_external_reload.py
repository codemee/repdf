"""External PDF edits keep the user's view until a replacement opens successfully."""

import os

from pypdf import PdfWriter

from test_navigation import load_window
from test_page_view import settled


def write_pdf(path, pages):
    writer = PdfWriter()
    for _ in range(pages):
        writer.add_blank_page(300, 400)
    writer.write(path)


def test_external_change_prompt_once_and_reload_preserves_view(qtbot, tmp_path, monkeypatch):
    path = tmp_path / 'changed.pdf'
    write_pdf(path, 4)
    window, old = load_window(qtbot, path)
    window._source_check.stop()
    window._set_manual_zoom(125)
    old.jump_to_page(2)
    qtbot.waitUntil(lambda: old.preview_page_index() == 2 and settled(old), timeout=15000)

    observed = []
    monkeypatch.setattr(window, '_prompt_source_change', observed.append)
    write_pdf(path, 3)
    os.utime(path, ns=(path.stat().st_atime_ns, path.stat().st_mtime_ns + 1_000_000_000))
    window._check_source_files()
    window._check_source_files()
    assert observed == [old]
    assert window.current_document() is old

    window._reload_document(old)
    qtbot.waitUntil(lambda: window.current_document() is not old and window.current_document().ready,
                    timeout=10000)
    replacement = window.current_document()
    qtbot.waitUntil(lambda: settled(replacement), timeout=15000)
    assert window.tabs.count() == 1
    assert replacement.page_count == 3
    assert replacement.preview_page_index() == 2
    assert replacement.zoom == 125
    assert not replacement.fit_mode


def test_failed_external_reload_keeps_original_tab(qtbot, tmp_path):
    path = tmp_path / 'broken.pdf'
    write_pdf(path, 2)
    window, old = load_window(qtbot, path)
    window._source_check.stop()
    path.write_bytes(b'not a PDF')
    window._reload_document(old)
    qtbot.waitUntil(lambda: not window._reload_context, timeout=10000)
    assert window.current_document() is old
    assert window.tabs.count() == 1
