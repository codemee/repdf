"""OCR model catalog pinned to the official RapidOCR 3.10.0 manifest."""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
import sys

PROFILES = {
    'auto': {'label': '自動＋已下載模型'},
    'builtin': {'label': '自動'},
    'korean': {
        'label': '韓文',
        'url': 'https://www.modelscope.cn/models/RapidAI/RapidOCR/resolve/v3.10.0/onnx/PP-OCRv5/rec/korean_PP-OCRv5_rec_mobile.onnx',
        'sha256': 'cd6e2ea50f6943ca7271eb8c56a877a5a90720b7047fe9c41a2e541a25773c9b',
    },
    'th': {
        'label': '泰文',
        'url': 'https://www.modelscope.cn/models/RapidAI/RapidOCR/resolve/v3.10.0/onnx/PP-OCRv5/rec/th_PP-OCRv5_rec_mobile.onnx',
        'sha256': 'de541dd83161c241ff426f7ecfd602a0ba77d686cf3ab9a6c255ea82fd08006e',
    },
    'cyrillic': {
        'label': '俄文／烏克蘭文（西里爾字母）',
        'url': 'https://www.modelscope.cn/models/RapidAI/RapidOCR/resolve/v3.10.0/onnx/PP-OCRv5/rec/cyrillic_PP-OCRv5_rec_mobile.onnx',
        'sha256': '90f761b4bfcce0c8c561c0cb5c887b0971d3ec01c32164bdf7374a35b0982711',
    },
    'arabic': {
        'label': '阿拉伯文',
        'url': 'https://www.modelscope.cn/models/RapidAI/RapidOCR/resolve/v3.10.0/onnx/PP-OCRv5/rec/arabic_PP-OCRv5_rec_mobile.onnx',
        'sha256': 'c1192e632d0baa9146ae5b756a0e635e3dc63c1733737ebfd1629e87144e9295',
    },
    'devanagari': {
        'label': '印地文／尼泊爾文（天城文）',
        'url': 'https://www.modelscope.cn/models/RapidAI/RapidOCR/resolve/v3.10.0/onnx/PP-OCRv5/rec/devanagari_PP-OCRv5_rec_mobile.onnx',
        'sha256': 'd6f0a906580e3fa6b324a318718f1f31f268b6ea8ef985f91c2012a37f52c91e',
    },
    'el': {
        'label': '希臘文',
        'url': 'https://www.modelscope.cn/models/RapidAI/RapidOCR/resolve/v3.10.0/onnx/PP-OCRv5/rec/el_PP-OCRv5_rec_mobile.onnx',
        'sha256': 'b4368bccd557123c702b7549fee6cd1e94b581337d1c9b65310f109131542b7f',
    },
    'ta': {
        'label': '泰米爾文',
        'url': 'https://www.modelscope.cn/models/RapidAI/RapidOCR/resolve/v3.10.0/onnx/PP-OCRv5/rec/ta_PP-OCRv5_rec_mobile.onnx',
        'sha256': 'a42448808b7dea87597336f12438935f40353f1949e8360acd9e06b4da21bfe1',
    },
    'te': {
        'label': '泰盧固文',
        'url': 'https://www.modelscope.cn/models/RapidAI/RapidOCR/resolve/v3.10.0/onnx/PP-OCRv5/rec/te_PP-OCRv5_rec_mobile.onnx',
        'sha256': 'a3690451b50028a09a3316a1274f7c05728151ea3f8fd392696397a7fefcbd92',
    },
}


def model_directory():
    # Never write to site-packages, a frozen bundle, or PyInstaller's extraction dir.
    if sys.platform == 'win32':
        base = Path(os.environ.get('LOCALAPPDATA', Path.home() / 'AppData/Local'))
    elif sys.platform == 'darwin':
        base = Path.home() / 'Library/Application Support'
    else:
        base = Path(os.environ.get('XDG_DATA_HOME', Path.home() / '.local/share'))
    return base / 'RePDF/ocr/models'


def model_path(profile):
    return model_directory() / PROFILES[profile]['url'].rsplit('/', 1)[1]


def model_available(profile):
    if profile in ('auto', 'builtin'):
        return True
    path = model_path(profile)
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest() == PROFILES[profile]['sha256']
    except OSError:
        return False


def installed_profiles():
    return tuple(profile for profile, info in PROFILES.items()
                 if 'url' in info and model_available(profile))
