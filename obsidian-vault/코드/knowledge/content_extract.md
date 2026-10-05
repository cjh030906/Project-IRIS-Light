# content_extract

`iris/knowledge/content_extract.py`

PDF·URL·텍스트 파일에서 위키 저장용 본문 추출.

## 주요 정의

- `class UnsupportedAttachmentTypeError`
- `class _HtmlTextExtractor`
- `def _truncate`
- `def _looks_like_url`
- `def _extract_pdf_text_pypdf`
- `def _resolve_tesseract_cmd`
- `def _iris_tessdata_dir`
- `def _system_tessdata_dir`
- `def _download_tessdata`
- `def _bootstrap_tessdata`
- `def _configure_tesseract`
- `def _ensure_tesseract`
- `def _extract_pdf_text_ocr`
- `def extract_pdf_text`
- `def fetch_firecrawl_text`
- `def fetch_url_text`
- `def _fetch_url_text_stdlib`
- `def extract_from_source`

## 내부 의존성

- [[api_quota]]
