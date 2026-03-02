# Extraction Module

PDF text extraction, chunking, and structured fact extraction for course equivalency evaluation.

## Dependencies

### Python Packages

```bash
pip install pdfplumber pytesseract pdf2image python-dotenv sqlalchemy
```

| Package | Purpose |
|---------|---------|
| `pdfplumber` | Primary PDF text extraction (embedded text) |
| `pytesseract` | OCR engine Python bindings |
| `pdf2image` | Convert PDF pages to images for OCR |
| `python-dotenv` | Load environment variables from `.env` |
| `sqlalchemy` | Database ORM for storing extraction results |

### System Dependencies

#### Tesseract OCR
Required for OCR fallback on image-only/scanned PDFs.

**Windows:**
```bash
# Install via chocolatey
choco install tesseract

# Or download installer from:
# https://github.com/UB-Mannheim/tesseract/wiki
```

**macOS:**
```bash
brew install tesseract
```

**Linux:**
```bash
sudo apt-get install tesseract-ocr
```

#### Poppler
Required by `pdf2image` to convert PDFs to images.

**Windows:**
```bash
# Install via chocolatey
choco install poppler

# Or download from:
# https://github.com/osborn/poppler/releases
# Extract to C:\tools\poppler\ and add bin folder to PATH
```

Set the `POPPLER_PATH` environment variable if not in system PATH:
```bash
export POPPLER_PATH="C:\tools\poppler\poppler-25.12.0\Library\bin"
```

**macOS:**
```bash
brew install poppler
```

**Linux:**
```bash
sudo apt-get install poppler-utils
```

## Module Structure

```
app/extraction/
├── __main__.py        # CLI entrypoint (run/validate commands)
├── pipeline.py        # Orchestrates extraction, writes to DB
├── pdf_text.py        # PDF text extraction + OCR fallback
├── chunking.py        # Text chunking for citations
├── syllabus_parser.py # Extract facts from syllabus PDFs
├── catalog_parser.py  # Extract course candidates from catalog PDFs
└── README.md          # This file
```

## Usage

### CLI Commands

```bash
# Run extraction for a request
python -m app.extraction run <request_id>

# Validate extraction outputs
python -m app.extraction validate <request_id>
```

### Programmatic Usage

```python
from app.extraction.pipeline import run_extraction

# Run extraction (requires DATABASE_URL env var)
run_id = run_extraction(request_id="your-request-uuid")
```

### Direct PDF Text Extraction

```python
from app.extraction.pdf_text import ensure_searchable_text

pages_text, used_ocr, ocr_output, warning = ensure_searchable_text(
    pdf_path="path/to/file.pdf",
    output_dir="output/",
    prefer_ocr=True
)
```

## Supported Course Code Formats

The catalog parser recognizes:

| Format | Example | Pattern |
|--------|---------|---------|
| Traditional | `MED 2150`, `BIOL 0420` | `[A-Z]{2,6} \d{3,4}` |
| MIT dot notation | `10.213`, `5.12`, `18.03` | `\d{1,2}\.\d{2,4}` |

## Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `DATABASE_URL` | PostgreSQL connection string | Required |
| `POPPLER_PATH` | Path to Poppler bin directory | `C:\tools\poppler\poppler-25.12.0\Library\bin` |

## OCR Fallback Chain

1. **pdfplumber** - Extracts embedded text (fast, no dependencies)
2. **ocrmypdf** - Creates searchable PDF via Tesseract (if installed)
3. **pytesseract + pdf2image** - Direct OCR to text (fallback)

If all OCR methods fail, extraction continues with a warning.
