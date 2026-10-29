# RePDF 實作與維護指南

[繁體中文](IMPLEMENTATION.md) | [English](IMPLEMENTATION.en.md)

本文件描述 RePDF 目前的程式架構、主要資料流、重要設計決策與修改注意事項。RePDF 代表 Read the PDF，定位為支援搜尋、書籤、OCR 與頁面重組的 PDF 閱讀器；命令、套件與 Python 模組名稱維持 `repdf`。若要新增功能或除錯，建議先閱讀本文件，再從 `src/repdf/app.py` 進入程式。

## 1. 專案概觀

RePDF 是支援 Windows 與 macOS 的 Python 桌面程式，主要功能包括：

1. 以可勾選、拖曳排序及關閉的標籤頁開啟多個 PDF。
2. 按可見頁載入預覽，提供縮放、全螢幕、搜尋、書籤、連結與頁碼導覽。
3. 在整合列印視窗設定頁面範圍、印表機與紙張，預覽確認後逐頁送印。
4. 選字複製、OCR 辨識及內嵌點陣圖片擷取。
5. 拖曳調整標籤與頁面排列，勾選頁面後重組或拆分輸出。

執行環境由 `uv` 管理，Python 版本需求為 3.11 以上。Clone 儲存庫後，在專案目錄執行：

```powershell
uv sync
uv run repdf
uv run --locked python -m pytest
```

## 2. 技術組成

| 套件 | 用途 |
| --- | --- |
| PySide6 | 視窗、控制項、主題、執行緒池與 Qt 訊號 |
| pypdf（crypto extra） | 驗證及解鎖來源 PDF、讀取頁數、無損複製選取頁面 |
| cryptography | 提供 AES PDF 加解密所需的原生實作，由 uv 與桌面打包自動收集 |
| pypdfium2 | 在獨立處理程序中將 PDF 頁面渲染為縮圖 |
| Pillow | 將 PDFium bitmap 儲存為 PNG |
| RapidOCR（rtl extra）／ONNX Runtime | 本機 OCR 推論、內建多語言與額外文字系統模型；RTL extra 提供阿拉伯文所需處理 |
| Qt Network | 經確認後非同步下載額外模型，以 SHA256 校驗並原子寫入使用者資料目錄 |
| pytest | 核心與整合測試 |
| pytest-qt | Qt GUI 與非同步行為測試 |

## 3. 目錄與模組責任

```text
src/repdf/
├── app.py             主視窗與独立文件元件 DocumentView、標籤、GUI 事件與資料流協調
├── core.py            不依賴 GUI 的選取、驗證與 PDF 輸出邏輯
├── widgets.py         單一頁面預覽卡片 PageCard
├── page_view.py       可見頁排程、頁面卡片虛擬化與共用影像快取
├── navigation.py      書籤／註解側欄與內部連結跳頁控制
├── printing.py        列印設定、範圍快照與逐頁送印
├── print_preview.py   按需列印預覽與紙張配置畫布
├── pdf_annotations.py PDFium 註解內容與文字標示原文擷取
├── pdf_navigation.py  後端讀取書籤、連結註解與目的地座標
├── preview.py         全螢幕單頁／對頁／封面預覽、等比例適應、切頁與選頁
├── theme.py           系統深色／淺色模式與控制項樣式
├── workers.py         PDF 載入及輸出的 QRunnable 工作
├── renderer.py        常駐縮圖後端程序與主程序之間的通訊
├── ocr.py             OCR 推論、依語言切換引擎與離線模型校驗
├── ocr_models.py      固定版官方模型 URL／SHA256 與使用者模型目錄
├── ocr_languages.py   語言選單、非同步下載交談窗與重試控制
├── render_worker.py   子程序內的 PDFium 渲染服務
└── assets/            PNG 與 Windows ICO 應用程式圖示

tests/
├── test_core.py       選取規則、PDF 驗證與輸出測試
├── test_gui.py        GUI 狀態、多檔標籤、跨檔輸出與預覽整合測試
└── test_renderer.py   各文件要求合併、優先順序與取消測試
```

## 4. 啟動與元件生命週期

公開入口為 `repdf.entrypoint:main`，一般啟動交由 `repdf.app:main`；封裝版渲染服務與 `--self-test` 由 entrypoint 分派。

啟動順序刻意設計如下：

1. `start_render_backend()` 先啟動常駐 PDF 預覽子程序。
2. 建立 `QApplication`。
3. `configure_application()` 設定 Fusion 樣式、圖示與繁中字型回退。
4. 建立 `ThemeController`，套用目前系統配色並監聽後續變化。
5. 建立 `MainWindow`，把已啟動的預覽後端交給 `RenderService`。

不要把預覽後端移回 GUI 執行緒，也不要直接在多個執行緒中呼叫 PDFium。PDFium 本身不是 thread-safe；目前用單一常駐子程序隔離原生渲染狀態，並確保主視窗不會因預覽工作凍結。

視窗關閉時，`closeEvent()` 會：

- 設定 `_closing`，停止各文件縮放 timer，讓未完成的舊結果失效。
- 結束預覽子程序。
- 清除尚未開始的 Qt 工作並等待進行中的輸出工作結束。
- 清理預覽 PNG 暫存目錄。

## 5. 主視窗與狀態

主畫面在 `MainWindow.__init__()` 中建立，分為三個區域：

- 上方固定工具列：開啟 PDF、輸出選取頁面、固定寬度比例顯示及其右側的比例滑桿。點擊比例回到 100%，完整縮放說明集中於比例 tooltip。放大／縮小 QAction 掛於主視窗，僅提供快捷鍵。檔案操作由 QAction 統一管理啟用狀態與快捷鍵，完整來源路徑顯示於標籤 tooltip；視窗標題僅為 `RePDF <版本>`，不隨語言與目前檔案改變。
- 奇偶頁三態核取方塊位於各頁頁首核取方塊右側；單數頁提供單數工具、雙數頁提供雙數工具，操作該文件的原始頁碼。中央為標籤頁與各文件的可捲動頁面網格。
- `close_tab_action` 採 `QKeySequence.StandardKey.Close` 的平台標準按鍵，快捷鍵作用於目前視窗，並呼叫既有 `close_tab()` 清理文件。關閉期間或沒有標籤時停用，關閉按鈕 tooltip 顯示本機可用按鍵。
- 下方狀態列：載入、選取及輸出進度。

`MainWindow` 管理共享工具列、`QTabWidget`、固定文件 ID 與輸出工作 ID；`DocumentView` 各自持有來源、頁數、`selected_pages`、`page_order`、`page_cards`、縮放比例、渲染世代與捲動區。切換標籤時同步工具列與奇偶頁三態，不重建文件內容。標籤核取方塊與關閉按鈕綁定文件物件，不以易變的標籤索引保存狀態。

`_active_tasks` 保留 `QRunnable` 的 Python 參考，完成或失敗後才移除。背景載入以文件 ID 回傳；輸出完成以 `_export_id` 回傳，不受目前標籤影響。

## 6. PDF 載入流程

`choose_pdf()` 使用多選對話框，與多檔拖入共用 `load_pdfs()`：

1. 依輸入順序建立載入中的標籤；同一 resolved 路徑已存在時切換到既有標籤。
2. 以 `LoadPdfTask` 在共用 `QThreadPool` 中呼叫 `core.inspect_pdf()`。
3. 開檔先讀取頁樹根節點的 `/Count`，避免以 `len(reader.pages)` 展開全頁樹；缺少有效計數才回退完整檢查。頁面內容及實際尺寸在需要渲染時讀取。
4. `DocumentView` 的 `PageViewport` 只要求可見頁與前後各一個畫面範圍的預覽；背景標籤暫停預覽，影像保留在有上限的共用快取。
5. 失敗時移除該標籤，保留其他成功文件；同批錯誤在全部載入完成後合併呈現。
6. 已關閉文件的回傳結果只完成工作清理，不重新建立標籤。

### 密碼保護文件

