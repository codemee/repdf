# Third-party notices

RePDF is licensed under GPL-3.0-only. Its dependencies and OCR models retain
their own copyright and license terms; they are not all relicensed as GPL.

The version-specific review covers 45 dependency names / 46 locked version
records in `uv.lock`, including conditional, test, and build dependencies.
See [the package table](third_party/package-table.md),
[machine-readable evidence](third_party/locked-packages.json), and
[complete preserved notices](third_party/notices/).

- Qt / PySide6 / Shiboken: the open-source GPL-3.0 option is used for this
  GPL application. Commercial-license reference files do not indicate that
  RePDF has or requires a commercial Qt license. The Qt source notice snapshot
  includes QtBase, QtSvg, QtImageFormats, QtTranslations and PySide, including
  notices for components not necessarily present in the final executable.
- PDFium and pypdfium2: retain their BSD / Apache notices and the native
  PDFium build's complete dependency notices. Documentation has separate
  CC-BY-4.0 terms; no pypdfium2 documentation is incorporated into RePDF docs.
- ONNX Runtime, NumPy, OpenCV, Pillow, Shapely, cryptography and python-bidi:
  retain the full bundled-library notices. These include LGPL terms for
  GEOS, FFmpeg and python-bidi, and the GCC Runtime Library Exception where
  applicable. The PyInstaller bootloader exception permits GPL-3.0 RePDF
  executables; it does not waive other dependencies' requirements.
- OCR source code and conversion/packaging: copyright RapidOCR Authors,
  Apache-2.0. Upstream PaddleOCR model weights: copyright Baidu and/or the
  applicable PaddleOCR rights holders, Apache-2.0. RapidOCR converted the
  upstream models to ONNX; RePDF uses the supplied weights without modifying
  them. Neither project nor model names imply endorsement.
- Bundled OCR weights are `PP-OCRv6_det_small.onnx` and
  `PP-OCRv6_rec_small.onnx`. The optional PP-OCRv5 Korean, Thai, Cyrillic,
  Arabic, Devanagari, Greek, Tamil and Telugu recognition weights are
  downloaded from the official RapidOCR ModelScope registry. Exact artifact
  URLs, hashes and upstream model-card revisions are in
  [models.json](third_party/models.json). All ten reviewed weights have
  Apache-2.0 licensing evidence; the full Apache license and model notices
  are preserved under `third_party/notices/`.
- CPython uses its PSF license and included historical notices. The desktop
  license collection includes the license supplied with the actual build
  interpreter. Operating-system libraries and user-installed fonts are not
  newly licensed by RePDF. No external font package is bundled by this repo.
- The project owner confirmed ownership of the PDFPick-derived code and
  project assets. The SVG controls and toolbar drawing code are part of
  RePDF. Theme color inspiration does not incorporate third-party character
  artwork or grant any trademark rights.

Desktop releases include a platform-specific `*-licenses.zip`, containing
these notices, actual build-environment license files, source locations,
version inventory and SHA-256 checksums. This is a conservative superset of
the packages included by PyInstaller. License material is also embedded in
the application. Source distributions retain the review and build scripts.

The source locations and release instructions are part of the distribution
process: matching source and build material must remain available with
binary downloads. A notice archive alone does not replace corresponding
source obligations. See [the release review](docs/LICENSE_AUDIT.en.md).
