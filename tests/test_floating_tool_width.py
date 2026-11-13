import pytest

from test_proofreading import files, choose


@pytest.mark.parametrize('comparison', [False, True])
def test_fullscreen_tools_use_full_content_width_and_overflow_only_when_narrow(qtbot, tmp_path, comparison):
    window, docs = files(qtbot, tmp_path)
    window.settings.setValue('view/fullscreen_tools_expanded', False)
    if comparison:
        choose(docs)
    window.fullscreen_action.trigger()
    viewer = window._fullscreen_preview
    floating = viewer.floating_tools
    assert floating.layout().itemAt(floating.layout().count() - 1).widget() is floating.page_navigation
    assert (window.sync_views_action in floating.mode_toolbar.actions()) is comparison
    viewer.resize(1200, 700)
    qtbot.waitUntil(lambda: viewer.width() == 1200)
    floating.reposition()
    qtbot.wait(100)
    assert all(button.isVisible() for button in floating.buttons.values()), (
        floating.size(), floating.layout().sizeHint(), floating.toolbar.size(), floating.toolbar.sizeHint(),
        floating.mode_toolbar.size(), floating.mode_toolbar.sizeHint(),
        [action.text() for action, button in floating.buttons.items() if not button.isVisible()])
    assert floating.toggle.isChecked() and floating.toolbar.isVisible()
    assert not floating.toolbar.overflow_button.isVisible()
    assert not floating.mode_toolbar.overflow_button.isVisible()
    assert viewer.rect().contains(floating.geometry())
    full_width = floating.width()
    viewer.resize(320, 400)
    qtbot.waitUntil(lambda: floating.width() < full_width)
    qtbot.waitUntil(lambda: floating.toolbar.overflow_button.isVisible() or
                   floating.mode_toolbar.overflow_button.isVisible())
    assert viewer.rect().contains(floating.geometry())
    viewer.resize(1200, 700)
    qtbot.waitUntil(lambda: all(button.isVisible() for button in floating.buttons.values()))
    qtbot.waitUntil(lambda: not floating.toolbar.overflow_button.isVisible() and
                   not floating.mode_toolbar.overflow_button.isVisible())
    assert floating.width() == full_width
    assert not floating.toolbar.overflow_button.isVisible()
    assert not floating.mode_toolbar.overflow_button.isVisible()
    viewer.close()
