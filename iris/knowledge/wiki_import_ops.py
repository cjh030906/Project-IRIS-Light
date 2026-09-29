"""위키 import 공통 로직 (로컬·control surface)."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from iris.knowledge.content_extract import extract_from_source
from iris.knowledge.iris_wiki import IrisWiki, slugify_note_name


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
