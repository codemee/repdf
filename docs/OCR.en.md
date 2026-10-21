# OCR text extraction

[繁體中文](OCR.md) | [English](OCR.en.md)

RePDF provides an OCR fallback for text selection and manual region OCR. Recognized text is copied to the clipboard; the PDF is unchanged.

## Usage

- The toolbar provides Copy text and Region OCR modes.
- Both work in normal and fullscreen view.
- They are mutually exclusive with each other and with Extract image mode.

### Copy text

1. Click Copy text in the toolbar.
2. Drag across text on the page. The selected text is highlighted.
3. Release the mouse to copy the text to the clipboard.
4. If the original text appears damaged, RePDF automatically tries OCR. Check the status bar and review the result afterward.

### Region OCR

1. Click Region OCR in the toolbar. The cursor becomes a crosshair.
2. Draw a rectangle around the area to recognize on a page or image.
3. Release the mouse to recognize and copy the text.
4. An empty region leaves the clipboard unchanged.

### When the automatic fallback runs

- Normal text is copied directly. Dragging only updates the highlight.
- OCR runs after release if the extracted text contains U+FFFD (�), Unicode noncharacters, or unpaired surrogates.
- Control characters also trigger OCR, except normal line breaks and <kbd>Tab</kbd>.
- Empty selections and image-only selections do not trigger OCR in Copy text mode.
- Damaged mappings that happen to produce valid Chinese characters, and text using private-use characters, retain the original extracted text. Not every incorrect character can be detected.

## Recognition and limitations

- Region OCR works on scanned images, screenshots, and ordinary PDFs. No background OCR runs while dragging.
- Region OCR detects text lines, then combines short dashes, underscores, and similar marks on the same line for recognition.
- OCR runs in the existing backend process. Selected glyphs are rendered by line at 400 DPI. Successful recognition is copied to the clipboard, with a status message asking you to review it.
- Large regions use a reduced resolution to stay within approximately 19 million pixels.
- Recognition runs directly in Python using RapidOCR 3.10.0 and the CPU version of ONNX Runtime.
- Recognition images are processed in memory without writing temporary image files.
- Models load only when OCR is first needed. Later requests reuse the same engine.
- Text-selection fallback loads only the recognition model. The first region OCR request additionally loads the detection model; both share the recognition engine.
- The orientation classification model is not loaded. Horizontal text is the intended use; recognition quality for rotated or vertical text has not been validated.
- Missing models/libraries, initialization failure, empty or damaged results, or average character confidence below 0.8 preserve the original text and display a reason.
- Each request handles at most 30 lines, with a limit of 20 million pixels per line image.
- A total budget of 60 seconds is checked between lines. Native inference cannot be forcibly interrupted while running.
- OCR may introduce character, punctuation, or layout errors. Review the output.

## Recognition languages

- Automatic supports Traditional Chinese, Simplified Chinese, English, Japanese, and Latin-script languages such as French, German, Spanish, Portuguese, Italian, and Vietnamese. No download is needed.
- Use the arrow beside Region OCR to choose a recognition language. The main button still toggles region OCR.
- Common additional choices are Korean, Thai, Russian/Ukrainian (Cyrillic), Arabic, and Hindi/Nepali (Devanagari).
- Greek, Tamil, and Telugu are also available.
- Automatic + downloaded models combines locally available models and chooses results per line. It never downloads other models automatically.
- Separators divide automatic choices, downloaded models, and models not downloaded, without group headings. Downloaded models have a (downloaded) suffix. Groups and labels update after downloads or when files are missing or corrupt.
- In narrow windows, use OCR recognition language in the three-dot overflow menu.
- The first selection of an additional language opens a confirmation dialog. Only Download and use starts a network request. You can cancel a download or retry a failure in the same dialog.
- The language changes only after model verification succeeds. Canceling, timeout, network errors, or failed checksums preserve the current setting and do not replace existing models with partial files.
- Your choice is saved and shared by region OCR and damaged-text fallback. Select Automatic to return to the default model.
- If the active model is deleted or damaged, the next OCR operation offers to download it again, then retries the original selection if it is still valid.
- Automatic + downloaded models compares confidence and writing-system consistency; cross-model confidence scores are not calibrated probabilities. Language detection is not guaranteed. Uncertain candidates may retain the built-in result or fail recognition, so review the output.
- Automatic + downloaded models tries all downloaded models and is usually slower than a single model. Different languages on separate lines can be handled independently; mixed writing systems within one line may remain incomplete. Select a specific model when the document language is known. Additional models do not necessarily cover every built-in language.
- Interface and recognition languages are independent. Review recognized text; model coverage does not guarantee accuracy for every document.
- See the [RapidOCR model documentation](https://rapidai.github.io/RapidOCRDocs/main/model_list/). RePDF pins RapidOCR 3.10.0, with built-in PP-OCRv6 small and additional PP-OCRv5 mobile models.

## Installation and offline use

See [Install and launch](../README.en.md#install-and-launch).

- The OCR runtime and built-in models ship with the package. No separate Python, CLI, or inference application is required; additional languages download model files only.
- The `rapidocr==3.10.0` Python wheel includes the multilingual recognition model `PP-OCRv6_rec_small.onnx`, approximately 20.3 MiB.
- Region OCR also uses the bundled detection model `PP-OCRv6_det_small.onnx`, approximately 9.5 MiB.
- Explicit local model paths and SHA256 checks are used, bypassing the default automatic model download flow.
- Additional models are downloaded from RapidOCR's official ModelScope source and checked against the pinned official SHA256. Networking occurs only after download confirmation; PDFs are never uploaded for recognition.
- Downloaded models live in your user data directory and survive application updates:
  - Windows: `%LOCALAPPDATA%/RePDF/ocr/models`
  - macOS: `~/Library/Application Support/RePDF/ocr/models`
  - Linux: `$XDG_DATA_HOME/RePDF/ocr/models`, or `~/.local/share/RePDF/ocr/models` if unset.
- Models are never written to the installation or frozen extraction directory. Both source installations and packaged executables/Apps work offline after download.
- Recognition model SHA256: `6f327246b50388f3c176ae304bd95767ea6dc0c9ae92153ef8cbe210b3c14884`.
- Detection model SHA256: `090f04abcd9d9a7498bc4ebf677e4cb9bdce1fe4197ddb7e529f1ef44e1ff94f`.
- See [Packaging and releases](IMPLEMENTATION.en.md#15-packaging-and-releases) for desktop model collection, cloud builds, and packaged smoke tests.

## Validation

```sh
uv run python -m pytest
```

- Fallback triggers: normal text, dragging highlights, and empty selections do not trigger OCR; damaged characters do; failures preserve the original text.
- Recognition: offline inference with local models, image-only region recognition, and rectangles drawn in reverse directions.
- Interface integration: mode switching, fullscreen, backend messages, and the complete backend-to-clipboard flow.
- Synthetic PDFs are generated during tests. User PDFs are not added to the repository.