- `inspect_pdf(source, password=None)` 先嘗試空密碼，讓只有權限密碼、不需開啟密碼的 PDF 直接讀取。
- 需要密碼時拋出 `PasswordRequiredError`；輸入錯誤時拋出 `IncorrectPasswordError`。兩者繼承保留供呼叫端相容的 `UnsupportedEncryptedPdfError`。
- `LoadPdfTask.password_required` 以文件 ID 與是否輸入錯誤通知主視窗；GUI 將密碼要求排隊，逐一顯示 `PdfPasswordDialog`，避免同時出現多個對話框。
- 接受後將密碼存於 `DocumentView.password` 並重試載入；取消只移除該標籤並完成該檔案的批次清理。
- 密碼輸入預設遮蔽，可勾選顯示；對話框結束後清空輸入欄位。密碼不寫入 QSettings、命令列或記錄。
- 預覽、全螢幕、文字、區域 OCR 與圖片擷取要求，以既有本機通訊附帶密碼，交給 PDFium 開啟原始文件；不建立解密後的暫存 PDF。
- `DocumentSelection` 以不參與 repr 的密碼欄位供輸出工作解鎖來源；各檔案使用自己的密碼。輸出一律產生未加密 PDF，對話框標題及完成訊息明示此行為。
- 關閉文件或程式時清除文件密碼參照，取消尚未執行的工作與密碼要求；載入／輸出任務完成後釋放密碼參照。背景程序完成要求後也移除密碼欄位及輸入行的參照。
- 使用 `pypdf[crypto]` 引入 `cryptography`，涵蓋 AES-128／AES-256；目前不提供輸出密碼設定。

## 7. 預覽渲染架構

### 7.1 為何使用獨立處理程序

`pypdfium2` 只在 `render_worker.py` 子程序內匯入。主 GUI 不直接載入 PDFium，避免原生函式庫的 thread-safety 與 GUI 字型／繪圖狀態互相影響。

`RenderService` 使用 stdin/stdout 傳送每行一筆 JSON：

請求：

```json
{
  "source": "C:/path/input.pdf",
  "scale": 1.3333333333,
  "output_dir": "C:/Temp/repdf-preview-...",
  "generation": 4
}
```

逐頁結果：

```json
{
  "type": "page",
  "generation": 4,
  "page": 0,
  "path": "C:/Temp/repdf-preview-.../g4-p0.png"
}
```

完成或失敗：

```json
{"type": "done", "generation": 4}
{"type": "error", "generation": 4, "message": "..."}
```

GUI 收到單頁結果後會把 PNG 完整複製成 `QImage`，立即刪除該暫存 PNG，再更新對應卡片。

文字複製模式下，頁面預覽接收拖曳的起點與終點，換算成頁面相對座標，透過 `RenderService.request_text()` 交給同一子程序。PDFium 依頁面旋轉角度還原 PDF 座標、找出兩端字元並擷取其間文字；找不到端點時依字元方框判定範圍。後端同時回傳 `text` 與實際字元的相對方框，GUI 據此繪製螢光標示。拖曳時使用 90 毫秒計時器更新預覽，放開滑鼠後才將最終結果寫入系統剪貼簿。切換模式、關閉文件或提出更新的選取要求會淘汰舊結果。影像型 PDF 不含文字時不覆寫剪貼簿。

### 7.2 最新要求優先

後端一次只執行一個渲染要求。`RenderService` 使用依文件 ID 索引的待處理佇列，各文件只保留最新一筆要求；目前標籤優先。主視窗每批最多兩頁，先可見頁、再附近頁，完成一批後重新根據 viewport 排程。捲動以 40ms 計時器合併要求；手動縮放仍等待 250ms 停頓，暫用舊影像縮放顯示。`cancel_pending()` 在離開標籤或關閉文件時移除尚未開始的要求。

世代編號由主視窗全域遞增，透過 `_render_documents` 對應到文件 ID。結果交給來源文件，與目前標籤或標籤順序無關；比例過期或文件已關閉的頁面結果直接清理暫存圖片。進行中的原生渲染不強制中斷，避免不安全的 PDFium 操作。

渲染要求可提供 `pages`（零起始頁碼陣列）以只產生指定頁面；省略時仍渲染整份文件。頁面結果附帶 `width_points`、`height_points`，供 Fit 與全螢幕依 PDF 實際尺寸計算比例。全螢幕使用負的文件 ID 作為獨立排程鍵與自己的世代編號，切頁立即淘汰舊結果，關閉時取消尚未開始的要求。

主視窗一律傳入 `pages`；不會因開檔或縮放而預覽全檔。`PreviewCache` 以文件 ID、原始頁碼及渲染比例為鍵，共用 128MiB 的 LRU 影像預算；離開附近範圍的卡片釋放 pixmap，關閉文件時移除其快取。此預算只計快取中的 `QImage`，不包含目前顯示的 pixmap、Qt 控制項、PDFium 控制代碼等整體程序記憶體。

後端的 `PdfDocumentCache` 最多保留三份 PDFium 文件，依來源路徑、檔案大小、修改時間與密碼識別，讓不同批次和全螢幕重用開檔結果。所有 PDFium 操作都在該後端程序的單一執行緒執行；關閉標籤會送出 `release_document`，後端結束時釋放全部控制代碼。

### 7.3 縮放定義

100% 以 Windows 標準 96 DPI 顯示 PDF 的 72 DPI 點數：

```text
render_scale = slider_percent / 100 × 96 / 72
```

因此 300pt 寬的頁面在 100% 時約為 400px。每一頁依自己的實際尺寸渲染，橫向頁面不會被強制壓成與直向頁面相同寬度。

Fit 使用最近點擊且仍可見的頁面，或距預覽區中央最近的頁面；扣除卡片標頭與卡片內邊距後，以可用寬／頁寬和可用高／頁高的較小值計算比例。高度不扣除整份文件網格的上下邊距，並在渲染後將參考頁面置中對齊 viewport，避免底部留白或露出下一頁。每個文件保留 Fit 模式與參考頁面，viewport resize 以 150ms timer 更新；手動縮放停止 Fit 模式。Fit 比例可超出手動滑桿的 25%–200% 範圍。

`FullscreenPreview` 是獨立的模態頂層視窗，保留文件縮放，核取方塊透過 `PageCard.set_selected()` 與 `DocumentView._page_selection_changed()` 同步選頁。以目前 `page_order` 建立群組：`single` 每頁一組、`spread` 從第一頁起兩頁一組、`cover` 第一頁單獨一組後再兩頁一組；最後剩一頁時單獨顯示。開啟時定位到包含目前預覽頁的群組。

顯示時保留 30px 選頁列，對頁依頁面寬度總和與最大高度計算共同縮放比例，使用 device pixel ratio 產生清晰預覽；一次只渲染目前群組，合計 raster 上限為 3000 萬像素。<kbd>F11</kbd>／<kbd>Esc</kbd> 返回，<kbd>←</kbd>、<kbd>↑</kbd>、<kbd>→</kbd>、<kbd>↓</kbd> 或 <kbd>Page Up</kbd>／<kbd>Page Down</kbd> 切換群組。

主視窗與全螢幕視窗各自安裝 QApplication event filter，僅攔截自己的視窗內未帶修飾鍵的導覽按鍵，不影響檔案對話框。一般預覽對應捲動條的 single/page step；Fit 模式切換參考頁並重新適應。即使縮放滑桿或全螢幕核取方塊有焦點，導覽按鍵仍操作預覽。

滑桿有 250ms 防抖；連續拖動時只會在停止變動後送出渲染要求。若修改比例範圍或 DPI 定義，需同步檢查：

- `DocumentView._preview_scale()`
- `DocumentView._target_preview_width()`
- `render_worker.render_document()`
- `test_pdf_loads_and_renders_page_previews`

## 8. 網格與頁面卡片

網格採上方對齊、水平置中，各卡片在所在欄位內也水平置中。捲動範圍因頁面尺寸或視窗寬度改變時，水平捲動條回到中央；使用者仍可用 <kbd>←</kbd>、<kbd>↑</kbd>、<kbd>→</kbd>、<kbd>↓</kbd> 或捲動條查看超出寬度的部分。Fit 固定為單欄。Fit 導覽以預覽區中央最近的可見頁面為起點；切頁或渲染尚未完成時保留已要求的參考頁，讓連續快速按鍵順序正確。越界時不送出縮放或捲動要求。

`PageCard` 持有：

- 顯示自然頁碼的 `QCheckBox`。
- 顯示縮圖或錯誤狀態的 `QLabel`。
- 零起始 `page_index`。

