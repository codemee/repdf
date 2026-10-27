# RePDF implementation and maintenance guide

[繁體中文](IMPLEMENTATION.md) | [English](IMPLEMENTATION.en.md)

This guide describes RePDF's current architecture, data flow, design decisions, and maintenance considerations. RePDF stands for Read the PDF: a PDF reader with search, bookmarks, OCR, and page rearrangement. The command, package, and Python module name remain `repdf`. Start here before adding features or debugging, then follow the entry points in `src/repdf/app.py`.

## 1. Project overview

RePDF is a Python desktop application for Windows and macOS. Its main features are:

1. Open multiple PDFs in checkable, reorderable, closable tabs.
2. Load previews around visible pages, with zoom, fullscreen, search, bookmarks, links, and page navigation.
3. Configure ranges, printers, and paper in an integrated print window, then preview and print page by page.
4. Copy selected text, recognize text with OCR, and extract embedded raster images.
5. Rearrange tabs and pages, then export or split selected pages.

The environment is managed with `uv` and requires Python 3.11 or later. After cloning, run these commands in the project directory:

```sh
uv sync
uv run repdf
uv run --locked python -m pytest
```

## 2. Technology stack

| Package | Purpose |
| --- | --- |
| PySide6 | Windows, controls, themes, thread pools, and Qt signals |
| pypdf (crypto extra) | Validate/unlock source PDFs, read page counts, and copy selected pages without rasterizing |
| cryptography | Native AES PDF encryption/decryption support, collected by uv and desktop packaging |
| pypdfium2 | Render PDF pages in a separate process |
| Pillow | Save PDFium bitmaps as PNGs |
| RapidOCR (rtl extra) / ONNX Runtime | Local OCR with built-in and additional script models; the RTL extra supports Arabic processing |
| Qt Network | Confirmed asynchronous model downloads, SHA256 verification, and atomic writes to user data |
| pytest | Core and integration tests |
| pytest-qt | Qt GUI and asynchronous behavior tests |

## 3. Directories and module responsibilities

```text
src/repdf/
├── app.py             MainWindow, per-document DocumentView, tabs, and GUI coordination
├── core.py            GUI-independent selection, validation, and PDF output logic
├── widgets.py         Individual PageCard previews
├── page_view.py       Visible-page scheduling, card virtualization, and shared image cache
├── navigation.py      Bookmark/annotation sidebar and internal-link navigation
├── printing.py        Print settings, range snapshots, and page-by-page printing
├── print_preview.py   On-demand print preview and paper layout canvas
├── pdf_annotations.py PDFium annotation metadata and marked-text extraction
├── pdf_navigation.py  Backend bookmark/link/destination extraction
├── preview.py         Fullscreen single-page/spread/cover view, fitting, and selection
├── theme.py           System/light/dark modes and control styling
├── workers.py         QRunnable PDF loading and export tasks
├── renderer.py        Communication with the persistent rendering backend
├── ocr.py             OCR inference, language-specific engines, and offline verification
├── ocr_models.py      Pinned official model URLs/SHA256 and user model directory
├── ocr_languages.py   Language menu, asynchronous download dialog, and retries
├── render_worker.py   PDFium service in the child process
└── assets/            PNG and Windows ICO application icons

tests/
├── test_core.py       Selection rules, PDF validation, and export tests
├── test_gui.py        GUI state, tabs, cross-file output, and preview integration
└── test_renderer.py   Request coalescing, priority, and cancellation tests
```

## 4. Startup and component lifecycle

The public entry point is `repdf.entrypoint:main`. Ordinary startup delegates to `repdf.app:main`; entrypoint also dispatches packaged backend and `--self-test` modes.

Startup order is intentional:

1. `start_render_backend()` starts the persistent PDF preview child process.
2. Create `QApplication`.
3. `configure_application()` configures Fusion, icons, and Traditional Chinese font fallbacks.
4. Create `ThemeController`, apply the current system theme, and monitor changes.
5. Create `MainWindow` and pass the existing backend to `RenderService`.

Do not move rendering back onto the GUI thread or call PDFium concurrently from multiple threads. PDFium is not thread-safe. A persistent child process isolates native rendering state and keeps preview work from freezing the main window.

On window close, `closeEvent()`:

- Sets `_closing`, stops document zoom timers, and invalidates pending old results.
- Stops the preview child process.
- Clears Qt tasks that have not started and waits for active export tasks.
- Removes temporary preview PNG directories.

## 5. Main window and state

`MainWindow.__init__()` builds the toolbar, central document tabs/scrollable page grid, and bottom status bar.

- The fixed toolbar contains file actions and a fixed-width zoom percentage followed by its slider. Clicking the percentage resets to 100%; its tooltip describes zoom controls. Zoom QActions belong to the main window and provide shortcuts without separate buttons.
- File QActions centralize enabled state and shortcuts. Tabs show full source paths in tooltips. The window title remains `RePDF <version>`, independent of language and current file.
- Odd/even tri-state checkboxes follow file actions.
- `close_tab_action` uses `QKeySequence.StandardKey.Close`, a window-scoped shortcut, and the existing `close_tab()` cleanup. It is disabled during closing or without tabs. Close-button tooltips show platform shortcuts.
- The status bar reports loading, selection, and export progress.

`MainWindow` owns shared controls, `QTabWidget`, stable document IDs, and export job IDs. Each `DocumentView` owns its source, page count, `selected_pages`, `page_order`, `page_cards`, zoom, render generation, and scroll area. Tab changes synchronize toolbar and parity states without rebuilding document content. Tab checkboxes and close buttons bind to document objects rather than mutable tab indices.

`_active_tasks` retains Python references to `QRunnable` objects until completion or failure. Loading results carry document IDs; export results carry `_export_id`, independently of the active tab.

## 6. PDF loading

`choose_pdf()` uses a multiple-file dialog and shares `load_pdfs()` with file drops:

1. Create loading tabs in input order. A duplicate resolved path activates its existing tab.
2. Run `core.inspect_pdf()` through `LoadPdfTask` in the shared `QThreadPool`.
3. Read `/Count` from the page-tree root rather than expanding the whole tree with `len(reader.pages)`. Fall back to full inspection only if the count is invalid. Read page content and actual dimensions when rendering requires them.
4. `DocumentView`'s `PageViewport` requests visible pages plus one screen before and after them. Background tabs pause preview requests; images remain in a bounded shared cache.
5. Remove failed tabs without disturbing successful files. Batch errors are combined after loading finishes.
6. Results for closed documents only finish task cleanup; they do not recreate tabs.

