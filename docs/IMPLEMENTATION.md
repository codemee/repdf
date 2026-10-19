# RePDF 實作與維護指南

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
| pytest | 核心與整合測試 |
| pytest-qt | Qt GUI 與非同步行為測試 |

## 3. 目錄與模組責任

```text
src/repdf/
├── app.py             主視窗與独立文件元件 DocumentView、標籤、GUI 事件與資料流協調
├── core.py            不依賴 GUI 的選取、驗證與 PDF 輸出邏輯
├── widgets.py         單一頁面預覽卡片 PageCard
├── page_view.py       可見頁排程、頁面卡片虛擬化與共用影像快取
├── navigation.py      書籤側欄與內部連結跳頁控制
├── printing.py        列印設定、範圍快照與逐頁送印
├── print_preview.py   按需列印預覽與紙張配置畫布
├── pdf_navigation.py  後端讀取書籤、連結註解與目的地座標
├── preview.py         全螢幕單頁／對頁／封面預覽、等比例適應、切頁與選頁
├── theme.py           系統深色／淺色模式與控制項樣式
├── workers.py         PDF 載入及輸出的 QRunnable 工作
├── renderer.py        常駐縮圖後端程序與主程序之間的通訊
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
- 單數頁／雙數頁三態核取方塊位於工具列的檔案操作按鈕後方；中央為標籤頁與各文件的可捲動頁面網格。
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

`choose_output()` 使用系統另存新檔視窗，預設名稱為 `<來源檔名>_selected.pdf`。輸出按鈕只在至少選一頁且沒有輸出工作時啟用。

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

輸出期間允許切換標籤查看與縮放，但禁止開檔、關閉、標籤勾選／排序與頁面選取／重排。背景輸出使用開始時的不可變快照；全部選頁為空時停用輸出按鈕，不自動回退到其他檔案。拆分序號跨檔連續，沿用至少兩位補零。

## 11. 主題、字型與圖示

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

圖示位於 `src/repdf/assets/repdf.png` 與 `repdf.ico`。目前程式使用 PNG 建立 `QIcon`；Windows EXE 打包使用 ICO，內含 16、24、32、48、64、128、256px 尺寸。

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

- `search_panel.py` 的 `SearchController` 管理右側窗格、單選範圍、查詢世代、結果與取消；`SearchPanel` 提供輸入、選項與上下結果清單。
- 搜尋時固定當下的已載入文件、標籤順序與頁面順序；標籤勾選只控制文件範圍，不使用頁面核取方塊篩選。
- 搜尋服務首次執行才啟動獨立 PDF 後端，重用既有原始碼／封裝通訊方式，不與預覽、OCR、圖片擷取共用佇列。
- `RenderService.request_search()` 依序送出單檔要求：`type=search`、文件 ID、世代、來源、原始頁面索引、查詢、正則／大小寫／僅限單字旗標及必要密碼。
- 後端逐頁回傳 `search_page`，包含原始頁面索引、進度、段落 ID、段落文字、命中範圍、正規化字形矩形與命中次數；`done`／`error` 亦帶文件 ID。
- `search.py` 按 PDFium 字形索引讀取 Unicode 與位置，建立文字到字形的對映；不假設擷取字串索引等於原始字形索引，也不啟動 OCR。
- 文字行按幾何位置合成段落；空行、分欄、頁界與大於 1.5 倍行高的間隔切段，續行需有至少短行寬度 50% 的水平重疊。中日文字續行直接銜接，其餘補空格；補入的空格不對應字形矩形。
- 使用 `regex` 套件，普通模式先跳脫輸入，正則模式採 Python 相容語法；每段匹配預算 1 秒，零長度命中略過。
- 「僅限單字」透過 `whole_word` 旗標傳給後端，以 Unicode `\w` 的前後否定環視限制整個查詢的邊界，可與正則及大小寫設定併用；不進行中文斷詞。
- 字形分行使用整行垂直範圍與間距判斷，避免底線等低位字形被拆開，保留 `cat_` 等字串的單字邊界；正則 verbose 模式的行末註解不會吞掉外加的邊界條件。
- 停止、新搜尋或關閉窗格會終止搜尋後端並淘汰過期世代；關閉搜尋中的檔案時，移除該檔案並重新派送其餘未完成的文件。單檔失敗保留其他檔案的結果，逾時則停止整次搜尋並標示未完成。
- `PagePreviewLabel` 的搜尋矩形獨立於文字選取高亮，以正規化座標在重繪後保留；`DocumentView.jump_to_search_result()` 依穩定頁面索引定位，保留目前縮放／Fit 模式並等待渲染後捲至命中處。
- 搜尋窗格預設寬 320px，可調整寬度及上下分隔。寬度小於 640px 時使用單一窗格；高度小於 360px 時將範圍與旗標收進選單，維持最小視窗 320 × 240。
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
