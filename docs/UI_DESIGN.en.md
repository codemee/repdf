# RePDF UI design reference

[繁體中文](UI_DESIGN.md) | [English](UI_DESIGN.en.md)

This document describes the implementation in RePDF as a reference for other desktop projects. Values come from the code. “Fixed” means an explicitly configured size; “automatic” means Qt, fonts, or content determine the size.

## 1. Style and units

- Framework: PySide6/Qt Widgets with the `Fusion` style, customized using QPalette and QSS.
- The interface uses a flat toolbar, thin-line icons, light borders, small corner radii, and low-saturation backgrounds.
- Unless specified as font points or icon drawing coordinates, sizes are **Qt logical pixels**. At 150% Windows display scaling, 34 logical pixels correspond to approximately 51 physical pixels.
- PDF zoom is separate from operating-system DPI scaling and does not affect toolbar or button dimensions.

## 2. Window and main layout

| Item | Current specification | Type |
| --- | --- | --- |
| Main window | 1040 × 760, excluding the OS window frame | Initial size |
| Minimum main window | 320 × 240 | Fixed minimum |
| Main content margins | Left 12, top 10, right 12, bottom 12 | Fixed |
| Document root layout margins | 0 on all sides | Fixed |
| Page grid margins | 12 on all sides | Fixed |
| Page card spacing | 12 horizontally and vertically | Fixed |
| Page grid alignment | Top, horizontally centered | Automatic layout |
| Status bar | Window background, no border or resize grip | Automatic height |

The main layout contains the toolbar, document tabs, scrollable reading area, and bottom status bar. Normal view arranges cards according to available width; Fit mode uses one column.

- The left bookmark pane starts at width 260, with margins 8, spacing 6, and tree indentation 16. Its close button uses the same 34 × 34 button and 20 × 20 icon sizes.
- Below window width 640, bookmarks and the PDF share one pane. Bookmark and search panes are mutually exclusive.
- A permanent page control occupies the right side of the status bar. Margins: left 8, right 4, top/bottom 0; spacing 4. The input is 22 high and 44–88 wide depending on the number of page digits.
- PDF page labels use a single line with a maximum width of 180, shortened further in narrow windows. The full label appears in the tooltip.

## 3. Toolbar and buttons

Fullscreen uses a 34 × 34 main button with a 14 × 34 right-hand dropdown arrow, spacing 2 and 20 × 20 icons. Its menu offers single page, spread and cover plus spread; the main button and <kbd>F11</kbd> reuse the last mode selected in this session.

The main row places Open, Save, Save As, Print, Search, Bookmarks, Annotations, the annotation-tools toggle, copy text, OCR, image extraction, export and split on the left. An expanding spacer keeps zoom, Fit, the fullscreen mode dropdown, language and theme on the right. Markup, text annotations and drawings use a draggable horizontal floating toolbar with remembered visibility.

| Item | Current specification |
| --- | --- |
| Toolbar height | **Fixed 42** |
| Toolbar padding | 4 on all sides |
| Toolbar spacing | 4 |
| Toolbar bottom border | 1, using the border color |
| Toolbar behavior | Not movable or floatable; no context menu |
| Insufficient width | A 34 × 34 three-dot button opens tools that do not fit; they return automatically when widened |
| Icon button outer size | **Fixed 34 × 34** |
| Icon display area | **20 × 20**, centered horizontally and vertically |
| Button clearance within toolbar | 4 above and below |
| Icon-area clearance within button | 7 on all sides, including the border area |
| Tool button QSS padding | 4; this style declaration is not the final icon clearance |
| Tool button border | 1; transparent in normal state to avoid size changes |
| Tool button radius | 4 for ordinary buttons; 8 for state buttons |
| Normal tool button background | Transparent |
| Tool button text | Hidden by default; name and shortcut appear in the tooltip |
| OCR language arrow | **14 × 34**, grouped with the 34 × 34 OCR main button with spacing 2; independent hover, no border, and a 6 × 3 arrow |
| Percentage text button | **64 × 34**, with extra width for text |
| Separator | Width 1; margins top/bottom 5, left/right 4 |
| Odd/even checkbox group margins | Left 8, top 0, right 4, bottom 0 |
| Odd/even checkbox spacing | 8 |