### Password-protected documents

- `inspect_pdf(source, password=None)` first tries an empty password so encrypted PDFs without an opening password load directly.
- `PasswordRequiredError` requests a password; `IncorrectPasswordError` reports a failed attempt. Both inherit `UnsupportedEncryptedPdfError` for caller compatibility.
- `LoadPdfTask.password_required` identifies the document and whether the password was incorrect. The GUI queues requests and shows one `PdfPasswordDialog` at a time.
- Accepted passwords are stored in `DocumentView.password` before retrying. Canceling removes only that tab and completes its batch cleanup.
- Input is masked by default with an option to reveal it, and is cleared after the dialog closes. Passwords are not written to QSettings, command lines, or logs.
- Preview, fullscreen, text, region OCR, and image requests carry passwords through existing local communication. PDFium opens the original file; no decrypted temporary PDF is created.
- `DocumentSelection` carries a password field excluded from repr. Each export source uses its own password. Outputs are always unencrypted, explicitly stated in dialogs and completion messages.
- Closing a file/application clears document password references and cancels queued tasks/password requests. Load/export tasks release references after completion; the backend also removes password fields and input-line references after each request.
- `pypdf[crypto]` brings in `cryptography` for AES-128/AES-256 support. Output password configuration is not provided.

## 7. Preview rendering architecture

### 7.1 Separate process

`pypdfium2` is imported only in the `render_worker.py` child process. The GUI does not load PDFium directly, isolating native thread-safety concerns from GUI font/painting state.

`RenderService` exchanges one JSON object per line over stdin/stdout. A request has this general form:

```json
{
  "source": "C:/path/input.pdf",
  "scale": 1.3333333333,
  "output_dir": "C:/Temp/repdf-preview-...",
  "generation": 4
}
```

Per-page result:

```json
{
  "type": "page",
  "generation": 4,
  "page": 0,
  "path": "C:/Temp/repdf-preview-.../g4-p0.png"
}
```

Completion or failure:

```json
{"type": "done", "generation": 4}
{"type": "error", "generation": 4, "message": "..."}
```

The GUI copies each PNG completely into a `QImage`, immediately deletes the temporary PNG, and updates its card.

Text-copy mode converts drag endpoints to page-relative coordinates and calls `RenderService.request_text()` on the same backend. PDFium accounts for page rotation, finds endpoint characters, and extracts the intervening text; character boxes determine the range if endpoints cannot be found. Results include `text` and normalized character boxes for highlights. A 90 ms timer updates selection previews while dragging; only the final released selection writes to the clipboard. Mode changes, document closure, and newer requests invalidate older results. Image-only PDFs without text leave the clipboard unchanged.

### 7.2 Latest requests take priority

The backend executes one rendering request at a time. `RenderService` maintains a document-ID-keyed pending queue with only the newest request per document, prioritizing the active tab. Each main-window batch contains at most two pages: visible pages first, then nearby pages. Scheduling is reconsidered against the viewport after each batch. A 40 ms timer coalesces scrolling; manual zoom waits for a 250 ms pause and temporarily scales old images. `cancel_pending()` removes queued requests when leaving a tab or closing a document.

Generation numbers increase globally in the main window and map to document IDs through `_render_documents`. Results go to their source document independently of active tab or tab order. Obsolete-scale or closed-document results have their temporary images deleted. Active native rendering is not forcibly interrupted.

Requests can include `pages`, an array of zero-based page indices. Omitting it renders the entire document. Page results include `width_points` and `height_points` for actual-size Fit/fullscreen calculations. Fullscreen uses a negative document ID as its independent scheduling key and maintains its own generations. Navigation invalidates old results immediately; closing cancels pending requests.

The main window always supplies `pages`, so opening or zooming never previews the entire file. `PreviewCache` uses document ID, original page index, and render scale as keys, with a shared 128 MiB LRU image budget. Cards outside the nearby range release their pixmaps; closing a document removes its cache. The budget covers cached `QImage` data, not displayed pixmaps, Qt widgets, PDFium handles, or total process memory.

The backend's `PdfDocumentCache` holds at most three PDFium documents, keyed by source path, size, modification time, and password. Batches and fullscreen reuse these handles. All PDFium operations run on one thread in that backend. Tab closure sends `release_document`; backend shutdown releases all handles.

### 7.3 Zoom definition

100% maps PDF's 72 DPI points to the Windows-standard 96 DPI display scale:

```text
render_scale = slider_percent / 100 × 96 / 72
```

A 300pt-wide page is therefore about 400px wide at 100%. Each page uses its actual dimensions; landscape pages are not forced to portrait width.

Fit chooses the most recently clicked still-visible page, or the page nearest the viewport center. After subtracting card header and padding, it uses the smaller available-width/page-width and available-height/page-height ratio. It does not subtract the entire grid's vertical margins from height. After rendering, it centers the reference page in the viewport to avoid bottom gaps or exposing the next page. Each document retains Fit mode and its reference page. Resize updates use a 150 ms timer; manual zoom exits Fit. Fit may exceed the manual 25%–200% range.

`FullscreenPreview` is a separate modal top-level window. It preserves document zoom and synchronizes selection through `PageCard.set_selected()` and `DocumentView._page_selection_changed()`. Groups follow `page_order`: `single` uses one page per group; `spread` pairs from the first page; `cover` puts the first page alone before pairs. An odd final page appears alone. Opening selects the group containing the current preview page.

Fullscreen reserves a 30px selection header. Spreads use a shared scale calculated from total page width and maximum height. Device pixel ratio provides sharp images. Only the current group renders, capped at 30 million raster pixels in total. <kbd>F11</kbd> / <kbd>Esc</kbd> returns; arrow keys or <kbd>Page Up</kbd> / <kbd>Page Down</kbd> switch groups.

Main and fullscreen windows each install an application event filter, handling only unmodified navigation keys in their own window, without affecting file dialogs. Normal view uses scrollbar single/page steps; Fit changes and refits the reference page. Navigation still works when sliders or fullscreen checkboxes have focus.

The slider's 250 ms debounce sends a request only after changes pause. If changing the zoom range or DPI definition, also check:

- `DocumentView._preview_scale()`
- `DocumentView._target_preview_width()`
- `render_worker.render_document()`
- `test_pdf_loads_and_renders_page_previews`

## 8. Grid and page cards

