# RePDF — Read the PDF

[繁體中文](README.md) | [English](README.en.md)

RePDF 代表 **Read the PDF**，命令與 Python 套件名稱為 `repdf`。這是一套桌面 PDF 閱讀器，支援多標籤閱讀、列印、書籤與目錄跳頁、註解檢視與編輯、文字搜尋、選字複製、OCR 及圖片擷取，也可勾選頁面，依標籤與頁面排列順序重組或拆分輸出。重組與拆分保留原始頁面品質。

## 重點特色

- **支援規則表達式的搜尋**：可搜尋目前、勾選、所有標籤頁，或目前標籤所在資料夾的 PDF，並切換規則表達式、區分大小寫及僅限單字。點選搜尋結果即可跳到對應頁面，並以螢光筆效果標示命中文字。
- **直接擷取 PDF 內嵌圖片**：以滑鼠點選內嵌的點陣圖片，即可另存為 PNG，保留圖片的原始像素尺寸與透明度，不受閱讀時的縮放比例影響。

## 安裝與啟動

### 1. 下載發布的執行檔／App（建議）

從 [GitHub Releases](https://github.com/codemee/repdf/releases/latest) 下載適合平台的檔案，不需要安裝 Python 或 uv：

- **Windows x86_64**：下載 `repdf-<版本>-windows-x86_64.exe`，直接執行。
- **macOS Apple Silicon（arm64）**：下載 `repdf-<版本>-macos-arm64.dmg`，開啟後將 `RePDF.app` 拖入 Applications，再從 Applications 啟動。

- Release 同時提供 SHA256 校驗檔。
- 桌面套件已包含 OCR 執行環境與內建多語言模型；其他語言可在首次選用時下載，之後離線辨識。
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

## 操作方式

主工具列保留開檔、儲存、列印、搜尋、書籤、註解清單與檢視控制。

- 標籤過多時可使用標籤列兩端的線條箭頭捲動，或點右側向下箭頭，從完整檔名清單直接切換；清單依標籤排列順序顯示，並勾選目前標籤，滑鼠停留可看完整路徑。

- 複製文字、OCR 與擷取圖片直接位於主工具列。點「註解工具」顯示可拖移的水平懸浮工具列，提供文字畫線、文字註解及繪圖；顯示狀態會保留。
- 存檔與另存新檔為獨立按鈕；縮放、Fit、全螢幕模式下拉按鈕、語言與配色靠右排列。
- 單／雙頁選取工具位於各頁頁首核取方塊右側；重組與拆分保留在主工具列的同一組，右側以分隔線區分檢視控制。視窗寬度不足時，完整群組收入三點選單，選單內也以分隔線區分。
- 全螢幕下方提供可展開／收合的水平懸浮註解工具列，可拖曳左側握柄移動；不占用 PDF 的顯示區，退出後保留一般視窗懸浮工具列的顯示狀態，並可從懸浮列右側模式下拉選單切換全螢幕模式。

各工具的圖示與用途如下；將游標停在按鈕上也可查看 tooltip。

| 工具列圖示／控制元件 | 功能 | 操作說明 | 快捷鍵 |
| --- | --- | --- | --- |
| <picture><source media="(prefers-color-scheme: dark)" srcset="docs/images/toolbar-open-dark.png"><img src="docs/images/toolbar-open.png" width="24" alt="開啟 PDF 圖示"></picture> | 開啟 PDF | 一次選取多個 PDF，也可從檔案總管拖入。 | <kbd>Ctrl</kbd>+<kbd>O</kbd> |
| <picture><source media="(prefers-color-scheme: dark)" srcset="docs/images/toolbar-save-dark.png"><img src="docs/images/toolbar-save.png" width="24" alt="存檔"></picture> | 存檔 | 儲存目前檔案的完整頁面順序至原 PDF。 | <kbd>Ctrl</kbd>+<kbd>S</kbd> |
| <picture><source media="(prefers-color-scheme: dark)" srcset="docs/images/toolbar-save-as-dark.png"><img src="docs/images/toolbar-save-as.png" width="24" alt="另存新檔"></picture> | 另存新檔 | 將目前檔案的完整頁面順序另存為新 PDF。 | <kbd>Ctrl</kbd>+<kbd>Shift</kbd>+<kbd>S</kbd> |
| <picture><source media="(prefers-color-scheme: dark)" srcset="docs/images/toolbar-print-dark.png"><img src="docs/images/toolbar-print.png" width="24" alt="列印圖示"></picture> | 列印 | 設定頁面範圍、縮放與印表機，預覽確認後列印。 | Windows／Linux：<kbd>Ctrl</kbd>+<kbd>P</kbd>；macOS：<kbd>⌘</kbd>+<kbd>P</kbd> |
| <picture><source media="(prefers-color-scheme: dark)" srcset="docs/images/toolbar-annotation-tools-dark.png"><img src="docs/images/toolbar-annotation-tools.png" width="24" alt="註解工具"></picture> | 註解工具 | 顯示或隱藏可拖移的水平懸浮註解工具列；隱藏時完成目前文字輸入。 | — |
| <picture><source media="(prefers-color-scheme: dark)" srcset="docs/images/toolbar-more-dark.png"><img src="docs/images/toolbar-more.png" width="24" alt="更多"></picture> | 更多 | 視窗寬度不足時，開啟放不下的工具。 | — |
| <picture><source media="(prefers-color-scheme: dark)" srcset="docs/images/toolbar-copy-text-dark.png"><img src="docs/images/toolbar-copy-text.png" width="24" alt="複製文字圖示"></picture> | 複製文字 | 啟用後拖曳選取文字，放開滑鼠即複製到剪貼簿；選取的文字會顯示高亮。 | 啟用後：<kbd>Ctrl</kbd>+<kbd>A</kbd>（macOS：<kbd>⌘</kbd>+<kbd>A</kbd>） |
| <picture><source media="(prefers-color-scheme: dark)" srcset="docs/images/toolbar-ocr-region-dark.png"><img src="docs/images/toolbar-ocr-region.png" width="24" alt="區域 OCR 圖示"></picture> | 區域 OCR | 拖曳矩形框選頁面或圖片，放開滑鼠後辨識並複製文字。 | — |
| <picture><source media="(prefers-color-scheme: dark)" srcset="docs/images/toolbar-extract-image-dark.png"><img src="docs/images/toolbar-extract-image.png" width="24" alt="擷取圖片圖示"></picture> | 擷取圖片 | 啟用後點選內嵌點陣圖片，再選擇位置另存為 PNG。 | — |
| <picture><source media="(prefers-color-scheme: dark)" srcset="docs/images/toolbar-bookmarks-dark.png"><img src="docs/images/toolbar-bookmarks.png" width="24" alt="書籤圖示"></picture> | 書籤 | 在左側章節樹展開或收合書籤，點選章節即可跳頁。 | — |
| <picture><source media="(prefers-color-scheme: dark)" srcset="docs/images/toolbar-annotations-dark.png"><img src="docs/images/toolbar-annotations.png" width="24" alt="註解圖示"></picture> | 註解 | 在左側列出註解，點選即可跳至對應頁面。 | — |
| <picture><source media="(prefers-color-scheme: dark)" srcset="docs/images/toolbar-search-dark.png"><img src="docs/images/toolbar-search.png" width="24" alt="搜尋文字圖示"></picture> | 搜尋文字 | 在右側窗格搜尋文字，上方以「檔名／筆數」表格選檔案，下方以「頁碼／段落」表格選命中項目，單擊即可跳頁並高亮。 | Windows／Linux：<kbd>Ctrl</kbd>+<kbd>F</kbd>；macOS：<kbd>⌘</kbd>+<kbd>F</kbd> |
| <picture><source media="(prefers-color-scheme: dark)" srcset="docs/images/toolbar-text-markup-dark.png"><img src="docs/images/toolbar-text-markup.png" width="24" alt="文字畫線"></picture> | 文字畫線 | 拖曳選字畫線；下拉設定螢光筆、底線、刪除線、波浪線、顏色與粗細。 | — |
| <picture><source media="(prefers-color-scheme: dark)" srcset="docs/images/toolbar-callout-dark.png"><img src="docs/images/toolbar-callout.png" width="24" alt="箭頭文字註解"></picture> | 文字註解 | 下拉選擇箭頭文字框或便利貼，點選頁面新增；雙擊可編輯文字。 | — |
| <picture><source media="(prefers-color-scheme: dark)" srcset="docs/images/toolbar-drawing-dark.png"><img src="docs/images/toolbar-drawing.png" width="24" alt="繪圖註解"></picture> | 繪圖註解 | 下拉選擇直線、箭頭、矩形、橢圓或自由手繪；設定線條與填色後拖曳建立。 | — |
| <picture><source media="(prefers-color-scheme: dark)" srcset="docs/images/toolbar-odd-dark.png"><img src="docs/images/toolbar-odd.png" height="22" alt="單數頁工具"></picture> | 單數頁 | 位於每個單數頁的頁首，選取或取消本檔所有原始單數頁；核取方塊顯示三態。 | — |
| <picture><source media="(prefers-color-scheme: dark)" srcset="docs/images/toolbar-even-dark.png"><img src="docs/images/toolbar-even.png" height="22" alt="雙數頁工具"></picture> | 雙數頁 | 位於每個雙數頁的頁首，選取或取消本檔所有原始雙數頁；核取方塊顯示三態。 | — |
| <picture><source media="(prefers-color-scheme: dark)" srcset="docs/images/toolbar-export-dark.png"><img src="docs/images/toolbar-export.png" width="24" alt="重組輸出圖示"></picture> | 重組輸出 | 將選取頁面合併為單一 PDF；未選頁時輸出目前檢視頁面。 | — |
| <picture><source media="(prefers-color-scheme: dark)" srcset="docs/images/toolbar-split-dark.png"><img src="docs/images/toolbar-split.png" width="24" alt="拆分輸出圖示"></picture> | 拆分輸出 | 將選取頁面逐頁存成獨立 PDF 或 PNG；未選頁時使用目前檢視頁面。 | — |
| <picture><source media="(prefers-color-scheme: dark)" srcset="docs/images/toolbar-zoom-dark.png"><img src="docs/images/toolbar-zoom.png" width="160" alt="顯示比例與縮放滑桿"></picture> | 顯示比例 | 滑桿調整 25%–200%；點擊比例回到 100%。鍵盤縮放每次調整 25 個百分點。 | 放大：<kbd>Ctrl</kbd>+<kbd>+</kbd>／<kbd>Ctrl</kbd>+<kbd>=</kbd>；縮小：<kbd>Ctrl</kbd>+<kbd>-</kbd>；100%：<kbd>Ctrl</kbd>+<kbd>0</kbd> |
| <picture><source media="(prefers-color-scheme: dark)" srcset="docs/images/toolbar-fit-dark.png"><img src="docs/images/toolbar-fit.png" width="24" alt="Fit 圖示"></picture> | Fit | 將目前單頁等比例縮放至預覽區；調整視窗大小時自動適應。拖動滑桿或使用縮放快捷鍵會回到手動比例。 | — |
| <picture><source media="(prefers-color-scheme: dark)" srcset="docs/images/toolbar-trim-view-dark.png"><img src="docs/images/toolbar-trim-view.png" width="24" alt="裁切檢視圖示"></picture> | 裁切檢視 | 依 TrimBox 或可辨識的四角向量裁切線顯示裁切範圍；不修改 PDF。 | — |
| <picture><source media="(prefers-color-scheme: dark)" srcset="docs/images/toolbar-fullscreen-dark.png"><img src="docs/images/toolbar-fullscreen.png" width="24" alt="全螢幕"></picture> | 全螢幕 | 主按鈕開啟上次選擇的模式，右側下拉箭頭選擇單頁、對頁或封面＋對頁。 | <kbd>F11</kbd> 開啟／返回；<kbd>Esc</kbd> 返回 |
| <picture><source media="(prefers-color-scheme: dark)" srcset="docs/images/toolbar-language-system-dark.png"><img src="docs/images/toolbar-language-system.png" width="24" alt="跟隨系統語言"></picture> <picture><source media="(prefers-color-scheme: dark)" srcset="docs/images/toolbar-language-zh-dark.png"><img src="docs/images/toolbar-language-zh.png" width="24" alt="繁體中文"></picture> <picture><source media="(prefers-color-scheme: dark)" srcset="docs/images/toolbar-language-en-dark.png"><img src="docs/images/toolbar-language-en.png" width="24" alt="English"></picture> | 介面語言 | 點擊依序切換「跟隨系統 → 繁體中文 → English」，選擇會記住。 | — |
| <picture><source media="(prefers-color-scheme: dark)" srcset="docs/images/toolbar-theme-system-dark.png"><img src="docs/images/toolbar-theme-system.png" width="24" alt="跟隨系統配色：左白右黑圓形"></picture> <picture><source media="(prefers-color-scheme: dark)" srcset="docs/images/toolbar-theme-light-dark.png"><img src="docs/images/toolbar-theme-light.png" width="24" alt="淺色：太陽"></picture> <picture><source media="(prefers-color-scheme: dark)" srcset="docs/images/toolbar-theme-dark-dark.png"><img src="docs/images/toolbar-theme-dark.png" width="24" alt="深色：月亮"></picture> | 介面配色 | 點擊依序切換「跟隨系統 → 淺色 → 深色」，選擇會記住。 | — |

### 開啟與切換檔案

- 預設應用程式的 RePDF 設定頁中，`.pdf` 那一列顯示的是目前預設程式；點選該列，再選 RePDF。系統整合會安裝專用多尺寸圖示，供原始碼版與執行檔版共用。

- 可使用 `repdf "文件.pdf" "另一份文件.pdf"` 一次開啟多份 PDF。RePDF 已執行時，檔案會交給既有視窗；已開啟的檔案會切換至原標籤。
- **Windows**：按主視窗左上角程式圖示，選「系統整合 → 註冊 PDF 開啟功能」，加入 PDF 的「開啟方式」與「Open with RePDF」快顯選單。Windows 11 的獨立命令位於「顯示其他選項」。再按「開啟預設應用程式設定」，自行將 `.pdf` 指定給 RePDF。
- 免安裝版註冊時會複製到 `%LOCALAPPDATA%\Programs\RePDF\repdf.exe`；更新後請執行新版並重新註冊。若該位置的程式正在執行，請先關閉，再從新版註冊。Python 安裝版的關聯指向目前 Python 環境，移除或搬移環境後需重新註冊。
- 「取消註冊」移除 RePDF 的開啟功能，不會刪除 PDF 或固定位置的執行檔；更換預設程式請使用 Windows 設定。
- **macOS**：將 `RePDF.app` 放入 Applications。在 Finder 選取 PDF，按 <kbd>⌘</kbd>+<kbd>I</kbd> 開啟「取得資訊」，於「打開檔案的應用程式」選擇 RePDF，再按「全部更改」。應用程式選單的「系統整合」也提供操作提示。

- 檔案以主檔名顯示在標籤頁；將游標停在標籤上可查看完整路徑。
- 視窗標題列顯示 `RePDF` 與版本編號。
- 再次開啟同一路徑的檔案，會切換到既有標籤。
- 各檔案獨立保留比例、捲動位置、選頁與頁面排序。
- 下一個標籤（Windows／Linux）：<kbd>Ctrl</kbd>+<kbd>Tab</kbd>。
- 上一個標籤（Windows／Linux）：<kbd>Ctrl</kbd>+<kbd>Shift</kbd>+<kbd>Tab</kbd>。
- 標籤依排列順序循環切換；焦點在預覽、頁面核取方塊或工具列控制項時也可使用。
- 關閉標籤：點標籤右側的 ×；Windows／Linux 可按 <kbd>Ctrl</kbd>+<kbd>W</kbd>，Windows 另支援 <kbd>Ctrl</kbd>+<kbd>F4</kbd>，macOS 為 <kbd>⌘</kbd>+<kbd>W</kbd>。
- 關閉按鈕的 tooltip 會顯示目前平台適用的快捷鍵。

### 開啟密碼保護的 PDF

1. 開啟檔案；若需要密碼，程式會顯示密碼對話框。
2. 輸入密碼並按確認；可勾選「顯示密碼」檢查輸入內容。
3. 密碼錯誤時可重新輸入；取消只略過該檔案，不影響同批開啟的其他檔案。

- 不需要密碼即可開啟的加密 PDF 會直接讀取。
- 解鎖後可閱讀、搜尋、列印、重組、拆分、複製文字、區域 OCR 與擷取圖片。
- 同一標籤開啟期間不再詢問；關閉後再次開啟需重新輸入。
- 密碼只在記憶體中使用，不儲存到設定檔或記錄。
- 重組與拆分產生的 **新 PDF 不加密**，完成訊息會明確標示；原始檔案保持不變。

### 預覽與縮放

- 預覽頁面水平置中；Fit 使用單欄顯示。
- 大檔案優先顯示目前閱讀的頁面；跳頁時不必等待整份文件載入。
- 100% 對應 Windows 的 96 DPI 顯示尺度。
- Fit 與全螢幕優先使用最近點擊且仍可見的頁面；未指定時使用預覽區中央附近的頁面。
- Fit 的適應比例可超出滑桿的手動範圍，實際比例仍顯示於工具列。
- 滑桿的手動範圍為 25%–200%；完整縮放說明可查看比例按鈕的 tooltip。
- 全螢幕工具以主按鈕及右側下拉箭頭選擇單頁、對頁或封面＋對頁；<kbd>F11</kbd> 沿用本次執行中最近選擇的模式。單頁每次一頁，對頁由第一頁開始兩頁一組；封面＋對頁先單獨顯示第一頁，再將其餘頁面兩頁分組。
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

### 頁碼與直接跳頁

- 狀態列右側顯示目前頁碼與總頁數，捲動或使用搜尋、書籤跳頁時會同步更新。
- PDF 有內建頁碼標籤時，會同時顯示書頁與原始頁次，例如「書頁 iii｜PDF 3 / 800」或「書頁 12｜PDF 20 / 800」。較長的標籤會截短，滑鼠停留可查看完整內容；沒有標籤時維持一般頁碼顯示。
- 書頁使用 PDF 提供的標籤，不以 OCR 推測，也不保證與頁面上印出的數字相同；跳頁輸入欄仍使用原始 PDF 頁次。
- 點頁碼欄輸入號碼，按 <kbd>Enter</kbd> 跳到指定頁；按 <kbd>Esc</kbd> 或離開輸入欄可取消尚未送出的輸入。
- 頁碼與頁面卡片上的原始頁碼一致；重新排序後，輸入同一頁碼仍會找到原本的頁面。
- 跳頁保留目前縮放／Fit 模式；輸入超出範圍或無效內容時會顯示提示，不會改變目前頁面。

### 存檔與另存新檔

- 新開啟的 PDF 預設使用 Fit 模式，自動適應閱讀區；調整比例可切換為手動縮放。
- 「裁切檢視」優先使用有效 TrimBox；沒有 TrimBox 時辨識頁邊完整的四角向量裁切線。兩者都沒有或記號不完整時維持完整頁面，工具停用；影像中的裁切線目前不辨識。啟用後頁卡依裁切範圍縮小，框外留白不再佔用檢視空間；此模式不修改 PDF。
- 全螢幕的單頁、雙頁與封面模式也支援裁切檢視，可在懸浮工具列用裁切圖示切換；顯示組合中有可確認的裁切範圍時工具才會啟用。
- 拖曳調整頁面順序後，標籤名稱會顯示 `*`；點「存檔」或按 <kbd>Ctrl</kbd>+<kbd>S</kbd> 儲存原 PDF。
- 點「另存新檔」或按 <kbd>Ctrl</kbd>+<kbd>Shift</kbd>+<kbd>S</kbd>，選擇另一個檔名；儲存完成後，標籤改為新檔案。macOS 使用 <kbd>⌘</kbd> 取代 <kbd>Ctrl</kbd>。
- 存檔包含目前標籤的所有頁面，與頁面及標籤核取方塊無關；「重組輸出／拆分」使用勾選內容，沒有可輸出的勾選頁面時使用目前檢視頁面。
- 重組與拆分按鈕旁的下拉選單可勾選「依 TrimBox 裁切（隱藏裁切線）」，套用於輸出的 PDF，兩個工具各自設定、各自記住；預設關閉。輸出頁面的 MediaBox 與 CropBox 限縮至有效 TrimBox，隱藏框外裁切線，再移除 TrimBox 設定；沒有 TrimBox 的頁面保留原樣。原始檔與 PNG 輸出不受影響。
- 啟用時，重組與拆分圖示右上角會加上裁切標記，方便辨識目前輸出設定；關閉後恢復原圖示。
- 保留書籤、內部連結、註解、文件資料與頁碼標籤。密碼 PDF 以開啟時使用的密碼重新進行 AES-256 加密。
- 儲存失敗時保留原檔與目前頁序，可修正問題後重試；另存目的檔案若已在其他標籤開啟，請選擇其他檔名。
- 已開啟的 PDF 在磁碟上更新時會提示重新載入；重新載入保留標籤位置、頁碼與縮放。若有未儲存變更，可先另存新檔，或選擇保留目前內容。重新載入失敗時保留原標籤。

### 列印

- 點列印圖示，或按 <kbd>Ctrl</kbd>+<kbd>P</kbd>（macOS：<kbd>⌘</kbd>+<kbd>P</kbd>），直接開啟整合列印視窗；全螢幕中使用快捷鍵會先返回主視窗。
- 選擇目前文件全部頁面、目前頁面、指定頁次或勾選頁面；指定頁次使用原始 PDF 頁碼，例如 `1,3,5-8`。
- 勾選頁面沿用輸出規則：有勾選標籤時使用這些標籤內勾選的頁面；沒有勾選標籤時使用目前標籤內勾選的頁面。
- 列印依目前標籤與頁面排列順序進行；列印視窗會顯示文件數與頁數。
- 預設符合可列印範圍，也可選實際大小；每張紙放一頁並置中，不自動旋轉。實際大小超出可列印範圍時會裁切。
- 左側可直接選擇印表機、紙張、方向、份數、逐份列印、雙面及色彩；雙面與色彩選項依印表機能力提供，調整紙張與範圍時會同步更新右側預覽。
- 右側可用前後頁圖示、頁次輸入欄或 <kbd>Page Up</kbd>／<kbd>Page Down</kbd> 翻頁，並選擇符合視窗或放大檢視。預覽只載入目前頁面，大文件不會一次渲染全檔。
- 預覽中的白色紙張依本次紙張尺寸與方向顯示，虛線表示可列印範圍；可切換符合範圍／實際大小，查看邊距與裁切效果。視窗縮窄時，設定與預覽改為上下排列，設定區可捲動。
- 僅需紙匣、列印品質或其他驅動專屬選項時，再按「進階設定」開啟系統交談窗；返回後設定會同步至預覽。若在系統交談窗另選頁次，使用本次列印清單的 `1..N`。
- 預覽顯示一份列印內容，份數另列於紙張資訊；確認後按「列印」才開始送印。關閉或取消預覽不會送印。
- 列印 PDF 內容，不包含搜尋高亮、選字標記或操作介面。
- 大文件逐頁處理，進度視窗可取消後續送印；已送出的頁面可能仍需從系統列印佇列取消。
- 沒有印表機時仍可預覽，列印按鈕會停用；實際送印前需先安裝或設定系統印表機，不需要額外安裝列印工具。

### 書籤與目錄跳頁

- 點工具列的「書籤」圖示開啟左側章節樹，可展開或收合子章節，點選章節即可跳頁。
- 書籤跟隨目前標籤頁切換；沒有內建書籤的文件會顯示提示。
- 一般預覽與全螢幕都可直接點選 PDF 頁內的目錄連結；滑鼠移到可跳頁區域時會顯示手指游標與目的頁碼。
- 跳頁保留目前縮放／Fit 模式。頁面已重新排序時，仍會找到目的章節所屬的原始頁面。
- 視窗縮窄時，書籤與 PDF 以單一窗格切換；點選章節後返回 PDF，再點「書籤」可返回目錄。書籤、註解與搜尋窗格可透過各自的工具按鈕切換。
- 啟用複製文字、區域 OCR 或圖片擷取模式時，頁內連結暫停點選；停用後即可跳頁，拖曳頁面仍可排序。
- 一般預覽與全螢幕可點選 PDF 內建的 HTTP／HTTPS 超連結，以系統預設瀏覽器開啟；滑鼠停留可查看網址。
- 此功能使用 PDF 已有的書籤與連結；純文字或掃描圖片形式的目錄、網址不會自動變成連結。電子郵件、外部文件與其他動作不在支援範圍。

### 註解清單

- 點工具列的「註解」對話框圖示，開啟目前標籤頁的左側註解清單。
- 清單依 PDF 原始頁序分組，每頁顯示註解數量，預設收合；展開後查看個別註解的類型與摘要。切換標籤、書籤或介面語言後會保留展開狀態。滑鼠停留可查看完整內容、作者、主旨及修改時間（若文件有提供）。
- 點選頁碼群組即可跳到該頁清單中的第一個註解，並標示其範圍；點選個別註解會跳到對應位置，並以半透明底色與外框標示註解範圍。保留目前縮放／Fit 模式，頁面重新排列後仍會找到原始目標頁。
- 選取含文字的註解時，會自動將註解文字複製到剪貼簿；頁碼群組會複製第一個註解的文字。無文字的註解不會覆蓋剪貼簿內容。
- 關閉註解窗格或切換至其他側欄時，會取消框選；重新開啟清單不會自動複製文字或恢復框選。
- 框選會跟隨縮放與全螢幕顯示；點選另一註解或頁碼群組會更新標示，點選書籤或搜尋結果則清除標示。文件未提供有效註解範圍時，仍可跳頁。
- 支援備註、文字方塊、螢光標示、底線、刪除線、手繪及形狀等註解。文字標示若沒有附註內容，會嘗試顯示標示的原文。
- 在一般閱讀模式可直接點選頁面上的註解，框選其範圍並同步選取左側清單、展開對應頁面群組；全螢幕也可使用。選字、區域 OCR 與圖片擷取模式保留各自操作。窄視窗點選後維持 PDF 顯示，再按「註解」即可查看清單中的選取項目。
- 註解跟隨標籤頁切換；沒有註解時顯示提示。書籤、註解與搜尋窗格透過各自的按鈕切換。
- 視窗較窄時，點選後返回 PDF；再點「註解」可返回清單。
- 完整註解清單只在開啟窗格時於背景讀取；頁面點選範圍則隨目前需要顯示的頁面讀取，不會在開檔時掃描整份文件；可編輯的註解由下方工具操作；其他類型維持檢視，不執行附件內容。

### 新增與編輯註解

- 文字畫線面板可勾選「連帶加入文字註解」，選擇箭頭文字框或便利貼。選字完成後立即輸入說明；箭頭框指向選取範圍上緣中央，便利貼放在該處上方，位置會限制在頁面內。畫線與註解可一次復原；取消輸入則只保留畫線。
- **文字註解工具**：下拉面板選擇「箭頭文字框」或「便利貼」；選擇後啟用該工具，主按鈕圖示隨選擇切換。
- **便利貼**：點選頁面放置圖示，在交談窗輸入內容並儲存；雙擊圖示可編輯，拖曳圖示可移動，清單與快捷鍵也能複製其文字。
- **繪圖註解**：下拉選擇直線、箭頭、矩形、橢圓或自由手繪，於頁面拖曳建立；可調整顏色與 0.5–6 pt 粗細，矩形與橢圓另可設定填色或透明背景。
- 選取繪圖後可拖移、調整直線／箭頭端點，或以四角控點縮放矩形、橢圓與手繪；<kbd>Esc</kbd> 取消目前的繪製。

- **文字畫線**：啟用工具後拖曳選取文字，可跨行。下拉箭頭設定螢光筆、底線、刪除線或波浪線，以及顏色與 0.5–6 pt 粗細；選取範圍依文字順序呈現，拖曳時預覽選中的字元；預設紅色底線、1 pt。螢光筆預設半透明黃色，不使用線條粗細。沒有文字層的圖片區域不會自動 OCR。
- 註解清單以圖示標示類型，滑鼠停留可看完整類型與內容；每個有文字的項目右側提供複製按鈕，點一下即可複製完整內容，不會切換頁面；在清單或頁面上選取註解後，也可按 <kbd>Ctrl</kbd>+<kbd>C</kbd> 複製文字（macOS 使用 <kbd>⌘</kbd>+<kbd>C</kbd>）；選取有文字的項目後，下方內容區可拖曳選字、按全選按鈕或複製按鈕，也支援 <kbd>Ctrl</kbd>+<kbd>A</kbd>／<kbd>Ctrl</kbd>+<kbd>C</kbd>。
- **箭頭文字框**：啟用工具後點選指向位置，自動在旁邊建立文字框並輸入內容；文字框保留建立時的最小寬度，隨單行文字增寬，到頁面邊界才換行，並在頁面範圍內增高；在框外點一下完成輸入，再次點選才建立下一個註解。預設透明背景、藍字、紅框紅箭頭、12 pt；新建文字框預設 6 pt 圓角；下拉面板可分別調整文字色、線條色、線寬、字級、背景與圓角，圓角設為 0 即為直角。
- 直接雙擊文字框即可編輯，不必先開啟註解窗格；單擊會選取並開啟註解清單。<kbd>Enter</kbd> 換行，<kbd>Ctrl</kbd>+<kbd>Enter</kbd> 完成，<kbd>Esc</kbd> 取消本次編輯；空白內容不建立註解。
- 選取文字框後可拖動框本身、四角控制點或箭頭端點；游標分別顯示移動、對角縮放或手指提示；選取畫線可修改方式與樣式。<kbd>Delete</kbd> 刪除，<kbd>Ctrl</kbd>+<kbd>Z</kbd> 復原，<kbd>Ctrl</kbd>+<kbd>Y</kbd>／<kbd>Ctrl</kbd>+<kbd>Shift</kbd>+<kbd>Z</kbd> 重做；macOS 使用系統對應快捷鍵。
- 支援本程式建立的註解，以及可可靠解析的標準螢光筆、底線、刪除線、波浪線與箭頭文字框。本程式新增的便利貼與繪圖存檔重開後可繼續編輯；其他程式的便利貼、繪圖，以及鎖定、特殊外觀、無法還原字型或混合格式的項目維持檢視，選取時會顯示原因。
- 註解工具與選字、OCR、圖片擷取互斥，並支援全螢幕。樣式會記住供下次使用；選取可編輯項目時，面板的顏色與樣式修改直接套用該項目；切換文字或繪圖工具種類則準備建立新項目。
- 變更會顯示未儲存星號。存檔後重新開啟仍可編輯；列印、重組及拆分也會包含未儲存的註解變更。關閉文件時可選擇儲存、不儲存或取消。
- 儲存為標準 PDF 註解及完整外觀，包含中文字型資源，可由其他 PDF 閱讀器顯示；其他程式是否提供相同編輯操作，依其功能而定。

### 搜尋文字

1. 點「搜尋文字」或按 <kbd>Ctrl</kbd>+<kbd>F</kbd>（macOS：<kbd>⌘</kbd>+<kbd>F</kbd>），開啟右側窗格。
2. 輸入搜尋內容，選擇「目前標籤頁」、「勾選的標籤頁」、「所有標籤頁」或「目前標籤所在的資料夾」；同一列的 `.*`、`Aa` 與底線 `ab` 狀態按鈕分別切換「規則表達式」、「區分大小寫」與「僅限單字」，亮起表示啟用。
3. 按 <kbd>Enter</kbd> 或「搜尋」執行；修改條件後再次執行才會更新結果。
4. 上方「檔案」表格列出檔名與命中筆數；選取檔案後，下方「命中項目」表格以「頁碼／段落」分欄顯示，每次命中各自一列，以交錯底色單行呈現命中附近的摘要；內容過長時以 `...` 結尾，滑鼠停留可查看完整段落。
5. 單擊段落，或在命中項目清單中按 <kbd>↑</kbd>／<kbd>↓</kbd> 切換項目，會切換到對應標籤與頁面，讓命中處盡量顯示在預覽窗格的縱向中央；尚未載入的頁面會自動載入。只以螢光筆標示目前選取項目的命中文字，切換項目時會移除上一筆標示。

- 預設搜尋目前標籤頁、不區分大小寫、不使用規則表達式；四種範圍互斥。
- 搜尋工具是狀態按鈕，亮起表示搜尋面板正在顯示；再按一次即可關閉。關閉面板或切換其他側欄時，按鈕狀態會同步更新。
- 焦點在搜尋窗格時，方向鍵只操作搜尋控制項；命中清單到達首尾後再按上下鍵，不會捲動 PDF 預覽。
- 「僅限單字」預設關閉；啟用後，命中內容兩側不能緊接 Unicode 字母、數字、底線或組合標記，例如 `cat` 不會命中 `catalog`。可與規則表達式併用；此選項不會替連續中文斷詞。
- 「勾選的標籤頁」沿用標籤左側的核取方塊；沒有勾選時會提示，不自動改搜目前檔案。
- 搜尋涵蓋範圍內已成功載入檔案的全部頁面，不受頁面勾選限制；密碼文件需先解鎖。
- 「目前標籤所在的資料夾」搜尋該 PDF 所在資料夾這一層的所有 PDF，包含尚未開啟的檔案，不包含子資料夾；搜尋本身不會替所有檔案開啟標籤。
- 在結果中選取檔案或命中段落時，尚未開啟的 PDF 會自動開為新標籤；已開啟的檔案沿用原標籤，並跳到命中位置。密碼保護檔案請先開啟並輸入密碼，再進行資料夾搜尋；無法讀取的檔案會列入失敗提示，其餘結果仍可使用。
- 只搜尋既有文字層，不啟動 OCR；掃描圖片或損壞的文字層可能搜尋不到。
- 同段落內的多次命中各自列為一筆，可逐筆跳轉與標示。段落依文字行與版面位置推估，不跨頁搜尋，分欄及複雜版面可能有段落差異。
- 支援同一段落內的跨行搜尋：視覺換行會合併，中日文字之間不補空格，其餘續行以空格銜接；跨行命中會標示對應各行的文字。
- 規則表達式採 Python 相容語法；無效規則會顯示錯誤，零長度位置不列為可高亮的命中。
- 每段正則匹配最多 1 秒；逾時會停止搜尋並標示結果不完整。也可按「停止」保留目前已找到的結果。
- 可拖曳右側窗格寬度與上下結果區的分隔線；搜尋不改動選頁、排序或縮放模式。
- 視窗寬度小於 640px 時，搜尋與 PDF 改為單一窗格切換；點結果後顯示 PDF，再點搜尋按鈕可返回結果。
- 視窗較矮時，從三點「選項」選單調整範圍、規則表達式、區分大小寫與僅限單字設定。
- 點選搜尋選項列的色塊按鈕可設定命中標示顏色；較矮視窗可從「選項 → 命中標示顏色」開啟。變更會立即更新現有標示，無須重新搜尋，並套用至全螢幕與之後載入的頁面；選擇會記住，取消選色不會變更設定。
- 關閉搜尋窗格會停止搜尋並清除高亮，保留輸入與結果；標籤頁搜尋會在文件關閉時移除其結果；資料夾搜尋保留結果，方便再次開啟。
- 全螢幕使用搜尋快捷鍵時，會返回主視窗並開啟搜尋窗格。

### 選頁與拖曳排序

- 點各頁左上角的核取方塊可個別選頁；核取方塊取得焦點後，也可按 <kbd>Space</kbd> 勾選。
- 全螢幕核取方塊會同步主視窗的選頁，返回後即可重組或拆分。
- 拖曳頁面縮圖或「拖曳排序」把手，可調整頁面順序。
- 拖曳時縮圖會跟隨游標，其他頁面以動畫移開並顯示插入空位。
- 移到頁面左半部插入其前方，右半部插入其後方。
- 放開滑鼠確認排序；按 <kbd>Esc</kbd> 取消。

### 輸出 PDF、PNG 與拆分

- 標籤左側的核取方塊預設不勾選。
- 有勾選標籤：只輸出勾選檔案的已選頁面。
- 沒有勾選任何標籤：只輸出目前標籤的已選頁面。
- 若上述範圍內沒有勾選頁面，預設輸出目前標籤正在檢視的單一頁面；全螢幕並排時使用目前組的第一頁。
- 拖曳標籤可調整檔案順序；輸出先依標籤順序，再依各檔內的頁面排序，未勾選的頁面不會輸出。
- 拆分指定 `report.pdf` 時，會輸出 `report_01.pdf`、`report_02.pdf` 等檔案。
- 拆分序號跨檔連續、從 1 開始，至少兩位；依本次輸出總數補零對齊，例如 100 頁使用 `001`–`100`，與原始頁碼無關。
- 已存在的單頁檔案會先詢問是否覆蓋。
- 密碼保護的 PDF 須先成功解鎖；輸出的新 PDF 不加密。
- 「重組輸出」將選取頁面合併為單一 PDF；「拆分輸出」可選 PDF 或 PNG，每頁各產生一個檔案。PDF 保留原始頁面品質；PNG 將整頁文字、圖片與註解合成為圖檔，包含尚未儲存的註解。
- PNG 單頁使用指定檔名；多頁指定 `report.png` 時，依輸出順序產生 `report_01.png`、`report_02.png` 等檔案，序號規則與拆分相同。
- PNG 以 300 DPI 輸出，不受閱讀縮放比例影響；超大頁面會降低解析度，使單張不超過 3,000 萬像素。輸出期間可取消，取消時不發布本次產生的圖檔。

### 複製文字、區域 OCR 與擷取圖片

- 在複製文字模式持續拖曳到頁面上下邊緣，可延伸到前後頁；拖到閱讀區邊緣會自動捲動，全螢幕會切換前後頁組。放開滑鼠後依畫面頁序複製整段選取文字。

- 啟用「複製文字」後，在 PDF 閱讀區按 <kbd>Ctrl</kbd>+<kbd>A</kbd>（macOS：<kbd>⌘</kbd>+<kbd>A</kbd>），可選取整份 PDF 的文字並複製到剪貼簿，一般與全螢幕皆可使用。
- 全文複製依目前頁面排列順序處理全部頁面，不受頁面核取方塊影響；背景擷取期間顯示進度，完成前不改動剪貼簿。切換標籤、離開選字模式或關閉文件會取消進行中的擷取。
- 全文複製只讀取文字層，不自動 OCR 掃描頁，也不包含註解文字；無文字或失敗時保留原剪貼簿內容。搜尋欄與文字編輯框中的全選仍只選取該欄位。

- 三種模式互斥；一般預覽與全螢幕皆可使用。
- 啟用時按鈕以 hover 底色與強調色圖示標示，不顯示外框；關閉後恢復拖放排序。
- 複製文字：啟用後拖曳選取，放開滑鼠即可複製；掃描影像中的文字請使用區域 OCR。
- 區域 OCR：啟用後拖曳矩形範圍，放開滑鼠後辨識並複製；空白範圍保留原剪貼簿。
- 擷取圖片：啟用後點選內嵌點陣圖片，再選擇位置另存為 PNG。
- 圖片保留原始像素尺寸並套用透明遮罩，不受預覽縮放影響。
- 輸出完整內嵌圖片，不套用頁面上的旋轉或裁切，也不包含周圍文字與向量圖形。
- 點到空白處會顯示提示；同一位置有多張圖片時，選取最後繪製的圖片。
- 掃描頁面通常會擷取整張掃描圖，無法從中直接分離照片或圖表。
- OCR 預設支援繁體中文、簡體中文、英文、日文及多種拉丁字母語言。點「區域 OCR」旁的箭頭，可選韓文、泰文、俄文／烏克蘭文、阿拉伯文與印地文／尼泊爾文；另提供希臘文、泰米爾文與泰盧固文。
- 選「自動＋已下載模型」可共用內建與已下載模型，逐行選擇辨識結果，不會自行下載其他模型。
- 語言選單以分隔線區分自動選項、已下載與未下載三組，不顯示群組標題；已下載的模型名稱後會標記「已下載」。模型下載、遺失或損壞後，分組與標記會自動更新。
- 額外模型會先顯示下載確認，下載完成才切換語言；取消或失敗保留原設定。語言設定會記住，並套用於區域 OCR 及損壞文字備援。辨識後請校對結果。完整操作與限制見 [OCR 說明](docs/OCR.md)。

## 語言與配色

工具列右側提供兩個三態按鈕，首次使用皆預設跟隨系統，點擊即可立即切換：

- 介面語言：跟隨系統 → 繁體中文 → English → 跟隨系統。系統顯示語言為中文時使用繁體中文，其他語言使用 English；tooltip 顯示目前模式與實際語言。
- 介面配色：跟隨系統 → 淺色 → 深色 → 跟隨系統。手動指定配色後不受系統配色變化影響，回到系統模式則即時跟隨。
- 深色配色採《新世紀福音戰士》初號機風格，以紫黑背景、紫色面板、螢光綠強調色及少量橙色呈現；PDF 頁面保留原始顏色。

- 語言與配色的選擇會記住，重新啟動仍保留。
- 切換語言會更新既有頁面標籤、工具列、tooltip、狀態與對話框。
- 切換語言不改動檔名、選頁、頁序或比例。
- 檔案選擇視窗的按鈕與欄位會跟隨指定的中英文語言。

## 授權

RePDF 採用 **GNU General Public License v3.0（GPL-3.0-only）**。允許使用、修改與商用；散布程式或修改版時，須遵守 GPL，提供對應原始碼並保留授權與版權聲明。程式不提供任何擔保。

在程式內可開啟「關於 RePDF」，查看版本、版權、GPL 全文與離線第三方授權，或前往原始碼儲存庫。Windows：點選主視窗左上角程式圖示，在系統功能表選「關於 RePDF」（亦可按 <kbd>Alt</kbd>+<kbd>Space</kbd>）。macOS：在系統選單列的「RePDF」應用程式選單選「關於 RePDF」。

完整條款見 [LICENSE](LICENSE)，版權說明見 [NOTICE](NOTICE)，第三方程式庫與模型維持各自的授權；完整清單見 [第三方聲明](THIRD_PARTY_NOTICES.md) 與 [授權核對](docs/LICENSE_AUDIT.md)。

## 其他文件

- [OCR 操作與限制](docs/OCR.md)
- [開發、測試與發布指南](docs/IMPLEMENTATION.md)
- [UI 設計參考](docs/UI_DESIGN.md)
