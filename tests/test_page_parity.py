from pypdf import PdfWriter
from repdf.core import SelectionState
from test_navigation import load_window


def test_page_header_parity_tools_follow_original_numbers_and_sync(qtbot, tmp_path):
    source = tmp_path / 'parity.pdf'
    writer = PdfWriter()
    for _ in range(5):
        writer.add_blank_page(300,400)
    writer.write(source)
    window, doc = load_window(qtbot, source)
    odd = doc.page_cards[0].parity_button
    even = doc.page_cards[1].parity_button
    assert odd.odd and not even.odd
    doc.page_cards[2].checkbox.click()
    assert odd.selection_state == SelectionState.PARTIAL
    odd.click()
    assert doc.selected_pages == {0,2,4}
    assert doc.page_cards[4].parity_button.selection_state == SelectionState.ALL
    doc._move_page(4,0)
    even.click()
    assert doc.selected_pages == {0,1,2,3,4}
    odd.click()
    assert doc.selected_pages == {1,3}
    assert not window.odd_checkbox.isVisible()
    window.fullscreen_action.trigger()
    viewer = window._fullscreen_preview
    page = viewer.page_index
    viewer.parity_buttons[page].click()
    expected = {0,1,2,3,4} if page % 2 == 0 else set()
    assert doc.selected_pages == expected
    for index, checkbox in viewer.checkboxes.items():
        assert checkbox.isChecked() == (index in expected)
    viewer.close()