The grid is top-aligned and horizontally centered, with cards centered within their columns. When page dimensions or window width change the scroll range, horizontal scrolling returns to center. Arrow keys and scrollbars still expose content wider than the viewport. Fit uses one column. Fit navigation starts at the visible page nearest the viewport center; pending navigation/rendering retains the requested reference page so rapid repeated keys stay ordered. Boundary attempts do not trigger zoom or scroll requests.

`PageCard` holds a natural-page-number `QCheckBox`, a preview/error `QLabel`, and a zero-based `page_index`.

Images update fixed card dimensions using their actual width/height. `DocumentView._reflow_grid()` computes columns from the widest current card and available viewport width. Resize and new images reflow without reparsing the PDF.

Documents over 64 pages use virtualization: only visible/nearby cards exist. Whole-document state consists of order, selection, known dimensions, and geometry. `PageCards` indices remain original page indices; iteration visits only existing cards, so iteration positions must not be interpreted as page numbers. Unknown sizes temporarily use A4 proportions. New sizes trigger reflow while preserving the visible page's scroll position. Search highlights are stored separately and restored on card recreation. Drag/drop converts nearby-card geometry into whole-document insertion positions.

Documents of 64 pages or fewer retain the ordinary grid, with images still loaded on demand. `PageGridLayout` computes actual row heights beyond Qt's aggregate size limit of approximately 524287px, preventing tall pages from being compressed. Virtual layout directly uses page geometry and is unaffected by that aggregate limit.

`PageGrid` freezes original positions, pauses layout, and hides the source card during dragging. `QDrag` uses a numbered thumbnail capped at 180 × 240px. The left/right halves of original slots determine before/after insertion, avoiding unstable hit testing against moving cards. Other cards move with a 180 ms OutCubic animation around a dashed placeholder, wrapping in grid order. The preview does not modify `page_order`; release commits through `_insert_page()`, while cancellation restores the original grid. Layout resumes and reflows afterward. Export disables starting a drag.

## 9. Page selection rules

Internal indices are zero-based; displayed page numbers are one-based. `core.py` provides pure functions:

- `indices_for_parity()`: indices corresponding to odd/even natural page numbers.
- `set_parity()`: add/remove one parity group without changing the other.
- `parity_state()`: return `NONE`, `PARTIAL`, or `ALL`.

Odd/even controls are tri-state checkboxes. Partial manual selections show the intermediate state; selecting both groups selects all pages. Programmatic synchronization must preserve `_syncing_bulk` or block signals to avoid reentering selection logic.

## 10. PDF output and file safety

`choose_output()` and `choose_split_output()` share a Qt save dialog with default filename `<source_stem>_selected.pdf`. Merge offers PDF only and combines pages into one file. Split offers PDF or PNG and writes one file per page. Export is enabled when output pages are available and no export is active. `output_selection(fallback_current=True)` falls back to the active tab's `preview_page_index()` when the checked scope contains no selected pages; fullscreen uses the first page of the current group. The default does not fall back, preserving printing's own selection rules.

`core.export_documents()` behaves as follows; `export_selected_pages()` remains a single-file wrapper:

1. Collect checked documents in tab order, or only the current document if no tabs are checked. Filter each `page_order` by `selected_pages` into immutable `DocumentSelection(source, pages)` snapshots. Empty selections contribute no pages.
2. Reject destinations that match any participating or open source file.
3. Validate page ranges and source existence.
4. Add original pages directly with pypdf, without rebuilding from thumbnails.
5. Copy metadata from the first document that contributes pages.
6. Write a `.repdf-*.pdf` temporary file in the destination directory.
7. Complete writing and `fsync()`, then atomically replace the destination with `os.replace()`.
8. Delete temporary files on failure, leaving no partial output.

Reordering changes only original indices in `page_order`; `page_cards` and `selected_pages` keep original-page identities. Parity is independent of visual position.

`choose_split_output()` shares the save flow and uses `ExportPdfTask(split=True)` to call `core.split_documents()`; `split_selected_pages()` remains a single-file wrapper. `split_output_paths()` generates continuous zero-padded numbers with at least two digits, based on total output count. The GUI confirms overwriting actual single-page targets before starting; core logic again rejects source overwrites.

Each source is read once. Pages retain their source content and metadata. All PDFs are generated in a temporary directory within the destination directory, then published individually with atomic operations. Without overwrite authorization, existing targets are rejected. Generation failure leaves output unchanged. A disk error during publication reports the number already completed and retains published files.

During export, users may switch tabs, read, and zoom, but cannot open/close files, check/reorder tabs, or select/reorder pages. Background export uses an immutable starting snapshot of pages and unsaved annotations. Split numbering is continuous across source files.

`png_export.py` renders pages sequentially through PDFium in a dedicated `RenderService` subprocess. `PdfDocumentCache` applies each source password and annotation snapshot; rendering respects page rotation, crop, and visible annotations. RGB PNGs use 300 DPI with a 30-million-pixel cap per page, reducing DPI for larger pages. Single images use the chosen filename; multiple images use continuous numbering from `png_output_paths()`. All images are written and fsynced in a temporary directory beside the destination before individual atomic publication. Unauthorized overwrites and overwriting any open source are rejected. Canceling terminates the subprocess and removes temporary files without publishing images; publication disk errors report the completed count. This requires no new dependencies and is separate from extracting original embedded images.

## 11. Themes, fonts, and icons

- Checkable toolbar buttons and search options share the `stateButton` style: hover background when active, pressed background when hovering an active button, radius 8, and transparent border space without a visible outline. `icons.py` supplies `QPalette.Highlight` icons for QIcon's On state in both Normal and Active modes; disabled icons retain their disabled color. Buttons remain 34 × 34, icons 20 × 20, and icon design strokes 1.

The toolbar's `language_action` cycles `system → zh → en`; `theme_action` cycles `system → light → dark`. `QSettings("repdf", "repdf")` stores `ui/language` and `ui/theme`, defaulting to `system` and falling back to it for invalid values. On first startup, valid language/theme preferences from `QSettings("PDFPick", "PDFPick")` populate unset new keys, without overwriting existing repdf preferences or deleting old settings.

`preferences.LanguageController` prefers the first display language in `QLocale.system().uiLanguages()`, falling back to locale language only if none is available. Chinese selects Traditional Chinese; other languages select English. `LocaleChange` reevaluates language only in system mode. `strings.py` centralizes translations and `tr()` for GUI/core/backend errors. `localize_text()` updates existing text while preserving formatting arguments. Switching language updates text/tooltips without rebuilding documents or rerendering pages.

