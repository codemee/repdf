import pytest

from repdf import ocr, render_worker
from test_ocr import damaged_pdf


@pytest.mark.parametrize('candidates,expected', [
    ({'builtin': ('Copy this text', .99), 'korean': ('안녕하세요', .94)}, 'Copy this text'),
    ({'builtin': ('這是中文', .99), 'korean': None}, '這是中文'),
    ({'builtin': ('錯誤中文字', .96), 'korean': ('안녕하세요', .99)}, '안녕하세요'),
    ({'builtin': None, 'korean': ('안녕하세요', .85)}, '안녕하세요'),
    ({'builtin': ('Good text', .9), 'korean': ('Wrong Latin text', .99)}, 'Good text'),
    ({'builtin': ('這是中文', .92), 'th': ('สวัสดี', .98)}, 'สวัสดี'),
    ({'builtin': ('原文', .9), 'korean': ('안녕하세요', .97), 'th': ('สวัสดี', .96)}, '原文'),
])
def test_auto_candidate_selection_requires_script_evidence(candidates, expected):
    assert ocr._choose_candidate(candidates) == expected


@pytest.mark.parametrize('candidates', [
    {'builtin': None, 'korean': None},
    {'builtin': None, 'korean': ('Latin gibberish', .99)},
    {'builtin': None, 'korean': ('안녕하세요', .97), 'th': ('สวัสดี', .96)},
])
def test_uncertain_auto_results_fail_instead_of_guessing(candidates):
    with pytest.raises(ocr.OcrError, match='ambiguous'):
        ocr._choose_candidate(candidates)


def test_auto_loads_each_installed_model_once_for_all_lines(monkeypatch):
    monkeypatch.setattr(ocr, 'installed_profiles', lambda: ('korean',))
    calls = []
    def recognize(page, lines, profile, deadline, **kwargs):
        calls.append((profile, len(lines)))
        return ([('English', .99), None] if profile == 'builtin'
                else [None, ('안녕하세요', .99)])
    monkeypatch.setattr(ocr, '_recognize_candidates', recognize)
    assert ocr.recognize_selection(None, [[.1, .1, .9, .2], [.1, .4, .9, .5]], profile='auto') == 'English\n안녕하세요'
    assert calls == [('builtin', 2), ('korean', 2)]


def test_auto_ignores_unavailable_specialist_without_downloading(monkeypatch):
    monkeypatch.setattr(ocr, 'installed_profiles', lambda: ('korean',))
    def recognize(page, lines, profile, deadline, **kwargs):
        if profile == 'korean':
            raise ocr.OcrModelMissing('Removed during recognition')
        return [('Original text', .99)]
    monkeypatch.setattr(ocr, '_recognize_candidates', recognize)
    assert ocr.recognize_selection(None, [[.1, .1, .9, .2]], profile='auto') == 'Original text'


def test_auto_time_limit_cannot_be_hidden_by_specialist_failure(monkeypatch):
    clock = [0]
    monkeypatch.setattr(ocr.time, 'monotonic', lambda: clock[0])
    monkeypatch.setattr(ocr, 'installed_profiles', lambda: ('korean',))
    def recognize(page, lines, profile, deadline, **kwargs):
        if profile == 'korean':
            clock[0] = 61
            raise ocr.OcrError('Inference failed')
        return [('Original text', .99)]
    monkeypatch.setattr(ocr, '_recognize_candidates', recognize)
    with pytest.raises(ocr.OcrError, match='time limit'):
        ocr.recognize_selection(None, [[.1, .1, .9, .2]], profile='auto')


def test_auto_without_downloaded_models_recovers_original_offline(qapp, tmp_path, monkeypatch):
    from rapidocr.utils.download_file import DownloadFile
    monkeypatch.setattr(ocr, 'installed_profiles', lambda: ())
    monkeypatch.setattr(DownloadFile, 'run', lambda *_a: pytest.fail('Unexpected download'))
    path = tmp_path / 'damaged.pdf'
    damaged_pdf(path)
    result = render_worker.extract_selection_result(path, 0, [.12, .22], [.78, .27],
                                                    allow_ocr=True, ocr_profile='auto')
    assert result['text'] == 'Copy this text' and result['ocr_used']


def test_auto_successful_inference_still_obeys_total_deadline(monkeypatch):
    clock = [0]
    monkeypatch.setattr(ocr.time, 'monotonic', lambda: clock[0])
    monkeypatch.setattr(ocr, 'installed_profiles', lambda: ())
    def late_result(*args, **kwargs):
        clock[0] = 61
        return [('Text', .99)]
    monkeypatch.setattr(ocr, '_recognize_candidates', late_result)
    with pytest.raises(ocr.OcrError, match='time limit'):
        ocr.recognize_selection(None, [[.1, .1, .9, .2]], profile='auto')