圖片到達後，卡片會依縮圖實際寬高調整固定尺寸。`DocumentView._reflow_grid()` 以目前最寬卡片和預覽區可用寬度計算欄數；視窗改變大小或新縮圖到達時都會重新排列，但不重新解析 PDF。

超過 64 頁時使用虛擬化配置：只保留可見頁與附近範圍的卡片，整份文件只儲存頁面順序、選頁、已知尺寸與幾何位置。`PageCards` 的索引仍是原始頁碼，迭代只走訪現存卡片；不可用迭代結果的位置當作頁碼。尚未讀取尺寸的頁面暫用 A4 比例估算，尺寸到達後重排並保留可見頁的捲動位置。搜尋高亮獨立保存，卡片重建後還原；拖放將附近卡片位置換算成整份文件的插入位置。

64 頁以內保留一般卡片網格，但影像同樣按需載入。網格使用 `PageGridLayout`，在 Qt 彙總尺寸約 524287px 的上限之外按實際列高計算，避免非常高的頁面被壓矮。虛擬配置直接使用頁面幾何位置，不受此配置器的彙總尺寸上限影響。

`PageGrid` 管理拖曳預覽：開始時固定原始網格位置、暫停 layout 並隱藏來源卡片；`QDrag` 使用含頁碼的卡片縮圖（最大 180×240px）。滑鼠以原始格位的左／右半部決定前／後插入，避免移動中的卡片反覆改變命中位置。其餘卡片使用 180ms OutCubic 位置動畫讓出虛線空位，跨列時依網格順序換列。預覽不修改 `page_order`；放開才透過 `_insert_page()` 提交，取消則恢復原始網格。拖曳結束後重新啟用 layout 並重排，輸出期間禁止開始拖曳。

## 9. 頁面選取規則

內部一律使用零起始索引；畫面一律顯示一開始頁碼。

`core.py` 提供純函式：

- `indices_for_parity()`：取得奇數或偶數自然頁碼所對應的索引。
- `set_parity()`：只增加或移除指定奇偶群組，不改動另一群組。
- `parity_state()`：回傳 `NONE`、`PARTIAL` 或 `ALL`。

奇數頁與偶數頁控制項為三態核取方塊。手動勾選部分群組時顯示部分選取；同時全選奇數與偶數頁等同全選。程式化同步核取狀態時，必須保留 `_syncing_bulk` 或阻擋訊號，避免重入選取邏輯。

## 10. PDF 輸出與檔案安全

`choose_output()` 與 `choose_split_output()` 共用 Qt 另存新檔交談窗，預設名稱為 `<來源檔名>_selected.pdf`，重組只提供 PDF 並合併成單一檔案；拆分可選 PDF 或 PNG，逐頁輸出。有可輸出頁面且沒有輸出工作時啟用按鈕。`output_selection(fallback_current=True)` 在勾選範圍沒有選頁時回退到目前標籤的 `preview_page_index()`，全螢幕時使用目前組的第一頁；預設不回退，供列印維持自己的選頁規則。

`core.export_documents()` 的重要行為（既有 `export_selected_pages()` 保留為單檔包裝）：

1. GUI 依標籤順序取得有勾選的文件；若沒有勾選標籤則只取目前文件。各文件依 `page_order` 過濾 `selected_pages`，組成不可變 `DocumentSelection(source, pages)` 清單。空選頁的文件不提供輸出頁面。
2. 禁止目的地與參與輸出或任何已開啟的來源為同一檔案。
3. 驗證頁碼範圍與來源是否仍存在。
4. 使用 pypdf 直接加入原始頁面，不以縮圖重建 PDF。
5. 複製第一個實際提供頁面的文件 metadata。
6. 先在目的資料夾寫入 `.repdf-*.pdf` 暫存檔。
7. 寫入完成並 `fsync()` 後，以 `os.replace()` 原子替換目的檔。
8. 發生錯誤時刪除暫存檔，不留下半成品。

拖曳排序只移動 `page_order` 的原始頁碼索引，`page_cards` 和 `selected_pages` 仍以原始頁碼識別頁面。單雙數選取完全不受畫面位置影響。

單頁拆分由 `choose_split_output()` 共用另存流程，透過 `ExportPdfTask(split=True)` 呼叫 `core.split_documents()`（`split_selected_pages()` 保留為單檔包裝）。`split_output_paths()` 依輸出總數產生至少兩位補零的連續序號。GUI 在啟動前確認實際單頁檔案的覆蓋，核心再次禁止覆蓋來源。每個來源只讀取一次，各頁保留其所屬來源的原始頁面與 metadata；先在同一目的資料夾的暫存目錄產生所有 PDF，再逐檔原子發布。未授權覆蓋時，發布操作拒絕已存在的檔案。產生失敗不會修改輸出；若發布階段因磁碟錯誤中斷，錯誤訊息會顯示已完成的檔案數，先前發布的檔案會保留。

輸出期間允許切換標籤查看與縮放，但禁止開檔、關閉、標籤勾選／排序與頁面選取／重排。背景輸出使用開始時的不可變快照，包括頁面及未儲存註解。拆分序號跨檔連續，沿用至少兩位補零。

`png_export.py` 由獨立 `RenderService` 背景程序逐頁以 PDFium 渲染，使用 `PdfDocumentCache` 套用各來源密碼與註解快照，保留頁面旋轉、裁切及可見註解。輸出 RGB PNG，解析度為 300 DPI，單頁上限 3,000 萬像素，超過時降低 DPI。單張使用指定檔名，多張透過 `png_output_paths()` 連續編號。全部圖檔先寫入目的資料夾內的暫存目錄並 fsync，完成後逐檔原子發布；未授權覆蓋時拒絕既有檔案，且禁止覆蓋任何已開啟來源。取消會終止背景程序並清除暫存，不發布圖檔；發布階段的磁碟錯誤會報告已完成數量。PNG 輸出不新增依賴，與擷取原始內嵌圖片功能分開。

## 11. 主題、字型與圖示

- 工具列可切換狀態的按鈕與搜尋選項以 `stateButton` 屬性共用樣式：啟用時使用 hover 底色，移入已啟用按鈕時使用 pressed 底色，圓角 8，保留透明邊框但不顯示外框。`icons.py` 為 QIcon 的 On 狀態提供 `QPalette.Highlight` 圖示，Normal／Active 模式一致；停用時仍使用停用圖示色。尺寸維持 34 × 34、圖示 20 × 20 與設計筆畫 1。

工具列提供 `language_action`、`theme_action` 三態按鈕，分別循環 `system → zh → en` 與 `system → light → dark`。`QSettings("repdf", "repdf")` 的 `ui/language`、`ui/theme` 保存選擇，預設均為 `system`，無效值回退為系統模式。首次啟動會將舊版 `QSettings("PDFPick", "PDFPick")` 的有效語言與配色選擇複製到尚未設定的新欄位，不覆蓋 repdf 已有設定，也不刪除舊設定。

`preferences.LanguageController` 優先使用 `QLocale.system().uiLanguages()` 的第一個顯示語言，沒有顯示語言時才回退至 locale 語言；中文使用繁體中文，其餘使用英文。主視窗收到 `LocaleChange` 時僅在系統模式重新判斷。`strings.py` 集中翻譯表與 `tr()`，由 GUI、核心和背景錯誤共用；`localize_text()` 更新既有介面文字並保留格式化參數。切換時更新文字與提示，不重建文件或重新渲染頁面。

檔案對話框使用 `DontUseNativeDialog`，搭配 Qt `qtbase_zh_TW.qm` 與標準按鈕翻譯。封裝設定透過 `QLibraryInfo.TranslationsPath` 取得各平台的 Qt 翻譯資源路徑，將 qm 放入 `repdf/assets`；來源執行同樣讀取 Qt 的 translations 路徑。未翻譯文字回退原文。`packaging_smoke.py` 驗證 qm 存在與英文翻譯，GUI 測試以獨立設定檔隔離使用者偏好。

`ThemeController` 在 `system` 模式讀取 `QGuiApplication.styleHints().colorScheme()`，並監聽 `colorSchemeChanged`；`light`、`dark` 則優先使用手動設定。控制器由主視窗持有。每次套用主題時同時更新：