File, selection, and text tools are on the left. Stretchable space separates them from zoom, preview modes, language, and theme controls on the right.

### Tool button states

| State | Appearance |
| --- | --- |
| Normal | Transparent background/border, normal icon color |
| Hover | Hover background |
| Pressed | Pressed background |
| Keyboard focus | Accent border for ordinary tools; state buttons remain borderless |
| Disabled | Transparent background, disabled icon/text colors |
| State button active | Hover background with accent-colored icon and no outline; pressed background when hovered |

Copy text, region OCR, image extraction, bookmarks, annotations, Fit, and search options share the borderless `stateButton` styling with background radius 8. Copy text, region OCR, and image extraction remain mutually exclusive.

## 4. Icon drawing specifications

| Item | Current specification |
| --- | --- |
| Design coordinate canvas | **24 × 24** |
| Prerendered bitmap | **48 × 48**, transparent background |
| Prerender scale | 2×, `QPainter.scale(2, 2)` |
| Toolbar display size | **20 × 20** |
| Stroke width | **1.0 design coordinate unit** |
| Line style | `SolidLine` |
| Line caps | `RoundCap` |
| Line joins | `RoundJoin` |
| Antialiasing | Enabled |
| Normal icon color | `QPalette.ButtonText` |
| Active state icon color | `QPalette.Highlight`, including while hovered |
| Disabled icon color | `QPalette.Disabled.ButtonText` |
| Theme updates | Regenerate icons when the palette changes |

Stroke scaling:

```text
24 × 24 design canvas: stroke width 1
48 × 48 prerendered bitmap: approximately 2 bitmap pixels
20 × 20 display: approximately 1 × 20 / 24 = 0.83 logical pixels
```

For an SVG adaptation, `viewBox="0 0 24 24"`, `stroke-width="1"`, and display dimensions of 20 × 20 approximate the current line weight. A 1px stroke drawn directly on a 20 × 20 canvas looks slightly heavier. Antialiasing, DPI, and bitmap scaling also affect edges.

Icons are drawn geometrically in code and converted into raster QIcons. They are not SVG assets or vectors redrawn live for each DPI.

Shapes do not necessarily fill the canvas. Some circles use `(3, 3, 18, 18)`, for example. The 20 × 20 size refers to the entire icon canvas; the visible shape may be smaller.

### Special icons

- System language: thin-line globe.
- Explicit language: centered `中` / `En`, using a 16px design font size and scaling with the canvas.
- System theme: circle of diameter 18 design units, white on the left and black on the right; the outline uses the current icon color.
- Light/dark: sun/moon.
- Region OCR: corner frame around a centered `A`, using a bold 12px design font.
- Extract image: image frame, mountains, and downward arrow.
- Search text: magnifying glass, using a 20 × 20 icon in a 34 × 34 button. Documentation provides light and dark variants.
- Tab close: the text character `×`, rather than a drawn toolbar icon.
- Checkbox check/partial marks: 16 × 16 SVGs, strokes of width **2** with round caps; white in light mode and dark green-black in dark mode. Their stroke specification differs from toolbar icons.

## 5. Other controls

| Control | Current specification |
| --- | --- |
| Tab | Padding top/bottom 5, left/right 8; right margin 2; reserved bottom border 2 |
| Selected tab | Card background with accent bottom border |
| Tab text | Sized to content and available width; elided on the right |
| Tab close button | Fixed 22 × 22 |
| Tab checkbox | Extra left padding 8 to separate it from the tab edge |
| Tab behavior | Drag to reorder; full file path in tooltip |
| Checkbox indicator | QSS width/height 16 × 16, plus 1px border; radius 3 |
| Checkbox/text spacing | 6 |
| Checked checkbox background | `#0b57d0` in light; `#a8ed42` in dark |
| Standard QPushButton | QSS minimum content height 30, padding top/bottom 2 and left/right 12, border 1, radius 5 |
| Zoom slider | Fixed width 150; automatic height |
| Slider groove | Height 2, radius 1 |
| Slider handle | Width 10, radius 5, no border, vertical margin -4 |
| Vertical/horizontal scrollbar | Width/height 10, margin 2 |
| Scrollbar handle | Minimum length 24, radius 3 |
| Scrollbar end arrows | Hidden |
| Reading scroll container | Border 1, radius 6 |

