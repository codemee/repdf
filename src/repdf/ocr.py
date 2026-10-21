"""Optional, local OCR fallback for damaged PDF text mappings."""
from __future__ import annotations

import hashlib
import math
import re
import time
import unicodedata
from functools import lru_cache
from importlib.util import find_spec
from pathlib import Path

from PIL import ImageOps
from repdf.ocr_models import PROFILES, installed_profiles, model_available, model_path


class OcrError(RuntimeError):
    pass


class OcrModelMissing(OcrError):
    pass


def _clean_line(text: str) -> str:
    # Remove OCR segmentation spaces within CJK text; keep English word spaces.
    cjk = r'\u3400-\u9fff\uf900-\ufaff\U00020000-\U000323af'
    return re.sub(fr'(?<=[{cjk}]) +(?=[{cjk}])', '', text.strip())


def suspicious_text(text: str) -> bool:
    """Only flag explicit corruption; valid CJK, ligatures and private-use stay intact."""
    return any(char == '\ufffd' or 0xFDD0 <= ord(char) <= 0xFDEF
               or ord(char) & 0xFFFF in (0xFFFE, 0xFFFF) or unicodedata.category(char) == 'Cs'
               or (unicodedata.category(char) == 'Cc' and char not in '\r\n\t')
               for char in text)


MODEL_NAME = 'PP-OCRv6_rec_small.onnx'
MODEL_SHA256 = '6f327246b50388f3c176ae304bd95767ea6dc0c9ae92153ef8cbe210b3c14884'
DETECTION_MODEL = 'PP-OCRv6_det_small.onnx'
DETECTION_SHA256 = '090f04abcd9d9a7498bc4ebf677e4cb9bdce1fe4197ddb7e529f1ef44e1ff94f'


@lru_cache(maxsize=1)
def _engine(profile='builtin'):
    """Load only on first damaged selection, in the existing background process."""
    try:
        spec = find_spec('rapidocr')
        if spec is None or spec.origin is None:
            raise OcrError('RapidOCR is not installed. Run uv sync.')
        if profile not in PROFILES:
            raise OcrError('Unknown OCR language.')
        bundled = Path(spec.origin).parent / 'models'
        model = bundled / MODEL_NAME
        if profile != 'builtin':
            if not model_available(profile):
                raise OcrModelMissing('OCR language model is missing or damaged.')
            model = model_path(profile)
        if not model.is_file():
            raise OcrError('Bundled OCR model is missing. Reinstall RapidOCR 3.10.0.')
        if profile == 'builtin' and hashlib.sha256(model.read_bytes()).hexdigest() != MODEL_SHA256:
            raise OcrError('Bundled OCR model checksum mismatch.')
        from rapidocr import ModelType, OCRVersion, RapidOCR
        params = {
            'Global.use_det': False,
            'Global.use_cls': False,
            'Global.use_preprocess_img': False,
            'Global.log_level': 'error',
            'Rec.model_path': str(model),  # Explicit local path disables model downloads.
            'Det.model_path': str(bundled / DETECTION_MODEL),
            'EngineConfig.onnxruntime.intra_op_num_threads': 2,
            'EngineConfig.onnxruntime.inter_op_num_threads': 1,
        }
        if profile != 'builtin':
            params.update({'Rec.ocr_version': OCRVersion.PPOCRV5, 'Rec.model_type': ModelType.MOBILE,
                           'Rec.lang_type': profile})
        engine = RapidOCR(params=params)
        return engine
    except OcrError:
        raise
    except Exception as exc:
        raise OcrError(f'Cannot initialize RapidOCR: {exc}') from exc


