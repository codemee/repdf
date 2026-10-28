"""Discover an optional, non-destructive PDF viewing rectangle."""


def metadata_trim_box(page):
    """Return a meaningful TrimBox within the visible page, or None."""
    page_box = page.get_bbox()
    trim_box = page.get_trimbox(fallback_ok=False)
    if trim_box is None:
        return None
    left = max(page_box[0], trim_box[0])
    bottom = max(page_box[1], trim_box[1])
    right = min(page_box[2], trim_box[2])
    top = min(page_box[3], trim_box[3])
    if right - left < 10 or top - bottom < 10:
        return None
    if (abs(left - page_box[0]) < 0.5 and abs(bottom - page_box[1]) < 0.5
            and abs(right - page_box[2]) < 0.5 and abs(top - page_box[3]) < 0.5):
        return None
    return left, bottom, right, top


def crop_mark_box(page):
    """Recognize eight short, stroked corner marks; ambiguous pages stay whole."""
    from ctypes import byref, c_float, c_int
    from itertools import product
    import pypdfium2.raw as raw

    left, bottom, right, top = page.get_bbox()
    width, height = right - left, top - bottom
    horizontal, vertical = [], []
    budget = 20000
    for obj in page.get_objects():
        if obj.type != raw.FPDF_PAGEOBJ_PATH:
            continue
        count = raw.FPDFPath_CountSegments(obj)
        budget -= count
        if budget < 0:
            return None
        if not 2 <= count <= 128:
            continue
        fill, stroke = c_int(), c_int()
        if not raw.FPDFPath_GetDrawMode(obj, byref(fill), byref(stroke)) or not stroke.value or fill.value:
            continue
        segments = [raw.FPDFPath_GetPathSegment(obj, i) for i in range(count)]
        if any(raw.FPDFPathSegment_GetClose(segment) for segment in segments):
            continue
        matrices, ancestor = [obj.get_matrix()], obj.container
        while ancestor is not None:
            matrices.append(ancestor.get_matrix())
            ancestor = ancestor.container
        previous = None
        for segment in segments:
            kind = raw.FPDFPathSegment_GetType(segment)
            x, y = c_float(), c_float()
            if not raw.FPDFPathSegment_GetPoint(segment, byref(x), byref(y)):
                previous = None
                continue
            point = (x.value, y.value)
            for matrix in matrices:
                point = matrix.on_point(*point)
            if previous is not None and kind == raw.FPDF_SEGMENT_LINETO:
                x0, y0 = previous
                x1, y1 = point
                if abs(y0 - y1) < .3 and 5 <= abs(x1 - x0) <= min(65, width * .15):
                    horizontal.append((min(x0, x1), max(x0, x1), (y0 + y1) / 2))
                if abs(x0 - x1) < .3 and 5 <= abs(y1 - y0) <= min(65, height * .15):
                    vertical.append((min(y0, y1), max(y0, y1), (x0 + x1) / 2))
            previous = point if kind in (raw.FPDF_SEGMENT_MOVETO, raw.FPDF_SEGMENT_LINETO) else None
    xs = {round(x, 2) for _, _, x in vertical}
    ys = {round(y, 2) for _, _, y in horizontal}
    candidates = (
        sorted(x for x in xs if left + 5 < x < left + width * .18),
        sorted(y for y in ys if bottom + 5 < y < bottom + height * .18),
        sorted(x for x in xs if right - width * .18 < x < right - 5),
        sorted(y for y in ys if top - height * .18 < y < top - 5),
    )
    if any(not values or len(values) > 12 for values in candidates):
        return None
    found = []
    for l, b, r, t in product(*candidates):
        # Each corner must have a horizontal and vertical mark outside the box.
        if all(any(abs(y - edge) < .6 and -1 <= l - end <= 24 for start, end, y in horizontal)
               and any(abs(y - edge) < .6 and -1 <= start - r <= 24 for start, end, y in horizontal)
               for edge in (b, t)) and all(
                any(abs(x - edge) < .6 and -1 <= b - end <= 24 for start, end, x in vertical)
                and any(abs(x - edge) < .6 and -1 <= start - t <= 24 for start, end, x in vertical)
                for edge in (l, r)):
            found.append((l, b, r, t))
    return min(found, key=lambda box: (box[2] - box[0]) * (box[3] - box[1])) if found else None


def viewing_box(page):
    """Prefer an explicit TrimBox, then conservatively infer vector crop marks."""
    trim = metadata_trim_box(page)
    if trim is not None:
        return trim
    # An explicit full-page/invalid TrimBox is not a request for heuristic cropping.
    if page.get_trimbox(fallback_ok=False) is not None:
        return None
    return crop_mark_box(page)
