"""Text-layer search, executed only in the isolated PDF backend."""

from contextlib import closing
from statistics import median

import regex


def compile_query(query, regular_expression=False, case_sensitive=False, whole_word=False):
    if not query:
        raise ValueError('empty_query')
    source = query if regular_expression else regex.escape(query)
    flags = 0 if case_sensitive else regex.IGNORECASE
    pattern = regex.compile(source, flags)
    if whole_word:
        # End a possible verbose-mode trailing comment before closing our group.
        if pattern.flags & regex.VERBOSE:
            source += '\n'
        pattern = regex.compile(r'(?<!\w)(?:' + source + r')(?!\w)', flags)
    return pattern


def _bounds(entries):
    boxes = [box for _, box in entries if box is not None]
    if not boxes:
        return None
    return min(b[0] for b in boxes), min(b[1] for b in boxes), max(b[2] for b in boxes), max(b[3] for b in boxes)


def _lines(textpage):
    import pypdfium2.raw as raw
    lines, entries, section = [], [], 0

    def flush():
        nonlocal entries
        while entries and entries[0][0].isspace():
            entries.pop(0)
        while entries and entries[-1][0].isspace():
            entries.pop()
        bounds = _bounds(entries)
        if entries and bounds:
            lines.append({'entries': entries, 'bounds': bounds, 'section': section})
        entries = []

    previous_newline = False
    for index in range(textpage.count_chars()):
        value = raw.FPDFText_GetUnicode(textpage, index)
        if not value or value > 0x10FFFF or 0xD800 <= value <= 0xDFFF:
            continue
        char = chr(value)
        if char in '\r\n':
            # CRLF is a single line ending; two line endings split paragraphs.
            if char == '\n' and previous_newline == '\r':
                previous_newline = char
                continue
            if not any(not char.isspace() for char, _ in entries):
                section += 1
            flush()
            previous_newline = char
            continue
        previous_newline = False
        box = textpage.get_charbox(index)
        if not box or box[2] <= box[0] or box[3] <= box[1] or char.isspace():
            box = None
        if box and entries:
            previous = next((b for _, b in reversed(entries) if b), None)
            if previous:
                line_bounds = _bounds(entries)
                heights = max(box[3] - box[1], line_bounds[3] - line_bounds[1])
                widths = [b[2] - b[0] for _, b in entries[-32:] if b]
                if not widths:
                    widths = [previous[2] - previous[0]]
                # Small low glyphs (notably underscores) still belong to the
                # surrounding line; compare against its full vertical extent.
                vertical_gap = max(line_bounds[1] - box[3], box[1] - line_bounds[3])
                different_row = (abs((box[1] + box[3] - line_bounds[1] - line_bounds[3]) / 2) > heights * .5
                                 and vertical_gap > heights * .25)
                column_gap = box[0] - previous[2] > 3 * median(widths)
                if different_row or column_gap:
                    flush()
        entries.append((char, box))
    flush()
    return lines


def _paragraphs(lines):
    paragraphs = []
    for line in sorted(lines, key=lambda item: (-item['bounds'][3], item['bounds'][0])):
        left, bottom, right, top = line['bounds']
        candidates = []
        for paragraph in paragraphs:
            previous = paragraph[-1]
            a, b, c, d = previous['bounds']
            height = max(top - bottom, d - b)
            overlap = min(right, c) - max(left, a)
            if (line['section'] == previous['section'] and top < d - height * .25
                    and -height * .25 <= b - top <= height * 1.5
                    and overlap >= .5 * min(right - left, c - a)):
                candidates.append((abs(b - top), paragraph))
        if candidates:
            min(candidates, key=lambda item: item[0])[1].append(line)
        else:
            paragraphs.append([line])
    return paragraphs


def _cjk(char):
    return ('\u3400' <= char <= '\u9fff' or '\u3040' <= char <= '\u30ff'
            or '\uf900' <= char <= '\ufaff' or '\U00020000' <= char <= '\U000323af')


def normalized_box(page, box):
    left, bottom, right, top = page.get_bbox()
    width, height = right - left, top - bottom
    rotation = page.get_rotation()
    def point(x, y):
        if rotation == 90:
            return (y - bottom) / height, (x - left) / width
        if rotation == 180:
            return (right - x) / width, (y - bottom) / height
        if rotation == 270:
            return (top - y) / height, (right - x) / width
        return (x - left) / width, (top - y) / height
    corners = [point(x, y) for x in (box[0], box[2]) for y in (box[1], box[3])]
    xs, ys = zip(*corners)
    result = [max(0, min(xs)), max(0, min(ys)), min(1, max(xs)), min(1, max(ys))]
    return result if result[2] > result[0] and result[3] > result[1] else None


def search_page(page, pattern):
    with closing(page.get_textpage()) as textpage:
        paragraphs = _paragraphs(_lines(textpage))
    results, zero_width = [], 0
    for paragraph_id, lines in enumerate(paragraphs):
        entries = []
        for line in lines:
            if entries and not (_cjk(entries[-1][0]) and _cjk(line['entries'][0][0])):
                entries.append((' ', None))
            entries.extend(line['entries'])
        text = ''.join(char for char, _ in entries)
        spans, rects, match_rects = [], [], []
        # Finish timed matching before geometry conversion, so PDFium work does
        # not consume the regular-expression budget between iterator steps.
        matches = [match.span() for match in pattern.finditer(text, timeout=1)]
        for start, end in matches:
            if start == end:
                zero_width += 1
                continue
            boxes = [normalized_box(page, box) for _, box in entries[start:end] if box]
            boxes = [box for box in boxes if box]
            if boxes:
                spans.append([start, end])
                rects.extend(boxes)
                match_rects.append(boxes)
        if spans:
            results.append({'paragraph_id': paragraph_id, 'text': text, 'spans': spans,
                            'rects': rects, 'match_rects': match_rects, 'count': len(spans)})
    return results, zero_width


def search_document(request, emit):
    import pypdfium2 as pdfium
    pattern = compile_query(request['query'], request['regular_expression'], request['case_sensitive'],
                            request.get('whole_word', False))
    with closing(pdfium.PdfDocument(request['source'], password=request.get('password'))) as document:
        pages = request.get('pages')
        if pages is None:
            pages = list(range(len(document)))
        for position, index in enumerate(pages):
            with closing(document[index]) as page:
                paragraphs, zero_width = search_page(page, pattern)
            emit({'type': 'search_page', 'document_id': request['document_id'],
                  'generation': request['generation'], 'page': index, 'position': position + 1,
                  'total': len(pages), 'paragraphs': paragraphs, 'zero_width': zero_width})
