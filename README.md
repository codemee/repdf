# RePDF — Rearrange PDF

RePDF 是 **Rearrange PDF** 的意思，命令名稱與 Python 套件名稱為 `repdf`。這是使用 PySide6 製作的 Windows 桌面工具，可用標籤頁開啟多個 PDF、勾選指定頁面，並依標籤與頁面排列順序重組或拆分輸出。預覽縮圖不會影響輸出品質。

## 安裝與啟動

### 1. 下載發布的執行檔／App（建議）

從 [GitHub Releases](https://github.com/codemee/repdf/releases/latest) 下載適合平台的檔案，不需要安裝 Python 或 uv：

- **Windows x86_64**：下載 `repdf-<版本>-windows-x86_64.exe`，直接執行。
- **macOS Apple Silicon（arm64）**：下載 `repdf-<版本>-macos-arm64.dmg`，開啟後將 `RePDF.app` 拖入 Applications，再從 Applications 啟動。

既有 `v0.0.7` 及較早的 Release 仍使用 `PDFPick` 檔名與 `PDFPick.app`，`v0.0.8` 的 macOS App 名稱為 `repdf.app`；自 `v0.0.9` 起 App 名稱為 `RePDF.app`，命令與發布檔案前綴仍為 `repdf`。

- Release 同時提供 SHA256 校驗檔。
- 桌面套件已包含 OCR 執行環境與模型，不需要額外安裝。
- 目前未設定 Windows 程式碼簽章或 macOS Developer ID 簽章／公證，下載後可能出現系統安全提示。

### 2. 使用 uv tool 安裝

已有 [uv](https://docs.astral.sh/uv/) 時，可從 PyPI 安裝到獨立工具環境：

```powershell
uv tool install repdf
repdf
```

- 需要 Python 3.11 以上版本；uv 可在需要時下載適用的 Python。
- 也可使用 Release 的 `repdf` wheel 下載網址安裝。
- 若終端機找不到 `repdf`，執行 `uv tool update-shell` 後重新開啟終端機。
- 既有舊版 wheel 仍安裝為 `pdfpick` 指令。

### 3. 從原始碼使用 uv run

適合開發或修改程式。下載原始碼，或 clone 本儲存庫後，進入專案目錄執行：

```powershell
uv sync
uv run repdf
```

## 操作方式

工具列按鈕的圖示與用途如下；將游標停在按鈕上也可查看 tooltip。

| 工具列圖示／控制元件 | 功能 | 操作說明 | 快捷鍵 |
| --- | --- | --- | --- |
| <img src="docs/images/toolbar-open.png" width="24" alt="開啟 PDF 圖示"> | 開啟 PDF | 一次選取多個 PDF，也可從檔案總管拖入。 | <kbd>Ctrl</kbd>+<kbd>O</kbd> |
| <img src="docs/images/toolbar-export.png" width="24" alt="重組輸出圖示"> | 重組輸出 | 將選取頁面依目前順序合併為一個新 PDF，指定檔名與儲存位置。 | <kbd>Ctrl</kbd>+<kbd>S</kbd>／<kbd>Ctrl</kbd>+<kbd>Shift</kbd>+<kbd>S</kbd> |
| <img src="docs/images/toolbar-split.png" width="24" alt="拆分輸出圖示"> | 拆分輸出 | 將選取頁面依目前順序逐頁存成獨立 PDF，指定基本檔名與儲存位置。 | — |
| <img src="docs/images/toolbar-odd.png" height="22" alt="單數頁核取方塊"> | 單數頁 | 選取或取消目前標籤的原始單數頁；部分選取時顯示三態標記。 | — |
| <img src="docs/images/toolbar-even.png" height="22" alt="雙數頁核取方塊"> | 雙數頁 | 選取或取消目前標籤的原始雙數頁；部分選取時顯示三態標記。 | — |
| <img src="docs/images/toolbar-copy-text.png" width="24" alt="複製文字圖示"> | 複製文字 | 啟用後拖曳選取文字，放開滑鼠即複製到剪貼簿；選取的文字會顯示高亮。 | — |
| <img src="docs/images/toolbar-ocr-region.png" width="24" alt="區域 OCR 圖示"> | 區域 OCR | 拖曳矩形框選頁面或圖片，放開滑鼠後辨識並複製文字。 | — |
| <img src="docs/images/toolbar-extract-image.png" width="24" alt="擷取圖片圖示"> | 擷取圖片 | 啟用後點選內嵌點陣圖片，再選擇位置另存為 PNG。 | — |
| <img src="docs/images/toolbar-zoom.png" width="160" alt="顯示比例與縮放滑桿"> | 顯示比例 | 滑桿調整 25%–200%；點擊比例回到 100%。鍵盤縮放每次調整 25 個百分點。 | 放大：<kbd>Ctrl</kbd>+<kbd>+</kbd>／<kbd>Ctrl</kbd>+<kbd>=</kbd>；縮小：<kbd>Ctrl</kbd>+<kbd>-</kbd>；100%：<kbd>Ctrl</kbd>+<kbd>0</kbd> |
| <img src="docs/images/toolbar-fit.png" width="24" alt="Fit 圖示"> | Fit | 將目前單頁等比例縮放至預覽區；調整視窗大小時自動適應。拖動滑桿或使用縮放快捷鍵會回到手動比例。 | — |
| <img src="docs/images/toolbar-fullscreen.png" width="24" alt="全螢幕單頁圖示"> | 全螢幕單頁 | 每次顯示一頁，依螢幕寬度或高度等比例填滿；可用頁面上方的核取方塊選頁。 | <kbd>F11</kbd> 開啟／返回；<kbd>Esc</kbd> 返回 |
| <img src="docs/images/toolbar-fullscreen-spread.png" width="24" alt="全螢幕對頁圖示"> | 全螢幕對頁 | 依目前順序兩頁並排：第 1、2 頁一組，第 3、4 頁一組，以此類推；每頁可獨立勾選。 | <kbd>Esc</kbd>／<kbd>F11</kbd> 返回 |
| <img src="docs/images/toolbar-fullscreen-cover.png" width="24" alt="全螢幕封面加對頁圖示"> | 全螢幕封面＋對頁 | 目前順序的第一頁作為封面單獨顯示；第 2、3 頁一組，第 4、5 頁一組，以此類推；每頁可獨立勾選。 | <kbd>Esc</kbd>／<kbd>F11</kbd> 返回 |
| <img src="docs/images/toolbar-language-system.png" width="24" alt="跟隨系統語言"> <img src="docs/images/toolbar-language-zh.png" width="24" alt="繁體中文"> <img src="docs/images/toolbar-language-en.png" width="24" alt="English"> | 介面語言 | 點擊依序切換「跟隨系統 → 繁體中文 → English」，選擇會記住。 | — |
| <img src="docs/images/toolbar-theme-system.png" width="24" alt="跟隨系統配色：左白右黑圓形"> <img src="docs/images/toolbar-theme-light.png" width="24" alt="淺色：太陽"> <img src="docs/images/toolbar-theme-dark.png" width="24" alt="深色：月亮"> | 介面配色 | 點擊依序切換「跟隨系統 → 淺色 → 深色」，選擇會記住。 | — |

### 開啟與切換檔案

- 檔案以主檔名顯示在標籤頁；將游標停在標籤上可查看完整路徑。
- 視窗標題列顯示 `RePDF` 與版本編號。
- 再次開啟同一路徑的檔案，會切換到既有標籤。
- 各檔案獨立保留比例、捲動位置、選頁與頁面排序。
- 下一個標籤（Windows／Linux）：<kbd>Ctrl</kbd>+<kbd>Tab</kbd>。
- 上一個標籤（Windows／Linux）：<kbd>Ctrl</kbd>+<kbd>Shift</kbd>+<kbd>Tab</kbd>。
- 標籤依排列順序循環切換；焦點在預覽、頁面核取方塊或工具列控制項時也可使用。
- 關閉標籤：點標籤右側的 ×；Windows／Linux 可按 <kbd>Ctrl</kbd>+<kbd>W</kbd>，Windows 另支援 <kbd>Ctrl</kbd>+<kbd>F4</kbd>，macOS 為 <kbd>⌘</kbd>+<kbd>W</kbd>。
- 關閉按鈕的 tooltip 會顯示目前平台適用的快捷鍵。

### 預覽與縮放

- 預覽頁面水平置中；Fit 使用單欄顯示。
- 100% 對應 Windows 的 96 DPI 顯示尺度。
- Fit 與全螢幕優先使用最近點擊且仍可見的頁面；未指定時使用預覽區中央附近的頁面。
- Fit 的適應比例可超出滑桿的手動範圍，實際比例仍顯示於工具列。
- 滑桿的手動範圍為 25%–200%；完整縮放說明可查看比例按鈕的 tooltip。
- 全螢幕對頁以同一比例完整顯示兩頁，最後剩一頁時單獨顯示。
- 返回主視窗後，保留原有縮放比例。

### 鍵盤捲動與切頁

- 一般預覽：<kbd>←</kbd>、<kbd>↑</kbd>、<kbd>→</kbd>、<kbd>↓</kbd> 捲動畫面；<kbd>Page Up</kbd>／<kbd>Page Down</kbd> 捲動一個畫面。
- Fit 模式：上述按鍵依序切換上一頁／下一頁，以目前可見頁面為起點。
- Fit 模式到達第一頁或最後一頁時不會越界，反向按一次即可切頁。
- 全螢幕上一頁／上一組：<kbd>←</kbd>、<kbd>↑</kbd> 或 <kbd>Page Up</kbd>。
- 全螢幕下一頁／下一組：<kbd>→</kbd>、<kbd>↓</kbd> 或 <kbd>Page Down</kbd>。
- 跳至第一頁／最後一頁：<kbd>Home</kbd>／<kbd>End</kbd>，依目前頁面排列順序跳轉；全螢幕對頁與封面＋對頁則跳至第一組／最後一組。
- 以上按鍵在縮放滑桿或頁面核取方塊取得焦點時仍可操作預覽區，不會改動縮放比例。

### 選頁與拖曳排序

- 點各頁左上角的核取方塊可個別選頁；核取方塊取得焦點後，也可按 <kbd>Space</kbd> 勾選。
- 全螢幕核取方塊會同步主視窗的選頁，返回後即可重組或拆分。
- 拖曳頁面縮圖或「拖曳排序」把手，可調整頁面順序。
- 拖曳時縮圖會跟隨游標，其他頁面以動畫移開並顯示插入空位。
- 移到頁面左半部插入其前方，右半部插入其後方。
- 放開滑鼠確認排序；按 <kbd>Esc</kbd> 取消。

### 重組與拆分輸出

- 標籤左側的核取方塊預設不勾選。
- 有勾選標籤：只輸出勾選檔案的已選頁面。
- 沒有勾選任何標籤：只輸出目前標籤的已選頁面。
- 勾選檔案沒有選頁時，不提供輸出頁面，也不會自動改選目前檔案。
- 拖曳標籤可調整檔案順序；輸出先依標籤順序，再依各檔內的頁面排序，未勾選的頁面不會輸出。
- 拆分指定 `report.pdf` 時，會輸出 `report_01.pdf`、`report_02.pdf` 等檔案。
- 拆分序號跨檔連續、從 1 開始，至少兩位；依本次輸出總數補零對齊，例如 100 頁使用 `001`–`100`，與原始頁碼無關。
- 已存在的單頁檔案會先詢問是否覆蓋。
- 暫不支援密碼保護的 PDF。

### 複製文字、區域 OCR 與擷取圖片

- 三種模式互斥；一般預覽與全螢幕皆可使用。
- 啟用時按鈕會顯示選取底色；關閉後恢復拖放排序。
- 複製文字：啟用後拖曳選取，放開滑鼠即可複製；掃描影像中的文字請使用區域 OCR。
- 區域 OCR：啟用後拖曳矩形範圍，放開滑鼠後辨識並複製；空白範圍保留原剪貼簿。
- 擷取圖片：啟用後點選內嵌點陣圖片，再選擇位置另存為 PNG。
- 圖片保留原始像素尺寸並套用透明遮罩，不受預覽縮放影響。
- 輸出完整內嵌圖片，不套用頁面上的旋轉或裁切，也不包含周圍文字與向量圖形。
- 點到空白處會顯示提示；同一位置有多張圖片時，選取最後繪製的圖片。
- 掃描頁面通常會擷取整張掃描圖，無法從中直接分離照片或圖表。

## 語言與配色

工具列右側提供兩個三態按鈕，首次使用皆預設跟隨系統，點擊即可立即切換：

- 介面語言：跟隨系統 → 繁體中文 → English → 跟隨系統。系統顯示語言為中文時使用繁體中文，其他語言使用 English；tooltip 顯示目前模式與實際語言。
- 介面配色：跟隨系統 → 淺色 → 深色 → 跟隨系統。手動指定配色後不受系統配色變化影響，回到系統模式則即時跟隨。

- 語言與配色的選擇會記住，重新啟動仍保留。
- 切換語言會更新既有頁面標籤、工具列、tooltip、狀態與對話框。
- 切換語言不改動檔名、選頁、頁序或比例。
- 檔案對話框採用 Qt 介面，按鈕與欄位會跟隨指定的中英文語言。

## 測試

- 文字選取的 OCR 備援與手動區域辨識共用多語言模型。
- 支援繁／簡中文、英文、日文及多種拉丁字母語言，目前模型不支援韓文。
- 專案的辨識品質測試主要集中在中英文；完整語言說明、操作與限制見 [OCR 說明](docs/OCR.md)。

```powershell
uv run pytest
```

## 開發與維護

- 架構、背景預覽協定、縮放定義、輸出安全機制與修改入口：[實作與維護指南](docs/IMPLEMENTATION.md)。
- 雲端建置、封裝驗證與 PyPI 發布：[打包與發布](docs/IMPLEMENTATION.md#15-打包與發布)。
- 工具列、按鈕、圖示筆畫、字型與深淺配色規格：[UI 設計參考](docs/UI_DESIGN.md)，可供其他專案移植。
