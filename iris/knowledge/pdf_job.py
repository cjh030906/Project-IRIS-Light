"""PDF 도구가 넣을 본문과 저장 경로.

바이트는 pdf_export.save_pdf(자식 프로세스)만 만든다.
"""

from __future__ import annotations

from pathlib import Path

from iris.knowledge.wiki_places import is_sensitive

_MAX_FILES = 8
_MAX_CHARS = 200_000


def resolve_pdf_dest(raw: str, project_root: str = "") -> Path:
    """상대 경로는 열린 프로젝트. 비우면 프로젝트 또는 Documents/IRIS."""
    text = (raw or "").strip().strip('"').strip("'")
    root = Path(project_root).expanduser() if (project_root or "").strip() else None
    if text:
        dest = Path(text).expanduser()
        if not dest.is_absolute() and root is not None:
            dest = root / dest
        if dest.suffix.lower() != ".pdf":
            dest = dest.with_suffix(".pdf")
        return dest
    if root is not None and root.is_dir():
        return root / "iris-note.pdf"
    return Path.home() / "Documents" / "IRIS" / "iris-note.pdf"


def compose_pdf_text(content: str, sources: list[str], project_root: str = "") -> str:
    """content와 파일 본문을 한 PDF 문자열로. 비밀 형태 줄은 지운다."""
    parts: list[str] = []
    body = _redact(content or "").strip()
    if body:
        parts.append(body)
    root = Path(project_root).expanduser().resolve() if (project_root or "").strip() else None
    seen: set[str] = set()
    for raw in sources[:_MAX_FILES]:
        path = _source_path(str(raw or ""), root)
        if path is None:
            continue
        key = str(path).casefold()
        if key in seen:
            continue
        seen.add(key)
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        text = _redact(text)[:_MAX_CHARS].strip()
        if not text:
            continue
        parts.append(f"# {path.name}\n\n{text}")
    return "\n\n".join(parts).strip()


def source_list(args: dict) -> list[str]:
    raw = args.get("sources")
    if raw is None:
        raw = args.get("files")
    if isinstance(raw, str):
        items = [raw]
    elif isinstance(raw, list):
        items = [str(item) for item in raw]
    else:
        items = []
    one = str(args.get("source") or args.get("file") or "").strip()
    if one:
        items.append(one)
    return [item.strip() for item in items if str(item).strip()]


def _source_path(raw: str, root: Path | None) -> Path | None:
    text = raw.strip().strip('"').strip("'")
    if not text or "\x00" in text:
        return None
    path = Path(text).expanduser()
    if not path.is_absolute() and root is not None:
        path = root / path
    try:
        path = path.resolve()
    except OSError:
        return None
    if not path.is_file():
        return None
    if root is not None and root.is_dir() and path != root and root not in path.parents:
        if Path(text).expanduser().is_absolute():
            return path
        return None
    return path


def _redact(text: str) -> str:
    kept: list[str] = []
    for line in (text or "").splitlines():
        kept.append("[redacted]" if is_sensitive(line) else line)
    return "\n".join(kept)