- Qt palette。
- 頁面卡片與預覽區邊框。
- 按鈕基本尺寸。
- 滑桿軌道、已填區段與把手顏色。
- 工具列、核取方塊、捲軸與對話框按鈕的扁平樣式。`icons.py` 繪製工具列線條圖示；主視窗在 palette 改變時重建圖示，維持深淺色及停用狀態的可讀性。

`configure_application()` 依序嘗試：

1. Microsoft JhengHei UI
2. Microsoft JhengHei
3. Noto Sans TC
4. Arial

圖示位於 `src/repdf/assets/repdf.png` 與 `repdf.ico`。視窗與雲端打包共用 `icon_layout.fitted_icon()`，以 alpha ≥ 32 的可見範圍去除多餘留白，等比例置中至畫布 92%。Windows ICO 於建置時產生，包含 16、20、24、32、40、48、64、128、256px；macOS ICNS 使用相同視覺比例。

## 12. 測試覆蓋範圍

目前測試涵蓋：

- 奇偶頁選取、清除與三態判定。
- 預設輸出檔名。
- 集合選取依來源順序輸出；有序清單依拖曳順序輸出。
- 拖曳重排後，畫面順序、原始頁碼奇偶選取與實際輸出一致。
- 輸出後頁面尺寸保持不變。
- 空選取與覆蓋來源檔的拒絕行為。
- 損壞與密碼保護 PDF。
- GUI 初始控制項與圖示載入。
- 手動頁面選取與奇偶頁狀態同步。
- 縮放防抖。
- 從 PDF 載入到背景渲染縮圖的整合流程。
- 按需預覽、長文件虛擬化、快取淘汰與跳頁定位。
- 搜尋範圍、規則表達式、單字邊界、命中高亮、書籤與內外部連結。
- 列印範圍、排序、紙張邊距、縮放、份數、預覽快取、取消及後端釋放。
- 整合列印視窗的一般操作不開啟原生列印交談窗；無印表機時可預覽但不能送印。
- OCR 的損壞文字偵測、區域辨識、離線模型與剪貼簿流程，辨識品質測試以中英文為主。

測試使用 `QT_QPA_PLATFORM=offscreen`。Qt 的離屏外掛可能和原生 Windows 視窗有細微繪圖差異，因此涉及字型、圖示、主題或版面外觀的修改，仍應額外用原生 Windows 視窗檢查。

## 13. 常見修改入口

| 修改需求 | 主要入口 | 注意事項 |
| --- | --- | --- |
| 調整主畫面排列 | `MainWindow.__init__()` | 保持上、中、下三區結構 |
| 調整縮放範圍或 DPI | `app.py` 的 slider 與 scale 方法 | 同步更新測試與 README |
| 改縮圖格式或品質 | `render_worker.render_document()` | 主程序目前假設收到可由 `QImage` 讀取的路徑 |
| 改背景任務排程 | `renderer.RenderService` | 保留 generation 淘汰機制 |
| 新增選取方式 | `core.py` 純函式及 `_selection_updated()` | 以零起始索引為內部標準 |
| 改輸出順序 | `DocumentView.page_order`、`_move_page()`、`core.export_selected_pages()` | 保持原始頁碼索引與畫面位置分離 |
| 調整密碼支援 | `_unlock()`、`PdfPasswordDialog`、`MainWindow` 密碼佇列與背景要求 | 維持各文件密碼獨立、關閉清理及輸出不加密的明示 |
| 更換圖示 | `assets/` 與 `load_app_icon()` | PNG 與 ICO 應同步更新 |
| 調整深淺色配色 | `ThemeController.apply()` | 必須同時確認兩種系統模式 |

## 14. 已知限制與擴充方向

- 不支援跨標籤拖移頁面或重啟後還原工作階段。
- 支援輸入密碼開啟 PDF；目前不提供替輸出 PDF 設定密碼。
- 不提供頁面旋轉、裁切或內容編輯；跨文件重組依勾選頁面與畫面順序輸出。
- 縮圖按需載入並使用有上限的快取；目前顯示的高解析度頁面與 PDF 本身仍會占用額外記憶體。
- 不會強制中斷正在執行的 PDFium 原生呼叫；新位置可能需等待目前最多兩頁的批次完成，單頁本身非常複雜時仍可能延遲。
- GitHub Actions 可產出 Windows 單一 EXE 與 macOS App／DMG；目前未設定開發者簽章與 macOS 公證。

## 15. 打包與發布

- 封裝自我檢查必須先停止持有 PDF 快取的渲染後端，再清理測試用暫存目錄；成功或失敗時都依此順序釋放，避免 Windows 因檔案鎖定而無法刪除測試 PDF。
### 建置原則與產物

- 打包全程在 GitHub Actions 雲端環境執行；一般開發只執行原始碼與測試，不在本機打包。
- Windows x86_64：使用 PyInstaller onefile windowed 模式，產生單一 EXE。
- macOS Apple Silicon（arm64）：使用 onedir App bundle，保留原生函式庫的符號連結，再封裝為 DMG。
- Windows EXE 與 macOS App／DMG 分別在對應平台的原生 runner 建置。
- 桌面產物皆附 SHA256 校驗檔；OCR 執行環境與模型隨套件提供。
- 目前未設定 Windows 程式碼簽章或 macOS Developer ID 簽章／公證，因此下載後可能出現系統安全提示。

### 桌面套件工作流程

- 設定檔：[`.github/workflows/build-desktop.yml`](../.github/workflows/build-desktop.yml)，工作流程名稱為「Build desktop apps」。
- 正式發布 Release 時觸發，依 Release 標籤建置；標籤中的提交必須包含打包設定檔。
- 也可在 Actions 頁面使用「Run workflow」手動執行，以 `ref` 指定分支或標籤。
- 手動填入 `release_tag` 時，會優先依該標籤建置，並將成功產出的套件附加到指定的既有 Release。
- 建置流程先安裝鎖定的依賴並執行回歸測試，再打包及執行封裝自我檢查。
- 產物上傳至 Actions Artifacts，保留 30 天；手動建置未指定 `release_tag` 時可在此下載。
- Release 建置或手動指定 `release_tag` 時，待 Windows 與 macOS 建置都成功後，才將產物附加到 Release。

### 打包設定與資源

- [`packaging/repdf.spec`](../packaging/repdf.spec)：定義 Windows EXE 與 macOS App 的封裝模式和資源收集。
- 收集 RapidOCR 設定、辨識／偵測模型及 ONNX Runtime 原生函式庫；不攜帶未使用的方向分類模型。
- 同時收集已安裝的 `repdf` distribution metadata，讓視窗與套件版本保持一致。
- [`scripts/build_desktop.py`](../scripts/build_desktop.py)：執行 PyInstaller、封裝後功能檢查、DMG 建立與 SHA256 校驗檔產生。
- macOS 使用系統內建的 `ditto` 與 `hdiutil` 建立並驗證 DMG。
- [`entrypoint.py`](../src/repdf/entrypoint.py)：在載入 GUI 前辨識背景後端與封裝自我檢查模式，避免子程序再次開啟 GUI。
- [`renderer.py`](../src/repdf/renderer.py)：原始碼模式沿用 stdin/stdout；凍結模式改用 loopback TCP、一次性隨機握手 token 與 UTF-8 串流，因為 Windows windowed bootloader 沒有標準輸入輸出。

### 封裝自我檢查

- 入口：[`packaging_smoke.py`](../src/repdf/packaging_smoke.py)，由打包流程呼叫封裝執行檔執行。
- 驗證 Qt、應用程式圖示與對話框翻譯資源可用。
- 實際執行 OCR 推論及區域辨識，避免只確認套件 import 成功。
- 驗證 AES-256 加密 PDF 的密碼讀取與未加密輸出，確認封裝中包含加解密依賴。
- 透過背景程序渲染兩頁 PDF，並驗證指定順序的 PDF 輸出。

### PyPI 發布