Text buttons, whole checkboxes, and the tab bar do not have a single fixed height. Qt's box model, fonts, and content determine their dimensions. Distinguish content dimensions from outer dimensions when adapting them.

## 6. Page cards and interaction

| Item | Current specification |
| --- | --- |
| Page card | Border 1, radius 8 |
| Card padding | Left 11, top 9, right 11, bottom 11 |
| Header/preview spacing | 8 |
| Card width | Preview image width + 24 |
| Card header | Page checkbox on the left, drag handle on the right |
| Reorder animation | 180 ms, `OutCubic` |
| Insertion indicator | 2px dashed accent border, radius 8 |
| Text highlight | Accent color, alpha 90/255, approximately 35% opacity |
| Region OCR selection | Same translucent fill, plus accent outline |
| Normal page cursor | Hand when draggable |
| Text selection cursor | I-beam |
| Region OCR cursor | Crosshair |
| Extract image cursor | Pointing hand; clicking saves the full embedded raster image |

Fullscreen reserves a 30px header for the page checkbox, with a 12px spread gap. Pages are proportionally centered within available space. The checkbox is inset 6 from the page's left edge, with a top offset of 4 within the header.

## 7. Fonts

Global text uses **10pt**, not 10px. The first available font is selected in this order:

1. Microsoft JhengHei UI
2. Microsoft JhengHei
3. Noto Sans TC
4. Arial

If none is available, QApplication's default font and size are retained. Font metrics affect controls without fixed heights and the width of text.

## 8. Light and dark colors

| Purpose | Light | Dark |
| --- | --- | --- |
| Window/toolbar/status background | `#f5f6f8` | `#171321` |
| Base/input background | `#ffffff` | `#100e18` |
| Alternate base | `#eef0f3` | `#261d38` |
| Card/custom text button background | `#ffffff` | `#2b2142` |
| QPalette.Button | `#ffffff` | `#34264f` |
| Main text/normal icons | `#202124` | `#eee7f7` |
| Borders/separators | `#d5d8dc` | `#625079` |
| Accent/focus/filled slider | `#0b57d0` | `#a8ed42` |
| Selected text foreground | `#ffffff` | `#13190d` |
| Hover background | `#e7ebf0` | `#3b2a56` |
| Pressed background | `#d8e3f3` | `#4d376e` |
| Active state button background | `#e7ebf0` | `#3b2a56` |
| Hovered active state button background | `#d8e3f3` | `#4d376e` |
| Disabled text/icons | `#9aa0a6` | `#8f829f` |
| Placeholder text | `#6f7378` | `#b5a7c5` |
| Slider groove/scrollbar handle | `#c4c7c5` | `#695580` |
| Circular slider handle | `#0b57d0` | `#ff9d45` |

Dark mode uses an Evangelion Unit-01-inspired palette: purple-black backgrounds, purple panels, neon-green accents, and orange slider handles and links. PDF page content retains its original colors.

System, Light, and Dark modes are available and remembered. System mode listens for system theme changes and updates the palette, QSS, and toolbar icons.

## 9. Recommended dimensions for reuse

```text
toolbar.height              = 42
toolbar.padding             = 4
toolbar.spacing             = 4
toolButton.size             = 34 × 34
toolButton.radius           = 4
stateToolButton.radius      = 8
toolButton.border           = 1
toolButton.iconSize         = 20 × 20
icon.designCanvas           = 24 × 24
icon.designStroke           = 1
icon.cap                    = round
icon.join                   = round
content.margin              = 12
card.gap                    = 12
card.radius                 = 8
container.radius            = 6
textButton.radius           = 5
checkbox.radius             = 3
bodyFont.pointSize          = 10
reorderAnimation.durationMs = 180
```

