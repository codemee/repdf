"""Read existing PDF navigation in the isolated PDFium backend."""

import ctypes
from math import isfinite
from urllib.parse import urlsplit

import pypdfium2 as pdfium
import pypdfium2.raw as raw


def read_page_label(document, index):
    """Return an explicitly defined label, without inventing physical numbers."""
    try:
        return document.get_page_label(index) or None
    except (UnicodeError, ValueError):
        return None


def _destination(document, destination):
    if not destination:
        return None
    dest = pdfium.PdfDest(destination, pdf=document)
    index = dest.get_index()
    if index is None or not 0 <= index < len(document):
        return None
    mode, position = dest.get_view()
    result = {'page': index, 'view': mode, 'position': position}
    if mode == raw.PDFDEST_VIEW_XYZ:
        has_x, has_y, has_zoom = ctypes.c_int(), ctypes.c_int(), ctypes.c_int()
        x, y, zoom = ctypes.c_float(), ctypes.c_float(), ctypes.c_float()
        raw.FPDFDest_GetLocationInPage(destination, has_x, has_y, has_zoom, x, y, zoom)
        result['left'] = x.value if has_x.value else None
        result['top'] = y.value if has_y.value else None
    return result


def _goto_action(document, action):
    if action and raw.FPDFAction_GetType(action) == raw.PDFACTION_GOTO:
        return raw.FPDFAction_GetDest(document, action)
    return None


def _web_action(document, action):
    if not action or raw.FPDFAction_GetType(action) != raw.PDFACTION_URI:
        return None
    size = raw.FPDFAction_GetURIPath(document, action, None, 0)
    if size <= 1:
        return None
    buffer = ctypes.create_string_buffer(size)
    raw.FPDFAction_GetURIPath(document, action, buffer, size)
    try:
        data = buffer.raw[:-1]
        url = data.decode('utf-16' if data.startswith((b'\xfe\xff', b'\xff\xfe')) else 'utf-8')
        parsed = urlsplit(url)
        if (parsed.scheme.lower() in ('http', 'https') and parsed.hostname
                and not any(ord(char) < 32 or ord(char) == 127 for char in url)):
            return {'url': url}
    except (UnicodeError, ValueError):
        pass
    return None


def read_bookmarks(document):
    bookmarks = []
    for bookmark in document.get_toc(max_depth=64):
        destination = raw.FPDFBookmark_GetDest(document, bookmark)
        if not destination:
            destination = _goto_action(document, raw.FPDFBookmark_GetAction(bookmark))
        bookmarks.append({'title': bookmark.get_title(), 'level': bookmark.level,
                          'expanded': bookmark.get_count() > 0,
                          'destination': _destination(document, destination)})
    return bookmarks


def normalized_point(page, x, y):
    left, bottom, right, top = page.get_bbox()
    width, height = right - left, top - bottom
    rotation = page.get_rotation()
    if rotation == 90:
        point = (y - bottom) / height, (x - left) / width
    elif rotation == 180:
        point = (right - x) / width, (y - bottom) / height
    elif rotation == 270:
        point = (top - y) / height, (right - x) / width
    else:
        point = (x - left) / width, (top - y) / height
    return [max(0, min(1, value)) for value in point]


def read_page_links(document, page):
    links = []
    position = ctypes.c_int()
    link = raw.FPDF_LINK()
    while raw.FPDFLink_Enumerate(page, position, link):
        action = raw.FPDFLink_GetAction(link)
        destination = raw.FPDFLink_GetDest(document, link)
        if not destination:
            destination = _goto_action(document, action)
        target = _destination(document, destination) or _web_action(document, action)
        if target is None:
            continue
        rect = raw.FS_RECTF()
        if not raw.FPDFLink_GetAnnotRect(link, rect):
            continue
        if not all(isfinite(v) for v in (rect.left, rect.right, rect.bottom, rect.top)):
            continue
        points = [normalized_point(page, x, y) for x in (rect.left, rect.right)
                  for y in (rect.bottom, rect.top)]
        xs, ys = zip(*points)
        bounds = [min(xs), min(ys), max(xs), max(ys)]
        if bounds[2] > bounds[0] and bounds[3] > bounds[1]:
            links.append({'rect': bounds, 'destination': target})
    return links


def resolve_destination(document, destination):
    index = destination['page']
    if not isinstance(index, int) or not 0 <= index < len(document):
        raise ValueError('Invalid navigation page')
    page = document[index]
    try:
        left, _bottom, _right, top = page.get_bbox()
        mode, position = destination.get('view'), destination.get('position', [])
        if mode == raw.PDFDEST_VIEW_XYZ:
            left = destination.get('left') if destination.get('left') is not None else left
            top = destination.get('top') if destination.get('top') is not None else top
        elif mode in (raw.PDFDEST_VIEW_FITH, raw.PDFDEST_VIEW_FITBH) and position:
            top = position[0]
        elif mode in (raw.PDFDEST_VIEW_FITV, raw.PDFDEST_VIEW_FITBV) and position:
            left = position[0]
        elif mode == raw.PDFDEST_VIEW_FITR and len(position) == 4:
            left, top = position[0], position[3]
        if not isfinite(left) or not isfinite(top):
            raise ValueError('Invalid navigation position')
        width, height = page.get_size()
        result = {'page': index, 'point': normalized_point(page, left, top),
                'width_points': width, 'height_points': height,
                'page_label': read_page_label(document, index)}
        rect = destination.get('annotation_rect')
        if (isinstance(rect, (list, tuple)) and len(rect) == 4
                and all(isinstance(v, (int, float)) and isfinite(v) and 0 <= v <= 1 for v in rect)
                and rect[2] > rect[0] and rect[3] > rect[1]):
            result['annotation_rect'] = list(rect)
            result['point'] = list(rect[:2])
        return result
    finally:
        page.close()
