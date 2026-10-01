"""위키 import 공통 로직 (로컬·control surface)."""

from __future__ import annotations

from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urldefrag, urljoin, urlparse

from iris.knowledge.content_extract import extract_from_source
from iris.knowledge.iris_wiki import IrisWiki, slugify_note_name

_DOC_EXT = {"html", "htm"}
_SKIP_EXT = {
    "png",
    "jpg",
    "jpeg",
    "gif",
    "webp",
    "svg",
    "ico",
    "bmp",
    "avif",
    "pdf",
    "zip",
    "gz",
    "rar",
    "7z",
}


def _slug_base(title: str) -> str:
    """파일명이면 확장자를 뺀 stem으로 슬러그. 화면 제목(H1)은 원문을 유지한다."""
    name = Path(str(title).replace("\\", "/")).name
    if Path(name).suffix:
        name = Path(name).stem or name
    return slugify_note_name(name or title)


def _unique_inbox_rel(wiki: IrisWiki, title: str) -> str:
    base = _slug_base(title)
    rel = f"inbox/{base}.md"
    path = wiki.user_root / rel
    if not path.is_file():
        return rel
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    candidate = f"inbox/{base}-{stamp}.md"
    counter = 2
    while (wiki.user_root / candidate).exists():
        candidate = f"inbox/{base}-{stamp}-{counter}.md"
        counter += 1
    return candidate


def wiki_location_label(rel_path: str, title: str, *, project: str = "") -> str:
    """Wiki > 폴더 > 문서. inbox만 있으면 열린 프로젝트 이름을 쓴다."""
    rel = (rel_path or "").replace("\\", "/").strip("/")
    for prefix in ("user/", "docs/"):
        if rel.startswith(prefix):
            rel = rel[len(prefix):]
    parent = Path(rel).parent.as_posix() if rel else ""
    folders = [part for part in parent.split("/") if part and part != "."]
    if folders == ["inbox"] and (project or "").strip():
        folders = [(project or "").strip()]
    name = (title or "").strip() or (Path(rel).stem if rel else "") or "문서"
    return " > ".join(["Wiki", *folders, name])


def wiki_save_notice(result: dict[str, Any], *, project: str = "", href: str = "") -> str:
    """저장 직후 채팅 문장. href가 있으면 경로를 마크다운 링크로 둔다."""
    rel = str(result.get("rel_path") or "").replace("\\", "/")
    title = str(result.get("title") or "").strip()
    label = wiki_location_label(rel, title, project=project).replace("]", " ")
    where = f"[{label}]({href})" if href else label
    trunc = " (본문 일부 잘림)" if result.get("truncated") else ""
    return f"저장되었습니다{trunc}.\n저장 위치: {where}"


def save_answer_to_wiki(wiki: IrisWiki, *, title: str, content: str) -> dict[str, Any]:
    """Preserve an existing answer, including its Markdown source citations."""
    if not content.strip():
        raise ValueError("content required")
    path, rel = wiki.write_inbox_note(
        title, content, rel_path=_unique_inbox_rel(wiki, title),
    )
    return {
        "rel_path": f"user/{rel}", "path": str(path), "title": title,
        "kind": "answer", "mode": "raw", "truncated": False,
        "chars": len(content),
    }


def prepare_wiki_body(
    source: str,
    *,
    mode: str = "raw",
    summarize_fn: Callable[[str], str] | None = None,
) -> dict[str, Any]:
    data = extract_from_source(source)
    body = str(data["text"]).strip()
    if not body:
        raise ValueError("no content extracted")
    if mode == "summarize":
        if summarize_fn is None:
            raise ValueError("summarize_fn required for summarize mode")
        body = summarize_fn(body).strip() or body
    title = str(data["title"])
    source_url = source if str(data["kind"]) == "url" else str(data["source"])
    return {
        "title": title,
        "body": body,
        "source_url": source_url,
        "kind": data["kind"],
        "source": data["source"],
        "truncated": bool(data["truncated"]),
    }