File dialogs use `DontUseNativeDialog`, Qt's `qtbase_zh_TW.qm`, and standard-button translations. Packaging locates Qt translations via `QLibraryInfo.TranslationsPath` and collects qm files into `repdf/assets`. Source execution also reads Qt's translations directory. Missing translations fall back to source text. `packaging_smoke.py` checks qm availability and English translation behavior. GUI tests isolate user preferences in separate settings.

`ThemeController` reads `QGuiApplication.styleHints().colorScheme()` and listens to `colorSchemeChanged` in system mode; explicit light/dark settings take priority. The main window owns the controller. Applying a theme updates the Qt palette, card/preview borders, base button sizes, slider colors, and flat styles for toolbar controls, checkboxes, scrollbars, and dialog buttons. `icons.py` draws line icons; the main window rebuilds them on palette changes for readable light/dark and disabled states.

`configure_application()` tries Microsoft JhengHei UI, Microsoft JhengHei, Noto Sans TC, then Arial.

Application assets are `src/repdf/assets/repdf.png` and `repdf.ico`. Runtime and cloud builds share `icon_layout.fitted_icon()`: measure visible alpha ≥ 32, remove excess padding and fit proportionally into 92% of a square canvas. Build-time Windows ICO includes 16, 20, 24, 32, 40, 48, 64, 128 and 256px; macOS ICNS uses the same optical size.

## 12. Test coverage

Tests cover:

- Parity selection, clearing, and tri-state detection.
- Default output filenames.
- Source-order output for sets and drag-order output for ordered lists.
- Consistency of visual order, original-page parity, and output after reordering.
- Preserved page dimensions after export.
- Empty-selection and source-overwrite rejection.
- Damaged and password-protected PDFs.
- Initial GUI controls and icon loading.
- Manual selection/parity synchronization and zoom debounce.
- Integration from PDF loading through background preview rendering.
- On-demand preview, long-document virtualization, cache eviction, and navigation.
- Search scopes, regular expressions, word boundaries, highlights, bookmarks, and internal/external links.
- Print scopes/order, margins, scaling, copies, preview caching, cancellation, and backend cleanup.
- Ordinary integrated printing without native dialogs; preview without a printer while printing stays disabled.
- OCR damaged-text detection, region recognition, offline models, and clipboard flow. Recognition quality testing focuses on Chinese and English.

Tests use `QT_QPA_PLATFORM=offscreen`. The offscreen plugin can differ slightly from native Windows rendering. Font, icon, theme, and layout changes also require native-window visual checks.

## 13. Common modification entry points

| Change | Main entry point | Considerations |
| --- | --- | --- |
| Main layout | `MainWindow.__init__()` | Preserve toolbar/content/status regions |
| Zoom range or DPI | Slider/scale methods in `app.py` | Update tests and README together |
| Thumbnail format/quality | `render_worker.render_document()` | GUI expects a path readable by `QImage` |
| Backend scheduling | `renderer.RenderService` | Preserve generation-based invalidation |
| New selection method | Pure functions in `core.py` and `_selection_updated()` | Keep zero-based internal indices |
| Output order | `DocumentView.page_order`, `_move_page()`, `core.export_selected_pages()` | Separate original indices from visual positions |
| Password support | `_unlock()`, `PdfPasswordDialog`, main-window password queue, backend requests | Keep passwords per document, clean up on close, disclose unencrypted output |
| App icon replacement | `assets/` and `load_app_icon()` | Update PNG and ICO together |
| Theme colors | `ThemeController.apply()` | Check both system themes |

## 14. Known limitations and extension areas

- No page dragging across tabs or session restoration after restart.
- Opening PDFs with passwords is supported; assigning output passwords is not.
- No page rotation, cropping, or content editing. Cross-document exports follow checked pages and visual order.
- Thumbnails load on demand with a bounded cache, but displayed high-resolution pages and PDF state still consume additional memory.
- Active native PDFium calls are not forcibly interrupted. A new location may wait for the current batch of at most two pages; a very complex individual page can still cause delays.
- GitHub Actions builds Windows single-file EXEs and macOS App/DMGs. Developer signing and macOS notarization are not configured.

## 15. Packaging and releases

Packaged smoke tests must stop render backends holding cached PDFs before removing temporary test directories, on both success and failure. This avoids Windows file locks preventing test PDF cleanup.

### Build policy and artifacts

- All packaging runs in GitHub Actions. Local development runs source and tests without building desktop packages.
- Windows x86_64 uses PyInstaller onefile/windowed mode for a single EXE.
- macOS Apple Silicon (arm64) uses an onedir App bundle, preserving native-library symlinks, packaged into a DMG.
- Each desktop artifact is built on a native runner for its platform.
- Desktop artifacts include SHA256 checksum files and the OCR runtime/models.
- Windows code signing and macOS Developer ID signing/notarization are not configured; downloaded apps may trigger system security prompts.

### Desktop workflow

- Configuration: [`.github/workflows/build-desktop.yml`](../.github/workflows/build-desktop.yml), named “Build desktop apps”.
- Publishing a release triggers a build from its tag. The tagged commit must include packaging configuration.
- The Actions “Run workflow” button also supports manual builds with a branch/tag `ref`.
- A manual `release_tag` takes precedence as the build source and attaches successful artifacts to that existing release.
- The workflow installs locked dependencies and runs regression tests before packaging and packaged smoke tests.
- Actions artifacts are retained for 30 days. Manual builds without `release_tag` are downloaded there.
- Release builds and manual builds with `release_tag` upload release assets only after both Windows and macOS builds succeed.

### Packaging configuration and resources

- [`packaging/repdf.spec`](../packaging/repdf.spec) defines Windows EXE/macOS App modes and collected resources.
- RapidOCR configuration, recognition/detection models, and ONNX Runtime native libraries are collected. The unused orientation classification model is excluded.
- Installed `repdf` distribution metadata is collected so window and package versions agree.
- [`scripts/build_desktop.py`](../scripts/build_desktop.py) runs PyInstaller, packaged functional checks, DMG creation, and SHA256 generation.
- macOS uses system `ditto` and `hdiutil` to create and verify DMGs.
- [`entrypoint.py`](../src/repdf/entrypoint.py) detects backend and smoke-test modes before loading the GUI, preventing child processes from opening another window.
- [`renderer.py`](../src/repdf/renderer.py) uses stdin/stdout in source mode. Frozen mode uses loopback TCP, a one-time random handshake token, and UTF-8 streams because Windows windowed bootloaders lack standard streams.

### Packaged smoke tests