These values are a starting point for desktop tools. Adapt fixed button sizes, icon canvases, and stroke ratios together. QSS `padding: 4px` alone does not determine button size.

Search, Stop, Close, and compact Options buttons in the search pane also use 34 × 34 buttons and 20 × 20 icons, with tooltips, accessible names, and theme-aware colors. Each matching paragraph occupies one line, elided with `...`; the tooltip contains the complete text. Adjacent results alternate between palette Base and AlternateBase backgrounds.

The scope dropdown and `.*` (regular expression), `Aa` (case-sensitive), and underlined `ab` (whole-word) toggle buttons share one row. Selected backgrounds indicate active options; hovering changes the background without an outline. In compact-height mode, the options menu provides the same synchronized settings.

Search options and toolbar state buttons share borderless styling with background radius 8, retaining 34 × 34 buttons, 20 × 20 icons, and one-unit icon design strokes. Active buttons use the theme hover background; hovering an active button uses the pressed background. Transparent border space prevents icon movement between states. Ordinary non-state tool buttons retain radius 4.

A color swatch on the same row configures match highlighting, using a 34 × 34 button and 20 × 20 icon canvas. Its 24 × 24 design canvas contains a 16 × 16 swatch with radius 2 and a one-unit outline. Compact mode provides the option in the menu. Highlights default to yellow with customizable RGB; selected paragraphs overlay a darker shade of the same color, independently of the interface theme.

## 10. Implementation sources

