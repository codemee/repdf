# 授權核對

[English](LICENSE_AUDIT.en.md)

核對日期：2026-10-27。範圍為目前 `uv.lock` 的 **45 個第三方套件、46 筆版本紀錄**（NumPy 因 Python 版本有兩筆），以及內建與可下載的 **10 個 OCR 模型**。包含執行期、條件式、測試與建置依賴；不代表每個套件都放進執行檔。

## 結果與證據

- 未發現目前選用的依賴授權與專案 GPL-3.0-only 不相容的必要執行元件。這個結論以保留各元件條款、聲明及履行原始碼散布義務為前提，並非將依賴全部改為 GPL。
- PDFPick 與 RePDF 的權利人已確認為同一人 Shin-Wei Hwang，並指定 GPL-3.0-only。專案自有圖示與繪圖程式沿用本專案授權；未額外引入角色圖像或字型套件。
- [逐項套件表](../third_party/package-table.md) 列出每個版本及授權。[機器可讀紀錄](../third_party/locked-packages.json) 保存套件 metadata 來源、原始碼位置、雜湊與授權文件路徑；固定版本 wheel 的補抓資料以 `uv.lock` SHA-256 校驗。
- 已保存完整套件聲明與 Qt 官方固定版本原始碼中的授權／歸屬文件，見 [notices](../third_party/notices/)。Qt 快照涵蓋 QtBase、QtSvg、QtImageFormats、QtTranslations 與 PySide；屬保守的較大集合，亦有未使用的測試、平台及工具聲明，不應把其中任一授權單獨視為本程式實際連結的授權。

## 需要特別處理的元件

| 元件 | 核對與處理 |
| --- | --- |
| Qt / PySide6 / Shiboken 6.11.2 | 採開源 GPL-3.0 路徑。wheel 只帶商業授權參考文件，已補上官方 `v6.11.2` 的開源條款與原生元件歸屬。`qt-sources.json` 固定來源提交；不宣稱取得商業 Qt 授權。 |
| PDFium / pypdfium2 | 保留 Apache／BSD 條款與原生 build 的完整第三方聲明，包括 FreeType、ICU、JPEG、PNG、TIFF、OpenJPEG、zlib 等。文件範例另有 CC-BY-4.0；本專案沒有納入其文件內容。 |
| RapidOCR / PaddleOCR | 程式碼與模型分開歸屬。程式碼為 RapidOCR Authors；模型權重為 Baidu／相應 PaddleOCR 權利人，均有 Apache-2.0 證據。RePDF 不修改模型權重。 |
| python-bidi | LGPL-3.0，連同 Rust 依賴授權清單保留；提供對應原始碼位置。 |
| Shapely / GEOS | Shapely 為 BSD；隨附 GEOS 為 LGPL-2.1，保留其完整條款與對應來源。Windows 環境確認 GEOS 3.14.1。 |
| OpenCV / FFmpeg | Python 包裝、OpenCV 與 FFmpeg 分別有 MIT、Apache-2.0、LGPL 條款，不能只標成 Apache。保留 wheel 的 `LICENSE-3RD-PARTY.txt` 與 build/source 指引。 |
| NumPy / 原生數值函式庫 | 保留 OpenBLAS、LAPACK、各 SIMD 元件條款；GCC runtime 使用其 Runtime Library Exception，不將其誤判為無例外的 GPL 限制。 |
| cryptography / OpenSSL | 保留 Apache／BSD 雙授權及 OpenSSL 授權；Windows 環境確認 OpenSSL 4.0.3。 |
| Pillow / ONNX Runtime | 連同影像 codec 與原生依賴的完整合併聲明保存，不能只列主套件 MIT。 |
| Certifi / tqdm | 保留 MPL-2.0 與適用 MIT 聲明；未修改套件檔案，提供對應 source archive。 |
| PyInstaller / hooks | 建置工具的 GPL 與 bootloader 例外允許輸出 GPL-3.0 應用；不會免除其他依賴義務。 |
| CPython | 發行包收錄建置時解譯器的實際 `LICENSE.txt`；作業系統函式庫與使用者字型不會因此改為 GPL。 |

## OCR 模型

- 內建 `PP-OCRv6_det_small.onnx`、`PP-OCRv6_rec_small.onnx`：實體檔案雜湊與 RapidOCR 附帶的 `MODEL_LICENSES.md` 一致。
- 額外的韓文、泰文、西里爾字母、阿拉伯文、天城文、希臘文、泰米爾文、泰盧固文：逐一核對 PaddlePaddle 官方模型卡，均標示 Apache-2.0；官方 RapidOCR ModelScope 倉庫亦標示 Apache License 2.0。
- 專案下載 URL 與雜湊固定於 RapidOCR 3.10.0 登錄；八筆 SHA-256 均已與安裝套件的正式模型登錄比對。官方原始模型與 RapidOCR 轉換檔不要求位元相同，轉換檔身分以 RapidOCR 登錄雜湊確認。
- [models.json](../third_party/models.json) 記錄 10 個模型、八份官方模型卡的固定 revision 及權重下載雜湊。完整 Apache 條款與模型歸屬另見 [第三方聲明](../THIRD_PARTY_NOTICES.md)。
- 官方依據：[RapidOCR 模型授權](https://rapidai.github.io/RapidOCRDocs/main/en/model_licenses/)、[Qt 授權](https://doc.qt.io/qt-6/licensing.html)、[PyInstaller 例外](https://pyinstaller.org/en/stable/license.html)。

## 發行流程

- `scripts/collect_licenses.py` 不打包程式，只彙整目前平台安裝套件的完整授權、既有核對證據、Python 條款、版本清單、對應原始碼位置及檔案雜湊。
- `uv.lock` 與核對紀錄不一致、套件版本未核對、缺少授權資料時會停止。FlatBuffers 的 wheel 未附全文，使用已保存的官方固定版本 Apache-2.0 條款補齊。
- 雲端桌面打包呼叫這個步驟，將結果嵌入程式並附上平台別的 `*-licenses.zip`。PyInstaller 收集到未核對範圍內的 Qt 模組時亦會停止；目前核對範圍為 QtBase 的 Core／Gui／Widgets／Network／PrintSupport／OpenGL／DBus 及 QtSvg。
- Python sdist 包含 `uv.lock`、建置腳本、打包設定、技術文件與核對證據；wheel 附上專案授權與第三方摘要，其依賴各自安裝。
- 發布二進位檔時，必須在下載處明確提供相同版本的 RePDF 原始碼、建置程序，以及相關 copyleft 元件的對應原始碼取得方式，並維持可用；必要時鏡像保存。`SOURCES.txt` 與 manifest 提供固定版本來源，但「只有授權 ZIP」不等於已履行原始碼義務。Qt/PySide、GEOS、OpenSSL 等來源 URL 已確認可存取；原生 build recipe 的完整性、來源持續可用性與最終實際發行包仍須在該次雲端發布確認。
- 本次完成的是目前程式碼、鎖定依賴與模型的授權核對及發行流程補強；未本機打包、未產生或發布新執行檔，也沒有把過去已發布的執行檔追溯認定為已通過新檢查。