def import_to_wiki(
    wiki: IrisWiki,
    *,
    source: str,
    title: str | None = None,
    mode: str = "raw",
    rel_path: str | None = None,
    open_note: bool = True,
    summarize_fn: Callable[[str], str] | None = None,
) -> dict[str, Any]:
    prepared = prepare_wiki_body(source, mode=mode, summarize_fn=summarize_fn)
    note_title = (title or prepared["title"] or "untitled").strip()
    rel_in = rel_path
    if not rel_in:
        rel_in = _unique_inbox_rel(wiki, note_title)
    path, rel = wiki.write_inbox_note(
        note_title,
        prepared["body"],
        source_url=prepared["source_url"],
        rel_path=rel_in,
    )
    wiki_rel = f"user/{rel}"
    return {
        "rel_path": wiki_rel,
        "path": str(path),
        "title": note_title,
        "kind": prepared["kind"],
        "source": prepared["source"],
        "truncated": prepared["truncated"],
        "chars": len(prepared["body"]),
        "mode": mode,
        "opened": open_note,
    }


class _HrefParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.hrefs: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() != "a":
            return
        for key, value in attrs:
            if key.lower() == "href" and value and value.strip():
                self.hrefs.append(value.strip())


def collect_same_origin_links(page_url: str, html: str, *, limit: int) -> list[str]:
    """page_url 과 같은 호스트의 문서 링크를 한 단계만 모은다. 네트워크 없음."""
    cap = max(0, int(limit))
    if cap == 0 or not (page_url or "").strip():
        return []
    base = urldefrag(page_url.strip())[0]
    host = (urlparse(base).hostname or "").casefold()
    if not host:
        return []
    parser = _HrefParser()
    parser.feed(html or "")
    found: list[str] = []
    seen: set[str] = set()
    for href in parser.hrefs:
        low = href.lower()
        if low.startswith(("javascript:", "mailto:", "data:", "tel:")):
            continue
        absolute = urldefrag(urljoin(base, href))[0]
        parsed = urlparse(absolute)
        if parsed.scheme not in ("http", "https"):
            continue
        if (parsed.hostname or "").casefold() != host:
            continue
        if absolute == base or not _is_document_path(parsed.path):
            continue
        if absolute in seen:
            continue
        seen.add(absolute)
        found.append(absolute)
        if len(found) >= cap:
            break
    return found


def _is_document_path(path: str) -> bool:
    name = (path or "").rsplit("/", 1)[-1]
    if not name or "." not in name:
        return True
    ext = name.rsplit(".", 1)[-1].casefold()
    if ext in _SKIP_EXT:
        return False
    return ext in _DOC_EXT


def import_pages(
    wiki: IrisWiki,
    sources: list[str],
    *,
    mode: str = "raw",
    summarize_fn: Callable[[str], str] | None = None,
) -> dict[str, Any]:
    """소스마다 import_to_wiki 한 번. 한 건 실패가 다음 건을 막지 않는다."""
    items: list[dict[str, Any]] = []
    saved = 0
    failed = 0
    for source in sources:
        try:
            result = import_to_wiki(
                wiki,
                source=source,
                mode=mode,
                open_note=False,
                summarize_fn=summarize_fn,
            )
        except Exception as exc:  # noqa: BLE001 — 한 건 실패 후 계속
            failed += 1
            items.append({"source": source, "ok": False, "error": str(exc)[:200]})
            continue
        saved += 1
        items.append({"source": source, "ok": True, "rel_path": result["rel_path"]})
    return {"saved": saved, "failed": failed, "items": items}


def _check() -> None:
    import tempfile

    page = "https://example.com/start"
    html = """
    <a href="/one.html">1</a>
    <a href="/two">2</a>
    <a href="https://other.test/three.html">3</a>
    <a href="/x.png">p</a>
    <a href="/one.html#section">dup</a>
    <a href="mailto:a@b.c">m</a>
    <a href="javascript:alert(1)">j</a>
    <a href="/four.pdf">pdf</a>
    <a href="/five.html">5</a>
    """
    links = collect_same_origin_links(page, html, limit=80)
    assert links == [
        "https://example.com/one.html",
        "https://example.com/two",
        "https://example.com/five.html",
    ], links
    assert all("other.test" not in url for url in links)
    assert all(not url.endswith(".png") for url in links)
    assert collect_same_origin_links(page, html, limit=1) == [
        "https://example.com/one.html"
    ]

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        files = []
        for name in ("a.txt", "b.txt"):
            path = root / name
            path.write_text(f"body {name}", encoding="utf-8")
            files.append(str(path))
        wiki = IrisWiki(docs_root=root / "docs", user_root=root / "user")
        result = import_pages(wiki, files)
        assert result["saved"] == 2, result
        assert result["failed"] == 0
        assert all(item["ok"] and item["rel_path"] for item in result["items"])
    print("wiki_import_ops ok")


if __name__ == "__main__":
    _check()
