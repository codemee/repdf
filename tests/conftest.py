import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest


@pytest.fixture(autouse=True)
def isolated_preferences(monkeypatch, tmp_path):
    # Automated PDF opens must not populate the user's real Windows Jump List.
    monkeypatch.setattr('repdf.recent_files.publish_recent_document', lambda path: False)
    from PySide6.QtCore import QSettings
    from repdf import strings
    monkeypatch.setattr("repdf.app.QSettings", lambda *_args: QSettings(str(tmp_path / "ui.ini"), QSettings.Format.IniFormat))
    monkeypatch.setattr("repdf.preferences.system_language", lambda: "zh")
    monkeypatch.setattr(strings, "LANGUAGE", "zh")

    # Test teardown discards edits; modal close decisions have dedicated coverage.
    monkeypatch.setattr("repdf.app.MainWindow._confirm_close", lambda self, doc, on_saved=None: True)
