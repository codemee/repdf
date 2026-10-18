# RePDF 實作與維護指南

本文件描述 RePDF 目前的程式架構、主要資料流、重要設計決策與修改注意事項。RePDF 代表 Rearrange PDF，命令、套件與 Python 模組名稱維持 `repdf`。若要新增功能或除錯，建議先閱讀本文件，再從 `src/repdf/app.py` 進入程式。

## 1. 專案概觀

RePDF 是 Windows 優先的 Python 桌面程式，功能是：

1. 以可勾選、拖曳排序及關閉的標籤頁開啟多個 PDF。
2. 顯示所有頁面的可捲動預覽。
3. 拖曳縮圖或把手調整頁面排列，手動或依原始頁碼的奇偶選取頁面。
4. 依畫面排列順序將選取頁面輸出成新 PDF。

執行環境由 `uv` 管理，Python 版本需求為 3.11 以上。

```powershell
uv sync
uv run repdf
uv run pytest
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
3. 成功後由對應 `DocumentView` 建立卡片；首次啟用該標籤才要求預覽，之後保留快取。
4. 失敗時移除該標籤，保留其他成功文件；同批錯誤在全部載入完成後合併呈現。
5. 已關閉文件的回傳結果只完成工作清理，不重新建立標籤。

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

後端一次只執行一個渲染要求。`RenderService` 使用依文件 ID 索引的待處理佇列，各文件只保留最新一筆要求；目前標籤優先。`cancel_pending()` 在關閉文件時移除尚未開始的要求。

世代編號由主視窗全域遞增，透過 `_render_documents` 對應到文件 ID。結果交給來源文件，與目前標籤或標籤順序無關；比例過期或文件已關閉的頁面結果直接清理暫存圖片。進行中的原生渲染不強制中斷，避免不安全的 PDFium 操作。

渲染要求可提供 `pages`（零起始頁碼陣列）以只產生指定頁面；省略時仍渲染整份文件。頁面結果附帶 `width_points`、`height_points`，供 Fit 與全螢幕依 PDF 實際尺寸計算比例。全螢幕使用負的文件 ID 作為獨立排程鍵與自己的世代編號，切頁立即淘汰舊結果，關閉時取消尚未開始的要求。

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
- 不支援旋轉、裁切或多 PDF 合併。
- 所有已渲染縮圖都保留在記憶體；極大量頁數或 200% 比例可能有較高記憶體用量。若要改善，優先考慮可視區域延遲渲染與縮圖快取淘汰。
- 後端忙碌時不會中斷目前 PDF，而是等待完成後處理最新要求；大型 PDF 的快速縮放可進一步加入可取消的工作協定。
- GitHub Actions 可產出 Windows 單一 EXE 與 macOS App／DMG；目前未設定開發者簽章與 macOS 公證。

## 15. 打包與發布

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
