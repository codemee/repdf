import sys
import tomllib
from PySide6.QtCore import QLibraryInfo
from pathlib import Path
from PyInstaller.utils.hooks import collect_all, copy_metadata

root = Path(SPECPATH).parent
version = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))["project"]["version"]
data = [(str(root / "src/repdf/assets"), "repdf/assets")]
data += [(str(root / name), "repdf/licenses") for name in ("LICENSE", "NOTICE")]
data += [(str(root / "output/desktop/licenses"), "repdf/licenses/third-party")]
data += [(str(Path(QLibraryInfo.path(QLibraryInfo.LibraryPath.TranslationsPath)) / "qtbase_zh_TW.qm"), "repdf/assets")]
data += copy_metadata("repdf")
binaries = []
hiddenimports = ['bidi.algorithm']
for package in ("pypdfium2", "pypdfium2_raw", "rapidocr", "onnxruntime"):
    package_data, package_binaries, package_imports = collect_all(package)
    # Region OCR also needs detection; direction classification is unused.
    if package == "rapidocr":
        package_data = [(source, target) for source, target in package_data
                        if not source.endswith('.onnx') or Path(source).name in
                        {'PP-OCRv6_rec_small.onnx', 'PP-OCRv6_det_small.onnx'}]
    data += package_data
    binaries += package_binaries
    hiddenimports += package_imports

a = Analysis(
    [str(root / "packaging/launcher.py")],
    pathex=[str(root / "src")],
    binaries=binaries, datas=data, hiddenimports=hiddenimports,
    excludes=["pytest", "tkinter", "PySide6.QtPdf", "PySide6.QtPdfWidgets", "PySide6.QtQml",
              "PySide6.QtQuick", "PySide6.QtQuickWidgets", "PySide6.QtVirtualKeyboard"], noarchive=False,
)
sys.path.insert(0, str(root / "scripts"))
from collect_licenses import check_qt_binaries, without_unused_qt_plugins
a.binaries = without_unused_qt_plugins(a.binaries)
a.datas = without_unused_qt_plugins(a.datas)
check_qt_binaries(a.binaries)
pyz = PYZ(a.pure)
if sys.platform == "darwin":
    exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="repdf",
              console=False, upx=False, argv_emulation=False)
    coll = COLLECT(exe, a.binaries, a.datas, name="repdf", upx=False)
    app = BUNDLE(coll, name="RePDF.app",
                 icon=str(root / "output/desktop/repdf.icns"),
                 bundle_identifier="io.github.codemee.repdf",
                 version=version,
                 info_plist={"CFBundleShortVersionString": version,
                             "CFBundleName": "RePDF",
                             "CFBundleDisplayName": "RePDF",
                             "CFBundleDocumentTypes": [{
                                 "CFBundleTypeName": "PDF document",
                                 "CFBundleTypeRole": "Editor",
                                 "LSHandlerRank": "Alternate",
                                 "LSItemContentTypes": ["com.adobe.pdf"],
                             }],
                             "NSHighResolutionCapable": True})
else:
    exe = EXE(pyz, a.scripts, a.binaries, a.datas, name="repdf",
              console=False, upx=False,
              icon=str(root / "output/desktop/repdf.ico"))
