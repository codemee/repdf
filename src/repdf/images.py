"""Hit-test embedded raster images, independently of preview resolution."""

from pathlib import Path
from contextlib import closing

import pypdfium2 as pdfium
import pypdfium2.raw as raw


def _images_at(page, point, form=None, depth=0):
    if depth >= 32:
        return
    for obj in page.get_objects(max_depth=1, form=form):
        if obj.type not in (raw.FPDF_PAGEOBJ_IMAGE, raw.FPDF_PAGEOBJ_FORM):
            continue
        matrix = obj.get_matrix()
        determinant = matrix.a * matrix.d - matrix.b * matrix.c
        if abs(determinant) < 1e-12:
            continue
        x, y = point[0] - matrix.e, point[1] - matrix.f
        local = ((matrix.d * x - matrix.c * y) / determinant,
                 (-matrix.b * x + matrix.a * y) / determinant)
        if obj.type == raw.FPDF_PAGEOBJ_FORM:
            yield from _images_at(page, local, obj, depth + 1)
        elif 0 <= local[0] <= 1 and 0 <= local[1] <= 1:
            yield obj


def extract_clicked_image(source: Path, page_index: int, point, destination: Path):
    """Save the last painted raster image at normalized displayed-page coordinates.

    Export the entire underlying raster, including its mask, rather than a crop
    of the rendered page. Page and image transforms affect hit-testing only.
    """
    if len(point) != 2 or not all(0 <= float(value) <= 1 for value in point):
        raise ValueError("Invalid image selection position")
    with closing(pdfium.PdfDocument(str(source))) as document:
        if not 0 <= page_index < len(document):
            raise ValueError("Invalid image selection page index")
        with closing(document[page_index]) as page:
            left, bottom, right, top = page.get_bbox()
            width, height = right - left, top - bottom
            x, y = map(float, point)
            rotation = page.get_rotation()
            if rotation == 90:
                position = left + y * width, bottom + x * height
            elif rotation == 180:
                position = right - x * width, bottom + y * height
            elif rotation == 270:
                position = right - y * width, top - x * height
            else:
                position = left + x * width, top - y * height
            hits = list(_images_at(page, position))
            if not hits:
                return None
            image = hits[-1]
            width, height = image.get_px_size()
            original_matrix = image.get_matrix()
            try:
                image.set_matrix(pdfium.PdfMatrix(width, 0, 0, height, 0, 0))
                with closing(image.get_bitmap(render=True, scale_to_original=False)) as bitmap:
                    bitmap.to_pil().save(destination, "PNG")
            finally:
                image.set_matrix(original_matrix)
            return {"path": str(destination), "width": width, "height": height}
