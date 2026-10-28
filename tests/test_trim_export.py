import pytest
from pypdf import PdfReader, PdfWriter
from pypdf.generic import DecodedStreamObject, NameObject
from contextlib import closing
import pypdfium2 as pdfium

from repdf.core import DocumentSelection, export_documents, split_documents


@pytest.mark.parametrize('split', [False, True])
@pytest.mark.parametrize('remove', [False, True])
def test_export_can_crop_to_trimbox_and_hide_outside_marks(tmp_path, split, remove):
    source = tmp_path / 'source.pdf'
    writer = PdfWriter()
    page = writer.add_blank_page(300, 400)
    page.cropbox.lower_left = (10, 15)
    page.cropbox.upper_right = (290, 385)
    page.trimbox.lower_left = (40, 40)
    page.trimbox.upper_right = (260, 360)
    stream = DecodedStreamObject()
    stream.set_data(b'0 g 0 0 300 400 re f 1 g 40 40 220 320 re f 0 g 100 100 50 50 re f')
    page[NameObject('/Contents')] = writer._add_object(stream)
    page.rotate(90)
    writer.add_blank_page(200, 300)
    writer.write(source)
    original = source.read_bytes()
    selection = [DocumentSelection(source, (1, 0))]
    destination = tmp_path / 'output.pdf'
    if split:
        paths = split_documents(selection, destination, remove_trimbox=remove)
        pages = [PdfReader(path).pages[0] for path in paths]
    else:
        export_documents(selection, destination, remove_trimbox=remove)
        pages = list(PdfReader(destination).pages)
    assert '/TrimBox' not in pages[0]
    assert ('/TrimBox' not in pages[1]) == remove
    assert list(pages[1].mediabox) == ([40, 40, 260, 360] if remove else [0, 0, 300, 400])
    assert list(pages[1].cropbox) == ([40, 40, 260, 360] if remove else [10, 15, 290, 385])
    assert list(pages[0].mediabox) == [0, 0, 200, 300]
    assert pages[1].rotation == 90
    assert source.read_bytes() == original
    output = paths[1] if split else destination
    with closing(pdfium.PdfDocument(str(output))) as document:
        with closing(document[0 if split else 1]) as rendered:
            with closing(rendered.render(scale=1)) as bitmap:
                color = bitmap.to_pil().convert('RGB').getpixel((2, 2))
                assert color == ((255, 255, 255) if remove else (0, 0, 0))