- 設定檔：[`.github/workflows/publish.yml`](../.github/workflows/publish.yml)，工作流程名稱為「Publish to PyPI」。
- 為 `codemee/repdf` 配置 PyPI `repdf` 專案的 Trusted Publisher，並將儲存庫變數 `PYPI_PUBLISH_ENABLED` 設為 `true`。
- 未啟用時不執行 PyPI 發布，只使用 GitHub Release 發布。
- 正式發布 Release 時觸發；也可手動執行並以 `tag` 指定既有 Release 標籤。
- 依標籤檢出原始碼，確認標籤與 `pyproject.toml` 的版本一致後，在雲端建置 wheel 與原始碼套件。
- 先將 Python 套件附加到 GitHub Release，再透過 Trusted Publishing 發布至 PyPI。

## 16. 文字搜尋

- 命中顏色由搜尋窗格色塊按鈕或精簡選項選單開啟 `QColorDialog` 設定，存於 `search/highlight_color`。僅保存 RGB，預設 `#ffe13c`，無效設定回退預設值；一般標示 alpha 100，選取段落以 `darker(120)` 與 alpha 115 疊加。修改時只重繪，不重新搜尋；既有頁面、虛擬卡片重建與全螢幕共用此設定，與介面配色獨立。
- `search_panel.py` 的 `SearchController` 管理右側窗格、單選範圍、查詢世代、結果與取消；`SearchPanel` 提供輸入、選項與上下兩個有欄位標題的結果表格。
- 搜尋時固定當下的已載入文件、標籤順序與頁面順序；標籤勾選只控制文件範圍，不使用頁面核取方塊篩選。
- 搜尋服務首次執行才啟動獨立 PDF 後端，重用既有原始碼／封裝通訊方式，不與預覽、OCR、圖片擷取共用佇列。
- `RenderService.request_search()` 依序送出單檔要求：`type=search`、文件 ID、世代、來源、原始頁面索引、查詢、正則／大小寫／僅限單字旗標及必要密碼。
- 後端逐頁回傳 `search_page`，包含原始頁面索引、進度、段落 ID、段落文字、命中範圍、正規化字形矩形與命中次數；`done`／`error` 亦帶文件 ID。
- `match_rects` 依命中範圍分別保存字形矩形。清單以文件、頁面、段落與命中索引識別每一列，同段落的多次命中分列，跨行的單次命中維持一列。滑鼠或鍵盤切換時只標示該次命中並盡量縱向置中；背景重建清單保留選取且不觸發跳轉。
- `search.py` 按 PDFium 字形索引讀取 Unicode 與位置，建立文字到字形的對映；不假設擷取字串索引等於原始字形索引，也不啟動 OCR。
- 文字行按幾何位置合成段落；空行、分欄、頁界與大於 1.5 倍行高的間隔切段，續行需有至少短行寬度 50% 的水平重疊。中日文字續行直接銜接，其餘補空格；補入的空格不對應字形矩形。
- 使用 `regex` 套件，普通模式先跳脫輸入，正則模式採 Python 相容語法；每段匹配預算 1 秒，零長度命中略過。
- 「僅限單字」透過 `whole_word` 旗標傳給後端，以 Unicode `\w` 的前後否定環視限制整個查詢的邊界，可與正則及大小寫設定併用；不進行中文斷詞。
- 字形分行使用整行垂直範圍與間距判斷，避免底線等低位字形被拆開，保留 `cat_` 等字串的單字邊界；正則 verbose 模式的行末註解不會吞掉外加的邊界條件。
- 停止、新搜尋或關閉窗格會終止搜尋後端並淘汰過期世代；關閉搜尋中的檔案時，移除該檔案並重新派送其餘未完成的文件。單檔失敗保留其他檔案的結果，逾時則停止整次搜尋並標示未完成。
- `PagePreviewLabel` 的搜尋矩形獨立於文字選取高亮，以正規化座標在重繪後保留；`DocumentView.jump_to_search_result()` 依穩定頁面索引定位並保留目前縮放／Fit 模式。尚無預覽圖時先依佔位幾何捲至命中位置，讓按需渲染啟動；目標頁及鄰頁實際尺寸到達後校正仍可見的命中位置，使用者已捲離時不因鄰頁更新拉回。
- 搜尋窗格預設寬 320px，可調整寬度及上下分隔。寬度小於 640px 時使用單一窗格；高度小於 360px 時將範圍與旗標收進選單，維持最小視窗 320 × 240。
- 主視窗每兩秒檢查已載入 PDF 的修改時間與大小，單次變更只提示一次。重新載入先非同步開啟新文件，成功後才換掉舊標籤並還原頁碼、縮放與標籤位置；失敗則保留舊標籤。未儲存時可另存新檔後開啟更新的來源檔。
- TrimBox 檢視以 PDFium 的實際 TrimBox（禁止回退 CropBox）與可見頁範圍交集判斷；若與原頁相同或尺寸無效則工具停用。預覽後端逐頁傳回正規化範圍，Fit 模式依裁切範圍計算縮放並捲至中心；來源 PDF 與輸出流程不改寫。
- 缺少 TrimBox 時，`trim_view.crop_mark_box()` 讀取有描邊、無填色且不閉合的向量路徑，套用物件與父 Form 矩陣，只接受頁邊四角各有橫、直短線且可互相對應的框。雙重記號取內側範圍，設有路徑與候選數量上限；不完整記號、一般矩形及點陣影像維持原頁面。
- 從工具列溢位選單開啟搜尋時，在下一輪事件處理恢復主視窗啟用狀態，再將焦點移至搜尋欄，避免 macOS 的選單視窗暫留啟用狀態。
- 密碼只經既有本機通訊傳遞，不建立解密 PDF、磁碟文字索引或含密碼的記錄。搜尋歷史與結果只保留於目前工作階段。

## 17. 書籤與內部連結

- `NavigationController` 管理左側書籤樹、各文件的展開／選取狀態與導航要求世代。書籤與搜尋窗格互相切換；寬度小於 640px 時以單一窗格切換書籤與 PDF，點選章節後返回 PDF。
- 書籤按鈕沿用 34 × 34 按鈕、20 × 20 圖示與深淺配色。樹狀清單保留原 PDF 標題；沒有書籤時顯示提示。標籤關閉時清除其狀態及尚未開始的導航要求。
- 書籤首次展開時才送出 `bookmarks` 要求，由現有單執行緒 PDFium 後端重用文件控制代碼讀取，結果保留於該文件工作階段。`get_toc(max_depth=64)` 保留階層，循環由 PDFium 包裝的遍歷保護處理。
- `render_document()` 只對目前要求的頁面列舉連結註解，將正規化矩形與目的地附於 `page.links`。不為建立導航掃描全檔頁面。主視窗及全螢幕共用 `DocumentView.page_links`，虛擬卡片重建或影像快取命中時仍可恢復連結。
- 同一文件的目的地與 GoTo 動作由 PDFium 解析直接或命名目的地。頁面 URI 動作以 `FPDFAction_GetURIPath()` 讀取網址，支援 UTF-8 與含 BOM 的 UTF-16 字串，只接受具主機名稱的 HTTP／HTTPS 連結；電子郵件、外部文件、程式啟動及 JavaScript 動作不執行。
- HTTP／HTTPS 連結沿用單頁按需讀取、快取與點擊判定，以 `QDesktopServices.openUrl()` 交給系統預設瀏覽器，主視窗與全螢幕共用。開啟前再次驗證網址，失敗時顯示狀態列訊息；網址提示經 HTML 跳脫。
- 點選後送出 `navigate` 要求，只開啟目的頁讀取實際尺寸、裁切與旋轉，將 XYZ、FitH、FitV、FitR 等目的地座標換算成顯示面的正規化位置。主視窗保留目前縮放／Fit 模式，以原始頁碼定位，再按目前 `page_order` 捲至該頁；全螢幕切到包含目的頁的群組。
- `PagePreviewLabel` 在一般模式對連結顯示手指游標與目的頁碼提示，左鍵按下及放開都在同一區域、且未超過拖曳門檻時才觸發。選字、區域 OCR 與圖片擷取模式優先，不啟用連結；拖曳仍交由既有頁面排序處理。
- 新導航淘汰舊要求世代；切換標籤或關閉文件後到達的舊跳頁結果不會改變目前文件。功能只使用 PDF 已有的導航資料，不替純文字／掃描目錄建立連結，也不提供書籤編輯或重建輸出 PDF 的書籤。

## 18. 狀態列頁碼

