# RePDF — Read the PDF

[繁體中文](README.md) | [English](README.en.md)

RePDF stands for **Read the PDF**. Its command and Python package name are `repdf`. This desktop PDF reader supports multiple tabs, printing, bookmarks and table-of-contents links, annotation viewing and editing, text search, text copying, OCR, and image extraction. You can also select pages and rearrange or split them into new PDFs in tab and page order, preserving the original page quality.

## Highlights

- **Search with regular expressions**: Search the current tab, checked tabs, all tabs, or PDFs in the current tab’s folder, with regular expression, case-sensitive, and whole-word options. Click a result to jump to its page and highlight the matching text.
- **Extract embedded PDF images directly**: Click an embedded raster image to save it as a PNG, preserving its original pixel dimensions and transparency regardless of the reading zoom level.

## Install and launch

### 1. Download the desktop app (recommended)

Download the file for your platform from [GitHub Releases](https://github.com/codemee/repdf/releases/latest). Python and uv are not required.

- **Windows x86_64**: Download and run `repdf-<version>-windows-x86_64.exe`.
- **macOS Apple Silicon (arm64)**: Download `repdf-<version>-macos-arm64.dmg`, open it, drag `RePDF.app` into Applications, and launch it from there.
- Releases include SHA256 checksum files.
- Desktop packages include the OCR runtime and built-in multilingual model. Additional languages can be downloaded when first selected, then used offline.
- The apps currently have no Windows code signature or macOS Developer ID signature/notarization, so your system may display a security prompt.

### 2. Install with uv tool

If you already have [uv](https://docs.astral.sh/uv/), install from PyPI into an isolated tool environment:

```sh
uv tool install repdf
repdf
```

- Python 3.11 or later is required. uv can download a suitable Python version when needed.
- You can also install using the download URL of a `repdf` wheel from a release.
- If your terminal cannot find `repdf`, run `uv tool update-shell` and reopen the terminal.

## Using RePDF

The main toolbar keeps file, search, navigation-pane and view controls.

- Copy text, OCR and image extraction appear directly on the main toolbar. **Annotation tools** shows a draggable horizontal floating toolbar for markup, text annotations and drawings; its visibility is remembered.
- **Save** and **Save As** have separate buttons. Zoom, Fit, the fullscreen mode dropdown, language and theme stay on the right.
- Odd/even selection, export and split appear directly as one group on the main toolbar, separated from the view controls. When space is insufficient, each complete group moves into the overflow menu, where separators retain the grouping.
- Fullscreen provides a collapsible horizontal floating annotation toolbar near the bottom. Drag its left grip to move it. It overlays the page without reducing the fit area, and exiting preserves the reading window’s floating-toolbar visibility. Use the mode dropdown at the right of the floating toolbar to switch fullscreen modes.

The controls are described below. Hover over a control to see its tooltip, including any keyboard shortcuts.

| Toolbar icon/control | Function | Usage | Shortcut |
| --- | --- | --- | --- |
| <picture><source media="(prefers-color-scheme: dark)" srcset="docs/images/toolbar-open-dark.png"><img src="docs/images/toolbar-open.png" width="24" alt="Open PDF"></picture> | Open PDF | Select multiple PDFs at once, or drag files in from your file manager. | <kbd>Ctrl</kbd>+<kbd>O</kbd> |
| <picture><source media="(prefers-color-scheme: dark)" srcset="docs/images/toolbar-save-dark.png"><img src="docs/images/toolbar-save.png" width="24" alt="Save"></picture> | Save | Save the current document with its complete page order to the original PDF. | <kbd>Ctrl</kbd>+<kbd>S</kbd> |
| <picture><source media="(prefers-color-scheme: dark)" srcset="docs/images/toolbar-save-as-dark.png"><img src="docs/images/toolbar-save-as.png" width="24" alt="Save As"></picture> | Save As | Save the current document with its complete page order as another PDF. | <kbd>Ctrl</kbd>+<kbd>Shift</kbd>+<kbd>S</kbd> |
| <picture><source media="(prefers-color-scheme: dark)" srcset="docs/images/toolbar-print-dark.png"><img src="docs/images/toolbar-print.png" width="24" alt="Print"></picture> | Print | Choose pages, scaling, and a printer, then review the preview before printing. | Windows/Linux: <kbd>Ctrl</kbd>+<kbd>P</kbd>; macOS: <kbd>⌘</kbd>+<kbd>P</kbd> |
| <picture><source media="(prefers-color-scheme: dark)" srcset="docs/images/toolbar-annotation-tools-dark.png"><img src="docs/images/toolbar-annotation-tools.png" width="24" alt="Annotation tools"></picture> | Annotation tools | Show/hide the draggable horizontal floating annotation toolbar. Hiding finishes text input. | — |
| <picture><source media="(prefers-color-scheme: dark)" srcset="docs/images/toolbar-more-dark.png"><img src="docs/images/toolbar-more.png" width="24" alt="More"></picture> | More | Open controls that do not fit in a narrow window. | — |
| <picture><source media="(prefers-color-scheme: dark)" srcset="docs/images/toolbar-copy-text-dark.png"><img src="docs/images/toolbar-copy-text.png" width="24" alt="Copy text"></picture> | Copy text | Drag to select text, then release to copy it to the clipboard. Selected text is highlighted. | When enabled: <kbd>Ctrl</kbd>+<kbd>A</kbd> (macOS: <kbd>⌘</kbd>+<kbd>A</kbd>) |
| <picture><source media="(prefers-color-scheme: dark)" srcset="docs/images/toolbar-ocr-region-dark.png"><img src="docs/images/toolbar-ocr-region.png" width="24" alt="Region OCR"></picture> | Region OCR | Draw a rectangle over a page or image, then release to recognize and copy the text. | — |
| <picture><source media="(prefers-color-scheme: dark)" srcset="docs/images/toolbar-extract-image-dark.png"><img src="docs/images/toolbar-extract-image.png" width="24" alt="Extract image"></picture> | Extract image | Enable this mode, click an embedded raster image, and choose where to save it as a PNG. | — |
| <picture><source media="(prefers-color-scheme: dark)" srcset="docs/images/toolbar-bookmarks-dark.png"><img src="docs/images/toolbar-bookmarks.png" width="24" alt="Bookmarks"></picture> | Bookmarks | Expand or collapse the chapter tree on the left. Click a chapter to jump to it. | — |
| <picture><source media="(prefers-color-scheme: dark)" srcset="docs/images/toolbar-annotations-dark.png"><img src="docs/images/toolbar-annotations.png" width="24" alt="Annotations"></picture> | Annotations | List comments in the left pane. Click one to jump to its page. | — |
| <picture><source media="(prefers-color-scheme: dark)" srcset="docs/images/toolbar-search-dark.png"><img src="docs/images/toolbar-search.png" width="24" alt="Search text"></picture> | Search text | Search in the right pane. Select a filename/count row above and a page/paragraph row below to navigate and highlight matches. | Windows/Linux: <kbd>Ctrl</kbd>+<kbd>F</kbd>; macOS: <kbd>⌘</kbd>+<kbd>F</kbd> |
| <picture><source media="(prefers-color-scheme: dark)" srcset="docs/images/toolbar-text-markup-dark.png"><img src="docs/images/toolbar-text-markup.png" width="24" alt="Text markup"></picture> | Text markup | Drag over text to add markup. The arrow opens highlight, underline, strikethrough, squiggly, colour and width options. | — |
| <picture><source media="(prefers-color-scheme: dark)" srcset="docs/images/toolbar-callout-dark.png"><img src="docs/images/toolbar-callout.png" width="24" alt="Callout annotation"></picture> | Text annotations | Choose a callout or sticky note in the dropdown, click the page to add it, and double-click to edit text. | — |
| <picture><source media="(prefers-color-scheme: dark)" srcset="docs/images/toolbar-drawing-dark.png"><img src="docs/images/toolbar-drawing.png" width="24" alt="Drawing annotations"></picture> | Drawing annotations | Choose a line, arrow, rectangle, ellipse or freehand stroke; set stroke/fill styles and drag to create it. | — |
| <picture><source media="(prefers-color-scheme: dark)" srcset="docs/images/toolbar-odd-dark.png"><img src="docs/images/toolbar-odd.png" height="22" alt="Odd pages checkbox"></picture> | Odd pages | Select or clear original odd-numbered pages in the current tab. A partial selection uses an intermediate checkbox state. | — |
| <picture><source media="(prefers-color-scheme: dark)" srcset="docs/images/toolbar-even-dark.png"><img src="docs/images/toolbar-even.png" height="22" alt="Even pages checkbox"></picture> | Even pages | Select or clear original even-numbered pages in the current tab. A partial selection uses an intermediate checkbox state. | — |
| <picture><source media="(prefers-color-scheme: dark)" srcset="docs/images/toolbar-export-dark.png"><img src="docs/images/toolbar-export.png" width="24" alt="Export"></picture> | Merge export | Combine selected pages into one PDF; without selected pages, export the currently viewed page. | — |
| <picture><source media="(prefers-color-scheme: dark)" srcset="docs/images/toolbar-split-dark.png"><img src="docs/images/toolbar-split.png" width="24" alt="Split"></picture> | Split | Save each selected page as a separate PDF or PNG; without selected pages, use the currently viewed page. | — |
| <picture><source media="(prefers-color-scheme: dark)" srcset="docs/images/toolbar-zoom-dark.png"><img src="docs/images/toolbar-zoom.png" width="160" alt="Zoom percentage and slider"></picture> | Zoom | Adjust from 25% to 200% with the slider. Click the percentage to reset to 100%. Keyboard shortcuts change zoom by 25 percentage points. | In: <kbd>Ctrl</kbd>+<kbd>+</kbd> / <kbd>Ctrl</kbd>+<kbd>=</kbd>; out: <kbd>Ctrl</kbd>+<kbd>-</kbd>; 100%: <kbd>Ctrl</kbd>+<kbd>0</kbd> |
| <picture><source media="(prefers-color-scheme: dark)" srcset="docs/images/toolbar-fit-dark.png"><img src="docs/images/toolbar-fit.png" width="24" alt="Fit"></picture> | Fit | Fit the current page proportionally into the reading area and adapt when the window is resized. The slider or zoom shortcuts return to manual zoom. | — |
| <picture><source media="(prefers-color-scheme: dark)" srcset="docs/images/toolbar-fullscreen-dark.png"><img src="docs/images/toolbar-fullscreen.png" width="24" alt="Fullscreen"></picture> | Fullscreen | Use the main button for the last selected mode, or its right-hand dropdown for single page, spread or cover plus spread. | <kbd>F11</kbd> to enter/return; <kbd>Esc</kbd> to return |
| <picture><source media="(prefers-color-scheme: dark)" srcset="docs/images/toolbar-language-system-dark.png"><img src="docs/images/toolbar-language-system.png" width="24" alt="System language"></picture> <picture><source media="(prefers-color-scheme: dark)" srcset="docs/images/toolbar-language-zh-dark.png"><img src="docs/images/toolbar-language-zh.png" width="24" alt="Traditional Chinese"></picture> <picture><source media="(prefers-color-scheme: dark)" srcset="docs/images/toolbar-language-en-dark.png"><img src="docs/images/toolbar-language-en.png" width="24" alt="English"></picture> | Language | Cycle through System → Traditional Chinese → English. Your choice is remembered. | — |
| <picture><source media="(prefers-color-scheme: dark)" srcset="docs/images/toolbar-theme-system-dark.png"><img src="docs/images/toolbar-theme-system.png" width="24" alt="System theme: half-white, half-black circle"></picture> <picture><source media="(prefers-color-scheme: dark)" srcset="docs/images/toolbar-theme-light-dark.png"><img src="docs/images/toolbar-theme-light.png" width="24" alt="Light theme: sun"></picture> <picture><source media="(prefers-color-scheme: dark)" srcset="docs/images/toolbar-theme-dark-dark.png"><img src="docs/images/toolbar-theme-dark.png" width="24" alt="Dark theme: moon"></picture> | Theme | Cycle through System → Light → Dark. Your choice is remembered. | — |

### Open and switch files

- Each tab shows the filename without its extension. Hover over a tab to see the full path.
- The window title shows `RePDF` and its version.
- Opening the same path again switches to its existing tab.
- Each file keeps its own zoom, scroll position, page selection, and page order.
- Next tab (Windows/Linux): <kbd>Ctrl</kbd>+<kbd>Tab</kbd>.
- Previous tab (Windows/Linux): <kbd>Ctrl</kbd>+<kbd>Shift</kbd>+<kbd>Tab</kbd>.
- Tab switching cycles through the tab order, including when the reading area, a page checkbox, or a toolbar control has focus.
- Close a tab with its × button. Shortcuts: <kbd>Ctrl</kbd>+<kbd>W</kbd> on Windows/Linux, also <kbd>Ctrl</kbd>+<kbd>F4</kbd> on Windows, and <kbd>⌘</kbd>+<kbd>W</kbd> on macOS.
- The close button's tooltip shows the shortcut for your platform.

### Open password-protected PDFs

1. Open the file. RePDF asks for a password if one is required.
2. Enter the password and confirm. Select “Show password” to check what you typed.
3. Retry if the password is incorrect. Canceling skips only that file; other files opened together are unaffected.

- Encrypted PDFs that open without a password are loaded directly.
- After unlocking, you can read, search, print, export, split, copy text, use region OCR, and extract images.
- You will not be asked again while the tab stays open. Reopening a closed file requires its password again.
- Passwords are used only in memory and are not saved to settings or logs.
- **New PDFs created by export or split are unencrypted**, as indicated in the completion message. The original file is unchanged.

### Reading and zoom

- Fullscreen uses a main button with a right-hand mode dropdown for single page, spread or cover plus spread. <kbd>F11</kbd> reuses the last mode selected in this session. Single page shows one page; spread pairs pages from the first; cover plus spread shows the first page alone and pairs the remaining pages.

- Pages are centered horizontally. Fit mode uses a single column.
- Large files prioritize the pages you are reading. Jumping to a page does not require waiting for the entire document to load.
- 100% corresponds to the Windows 96 DPI display scale.
- Fit and fullscreen prefer the most recently clicked page that is still visible; otherwise, they use a page near the center of the reading area.
- Fit may use a zoom level outside the slider's manual range. The actual percentage still appears in the toolbar.
- The manual slider range is 25%–200%. The percentage button's tooltip describes zoom controls.
- Fullscreen spreads display both pages in full at the same scale. A remaining last page is displayed alone.
- Returning to the main window preserves its original zoom level.

### Keyboard scrolling and navigation

- Normal view: <kbd>←</kbd>, <kbd>↑</kbd>, <kbd>→</kbd>, and <kbd>↓</kbd> scroll; <kbd>Page Up</kbd> / <kbd>Page Down</kbd> scroll by one screen.
- Fit mode: these keys move to the previous/next page, starting from the currently visible page.
- Fit navigation stops at the first and last pages. Pressing the opposite direction once moves away from the boundary.
- Fullscreen previous page/spread: <kbd>←</kbd>, <kbd>↑</kbd>, or <kbd>Page Up</kbd>.
- Fullscreen next page/spread: <kbd>→</kbd>, <kbd>↓</kbd>, or <kbd>Page Down</kbd>.
- First/last page: <kbd>Home</kbd> / <kbd>End</kbd>, following the current page order. Fullscreen spread modes jump to the first/last group.
- These keys still control the reading area when the zoom slider or a page checkbox has focus, without changing zoom.

### Page numbers and direct navigation

- The right side of the status bar shows the current page and total page count. It updates when you scroll or navigate using search or bookmarks.
- If the PDF includes page labels, both the label and original PDF page number are shown, such as “Book page iii | PDF 3 / 800” or “Book page 12 | PDF 20 / 800”. Long labels are shortened; hover to see the full label. Files without labels use ordinary page numbers.
- Book page labels come from the PDF, are not inferred by OCR, and may differ from numbers printed on the page. The navigation field always accepts original PDF page numbers.
- Click the page number field, enter a number, and press <kbd>Enter</kbd> to jump. Press <kbd>Esc</kbd> or leave the field to cancel unsubmitted input.
- Numbers match the original page numbers on page cards. After reordering, entering the same number still finds the original page.
- Navigation preserves zoom/Fit mode. Invalid or out-of-range input displays a message and leaves the current page unchanged.

### Save and Save As

- Newly opened PDFs use Fit mode and adapt to the reading area. Changing zoom switches to manual scaling.
- Reordering pages adds `*` to the tab name. Click Save or press <kbd>Ctrl</kbd>+<kbd>S</kbd> to save the original PDF.
- Click Save As or press <kbd>Ctrl</kbd>+<kbd>Shift</kbd>+<kbd>S</kbd> to choose another filename. The tab switches to the saved file. On macOS use <kbd>⌘</kbd> instead of <kbd>Ctrl</kbd>.
- Saving includes every page in the active tab, independently of page and tab checkboxes. Export and Split use checked selections, falling back to the currently viewed page when there are no eligible checked pages.
- Bookmarks, internal links, annotations, metadata, and page labels are preserved. Password PDFs are re-encrypted with AES-256 using the password used to open the file.
- Save failures preserve the original file and current page order for retry. Choose another filename if the destination is open in another tab.

### Printing

- Click Print or press <kbd>Ctrl</kbd>+<kbd>P</kbd> (macOS: <kbd>⌘</kbd>+<kbd>P</kbd>) to open the integrated print window. The fullscreen shortcut first returns to the main window.
- Choose all pages in the current document, the current page, a custom range, or checked pages. Custom ranges use original PDF page numbers, such as `1,3,5-8`.
- Checked pages follow the export rules: if tabs are checked, use the selected pages in those tabs; otherwise, use the selected pages in the current tab.
- Printing follows the current tab and page order. The print window shows document and page counts.
- Scaling defaults to fitting the printable area. Actual size is also available. One page is centered on each sheet without automatic rotation; content outside the printable area is clipped at actual size.
- Select the printer, paper, orientation, copies, collation, duplex, and color on the left. Duplex and color options depend on printer capabilities. Changing paper or page scope updates the preview on the right.
- Navigate the preview using the previous/next icons, page number field, or <kbd>Page Up</kbd> / <kbd>Page Down</kbd>. Choose fit-to-window or a larger zoom. Only the current preview page is loaded, so large documents are not rendered all at once.
- The white sheet reflects the selected paper size and orientation; a dashed outline marks the printable area. Switch between fit and actual size to inspect margins and clipping. Narrow windows stack settings above the preview, with scrollable settings.
- Use “Advanced settings” for paper trays, print quality, or other driver-specific options in the system dialog. Settings are synchronized back to the preview. Page ranges selected there refer to `1..N` in the current print list.
- The preview shows one copy; the copy count is listed separately in the paper information. Printing starts only when you click “Print”. Closing or canceling the preview does not print.
- Printed output contains PDF content, without search highlights, text selection marks, or interface controls.
- Large documents are processed page by page. Cancel in the progress window to stop sending further pages; pages already sent may need to be canceled in the system print queue.
- Preview remains available without a printer, with the Print button disabled. Install or configure a system printer before printing; no separate printing utility is needed.

### Bookmarks and table-of-contents links

- Click Bookmarks to open the chapter tree on the left. Expand or collapse subsections, and click a chapter to jump to it.
- Bookmarks follow the active tab. A message appears if the file has no embedded bookmarks.
- Click links in a PDF's table of contents in normal or fullscreen view. Hover over an internal link to see a hand cursor and destination page number.
- Navigation preserves zoom/Fit mode. Reordered pages are still located by their original destination page.
- In narrow windows, bookmarks and the PDF share a single pane. Selecting a chapter returns to the PDF; click Bookmarks again to return to the tree. Use the respective toolbar buttons to switch among search, bookmarks, and annotations.
- Page links are temporarily disabled while copy text, region OCR, or image extraction mode is active. Disable the mode to follow links again. Pages can still be dragged to reorder them.
- Embedded HTTP/HTTPS links open in your default browser in normal and fullscreen view. Hover to see the URL.
- This uses existing PDF bookmarks and links. Plain text or scanned tables of contents and URLs are not automatically converted into links. Email links, external documents, and other actions are not supported.

### Annotation list

- Click the Annotations speech-bubble icon to open the active tab's comments in the left pane.
- Annotations are grouped by original PDF page, with a count per page. Groups start collapsed; expand a page to view individual types and summaries. Expansion is preserved across tab, sidebar-mode, and interface-language changes. Hover for full text, author, subject, and modification time when provided.
- Click a page group to jump to and mark its first listed annotation. Click an individual annotation to jump to its position and mark its bounds with a translucent fill and outline. Zoom/Fit mode is preserved, including after page reordering.
- Selecting an annotation with text automatically copies its text to the clipboard; a page group copies its first annotation. Empty annotations leave the clipboard unchanged.
- Closing the annotation pane or switching to another sidebar clears the marker. Reopening the list does not automatically copy text or restore the marker.
- The marker follows zoom and fullscreen display. Selecting another annotation or page group updates it; selecting a bookmark or search result clears it. Annotations without valid bounds still support page navigation.
- Notes, text boxes, highlights, underlines, strikeouts, ink, and shapes are supported. Text markup without a comment attempts to show the marked source text.
- In normal reading mode, click an annotation on the page to mark its bounds and select its entry in the left list, expanding the matching page group. Fullscreen supports this too. Text selection, region OCR, and image extraction retain their own mouse actions. Narrow windows keep the PDF visible; reopen Annotations to see the selected entry.
- The list follows the active tab and shows a message for files without annotations. Use the respective buttons to switch among bookmarks, annotations, and search.
- In narrow windows, selecting a comment returns to the PDF. Click Annotations again to return to the list.
- The full annotation list is read in the background only when the pane is opened. Page hit targets are read only for pages requested for display, without scanning the entire file on opening. Use the annotation tools below to edit supported items. Other types remain view-only; attachments are not executed.

### Add and edit annotations

- Enable **Add a text annotation with markup** in the text markup panel and choose Callout or Sticky note. Enter the comment after selecting text. Callouts point to the selection’s upper midpoint; notes sit above it, constrained to the page. The pair can be undone together; cancelling text entry keeps only the markup.
- **Text annotation tool**: choose Callout or Sticky note in its dropdown. Choosing a type activates the tool and updates its main icon.
- **Sticky note**: click the page to place its icon, then enter and save text in the dialog. Double-click the icon to edit it, drag to move it, and use the list or copy shortcut to copy its contents.
- **Drawing annotations**: choose Line, Arrow, Rectangle, Ellipse or Freehand, then drag on the page. Set the colour and 0.5–6 pt width; rectangles and ellipses also support a fill colour or transparent background.
- Selected drawings can be moved. Drag line/arrow endpoints or use corner handles to resize rectangles, ellipses and ink. <kbd>Esc</kbd> cancels the current drawing.

- **Text markup**: activate the tool and drag across text, including multiple lines. Its arrow opens highlight, underline, strikethrough, squiggly, colour and 0.5–6 pt width settings. Selection follows the text flow and previews the selected glyphs. Defaults are red underline, 1 pt; highlights use translucent yellow and do not use line width. Image-only areas do not trigger OCR.
- Annotation list items use type icons, with full type and content in their tooltips. Each item with text has a copy button on the right that copies its complete content without navigating to its page. Select an annotation in the list or on the page and press <kbd>Ctrl</kbd>+<kbd>C</kbd> (<kbd>⌘</kbd>+<kbd>C</kbd> on macOS) to copy its text. Selecting an item with text shows a selectable text area below; drag to select part, use the select-all/copy buttons, or press <kbd>Ctrl</kbd>+<kbd>A</kbd> / <kbd>Ctrl</kbd>+<kbd>C</kbd>.
- **Callout**: click the target to automatically place a text box nearby and enter text. The box retains its initial minimum width and expands with a single line of text, wrapping at the page edge and growing vertically within the page. Click outside to finish editing; a subsequent click creates another annotation. Defaults are blue text, red border/arrow, transparent background and 12 pt. New callouts default to 6 pt rounded corners. The panel controls text colour, line colour/width, font size, background and corner radius; 0 restores square corners.
- Double-click a box directly to edit, even with the annotations pane closed. A single click selects it and opens the list. <kbd>Enter</kbd> adds a line, <kbd>Ctrl</kbd>+<kbd>Enter</kbd> finishes, and <kbd>Esc</kbd> cancels that edit. Blank text does not create an annotation.
- Drag a selected box, its corner handles, or its arrow endpoint. Selected text markup supports style changes. <kbd>Delete</kbd> deletes; <kbd>Ctrl</kbd>+<kbd>Z</kbd> undoes; <kbd>Ctrl</kbd>+<kbd>Y</kbd> / <kbd>Ctrl</kbd>+<kbd>Shift</kbd>+<kbd>Z</kbd> redo. macOS uses its standard equivalent shortcuts.
- RePDF annotations and reliably parsed standard highlight, underline, strikeout, squiggly and callout annotations are editable. Notes and drawings created in RePDF remain editable after saving and reopening. Notes and drawings from other programs, locked annotations, custom appearances, unavailable fonts and rich text remain view-only, with a reason shown when selected.
- Annotation tools are mutually exclusive with text copying, OCR and image extraction, and also work fullscreen. Styles are remembered. Colour and style changes apply to a selected editable annotation; choosing another text/drawing tool type prepares a new annotation.
- Changes add an unsaved asterisk. Saved annotations remain editable after reopening. Printing, exporting and splitting include unsaved annotation changes. Closing offers Save, Don’t Save and Cancel.
- Saved files contain standard PDF annotations and complete appearances with embedded text fonts for viewing in other PDF readers. Editing capabilities in those readers depend on their features.

### Search text

1. Click Search text or press <kbd>Ctrl</kbd>+<kbd>F</kbd> (macOS: <kbd>⌘</kbd>+<kbd>F</kbd>) to open the right pane.
2. Enter a query and choose the current tab, checked tabs, all tabs, or the current tab’s folder. On the same row, the `.*`, `Aa`, and underlined `ab` toggle buttons control regular expressions, case sensitivity, and whole-word matching. A highlighted button means the option is enabled.
3. Press <kbd>Enter</kbd> or Search. After changing the criteria, run the search again to update results.
4. The upper Files table shows filenames and matching-paragraph counts. Select a file to see its matches in the lower Page/Paragraph table, with alternating backgrounds and match counts in tooltips. Each paragraph occupies one line; long text ends with `...`. Hover to read the full paragraph.

- The folder scope searches all PDFs directly in the current PDF’s directory, including unopened files, without opening every file as a tab. Subfolders are excluded.
- Selecting a result file or paragraph opens an unopened PDF in a new tab, or reuses its existing tab, and navigates to the match. Open password-protected PDFs and enter their passwords before folder searches. Unreadable files are reported without discarding other results.
5. Click a paragraph to switch to its tab and page and scroll to the match. Pages that have not been loaded are loaded automatically. Matches use yellow highlighting by default; matches in the selected paragraph use a darker shade of the same color.

- By default, search covers the current tab, ignores case, and does not use regular expressions. The four search scopes are mutually exclusive.
- Whole-word matching is off by default. When enabled, matches cannot be immediately adjacent to Unicode letters, digits, underscores, or combining marks. For example, `cat` does not match `catalog`. This works with regular expressions but does not segment continuous Chinese text into words.
- Checked tabs use the checkboxes on the left of tabs. If none are checked, a message appears; search does not automatically fall back to the current file.
- Search covers all pages in successfully loaded files within the chosen scope, regardless of page selection. Password-protected files must be unlocked first.
- Search uses existing text layers and does not run OCR. Scanned images or damaged text layers may not produce results.
- Multiple matches in the same paragraph are grouped into one result. Paragraphs are inferred from text lines and layout. Search does not span pages; columns and complex layouts may affect paragraph boundaries.
- Search can span lines within the same paragraph: visual line breaks are joined, with no added spaces between Chinese/Japanese characters and spaces between other continued lines. Matches spanning lines highlight the corresponding text on each line.
- Regular expressions use Python-compatible syntax. Invalid patterns display an error; zero-length matches are excluded from highlighted results.
- Regular expression matching has a one-second limit per paragraph. A timeout stops the search and marks results as incomplete. You can also click Stop to keep the results found so far.
- Drag the right pane's edge or the divider between result lists to resize them. Search does not change page selection, order, or zoom mode.
- Below a window width of 640 px, search and the PDF share a single pane. Selecting a result displays the PDF; click Search again to return to results.
- In short windows, use the three-dot Options menu to change scope, regular expression, case-sensitive, and whole-word settings.
- Click the color swatch in the search options row to choose the match highlight color. In short windows, use Options → Match highlight color. Changes immediately recolor existing highlights without rerunning the search, including fullscreen and pages loaded later. Your choice is remembered; canceling the color picker leaves it unchanged.
- Closing the search pane stops searching and clears highlights while retaining the query and results. Closing a document removes its results for tab-based searches; folder results remain available for reopening.
- Using the search shortcut in fullscreen returns to the main window and opens the search pane.

### Select and reorder pages

- Use the checkbox at the upper left of each page to select it. With the checkbox focused, press <kbd>Space</kbd> to toggle it.
- Fullscreen checkboxes synchronize with the main window, so selected pages are ready to export or split when you return.
- Drag a page thumbnail or its reorder handle to change page order.
- The thumbnail follows the cursor while other pages move aside to show the insertion position.
- Drop on the left half of a page to insert before it, or the right half to insert after it.
- Release to confirm, or press <kbd>Esc</kbd> to cancel.

### Export PDF, PNG, and split

- Tab checkboxes are unchecked by default.
- If any tabs are checked, only selected pages from those files are exported.
- If no tabs are checked, only selected pages from the current tab are exported.
- If the scope above contains no selected pages, export the single page currently viewed in the active tab. Fullscreen spreads use the first page of the current group.
- Drag tabs to change file order. Output follows tab order, then each file's current page order, excluding unselected pages.
- Splitting with the name `report.pdf` creates files such as `report_01.pdf` and `report_02.pdf`.
- Split numbering is continuous across files, starts at 1, and uses at least two digits. Numbers are padded to the total output count, such as `001`–`100` for 100 pages, independently of original page numbers.
- You are asked before overwriting existing single-page files.
- Password-protected PDFs must be unlocked first. New output PDFs are unencrypted.
- Merge export combines selected pages into one PDF. Split offers PDF or PNG, producing one file per page. PDF preserves original page quality; PNG renders the entire page, including text, images, and unsaved annotations.
- A single PNG uses the chosen filename. Multiple pages named `report.png` produce `report_01.png`, `report_02.png`, and so on, following the same numbering and order as Split.
- PNG uses 300 DPI independently of reading zoom. Very large pages use a lower resolution to stay within 30 million pixels per image. You can cancel generation; canceled exports do not publish their images.

### Copy text, region OCR, and image extraction

- With Copy text enabled, press <kbd>Ctrl</kbd>+<kbd>A</kbd> (<kbd>⌘</kbd>+<kbd>A</kbd> on macOS) in the PDF reading area to select and copy the entire PDF text in normal or fullscreen view.
- All pages follow the current display order, independently of page checkboxes. Extraction runs in the background with progress; the clipboard changes only on success. Switching tabs, leaving text-copy mode or closing the document cancels an active extraction.
- Whole-document copying reads the text layer, without automatic OCR or annotation contents. Empty results and failures retain the clipboard. Select All inside search inputs or text editors still applies only to that field.

- These three modes are mutually exclusive and work in normal and fullscreen view.
- Active modes use the hover background and an accent-colored icon without an outline. Turning the mode off restores drag-and-drop reordering.
- Copy text: drag to select text, then release to copy it. Use region OCR for text in scanned images.
- Region OCR: draw a rectangle, then release to recognize and copy text. An empty region leaves the clipboard unchanged.
- Extract image: click an embedded raster image and choose where to save it as a PNG.
- Images retain their original pixel dimensions and use their transparency masks, independently of preview zoom.
- The full embedded image is exported, without page-level rotation or cropping, surrounding text, or vector graphics.
- Clicking an empty area displays a message. If images overlap, the last-painted image is selected.
- Scanned pages usually yield the whole scanned image; photos or charts within it cannot be directly separated.
- OCR defaults to Traditional Chinese, Simplified Chinese, English, Japanese, and multiple Latin-script languages. Use the arrow beside Region OCR to select Korean, Thai, Russian/Ukrainian, Arabic, or Hindi/Nepali. Greek, Tamil, and Telugu are also available.
- Automatic + downloaded models combines locally available models and chooses results per line. It never downloads other models automatically.
- Separators divide automatic choices, downloaded models, and models not downloaded, without group headings. Downloaded models have a (downloaded) suffix. Groups and labels update after downloads or when files are missing or corrupt.
- Additional models require download confirmation. The language changes only after a successful download; canceling or failure keeps the previous setting. Your language choice is saved and applies to both region OCR and damaged-text fallback. Review the output. See the [OCR guide](docs/OCR.en.md) for details and limitations.

## Language and theme

Two three-state buttons on the right of the toolbar follow the system by default. Click to switch immediately:

- Language: System → Traditional Chinese → English → System. System mode uses Traditional Chinese when the system display language is Chinese, and English otherwise. The tooltip shows both the selected mode and the effective language.
- Theme: System → Light → Dark → System. A manually chosen theme remains fixed; System mode follows system changes immediately.
- Dark mode uses an Evangelion Unit-01-inspired palette with purple-black backgrounds, purple panels, neon-green accents, and touches of orange. PDF pages retain their original colors.
- Language and theme choices are remembered across restarts.
- Changing language updates existing page labels, toolbar controls, tooltips, status messages, and dialogs.
- Language changes preserve filenames, selected pages, page order, and zoom.
- File dialogs use the selected Chinese or English language for their buttons and fields.

## License

RePDF is licensed under the **GNU General Public License v3.0 (GPL-3.0-only)**. Use, modification, and commercial use are permitted. Distribution of the program or modified versions must comply with the GPL, including providing corresponding source code and preserving license and copyright notices. The program comes without any warranty.

Open About RePDF to view the version, copyright, full GPL text and offline third-party licenses, or visit the source repository. On Windows, click the main window’s top-left application icon and select About RePDF from the system menu (also available via <kbd>Alt</kbd>+<kbd>Space</kbd>). On macOS, choose About RePDF in the standard RePDF application menu in the system menu bar.

See [LICENSE](LICENSE) for the full terms and [NOTICE](NOTICE) for copyright information. Third-party libraries, models, and assets retain their respective licenses; see [third-party notices](THIRD_PARTY_NOTICES.md) and the [license review](docs/LICENSE_AUDIT.en.md).

## Further documentation

- [OCR usage and limitations](docs/OCR.en.md)
- [Development, testing, and release guide](docs/IMPLEMENTATION.en.md)
- [UI design reference](docs/UI_DESIGN.en.md)