- [render_doc_icons.py](../scripts/render_doc_icons.py) generates documentation icons. Run `uv run python scripts/render_doc_icons.py` to update `docs/images/`.
- Transparent light/dark variants use `toolbar-<name>.png` and `toolbar-<name>-dark.png`, with identical dimensions.
- READMEs use `<picture>` and `prefers-color-scheme` so compatible readers select the theme automatically. GitHub supports this; see its [official explanation](https://github.blog/developer-skills/github/how-to-make-your-images-in-markdown-on-github-adjust-for-dark-mode-and-light-mode/).
- Readers without `<picture>` support, or without theme-aware media query updates, may show the default light variant. Behavior depends on the reader. In-app icons are drawn using the current palette.
- [app.py](../src/repdf/app.py): main window, toolbar, fixed sizes, zoom, and fonts.
- [theme.py](../src/repdf/theme.py): QPalette, QSS, state colors, and corner radii.
- [icons.py](../src/repdf/icons.py): icon geometry, canvas, strokes, and normal/disabled variants.
- [widgets.py](../src/repdf/widgets.py): page cards, drag animations, highlights, and OCR selection.
- [preview.py](../src/repdf/preview.py): fullscreen page layout and headers.
- [navigation.py](../src/repdf/navigation.py): bookmarks, narrow-window switching, and links.
- [printing.py](../src/repdf/printing.py): print range/scaling, system print dialog, and nonmodal progress window. The toolbar uses the same 34 × 34 button and 20 × 20 icon sizes.
- Printing uses one integrated window: scrollable settings on the left, preview on the right. Below width 720, they stack vertically. Minimum window size is 320 × 420; initial size is 1060 × 760. Advanced settings, Print, and Cancel remain at the bottom.
- Range and scaling hints appear below the options and update with them. The page range input appears only for custom ranges; a document/page summary remains below. Resolution and other implementation details belong in documentation.
- Print preview uses a white sheet with the actual paper proportions and a gray dashed printable boundary; the outer canvas follows the interface theme. Navigation buttons use 34 × 34 / 20 × 20 dimensions, with preview zoom on a separate row.
- [check.svg](../src/repdf/assets/check.svg) and [partial.svg](../src/repdf/assets/partial.svg): white checkbox symbols for light mode; [check-dark.svg](../src/repdf/assets/check-dark.svg) and [partial-dark.svg](../src/repdf/assets/partial-dark.svg) provide dark marks for the neon-green background in dark mode.

## OCR model download dialog

- Starts at 460 × 250 and follows the current theme, showing language, source, explanation, progress, and cancellation.
- Download and use explicitly starts a download. The active language changes only after success; failures show a reason and allow retries.
- Narrow windows expose OCR recognition language in toolbar overflow. An exclusive checked item identifies the active mode. Automatic and Automatic + downloaded models appear first. Two separators divide downloaded and not-downloaded models without headings; installed entries have a (downloaded) suffix.

- Dark popup menus use the toolbar hover color `#3b2a56` as their background, `#4d376e` for hovered items, and `#625079` for borders/separators. Light menus retain a white background and light gray hover.

## Annotations pane

- A 34 × 34 toolbar state button opens the pane. Its 20 × 20 speech-bubble icon uses a 1 px stroke and the standard checked/hover backgrounds and accent color.
- It shares the bookmark pane on the left: initial width 260, margins 8, spacing 6, and a 34 × 34 close button with a 20 × 20 icon. The pane status shows the count, loading state, or empty-list message.
- Selecting an annotation with text copies it and reports the character count in the status bar; empty annotations preserve the clipboard. Closing the annotation pane or switching sidebars clears markers. Reopening does not restore markers or copy text.
- In reading mode, annotation bounds use a pointing-hand cursor. Clicking marks the annotation and synchronizes the list selection and expanded group. Fullscreen stays open; narrow windows keep the PDF visible.
- Clicking a page group jumps to and marks its first listed annotation. Individual annotations use a 2 px accent outline with translucent fill, scaled with the page in both normal and fullscreen views.
- A single-column tree groups annotations by page. Page rows show the number and count and start collapsed; children elide long one-line summaries. Tooltips retain full text and metadata. In narrow windows, selecting an item returns to the PDF; the toolbar button reopens the list.

## Annotation editing tools

- Markup, text-annotation and drawing controls sit in the second toolbar. Each uses a 34 × 34 main button plus a 14 × 34 arrow, spacing 2, and a 20 × 20 icon with 1 px strokes.
- Popup style panels provide line icons, swatches, widths and text styles without a fixed sidebar. Selected callouts show accent-coloured corner and arrow handles and support inline text editing.
- Application artwork is retained, centred by its visible bounds and fitted to 92% of the canvas consistently for windows, Windows ICO and macOS ICNS.

- Clicking a target automatically places a text box with space for at least one line nearby. An outside click only finishes editing. Dragged boxes and handles share the same preview coordinates.
- Unsaved-change prompts use Qt message boxes with a 28 px orange circular warning icon, a 14 pt heading and a separate 10 pt explanation. Light mode uses white; dark mode retains the theme background.

- Inline callout editors use 6 px corners, theme backgrounds and a thin accent border. Content sizes the box automatically, wrapping at its width limit and growing within the page. Finished annotations use their configured PDF appearance.
- The markup panel offers highlight, underline, strikeout and squiggly modes. Drag previews follow glyph ranges instead of a rectangular selection. Highlights default to yellow at 35% opacity and disable the width control.
- Save prompts have 24 px padding and right-aligned 88 × 34 px buttons ordered Cancel, Don’t Save, Save. Cancel has an accent outline, Don’t Save uses orange text, and Save is the filled accent default button.

- Toolbar zoom percentages are rounded to whole numbers; Fit and page rendering retain the original precision.

- Clicking an existing callout selects it immediately. When the annotations pane is closed, opening the list waits for the system double-click interval so relayout cannot interrupt editing. Bodies use move cursors, corners use rotation-aware diagonal resize cursors, and arrow endpoints use pointing-hand cursors.

- Annotation list items use 20 px type icons without textual type prefixes. Type names remain in tooltips and accessible text; selected icons use the selected foreground colour.
- Items with text reveal a read-only selectable text area below the list, with 34 × 34 / 20 × 20 select-all and copy controls. Partial selections and standard keyboard selection/copy shortcuts work.
- New callouts default to 6 pt corners, adjustable from 0–24 pt in the style panel. Existing annotations retain their shape; 0 means square. Preview and saved PDF appearances share the rounded path.

- Rows with text reserve a 34 × 34 / 20 × 20 copy control on the right, eliding the summary before it. Clicking copies the complete item text without changing selection, navigating or opening the details area. The standard copy shortcut also works when the list is focused.
- The callout tool icon uses a text box and a single diagonal arrow.

- Inline typing retains the box’s original minimum width and expands it to the right with single-line content, wrapping only when page space is exhausted. IME composition participates in sizing without entering the saved PDF text.

- The text annotation main button combines callouts and sticky notes, with 34 × 34 / 20 × 20 type buttons in its dropdown. Notes show only applicable colour settings, defaulting to golden yellow and remembering their colour independently. Choosing a type activates the tool and updates its main icon without converting existing items.
- An adjacent drawing main button/dropdown offers lines, arrows, rectangles, ellipses and ink. Fill controls appear only for rectangles/ellipses. Annotation tools are mutually exclusive with copy text, OCR and image extraction.
- Notes appear as page icons and open a Qt text dialog on double-click. They can be moved, and the sidebar shows their content and copy action.

- Annotation-panel numeric fields use the same 12 × 12 chevrons as toolbar dropdowns, with up/down variants, press-and-hold stepping, keyboard entry and range limits.
- The markup panel optionally adds a callout or note via two type icons. Its anchor is the upper midpoint of the selected glyph bounds in display orientation, including rotated/cropped pages. Notes are constrained to page bounds when space above is limited.

- Fullscreen uses a movable, collapsible horizontal floating annotation toolbar without changing the PDF fit area. Its horizontal inner bar is 42 px high. Controls remain 34 × 34 with 20 × 20 icons; settings arrows stay to the right of their main buttons. The mode dropdown remains available when annotation tools are collapsed. Switching modes preserves the current page; exiting restores the reading window’s floating-toolbar visibility.

- First-row buttons are shown directly when space permits and enter the overflow menu when needed. Floating annotation expansion is remembered independently.

- Buttons with keyboard shortcuts list their actual bindings in tooltips, using native platform key names and updating with the UI language.

- Separators surround the page-output group. Odd/even tools sit beside each page checkbox: standard three-state checkboxes labeled Odd pages or Even pages. They act on original page numbers in that PDF and synchronize between normal and fullscreen views.

- Search results retain a vertical split: the upper Files table shows Filename/Count, where Count means individual matches. The lower Matches table shows Page/Paragraph; clicking either column navigates to the result. Numbers align right and paragraphs retain single-line ellipsis and full tooltips.

- The export icon uses a closed document outline with a downward arrow inside, retaining a 20 × 20 display area and 1 px design stroke so the small-size outline has no gaps.

- Search scope includes the current tab’s folder in both standard and compact controls, with the full selected name in its tooltip. Copy text tooltips describe Select All; normal and fullscreen reading views support whole-document text selection.

- Merge export produces one PDF. Split offers PDF or PNG in the save dialog, producing one file per page without adding toolbar buttons. With no selected pages, the buttons remain enabled and the status bar and tooltips explain the current-page default. Background PNG export displays page progress and a cancel button.

## Tab strip and search pane

- The left scroll control sits at the left end; the right scroll control and dropdown sit at the right end. All three use 16 × 16 outline icons in 26px-wide slots, matching the tab-bar height. Qt tear indicators are suppressed to avoid extra arrows.
- The dropdown lists full filenames in current tab order, checks the active tab, and shows complete paths in tooltips.
- Search uses the existing toggle-button appearance: highlighted while the pane is visible, and clicking again closes it. Closing the pane, switching sidebars, or changing narrow-window visibility updates the state. Find shortcuts continue to open and focus search.