- 書頁標籤透過 PDFium `get_page_label()` 隨單頁渲染或目的地解析按需讀取，存於 `DocumentView.page_labels`，不在開檔時掃描全檔。快取以原始頁次為鍵，重新排序或影像快取淘汰後仍可使用；沒有標籤時回傳 `None`，不合成書頁號碼。
- 有標籤時並列「書頁」與「PDF」原始頁次；輸入欄仍按原始頁次跳頁。標籤使用純文字與依視窗寬度截短的單行顯示，完整內容放在經 HTML 跳脫的提示中，不擴大最小視窗限制。
- 狀態列以 permanent widget 顯示原始頁碼輸入欄及總頁數，不會被 OCR、搜尋或輸出訊息取代。尚未載入文件時顯示 `- / 0` 並停用輸入。
- `_update_page_indicator()` 使用目前文件的 `preview_page_index()`，與預覽／Fit 的可見頁判定一致；控制狀態、頁面焦點、搜尋導航與合併後的捲動事件都會更新。
- 輸入中的草稿與文件 ID 分開追蹤；有焦點且已編輯時不覆蓋內容。切換標籤、離開輸入欄或按 <kbd>Esc</kbd> 會還原目前頁碼，避免將前一份文件的草稿帶到下一份。
- 按 <kbd>Enter</kbd> 驗證十進位整數及 `1..page_count` 範圍，依原始頁碼定位。手動縮放直接捲至該頁，Fit 則更新參考頁並重新適應；使用虛擬幾何位置，不建立途中所有頁面的卡片。
- 頁碼欄的方向鍵、<kbd>Home</kbd>／<kbd>End</kbd> 用於編輯文字，不觸發 PDF 導覽；送出後將焦點交回預覽區。狀態列輸入欄高度 22px，寬度依頁數位數調整，不擴大最小視窗限制。

## 19. 列印

- `PrintOptions` 為整合視窗內的範圍／縮放元件，固定當下的原始頁次、標籤／頁面順序及密碼；提供全部、目前頁、指定頁次及沿用 `output_selection()` 的勾選結果。指定頁次去重後按畫面順序排列，無效或空選取不能送出。
- 印表機、紙張、方向、份數、逐份、雙面與色彩直接操作 `QPrinter`，能力清單由 `QPrinterInfo` 提供。一般流程不開啟系統交談窗，僅「進階設定」使用 `QPrintDialog`，接受後將原生設定同步回自製控制項；範圍改變時清除原生頁次篩選，避免套用前一份列印清單的位置。
- 原生進階頁次範圍以列印清單的 1..N 計算。`printer_pages()` 套用頁次與倒序，驅動不支援多份列印時才展開份數及逐份／逐頁排序，避免重複套用。
- `PrintJob` 使用獨立 `RenderService`／後端，`print_page` 要求每次只渲染一頁，300 DPI、上限 3,000 萬像素。使用既有封裝後端啟動與驗證流程，不重組整份 PDF，也不使用預覽縮圖。Qt Print Support 與平台列印元件由 PyInstaller 的 Qt hook 收集。
- `QPainter` 在 GUI 執行緒逐頁繪製到 `QPrinter`，完整紙張為座標系，以可列印矩形裁切並置中。符合範圍模式等比例縮放，實際大小按 PDF points 換算至印表機 DPI；紙張與方向跟隨系統列印設定，不自動旋轉或依頁面更換紙張。
- 非模態進度視窗允許取消；取消時嘗試 `QPrinter.abort()`，已送入系統佇列的頁面不保證撤回。每個工作只保留當頁影像，完成、錯誤、取消與關閉程式時都先停止後端，再清理暫存資料與密碼參照。
- 工具列與標準列印快捷鍵共用控制器；同時只允許一個列印工作。全螢幕呼叫時保留該頁作為目前頁，返回主視窗後開啟整合列印視窗。取消預覽時停止預覽後端，不建立列印工作。
- 封裝自我檢查以 `QPrinter.PdfFormat` 驗證逐頁輸出及後端載入，不呼叫系統對話框或實體印表機。
- 入口開啟整合的 `PrintPreviewDialog`；寬視窗左右分欄，窄視窗上下排列。只有確認後才以 `accepted_pages` 移交最後範圍快照並建立 `PrintJob`，沒有印表機時仍可預覽但不能送印。`ordered_print_pages()` 純讀取頁次範圍與順序，不消耗或變更份數／倒序設定。預覽顯示單份，份數由紙張資訊另行顯示。
- 預覽使用獨立後端的 `print_preview` 要求，每次一頁、150 DPI、上限 400 萬像素，最多快取三頁；快速翻頁合併未執行要求，舊世代結果刪除後忽略。縮放與紙張變更共用 `print_rect()`，在白紙畫布重繪並裁切；預覽黑白模式依系統設定轉灰階。驅動端的雙面與裝訂不做紙張翻面模擬。
- 預覽可翻頁、輸入頁次、調整檢視倍率與列印縮放，或重新開啟系統印表機設定。關閉／取消時先停止後端，再清理影像、暫存檔及密碼快照；預覽尚未載入或失敗時不能送印。封裝自我檢查也驗證預覽可載入，且預覽不建立列印輸出檔。

## 20. OCR 語言與模型下載

- 工具列的區域 OCR 主按鈕維持 34 × 34、圖示 20 × 20；同組但獨立的 14 × 34 箭頭以 `OcrLanguageController` 開啟語言選單，窄視窗的 overflow 也保留此選單。
- `ocr/language` 存於既有 QSettings，預設 `builtin`。額外模型完成下載與 SHA256 校驗後才儲存選擇；缺少模型時不默默回退內建語言。
- `ocr_models.py` 的 URL 與 SHA256 固定自 RapidOCR 3.10.0 官方 `default_models.yaml`；模型寫至使用者資料目錄，與原始碼、安裝位置及 `_MEIPASS` 分離。
- `OcrModelDialog` 以 Qt Network 串流寫入 QSaveFile、同步計算 SHA256，成功才原子提交。30 秒無資料傳輸或 180 秒總預算觸發失敗，取消／錯誤丟棄暫存，不覆寫既有檔案。失敗可重試，對話窗關閉及主視窗結束都中止下載。
- 每次 `request_text` 附上 `ocr_profile`，傳至既有渲染後端，區域辨識與損壞文字備援共用。引擎以 profile 為快取鍵且最多保留一套，避免切換後累積模型記憶體。
- 內建辨識維持 PP-OCRv6 small；額外辨識明確指定 PP-OCRv5 mobile 的 OCRVersion、ModelType 列舉及語言，偵測仍使用內建模型。模型已內嵌字典，指定明確本機路徑，不依賴 RapidOCR 自動下載。
- 缺少／損壞模型以 `OcrModelMissing` 回傳，下載成功後只重試文件仍開啟、模式與語言仍相同、且沒有被新世代選取取代的要求。重試資料不保存 PDF 密碼或重新開啟已關閉文件。
- `rapidocr[rtl]` 與 PyInstaller 的 `bidi.algorithm` 隱式匯入支援阿拉伯文；額外模型不隨桌面程式打包。封裝自我檢查驗證 Qt HTTPS、RTL 執行環境、下載需確認與使用者目錄位置，不自動連網下載模型。
- `test_ocr_languages.py` 以本機 HTTP 伺服器驗證下載、校驗、取消、逾時、重試與設定保存；既有測試驗證內建模型離線辨識。模型網址或雜湊更新時，另實測官方下載、ONNX 載入與對應文字系統辨識。桌面封裝僅由雲端工作流程執行。

- `auto` 是虛擬選項，不對應額外模型檔；區域偵測使用內建引擎。辨識先逐行跑內建，再按模型依序處理所有文字行，讓每個模型每次要求只載入一次，仍只快取一套引擎、一次保留一張裁切影像。
- 自動模式只枚舉 SHA256 驗證成功的已下載模型，不在後端下載。以 0.8 基本信心門檻、候選文字系統至少六成、覆蓋有效內建結果時至少 0.9、保守差距與相近候選歧義檢查選擇文字；這是啟發式規則，不是跨模型機率校準。共用 60 秒預算，過期不能因略過失敗模型而被吞掉。
- 語言選單保留穩定 QAction，依驗證可用的模型以兩條分隔線重建三組選項，不顯示標題；已下載項目加文字標記。`auto` 可直接選取；下載成功、外部刪除或損壞後，在重新開啟選單時更新分組。`test_ocr_auto.py` 涵蓋逐行選擇、模型載入順序、文字系統、歧義及時間上限。