- Entry point: [`packaging_smoke.py`](../src/repdf/packaging_smoke.py), invoked through the packaged executable during builds.
- Verify Qt, app icons, and dialog translation resources.
- Run actual OCR inference and region recognition rather than checking imports alone.
- Verify AES-256 password loading and unencrypted output to check bundled cryptographic dependencies.
- Render a two-page PDF through the backend and verify ordered PDF export.

### PyPI publishing

- Configuration: [`.github/workflows/publish.yml`](../.github/workflows/publish.yml), named “Publish to PyPI”.
- Configure the PyPI `repdf` project's Trusted Publisher for `codemee/repdf`, and set repository variable `PYPI_PUBLISH_ENABLED` to `true`.
- If disabled, PyPI publishing is skipped and distribution uses GitHub Releases only.
- Publishing a release triggers the workflow; manual runs can specify an existing release using `tag`.
- Check out the tag, verify it matches `pyproject.toml`, and build the wheel/source distribution in the cloud.
- Attach Python packages to the GitHub Release, then publish to PyPI using Trusted Publishing.

## 16. Text search

- A swatch button or compact options menu opens `QColorDialog` for match colors, stored as RGB in `search/highlight_color`. The default and fallback for invalid settings is `#ffe13c`. Ordinary highlights use alpha 100; selected paragraphs overlay `darker(120)` with alpha 115. Changes repaint without rerunning searches. Existing pages, recreated virtual cards, and fullscreen share this setting independently of the interface theme.
- `SearchController` in `search_panel.py` manages the right pane, exclusive scope, query generations, results, and cancellation. `SearchPanel` supplies input, options, and upper/lower result tables with column headers.
- Search snapshots loaded documents, tab order, and page order at execution. Tab checkboxes control document scope; page checkboxes do not filter searches.
- A dedicated PDF backend starts lazily for the first search, reusing source/frozen communication without sharing the preview/OCR/image queue.
- `RenderService.request_search()` sends one file at a time with `type=search`, document ID, generation, source, original page indices, query, regex/case/whole-word flags, and any password.
- `search_page` results carry original page index, progress, paragraph IDs/text, match ranges, normalized glyph rectangles, and counts. `done`/`error` also carry document IDs.
- `search.py` reads Unicode and positions by PDFium glyph index and maps text back to glyphs. Extracted-string offsets are not assumed to equal glyph indices. OCR is not invoked.
- Geometric text lines form paragraphs. Empty lines, columns, page boundaries, and gaps over 1.5 line heights split paragraphs. Continued lines need horizontal overlap of at least 50% of the shorter line's width. Chinese/Japanese continuations join directly; others receive a space with no corresponding glyph rectangle.
- The `regex` package escapes literal input in ordinary mode and uses Python-compatible syntax in regex mode. Matching is limited to one second per paragraph; zero-length matches are skipped.
- The backend's `whole_word` flag wraps the entire query in negative lookarounds using Unicode `\w`. It combines with regex/case options but does not segment Chinese text.
- Line grouping uses full vertical extents and spacing so low glyphs such as underscores remain attached, preserving boundaries for strings such as `cat_`. Trailing comments in verbose regex mode cannot consume appended boundary conditions.
- Stop, a new query, or closing the pane terminates the search backend and invalidates old generations. Closing a searched file removes it and reschedules remaining unfinished files. Single-file failures preserve other results; timeouts stop the whole search and mark it incomplete.
- `PagePreviewLabel` stores search rectangles independently of selection highlights using normalized coordinates. `DocumentView.jump_to_search_result()` locates stable page indices and preserves zoom/Fit. Before an image is available, it scrolls using placeholder geometry to trigger on-demand rendering. Actual dimensions from the target and neighboring pages refine the still-visible match position; neighboring updates do not pull users back after they scroll away.
- The search pane starts at width 320px with resizable width and list divider. Below width 640px it shares a single pane with the PDF; below height 360px scope/flags move into a menu, preserving the 320 × 240 minimum window.
- Opening search from toolbar overflow reactivates the main window on the next event-loop turn before focusing input, avoiding a lingering active menu window on macOS.
- Passwords travel only through local communication. No decrypted PDF, disk text index, or password log is created. Search history and results last only for the current session.

## 17. Bookmarks and internal links

- `NavigationController` manages the left bookmark tree, per-document expansion/selection, and request generations. Search and bookmarks share the sidebar space. Below width 640px, bookmarks and the PDF share one pane; selecting a chapter returns to the PDF.
- The bookmark button uses 34 × 34 / 20 × 20 sizing and theme-aware colors. The tree preserves original PDF titles and shows a message without bookmarks. Closing tabs clears their state and queued navigation requests.
- The first expansion sends a `bookmarks` request. The existing single-threaded PDFium backend reuses document handles, and results remain for the document session. `get_toc(max_depth=64)` preserves hierarchy, with traversal-cycle protection provided by the PDFium wrapper.
- `render_document()` enumerates link annotations only on requested pages and attaches normalized rectangles/destinations to `page.links`. Navigation never requires scanning all pages. Main/fullscreen views share `DocumentView.page_links`, restoring links after card recreation or image-cache hits.
- PDFium resolves direct/named destinations and same-document GoTo actions. `FPDFAction_GetURIPath()` reads URI actions, supporting UTF-8 and BOM-marked UTF-16. Only HTTP/HTTPS URLs with hostnames are accepted. Email, external-document, application-launch, and JavaScript actions are not executed.
- HTTP/HTTPS links use the same on-demand reading, caching, and click detection, and open through `QDesktopServices.openUrl()` in the default browser. URLs are revalidated before opening; failures appear in the status bar, and tooltips HTML-escape URLs.
- Clicking sends `navigate`, opening only the destination page to read actual size, crop, and rotation. XYZ, FitH, FitV, FitR, and other destinations become normalized display positions. The main window preserves zoom/Fit, locates the original page, and scrolls using current `page_order`; fullscreen switches to the containing group.
- In normal mode, `PagePreviewLabel` shows a pointing hand and destination tooltip. A link activates only if left-button press/release remain in the same region within the drag threshold. Text selection, OCR, and image extraction take priority and disable links. Dragging still uses page reordering.
- New navigation invalidates old generations. Results arriving after tab switches or document closure cannot change the active document. Only existing PDF navigation data is used; plain/scanned contents are not linked automatically. Bookmark editing and rebuilding output bookmarks are not provided.

## 18. Status-bar page numbers

