"""Read PDF markup annotations without modifying or rendering the document."""

import ctypes
from math import isfinite

import pypdfium2.raw as raw

from repdf.pdf_navigation import normalized_point


ANNOTATION_TYPES = {
    raw.FPDF_ANNOT_TEXT: '備註', raw.FPDF_ANNOT_FREETEXT: '文字方塊',
    raw.FPDF_ANNOT_LINE: '直線', raw.FPDF_ANNOT_SQUARE: '矩形',
    raw.FPDF_ANNOT_CIRCLE: '橢圓', raw.FPDF_ANNOT_POLYGON: '多邊形',
    raw.FPDF_ANNOT_POLYLINE: '折線', raw.FPDF_ANNOT_HIGHLIGHT: '螢光標示',
    raw.FPDF_ANNOT_UNDERLINE: '底線', raw.FPDF_ANNOT_SQUIGGLY: '波浪底線',
    raw.FPDF_ANNOT_STRIKEOUT: '刪除線', raw.FPDF_ANNOT_STAMP: '印章',
    raw.FPDF_ANNOT_CARET: '插入符號', raw.FPDF_ANNOT_INK: '手繪',
    raw.FPDF_ANNOT_FILEATTACHMENT: '附件', raw.FPDF_ANNOT_REDACT: '遮蔽標記',
}
TEXT_MARKUPS = {raw.FPDF_ANNOT_HIGHLIGHT, raw.FPDF_ANNOT_UNDERLINE,
                raw.FPDF_ANNOT_SQUIGGLY, raw.FPDF_ANNOT_STRIKEOUT}


def _string(annotation, key):
    size = raw.FPDFAnnot_GetStringValue(annotation, key.encode('ascii'), None, 0)
    if size <= 2 or size > 2_000_000:
        return ''
    buffer = (ctypes.c_ushort * ((size + 1) // 2))()
    raw.FPDFAnnot_GetStringValue(annotation, key.encode('ascii'), buffer, size)
    return bytes(buffer)[:size - 2].decode('utf-16-le', errors='replace').replace('\x00', '')


def _marked_text(page, annotation, rect):
    textpage = page.get_textpage()
    try:
        boxes = []
        for index in range(raw.FPDFAnnot_CountAttachmentPoints(annotation)):
            quad = raw.FS_QUADPOINTSF()
            if raw.FPDFAnnot_GetAttachmentPoints(annotation, index, quad):
                xs = [getattr(quad, f'x{i}') for i in range(1, 5)]
                ys = [getattr(quad, f'y{i}') for i in range(1, 5)]
                if all(isfinite(value) for value in (*xs, *ys)):
                    boxes.append((min(xs), min(ys), max(xs), max(ys)))
        if not boxes and rect is not None:
            boxes = [(rect.left, rect.bottom, rect.right, rect.top)]
        return '\n'.join(filter(None, (textpage.get_text_bounded(*box).strip() for box in boxes)))
    finally:
        textpage.close()


def read_annotations(document, pages=None, *, include_text=True):
    result = []
    for page_index in (range(len(document)) if pages is None else pages):
        page = document[page_index]
        try:
            for index in range(raw.FPDFPage_GetAnnotCount(page)):
                annotation = raw.FPDFPage_GetAnnot(page, index)
                if not annotation:
                    continue
                try:
                    subtype = raw.FPDFAnnot_GetSubtype(annotation)
                    if subtype not in ANNOTATION_TYPES:
                        continue  # Links, widgets and popup containers are not comments.
                    rect = raw.FS_RECTF()
                    if not raw.FPDFAnnot_GetRect(annotation, rect) or not all(
                            isfinite(value) for value in (rect.left, rect.bottom, rect.right, rect.top)):
                        rect = None
                    contents = _string(annotation, 'Contents') if include_text else ''
                    if include_text and not contents and subtype in TEXT_MARKUPS:
                        try:
                            contents = _marked_text(page, annotation, rect)
                        except (ValueError, RuntimeError, UnicodeError):
                            pass
                    destination = {'page': page_index}
                    if rect is not None:
                        destination.update(view=raw.PDFDEST_VIEW_XYZ, left=rect.left, top=rect.top)
                        points = [normalized_point(page, x, y) for x in (rect.left, rect.right)
                                  for y in (rect.bottom, rect.top)]
                        xs, ys = zip(*points)
                        bounds = [min(xs), min(ys), max(xs), max(ys)]
                        if bounds[2] > bounds[0] and bounds[3] > bounds[1]:
                            destination['annotation_rect'] = bounds
                    result.append({'page': page_index, 'index': index, 'kind': ANNOTATION_TYPES[subtype],
                                   'contents': contents, 'author': _string(annotation, 'T') if include_text else '',
                                   'subject': _string(annotation, 'Subj') if include_text else '',
                                   'modified': _string(annotation, 'M') if include_text else '', 'destination': destination})
                finally:
                    raw.FPDFPage_CloseAnnot(annotation)
        finally:
            page.close()
    return result