def _line_regions(rects: list[list[float]]) -> list[list[float]]:
    """Keep selected glyph order and avoid including unselected line beginnings/ends."""
    if not rects:
        return []
    heights = sorted(bottom - top for _, top, _, bottom in rects)
    # A leading space/dash has almost no ink height. Use the selection's typical
    # full glyph height so these marks can join the following letters as well.
    typical_height = heights[len(heights) * 3 // 4]
    lines: list[list[float]] = []
    for left, top, right, bottom in rects:
        if lines:
            previous = lines[-1]
            # Underscores and dashes can sit entirely below/inside a letter's
            # vertical range. Compare centres against the taller glyph/line,
            # rather than requiring bounding boxes to overlap.
            centre_distance = abs((top + bottom - previous[1] - previous[3]) / 2)
            line_height = max(bottom - top, previous[3] - previous[1], typical_height)
            same_line = centre_distance <= 0.75 * line_height
            if same_line:
                previous[:] = [min(left, previous[0]), min(top, previous[1]),
                               max(right, previous[2]), max(bottom, previous[3])]
                continue
        lines.append([left, top, right, bottom])
    return lines


def _recognize_candidates(page, lines, profile, deadline, *, tolerate_errors=False):
    width, height = page.get_size()
    scale = 400 / 72
    if time.monotonic() >= deadline:
        raise OcrError('OCR time limit reached.')
    engine = _engine() if profile == 'builtin' else _engine(profile)
    output = []
    for left, top, right, bottom in lines:
        # Small padding preserves antialiased glyph edges without adding neighbours.
        x0, y0 = max(0, left * width - 0.5), max(0, top * height - 0.5)
        x1, y1 = min(width, right * width + 0.5), min(height, bottom * height + 0.5)
        if (x1 - x0) * (y1 - y0) * scale ** 2 > 20_000_000:
            raise OcrError('Selected OCR region is too large.')
        bitmap = page.render(scale=scale, crop=(x0, height - y1, width - x1, y0))
        try:
            image = ImageOps.expand(bitmap.to_pil().convert('RGB'), border=2, fill='white')
        finally:
            bitmap.close()
        if time.monotonic() >= deadline:
            raise OcrError('OCR time limit reached.')
        try:
            result = engine(image, use_det=False, use_cls=False, use_rec=True)
        except Exception as exc:
            if time.monotonic() >= deadline:
                raise OcrError('OCR time limit reached.') from exc
            if tolerate_errors:
                output.append(None)
                continue
            raise OcrError(f'RapidOCR failed: {exc}') from exc
        if time.monotonic() >= deadline:
            raise OcrError('OCR time limit reached.')
        if not result.txts or not result.scores:
            output.append(None)
            continue
        text = result.txts[0].strip()
        score = min(result.scores)
        if not text or suspicious_text(text) or not math.isfinite(score) or not .8 <= score <= 1:
            output.append(None)
        else:
            output.append((_clean_line(text), score))
    return output


_SCRIPT_NAMES = {'korean': ('HANGUL',), 'th': ('THAI',), 'cyrillic': ('CYRILLIC',),
                 'arabic': ('ARABIC',), 'devanagari': ('DEVANAGARI',), 'el': ('GREEK',),
                 'ta': ('TAMIL',), 'te': ('TELUGU',)}


def _choose_candidate(candidates):
    """Conservative heuristics, not calibrated cross-model probabilities."""
    baseline = candidates.get('builtin')
    alternatives = []
    for profile, candidate in candidates.items():
        if profile == 'builtin' or candidate is None:
            continue
        text, score = candidate
        letters = [char for char in text if unicodedata.category(char).startswith('L')]
        matching = sum(any(script in unicodedata.name(char, '') for script in _SCRIPT_NAMES[profile])
                       for char in letters)
        # A specialist returning Latin gibberish must not replace multilingual text.
        if not letters or matching / len(letters) < .6:
            continue
        if baseline is not None and score < .9:
            continue
        alternatives.append((score, text))
    alternatives.sort(reverse=True)
    if alternatives:
        score, text = alternatives[0]
        # Conflicting scripts with nearly equal evidence remain uncertain.
        ambiguous = len(alternatives) > 1 and score - alternatives[1][0] < .03
        if not ambiguous and (baseline is None or score + .04 > baseline[1] + .02):
            return text
    if baseline is not None:
        return baseline[0]
    raise OcrError('OCR result is empty, damaged, ambiguous or low confidence.')


def recognize_selection(page, rects: list[list[float]], *, profile='builtin') -> str:
    """Recognize each line, optionally comparing only already installed models."""
    if not rects:
        raise OcrError('No selected text bounds are available.')
    lines = _line_regions(rects)
    if len(lines) > 30:
        raise OcrError('Please select at most 30 lines for OCR.')
    deadline = time.monotonic() + 60
    if profile != 'auto':
        candidates = _recognize_candidates(page, lines, profile, deadline)
        if any(candidate is None for candidate in candidates):
            raise OcrError('OCR result is empty, damaged or low confidence.')
        return '\n'.join(candidate[0] for candidate in candidates)
    results = {'builtin': _recognize_candidates(page, lines, 'builtin', deadline, tolerate_errors=True)}
    # Model-major order loads each engine once per request, rather than once per line.
    # Rendering one crop at a time also avoids retaining thirty large line images.
    for installed in installed_profiles():
        if time.monotonic() >= deadline:
            raise OcrError('OCR time limit reached.')
        try:
            results[installed] = _recognize_candidates(page, lines, installed, deadline, tolerate_errors=True)
        except OcrError:
            # A model removed/damaged after discovery must not trigger a download.
            if time.monotonic() >= deadline:
                raise OcrError('OCR time limit reached.')
            continue
    if time.monotonic() >= deadline:
        raise OcrError('OCR time limit reached.')
    return '\n'.join(_choose_candidate({name: values[index] for name, values in results.items()})
                     for index in range(len(lines)))


def recognize_region(page, start, end, *, profile='builtin') -> dict[str, object]:
    """OCR the displayed page rectangle, including image-only PDF content."""
    if len(start) != 2 or len(end) != 2:
        raise OcrError('Invalid OCR region.')
    values = [float(value) for value in (*start, *end)]
    if not all(math.isfinite(value) for value in values):
        raise OcrError('Invalid OCR region.')
    x0, x1 = sorted(max(0, min(1, value)) for value in (values[0], values[2]))
    y0, y1 = sorted(max(0, min(1, value)) for value in (values[1], values[3]))
    width, height = page.get_size()
    crop_width, crop_height = (x1 - x0) * width, (y1 - y0) * height
    if min(crop_width, crop_height) < 2:
        return {'text': '', 'rects': []}
    spec = find_spec('rapidocr')
    if spec is None or spec.origin is None:
        raise OcrError('RapidOCR is not installed. Run uv sync.')
    model = Path(spec.origin).parent / 'models' / DETECTION_MODEL
    if not model.is_file() or hashlib.sha256(model.read_bytes()).hexdigest() != DETECTION_SHA256:
        raise OcrError('Bundled OCR detection model is missing or damaged.')
    scale = min(400 / 72, math.sqrt(19_000_000 / (crop_width * crop_height)))
    bitmap = page.render(scale=scale, crop=(x0 * width, (1 - y1) * height,
                                          (1 - x1) * width, y0 * height))
    try:
        image = bitmap.to_pil().convert('RGB')
    finally:
        bitmap.close()
    try:
        engine = _engine() if profile in ('builtin', 'auto') else _engine(profile)
        result = engine(image, use_det=True, use_cls=False, use_rec=False)
    except OcrError:
        raise
    except Exception as exc:
        raise OcrError(f'RapidOCR failed: {exc}') from exc
    if result.boxes is None or len(result.boxes) == 0:
        return {'text': '', 'rects': []}
    rects = []
    for box in result.boxes:
        xs, ys = zip(*[(float(x), float(y)) for x, y in box])
        rects.append([x0 + min(xs) / image.width * (x1 - x0),
                      y0 + min(ys) / image.height * (y1 - y0),
                      x0 + max(xs) / image.width * (x1 - x0),
                      y0 + max(ys) / image.height * (y1 - y0)])
    rects = _line_regions(rects)
    return {'text': recognize_selection(page, rects, profile=profile), 'rects': rects, 'ocr_used': True}