- PDFium `get_page_label()` reads labels on demand during page rendering/destination resolution into `DocumentView.page_labels`; opening never scans all pages. Keys are original page indices, surviving reorder and image-cache eviction. Missing labels return `None`; labels are not synthesized.
- Labels appear beside original PDF page numbers. Input still uses original page numbers. Labels are plain, single-line, width-elided text with full HTML-escaped tooltips, without increasing the minimum window size.
- A permanent status widget holds the original-page input and total count, so OCR/search/export messages do not replace it. Without a loaded document it shows `- / 0` and disables input.
- `_update_page_indicator()` uses the active document's `preview_page_index()`, matching preview/Fit visible-page selection. Control state, page focus, search navigation, and coalesced scrolling update it.
- Draft input is tracked separately from document ID. Focused, edited text is not overwritten. Switching tabs, leaving input, or pressing <kbd>Esc</kbd> restores the current page, preventing drafts from carrying across documents.
- <kbd>Enter</kbd> validates a decimal integer in `1..page_count`, then locates the original page. Manual zoom scrolls directly; Fit updates/refits the reference page. Virtual geometry avoids creating intervening cards.
- Arrow keys and <kbd>Home</kbd> / <kbd>End</kbd> edit the field rather than navigating the PDF. Submission returns focus to the reading area. Input height is 22px; width depends on page digits without increasing the minimum window size.

## 19. Printing

- `PrintOptions` is the integrated range/scaling widget, snapshotting original page numbers, tab/page order, and passwords. It offers all/current/custom/checked scopes, with checked scope using `output_selection()`. Custom ranges are deduplicated into visual order. Invalid or empty selections cannot be submitted.
- Printer, paper, orientation, copies, collation, duplex, and color operate directly on `QPrinter`, with capabilities from `QPrinterInfo`. Ordinary use opens no system dialog. Only Advanced settings uses `QPrintDialog`, then synchronizes accepted native settings back. Scope changes clear native page filtering to avoid stale positions from another list.
- Native advanced ranges use `1..N` in the print list. `printer_pages()` applies ranges/reverse order, expanding copies and collated/uncollated order only if the driver lacks multiple-copy support, avoiding duplication.
- `PrintJob` has a dedicated `RenderService`/backend. Each `print_page` request renders one page at 300 DPI, capped at 30 million pixels. It reuses packaged backend startup/authentication without reconstructing a whole PDF or using preview thumbnails. PyInstaller's Qt hooks collect Qt Print Support and platform printing components.
- `QPainter` draws page by page on the GUI thread into `QPrinter`, using full-paper coordinates, centering and clipping to the printable rectangle. Fit scales proportionally; actual size converts PDF points to printer DPI. Paper/orientation follow printer settings, without auto-rotation or per-page paper changes.
- A nonmodal progress window supports cancellation, attempting `QPrinter.abort()`. Pages already spooled may not be recalled. Only the current image is retained. Completion, error, cancellation, and app closure stop the backend before removing temporary data and password references.
- Toolbar and standard print shortcuts share one controller; only one print job runs at once. Fullscreen invocation preserves its current page, returns to the main window, and opens integrated printing. Canceling preview stops its backend without creating a print job.
- Packaged smoke tests use `QPrinter.PdfFormat` for page-by-page output and backend verification, without native dialogs or physical printers.
- The entry point opens `PrintPreviewDialog` with horizontal panels in wide windows and stacked panels in narrow ones. Only confirmation transfers the final snapshot through `accepted_pages` and creates `PrintJob`. Without a printer, preview remains available while printing is disabled. `ordered_print_pages()` reads ranges/order without consuming or changing copies/reverse settings. Preview shows one copy, with the copy count in paper information.
- Preview uses a separate backend with one-page `print_preview` requests at 150 DPI, capped at 4 million pixels and three cached pages. Rapid navigation coalesces pending requests; stale-generation results are deleted and ignored. Zoom/paper changes share `print_rect()` for drawing/clipping on white paper. Monochrome preview converts to grayscale according to settings. Driver duplex/binding is not simulated as paper flipping.
- Preview supports navigation, page input, view zoom, print scaling, and reopening printer settings. Closing/canceling stops the backend before clearing images, temporary files, and password snapshots. Printing is disabled until a preview loads successfully. Packaged smoke tests also verify preview loading without creating print output files.

## 20. OCR languages and model downloads

- Region OCR keeps its 34 × 34 main button and 20 × 20 icon. A separate 14 × 34 arrow in the same group opens the language menu managed by `OcrLanguageController`; toolbar overflow preserves this menu.
- `ocr/language` uses existing QSettings, defaulting to `builtin`. Additional choices are saved only after download and SHA256 verification succeed. Missing models never silently fall back to the built-in language.
- `ocr_models.py` pins URLs and SHA256 values from RapidOCR 3.10.0's official `default_models.yaml`. Models live in user data, separate from source, installation paths, and `_MEIPASS`.
- `OcrModelDialog` streams Qt Network data into QSaveFile while computing SHA256, then commits atomically. A 30-second transfer inactivity timeout and 180-second total budget bound downloads. Cancellation/errors discard temporary data without overwriting existing files. Failures can be retried; closing the dialog or application aborts downloads.
- Every `request_text` carries `ocr_profile` to the existing rendering backend, shared by region recognition and damaged-text fallback. The engine cache is keyed by profile and holds at most one engine to limit memory after language switches.
- Built-in recognition uses PP-OCRv6 small. Additional recognition explicitly selects PP-OCRv5 mobile using OCRVersion/ModelType enums and a language code; detection retains the bundled model. ONNX models embed their dictionaries. Explicit local paths bypass RapidOCR's automatic downloader.
- `OcrModelMissing` reports missing/damaged models. After download, retry only if the document is open, mode/language still match, and no newer selection replaced the generation. Retry snapshots do not retain PDF passwords or reopen closed documents.
- `rapidocr[rtl]` and the explicit PyInstaller `bidi.algorithm` hidden import support Arabic. Optional models are excluded from desktop bundles. Packaged self-tests check Qt HTTPS, RTL runtime, confirmation before downloading, and user data placement without downloading models.
- `test_ocr_languages.py` uses a local HTTP server for downloads, checksums, cancellation, timeout, retry, and saved settings. Existing tests cover offline built-in inference. When model URLs/hashes change, also verify official downloads, ONNX loading, and matching scripts. Desktop packaging runs only in cloud workflows.

