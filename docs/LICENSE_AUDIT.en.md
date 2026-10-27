# License review

[繁體中文](LICENSE_AUDIT.md)

Reviewed on 2026-10-27: **45 third-party dependency names / 46 locked version
records** in `uv.lock` (two conditional NumPy versions), and **10 OCR model
artifacts**. Runtime, conditional, test and build dependencies are included;
the list is a conservative superset of packages shipped in an executable.

## Findings and evidence

No required runtime component with an identified license conflict with
GPL-3.0-only was found, provided its own notices, terms and corresponding
source requirements are fulfilled. Dependencies are not all relicensed GPL.
The owner confirmed that PDFPick-derived code and RePDF share the same
rights holder, Shin-Wei Hwang. Project icons and drawing code are covered by
the project license; no character artwork or font package was introduced.

The [package table](../third_party/package-table.md) lists every locked
version and reviewed terms. [locked-packages.json](../third_party/locked-packages.json)
records metadata sources, source locations, hashes and complete notice paths.
Supplemental wheels were checked against hashes in `uv.lock`.
[Preserved notices](../third_party/notices/) include the official fixed
QtBase, QtSvg, QtImageFormats, QtTranslations and PySide source licensing
files. This snapshot includes unused tests, tools and platforms: its mere
presence does not mean every component is linked into RePDF.

## Components needing additional handling

| Component | Review and handling |
| --- | --- |
| Qt / PySide6 / Shiboken 6.11.2 | Use the open-source GPL-3.0 option. Wheels contain only a commercial-reference license file; official `v6.11.2` open-source terms and native attributions were added. Source commits are fixed in `qt-sources.json`. No commercial Qt entitlement is claimed. |
| PDFium / pypdfium2 | Preserve Apache/BSD terms and the complete native build dependency notices, including FreeType, ICU, JPEG, PNG, TIFF, OpenJPEG and zlib. Documentation has separate CC-BY-4.0 terms; it is not incorporated into RePDF documentation. |
| RapidOCR / PaddleOCR | Code is attributed to RapidOCR Authors; weights to Baidu and/or the applicable PaddleOCR rights holders. Apache-2.0 evidence covers both, with separate ownership. RePDF does not modify weights. |
| python-bidi | LGPL-3.0 and Rust dependency notices; preserve terms and corresponding source access. |
| Shapely / GEOS | BSD wrapper with LGPL-2.1 GEOS; preserve both and source access. Windows environment contains GEOS 3.14.1. |
| OpenCV / FFmpeg | MIT packaging, Apache-2.0 OpenCV and LGPL FFmpeg; preserve the full wheel third-party notices and build/source directions. |
| NumPy | Preserve OpenBLAS, LAPACK, SIMD notices and the GCC Runtime Library Exception. Do not treat the runtime as GPL without that exception. |
| cryptography / OpenSSL | Preserve Apache/BSD alternatives and OpenSSL attribution; Windows environment contains OpenSSL 4.0.3. |
| Pillow / ONNX Runtime | Preserve full codec and native dependency notices, not just the main package license. |
| Certifi / tqdm | Retain MPL-2.0 and applicable MIT notices. Package files are unmodified; corresponding source archive locations are recorded. |
| PyInstaller / hooks | The bootloader exception permits GPL-3.0 executables without waiving dependency obligations. |
| CPython | Collect the actual build interpreter's license. OS libraries and user fonts do not become GPL through use by RePDF. |

## Models

The actual bundled `PP-OCRv6_det_small.onnx` and `PP-OCRv6_rec_small.onnx`
hashes match the installed RapidOCR `MODEL_LICENSES.md`. Official PaddlePaddle
model cards for Korean, Thai, Cyrillic, Arabic, Devanagari, Greek, Tamil and
Telugu all specify Apache-2.0. The official RapidOCR ModelScope repository
also specifies Apache License 2.0. All eight conversion hashes in the app
match the RapidOCR 3.10.0 registry. Original PaddleOCR artifacts need not be
byte-identical to RapidOCR conversions: conversion identity is established
through the RapidOCR registry hashes.

[models.json](../third_party/models.json) records all ten artifacts and
fixed revisions for all eight upstream model cards. Preserve the Apache
terms, RapidOCR conversion notice and upstream model ownership in
[THIRD_PARTY_NOTICES.md](../THIRD_PARTY_NOTICES.md).

Primary guidance: [RapidOCR model licensing](https://rapidai.github.io/RapidOCRDocs/main/en/model_licenses/),
[Qt licensing](https://doc.qt.io/qt-6/licensing.html), and
[PyInstaller's exception](https://pyinstaller.org/en/stable/license.html).

## Distribution process and limits

- `scripts/collect_licenses.py` collects actual platform license files,
  preserved evidence, Python terms, a version inventory, corresponding source
  locations and file hashes without building an executable.
- Lock changes, unreviewed versions or missing license material stop the
  process. FlatBuffers' wheel lacks the full text; the pinned official
  Apache-2.0 license is provided as a supplement.
- Cloud desktop builds embed this collection and attach a platform-specific
  `*-licenses.zip`. PyInstaller rejects Qt modules outside the reviewed
  QtBase Core/Gui/Widgets/Network/PrintSupport/OpenGL/DBus and QtSvg scope.
- Source distributions retain the lockfile, build and packaging scripts,
  technical docs and evidence. Python wheels contain the project license
  and third-party summary; dependencies install as separate distributions.
- Binary downloads must clearly provide access to matching RePDF source,
  build material and applicable copyleft component sources, maintaining
  availability and mirroring when needed. `SOURCES.txt` and manifests give
  version-specific locations, but a notice archive alone is not corresponding
  source compliance. Qt/PySide, GEOS and OpenSSL source URLs were checked;
  complete native build recipes, continuing availability and actual binary
  contents still require verification for each cloud release.
- This review covers the current source, lockfile and models and adds release
  safeguards. No executable was built locally or published. Previously
  published binaries are not retrospectively certified by this review.