## 21. 註解清單

- `NavigationController` 共用一個左側窗格，以 `bookmarks`／`annotations` 區分內容；各標籤與模式分別保留選取、展開狀態，與搜尋窗格互斥。窄視窗沿用清單／PDF 單窗格切換。
- `DocumentView.annotations` 初始為 `None`，開檔不掃描完整註解清單。首次開啟註解窗格才啟動專用 `RenderService`／既有可封裝後端，避免全檔掃描佔用預覽的要求佇列。切換文件或模式、關閉窗格／文件／程式時停止註解服務並丟棄失效世代。
- `pdf_annotations.py` 逐頁使用 PDFium annotation API 讀取支援的 markup 類型、UTF-16LE Contents／T／Subj／M 字串與矩形；排除連結、表單 widget 與 popup 容器，避免把連結當註解或重複列出彈出內容。每個 annotation、page 與掃描文件都明確關閉。
- 螢光標示、底線、波浪底線、刪除線未提供 Contents 時，按 attachment quad 擷取底下文字；沒有文字層時顯示無文字提示，不執行 OCR。註解矩形無效時仍可按頁跳轉。
- 頁面群組列顯示原始頁碼與註解數量，預設收合；子項顯示類型與單行摘要，群組展開狀態按文件記住並在介面翻譯後保留，完整內容及中繼資料放在經 HTML 跳脫的 tooltip。點選沿用 `navigate` 世代及原始頁碼，按頁面旋轉／裁切轉換 XYZ 位置，保留縮放與頁面重排。
- 群組共用該頁第一個註解的目的地與框選範圍；個別註解將矩形四角依裁切與旋轉正規化為 `annotation_rect`，經導航回應定位至顯示範圍左上角。`PageViewport` 獨立保存註解框選，卡片重建與全螢幕均恢復；群組切換更新框選，書籤及搜尋結果會清除舊框選，不改寫 PDF。
- 預覽只對要求的頁面呼叫 `read_annotations(..., include_text=False)`，回傳 `annotation_hits`，以原始頁碼及 PDF annotation index 作為穩定識別；不擷取內容或掃描其他頁。`DocumentView.page_annotations` 保存命中範圍，卡片與全螢幕重建時恢復。一般閱讀模式優先命中註解，再命中連結；拖曳與選字／OCR／圖片模式維持既有處理。頁面點選開啟清單並等待背景結果同步選取，不重新跳頁，全螢幕及窄視窗不切離目前頁面。
- 使用者選取註解時，以文件／原始頁碼／annotation index 記錄一次性複製要求；清單跳頁成功或頁面點選取得背景文字後，才將非空 Contents（含標示原文回退）寫入剪貼簿。狀態還原與翻譯不觸發複製。關閉窗格或切換其他側欄清除所有文件及全螢幕框選、待複製要求及導航世代，避免遲到結果重新框選或改寫剪貼簿。
- `test_annotations.py` 驗證中英文、密碼 PDF、標示原文、旋轉／裁切、重排跳頁、模式與標籤切換、空清單及關閉後舊結果保護；註解清單與編輯工具共用資料；不支援的類型維持檢視，不執行附件。

## 22. 整份文件存檔

- `DocumentView` 預設開啟 Fit，頁面載入後再計算實際尺寸；手動縮放仍退出 Fit。
- `modified` 比較目前 `page_order` 與來源頁序；順序變更顯示星號並啟用存檔。存檔及另存新檔分別使用標準 Save／SaveAs 快捷鍵，選取頁面輸出不再占用這些快捷鍵。
- `SaveController` 與 `SavePdfTask` 儲存目前文件全部頁面。`core.save_document()` 克隆文件後重排頁樹，保留頁面間接參照與章節／連結目的地，將數字型本地目的地轉為原頁參照；頁碼標籤按原頁轉換為各頁固定標籤。
- 以開啟時的密碼及原權限旗標重新 AES-256 加密，無法取得的原 owner 密碼不保留。先寫同目錄暫存檔、flush／fsync 完成後原子替換；失敗清理暫存並保留原檔。
- Windows 寫回前停止預覽、搜尋及註解讀取，釋放 PDFium 的來源檔控制代碼；完成或失敗後重建預覽服務。成功後重建該標籤，重新對應目前頁、選取頁及 Fit／縮放，避免將舊原始頁索引用在重排後的來源。

- 全螢幕主 QAction 負責開啟／退出，右側下拉選單共用三個互斥模式 QAction；<kbd>F11</kbd> 使用本次執行保留的 `fullscreen_mode`。既有全螢幕視窗以 `set_mode()` 重組頁面群組、失效舊渲染並保留目前頁面，不關閉重建視窗。

## 23. 註解建立與相容編輯

- `annotation_data.py` 解析可編輯的標準 Underline／StrikeOut／Squiggly／FreeTextCallout 與本程式版本化資料。完整樣式與幾何可還原才進入編輯模型；鎖定、混合格式、未支援字型、透明或特殊外觀保留原始顯示並回報唯讀原因。不可見註解不進入互動繪製層。
- `annotation_store.py` 保存原始模型及編輯差異，以 `QUndoStack` 支援新增、樣式、文字、移動、縮放及刪除；`modified` 同時比較頁序與註解差異。幾何使用原始 PDF 座標，識別與頁面順序分開。
- `annotation_editor.py` 共用一般／全螢幕的滑鼠事件、樣式面板與文字編輯器。文字編輯焦點優先處理方向鍵、復原與 Esc；離開編輯、存檔、列印或輸出前提交文字。拖曳只更新暫態畫面，放開後形成單一復原命令。
- `annotation_graphics.py` 共用向量繪製，使用 Qt PDF 產生內嵌字型的 appearance PDF。寫入時轉成 `/AP /N` Form XObject，克隆 `/Resources`，並設定 QuadPoints、CL、LE、DA、DR、RD、BS 等標準欄位。`/RepdfData` 保存版本化樣式供重新開啟編輯；不壓平註解。
- 螢幕後端僅解析所要求頁面的註解，暫時隱藏可編輯原生外觀、在繪製後還原旗標，再由 Qt 向量層繪製，避免重複。metadata reader 採可 seek 的檔案串流與三份文件上限，關閉或汰換時釋放串流，不先複製整份 PDF 至記憶體。
- `DocumentSelection`、`SavePdfTask`、`PrintPage` 增加預設為空的註解快照。存檔、選取頁輸出及列印均套用相同差異；列印後端依來源及快照指紋重用文件，不每頁重建完整 PDF。套用差異在重排前進行，刪除延後以維持來源索引。
- 成功存檔後沿用既有標籤重建與頁碼對應流程，重新讀取穩定註解識別碼。關閉有變更的標籤或視窗時可儲存、捨棄或取消；儲存失敗保持原文件與編輯狀態。
- `test_annotation_editing.py` 覆蓋標準外觀／中文、重新開啟編輯、唯讀匯入、拖曳、復原、關閉決策、裁切／旋轉座標與圖示有效尺寸；以 PDFium 及 Poppler 交叉驗證顯示。

- 私有編輯資料保存標準欄位與外觀串流指紋；重新開啟時檢查一致性。其他程式改寫外觀或文字導致資料不一致時，保留原生顯示並設為唯讀，避免回寫舊模型。

- 畫線工具以 90 ms 單次計時器要求文字層選字預覽；預覽不寫入註解、不改剪貼簿，放開滑鼠後以最終結果建立一筆可復原的註解。使用標準 `/Highlight` 與 `/QuadPoints` 儲存螢光筆，透明外觀寫入 `/AP`。
- 箭頭文字框以與 PDF 外觀相同的 QTextDocument 字型、邊距量測內容，於直立頁面座標中調整尺寸，再映回旋轉／裁切座標；箭頭目標維持不變，取消編輯還原原尺寸。

- 箭頭文字框圓角存於可編輯資料 `radius`，並以向量路徑寫入標準 `/AP` 外觀；仍使用 `/FreeText`、`/CL`、`/Contents`，不將註解扁平化。舊註解缺少圓角資料時視為 0。