- `auto` is a virtual choice with no model file. Region detection uses the built-in engine. Recognition processes all lines with the built-in model first, then one specialist at a time, loading each model once per request while retaining one engine and one crop image at a time.
- Automatic mode enumerates only SHA256-verified downloaded models and never downloads in the backend. Selection uses a 0.8 basic confidence threshold, at least 60% matching-script letters, at least 0.9 confidence when replacing a valid built-in result, conservative margins, and ambiguity checks. These heuristics do not calibrate cross-model probabilities. The shared 60-second deadline cannot be swallowed by ignoring specialist failures.
- Stable QActions are regrouped with two separators and no headings based on verified availability, with downloaded suffixes on installed models. `auto` can be selected without downloads. Successful downloads and externally removed/corrupt models update grouping when the menu is reopened. `test_ocr_auto.py` covers per-line selection, model-major loading, scripts, ambiguity, and deadlines.

## 21. Annotation list

- `NavigationController` shares the left pane between `bookmarks` and `annotations`, retaining selection/expansion per document and mode. Search remains mutually exclusive. Narrow windows reuse the list/PDF single-pane layout.
- `DocumentView.annotations` starts as `None`; opening files does not scan the full annotation list. The first annotation-pane request starts a dedicated `RenderService` through the existing frozen-compatible backend, keeping whole-document scanning out of the preview queue. Switching documents/modes or closing the pane/document/application stops this service and invalidates its generations.
- `pdf_annotations.py` reads supported markup subtypes, UTF-16LE Contents/T/Subj/M strings, and rectangles through PDFium, one page at a time. Links, form widgets, and popup containers are excluded. Annotation/page/document handles are explicitly closed.
- Highlights, underlines, squiggles, and strikeouts without Contents extract source text from attachment quads. Image-only markup shows an empty-text label without running OCR. Invalid rectangles still allow page-level navigation.
- Collapsed-by-default page groups show original page numbers and annotation counts; child rows show types and one-line summaries. Expansion is remembered per document and survives interface translation. Full content and metadata appear in HTML-escaped tooltips. Activation reuses navigation generations and original page indices, converting XYZ positions for rotation/crop while preserving zoom and reordered pages.
- Page groups share the destination and bounds of their first listed annotation. Individual annotations normalize all four rectangle corners for crop/rotation into `annotation_rect`; navigation targets the displayed top-left corner. `PageViewport` retains this independent overlay across card recreation and fullscreen views. Page groups update the marker; bookmarks and search results clear it without modifying the PDF.
- Preview requests call `read_annotations(..., include_text=False)` only for requested pages, returning `annotation_hits` identified by original page and PDF annotation index without extracting text or scanning other pages. `DocumentView.page_annotations` restores hit targets in recreated cards and fullscreen labels. Reading mode prioritizes annotations over links; drag and selection/OCR/image modes retain their behavior. Page clicks open the list and synchronize selection after background loading without another page jump, preserving fullscreen and the narrow-window PDF view.
- User selection records a one-shot copy request by document, original page, and annotation index. After successful list navigation or background text loading for a page click, nonempty Contents (including the marked-text fallback) is copied. Restoring UI state or translating does not copy. Closing the pane or switching sidebars clears markers across documents and fullscreen labels, pending copy requests, and the latest navigation generation so late results cannot restore markers or change the clipboard.
- `test_annotations.py` covers Unicode, encrypted PDFs, marked text, rotation/crop, reordered navigation, mode/tab switching, empty lists, and stale-result protection. The list shares data with annotation editing; unsupported types remain view-only and attachments are not executed.

## 22. Whole-document saving

- `DocumentView` starts in Fit mode and computes actual sizing after loading; manual zoom exits Fit.
- `modified` compares `page_order` to source order, adding a tab asterisk and enabling Save. Standard Save/SaveAs shortcuts belong to document saving; selected-page export no longer uses them.
- `SaveController` and `SavePdfTask` save every page of the active document. `core.save_document()` clones the document and reorders the page tree, retaining indirect page references and bookmark/link destinations. Numeric local destinations become original page references; page labels are preserved as per-page fixed labels.
- Encrypted PDFs use AES-256 with the opening password and original permission flags. An unknown original owner password cannot be preserved. A same-directory temporary file is flushed/fsynced before atomic replacement; failure removes the temporary file and preserves the original.
- Before writing on Windows, preview/search/annotation readers stop to release PDFium file handles. Preview services restart on success or failure. Successful saving rebuilds the tab and remaps the current page, selection, and Fit/zoom state so old source indices cannot refer to the reordered file.

- The main fullscreen QAction opens or closes fullscreen; its right-hand dropdown provides three exclusive mode actions. <kbd>F11</kbd> uses the session’s `fullscreen_mode`. An existing fullscreen window switches through `set_mode()`, regrouping pages and invalidating old renders while retaining the current page.

## 23. Annotation creation and compatible editing

- `annotation_data.py` imports representable standard Underline/StrikeOut/Squiggly/FreeTextCallout annotations and versioned RePDF data. Locked annotations, rich text, unavailable fonts, transparency and unsupported appearances remain native/view-only with a reason. Invisible annotations do not become interactive overlays.
- `annotation_store.py` retains baseline models and a delta, with `QUndoStack` for creation, style/text changes, movement, resizing and deletion. Dirty state compares both page order and annotation changes. Geometry uses source PDF coordinates and identities remain separate from page order.
- `annotation_editor.py` shares mouse editing, style menus and inline text editing across normal/fullscreen views. Text input takes priority for arrows, undo and Esc. Commit text before saving, printing or exporting. Drags update a transient preview and produce one undo command on release.
- `annotation_graphics.py` shares vector painting and Qt PDF font embedding. Persistence imports the appearance as an `/AP /N` Form XObject with cloned resources, and writes standard QuadPoints, CL, LE, DA, DR, RD and BS fields. `/RepdfData` retains versioned editing styles; annotations are not flattened.
- Screen rendering parses only requested pages, temporarily hides editable native appearances, restores flags afterwards, and uses Qt overlays to avoid double drawing. Metadata readers use seekable file streams, with three cached documents and explicit closure on eviction/release, rather than copying entire source files into memory first.
- `DocumentSelection`, `SavePdfTask` and `PrintPage` accept annotation snapshots defaulting to empty. Saving, selected-page export and printing apply the same delta before reordering. Print backends cache by source and snapshot fingerprint instead of rebuilding every page; deletions are deferred to preserve source indices.
- Successful saves reuse tab rebuilding/page remapping and reload annotation identities. Closing dirty tabs/windows offers Save/Discard/Cancel; save failure retains the original file and edit state.
- `test_annotation_editing.py` covers native appearances/Unicode, reopened editing, conservative imports, movement, undo, close decisions, crop/rotation transforms and icon sizing. PDFium and Poppler provide independent display checks.

- Editing metadata stores a fingerprint of standard fields and the appearance stream. Reopening checks consistency. If another application changes the appearance/text without updating that metadata, native display remains authoritative and the annotation becomes view-only, preventing stale-model writeback.

- A 90 ms single-shot timer requests text-layer selection previews for markup. Previews neither create annotations nor touch the clipboard; release creates one undoable annotation from the final result. Highlights use standard `/Highlight` and `/QuadPoints`, with transparent appearance in `/AP`.
- Callout fitting measures QTextDocument content using the same font and margins as PDF appearances. Sizes are adjusted in upright page coordinates, then mapped back to rotated/cropped coordinates. The arrow target stays fixed; cancelling restores the original box.

- Callout corner radii are retained in editable `radius` data and drawn as vector paths in the standard `/AP` appearance. Annotations retain `/FreeText`, `/CL` and `/Contents` and remain unflattened. Missing radius data in older annotations means 0.

- `annotation_geometry.py` supplies drawing coordinates, translation and resizing. Notes, lines/arrows, rectangles, ellipses and strokes use `Text` / `Line` / `Square` / `Circle` / `Ink`, with standard `/L`, `/LE`, `/RD`, `/IC`, `/InkList`, `/Contents` and `/AP`. Editable data is retained without flattening.
- New-type signatures include their geometry fields while existing callout/markup signatures stay unchanged for backward compatibility. Notes/drawings from other applications retain native appearances and remain read-only.
- Drawing updates only the transient preview; release validates geometry and creates one undo command. Cancelled/empty note edits create no annotation. Saving, printing and exporting reuse the same change snapshots.

- `annotation_spin.py` combines Qt spin boxes without native buttons with shared chevron tool buttons, synchronizing range states even when value updates block signals.
- Markup requests snapshot companion settings; previews create nothing. Final glyph results determine the anchor and start an undo macro, completed on text acceptance/cancellation. Only confirmed text enters the PDF; cancellation retains the markup.

- `OverflowToolBar` displays page-selection controls and output actions directly. Checkboxes in narrow-window overflow mirror source controls; Save shortcuts belong directly to the main window.
- `floating_tools.py` hosts annotations in the reading window and shares annotation/extraction actions in fullscreen, with an always-visible mode dropdown. Menus are temporarily reparented during fullscreen and restored before exit to avoid modal blocking or deletion. Bars support dragging, bounds clamping and overflow, retaining position across page and mode changes.

- `shortcut_hints.py` derives tooltips from QAction bindings, watches action changes and refreshes hints on language changes. It uses NativeText and deduplicates Tab/Backtab display aliases.

- Checkbox and split-button groups use fixed content sizes. `OverflowToolBar` watches child LayoutRequest events and refreshes QWidgetAction geometry and overflow boundaries, preventing stale widths from clipping labels after language changes.

- `OverflowToolBar.group_sections()` packs separator-delimited runs into indivisible QWidgetAction containers, keeping expanding spacers separate. Overflow lists each complete group and its settings menus in order. `tool_actions()` exposes logical ordering and `widgetForAction()` retains individual-button lookup. Window registration keeps shortcuts active while sections are hidden.

- `message_dialogs.py` creates the Qt unsaved-changes prompt with a separate heading, filename and discard explanation. Save is the default and Cancel handles Escape; all three choices retain the existing save/close flow.

- Search results retain a vertical split: the upper Files table shows Filename/Count, where Count means matching paragraphs. The lower Matches table shows Page/Paragraph; clicking either column navigates to the result. Numbers align right and paragraphs retain single-line ellipsis and full tooltips.

## Folder search and whole-document text copying

- `SearchTarget` decouples paths, page orders and in-memory passwords from tab lifetimes. Open PDFs retain document IDs; unopened files use independent negative IDs. Folder enumeration is nonrecursive; background searches discover page counts when `pages=None`, without rendering or creating tabs first.
- Result activation records the query generation, loading document and paragraph key. `_pdf_loaded()` navigates only after loading. Stops, new searches, closure and newer selections invalidate pending jumps. Existing paths reuse their tabs. Folder results survive tab closure while password references are cleared.
- `document_text.py` uses a dedicated `RenderService` and `copy_document` request to stream page text and normalized text rectangles, merged in display order without OCR. Only complete success updates the clipboard; errors, cancellation and empty results retain its contents.
- Whole-document selections also apply to lazily realized cards and fullscreen pages. Select All is intercepted only in text-copy reading mode, excluding search inputs, annotation editors and other text fields. Closure, document/mode changes and saving stop the dedicated reader.

## Open-source licensing and releases

- The project license identifier is `GPL-3.0-only`. The root `LICENSE` contains the full terms; `NOTICE` provides the project grant and third-party information. Both are included in Python distributions through `license-files`.
- Cloud desktop builds embed both files under `repdf/licenses` and attach `LICENSE.txt` and `NOTICE.txt` to release artifacts. Executables are not built locally.
- Binary releases must preserve corresponding versioned source, locked dependencies, and build instructions, and meet the distribution requirements of the GPL and third-party components.
- The incorporated PDFPick source and this project share the same rights holder, Shin-Wei Hwang. The rights holder confirmed ownership of the associated author identities and accounts and selected `GPL-3.0-only` for this project; separate upstream author permission is not required. Third-party libraries, models, and assets retain their own licenses; see the [license review](LICENSE_AUDIT.en.md) for per-component findings and distribution requirements. Cloud builds use `scripts/collect_licenses.py` to embed full actual-environment notices and attach platform-specific license ZIPs, rejecting dependencies or Qt modules outside the reviewed scope.

- `about.py` provides the Qt About RePDF dialog, full GPL text and an offline third-party notice tree. Only the source button opens a website. Resource discovery supports checkouts, wheel dist-info licenses and frozen resources. UI labels follow language/theme changes; repeated activation reuses the dialog.
- On Windows, `system_menu.py` uses Win32 `GetSystemMenu` to append a separator and custom command. `nativeEvent` handles only its own `WM_SYSCOMMAND` ID and delegates all other messages to Qt. Refresh updates one entry across language changes and reinstalls it after native handle changes. On macOS, Qt places `QAction.AboutRole` from a native QMenuBar into the standard application menu. Windows gains no extra menu bar.

- Packaging excludes unused QtPdf/QtPdfWidgets and the QImage qpdf plugin, avoiding a second PDF engine pulled in by QtGui. PDF reading and output continue to use pypdfium2.