- `annotation_geometry.py` 提供繪圖座標、移動與縮放。`Text`／`Line`／`Square`／`Circle`／`Ink` 分別寫入便利貼、直線／箭頭、矩形、橢圓與手繪，使用標準 `/L`、`/LE`、`/RD`、`/IC`、`/InkList`、`/Contents` 及 `/AP`；保留可編輯資料，不扁平化。
- 新類型簽章加入相應的幾何欄位，原有文字框與畫線簽章不變，確保舊檔仍可編輯。其他程式產生的便利貼與繪圖目前保留原生外觀並以唯讀方式顯示。
- 繪製期間只更新暫存預覽，滑鼠放開後驗證幾何並建立單一復原命令；便利貼取消編輯或空白內容不建立註解。儲存、列印與輸出沿用同一份變更快照。

- `annotation_spin.py` 以無原生增減按鈕的 Qt SpinBox 搭配共用 chevron 工具按鈕；即使更新值時阻擋訊號，亦同步增減按鈕的上下限狀態。
- 畫線請求會快照連帶註解設定，預覽不建立項目；最終選字結果計算錨點後開始成組復原命令，文字完成或取消時結束。僅已確認文字寫入 PDF，取消時保留畫線。

- `OverflowToolBar` 顯示重組與拆分輸出動作；奇偶頁選取位於頁首。儲存快捷鍵直接掛在主視窗。
- `floating_tools.py` 在一般視窗承載註解工具列；全螢幕共用註解與擷取 QAction，另提供始終可見的模式下拉控制。選單進入全螢幕時暫移父物件，退出前還原，避免 ApplicationModal 阻擋選單或隨懸浮列刪除。懸浮列可拖移、限制在容器內並支援溢出，換頁或切換模式不重設位置。

- `shortcut_hints.py` 由 QAction 的實際快捷鍵產生 tooltip，監聽 action 變更並於語系切換時重建提示；使用 NativeText，合併重複的 Tab／Backtab 顯示名稱。

- 工具列的主按鈕／箭頭群組使用固定內容尺寸。`OverflowToolBar` 監聽子元件的 LayoutRequest，重新計算 QWidgetAction 的尺寸與溢出邊界，避免語系切換後沿用舊寬度而截字。

- `OverflowToolBar.group_sections()` 將分隔線之間的工具放入不可壓縮的 QWidgetAction 容器，彈性留白保持獨立。溢出時依原順序展開整組工具與設定選單；`tool_actions()` 提供邏輯工具順序，`widgetForAction()` 保留個別按鈕查詢。快捷鍵動作也註冊到所屬視窗，避免群組隱藏後停用。

- `message_dialogs.py` 建立未儲存變更的 Qt 訊息框，分開主標題、檔名及捨棄說明；明確設定儲存預設與取消 Escape 動作，三個選項沿用原有存檔／關閉流程。

- 搜尋結果維持上下分割：上方「檔案」以「檔名／筆數」兩欄顯示，筆數為個別命中數；下方「命中項目」以「頁碼／段落」分欄，點擊任一欄皆可跳頁。數字靠右，段落單行省略且保留完整提示。

## 資料夾搜尋與全文複製

- `SearchTarget` 將來源路徑、頁序及記憶體中的密碼與標籤生命週期分開；已開啟檔案沿用文件 ID，未開啟檔案使用獨立負 ID。資料夾僅枚舉同一層 PDF，背景服務在 `pages=None` 時開檔取得頁數，不預先渲染或建立全部標籤。
- 結果開檔記錄查詢世代、載入文件與段落 key；`_pdf_loaded()` 完成後才跳頁。停止、新查詢、關閉或改選結果會丟棄過期的跳頁；已開啟路徑沿用現有標籤。資料夾搜尋保留關閉標籤的結果，但移除其密碼參照。
- `document_text.py` 以獨立 `RenderService`／`copy_document` 後端要求逐頁擷取文字與正規化文字區塊，依頁序合併；不執行 OCR。只有完整成功才更新剪貼簿，失敗、取消或空白結果不覆蓋原內容。
- 全文選取區塊可套用於延遲建立的卡片及全螢幕頁面。快捷鍵僅於文字複製模式與閱讀介面攔截，排除搜尋欄、註解文字編輯及其他輸入欄位；關閉、切換文件、模式改變及存檔前停止專用讀取程序。

## 開源授權與發布

- 專案授權識別為 `GPL-3.0-only`；完整條款在根目錄 `LICENSE`，專案授權聲明與第三方說明在 `NOTICE`，兩者由 `license-files` 納入 Python 發行套件。
- 雲端桌面打包將兩份文件嵌入 `repdf/licenses`，並在 release 產物附上 `LICENSE.txt` 與 `NOTICE.txt`。不在本機打包執行檔。
- 發布執行檔時保留對應版本的原始碼、鎖定依賴與建置程序，並履行 GPL 及第三方元件各自的散布義務。
- 本專案沿用的 PDFPick 原始碼與本專案由同一權利人 Shin-Wei Hwang 持有；權利人已確認相關作者名稱與帳號均屬本人，並指定本專案採用 `GPL-3.0-only`，無須另行取得上游作者同意。第三方程式庫、模型與素材維持各自授權；逐項結果及發行要求見 [授權核對](LICENSE_AUDIT.md)。雲端打包以 `scripts/collect_licenses.py` 彙整實際環境的完整聲明，嵌入程式並產生平台別授權 ZIP；依賴或 Qt 模組超出核對範圍時停止。

- `about.py` 提供 Qt「關於 RePDF」、GPL 全文與離線第三方文件樹，僅點選原始碼按鈕才開啟外部網站。文件解析支援原始碼、Python wheel 的 dist-info 授權及 frozen 資源；介面跟隨中英文與配色，重複開啟沿用交談窗。
- Windows `system_menu.py` 以 Win32 `GetSystemMenu` 加入分隔線及自訂命令，`nativeEvent` 僅攔截自有的 `WM_SYSCOMMAND` ID，其餘交回 Qt。重複顯示或切換語系更新同一項，原生視窗 handle 改變後由獨立 QObject 事件篩選器重新掛載；不覆寫主視窗的通用 event()，也不攔截其他 Qt 事件。macOS 以 `QAction.AboutRole` 搭配原生 QMenuBar 交由 Qt 放入標準應用程式選單；不在 Windows 增加額外選單列。

- 打包排除未使用的 QtPdf／QtPdfWidgets、QImage 的 qpdf 外掛，以及 Qt 虛擬鍵盤與其 QML／Quick 原生模組。保留作業系統原生輸入法；PDF 閱讀及輸出仍使用 pypdfium2。Python 授權檔同時支援 Windows 安裝根目錄及 macOS／Unix 的 stdlib 位置。

## 選取與裁切輸出

- `tabs.DocumentTabs` 在標籤列左端與右端配置線條捲動按鈕，右側另放完整檔名下拉清單。捲動委派給 Qt 原生按鈕，原按鈕尺寸設為零且不繪製，並關閉 QTabBar::tear 撕裂提示，避免重複箭頭。重繪後維持兩端預留空間；清單依目前標籤順序建立並綁定文件物件，防止重排或關閉後索引失效。

- `drag_selection.py` 追蹤跨頁文字拖曳，在閱讀區邊緣自動捲動；全螢幕依頁組換頁。`copy_document` 要求可帶首尾座標，只擷取範圍內頁面；反向拖曳仍依目前頁序輸出，拖曳預覽不改寫剪貼簿。
- `ParityCheckBox` 以標準三態核取方塊呈現每頁所屬的奇偶頁群組，一般與全螢幕頁首共用文件選取狀態；全螢幕頁首用水平排版維持對齊。
- 重組與拆分的 `export_crop_actions` 分別保存 `export/export_remove_trimbox` 與 `export/split_remove_trimbox` 設定，各自更新裁切徽記圖示。`ExportPdfTask` 快照該次輸出選項。
- `_crop_to_trimbox()` 將輸出頁面的 MediaBox 與 CropBox 限縮至有效 TrimBox 與原可見框的交集，再移除 TrimBox；保留原座標與旋轉，因此不需平移內容或註解。無 TrimBox 時不裁切；來源檔與 PNG 輸出不受影響。
