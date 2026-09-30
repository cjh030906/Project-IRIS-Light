"""위키와 콘텐츠 가져오기 컨트롤 액션."""

from __future__ import annotations

from typing import Any, Callable
from urllib.request import Request, urlopen

from iris.system.control_surface import (
    ActionRegistry,
)
from iris.ui.control_actions.hosts import WikiHost

_PAGE_CAP = 80


def _page_limit(raw: object) -> int:
    try:
        n = int(raw)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return _PAGE_CAP
    if n < 1:
        return _PAGE_CAP
    return min(n, _PAGE_CAP)


def _truthy(raw: object) -> bool:
    if isinstance(raw, bool):
        return raw
    return str(raw or "").strip().lower() in {"1", "true", "yes", "on"}


def _dedupe_sources(items: list[str]) -> list[str]:
    from urllib.parse import urldefrag

    out: list[str] = []
    seen: set[str] = set()
    for item in items:
        text = item.strip()
        if not text:
            continue
        key = text
        if text.lower().startswith(("http://", "https://")):
            key = urldefrag(text)[0]
        if key in seen:
            continue
        seen.add(key)
        out.append(key)
    return out


def _page_sources(args: dict[str, Any]) -> list[str]:
    raw = args.get("sources")
    items: list[str] = []
    if isinstance(raw, (list, tuple)):
        items = [str(x).strip() for x in raw if str(x).strip()]
    elif isinstance(raw, str) and raw.strip():
        items = [raw.strip()]
    if items:
        return _dedupe_sources(items)
    one = str(args.get("source") or args.get("path") or args.get("url") or "").strip()
    return [one] if one else []


def _fetch_html(url: str) -> tuple[str, str]:
    req = Request(url, headers={"User-Agent": "Iris-Wiki/1.0 (+local content import)"})
    with urlopen(req, timeout=20) as resp:
        final = resp.geturl()
        raw = resp.read(2_000_000)
        ctype = (resp.headers.get("Content-Type") or "").lower()
    charset = "utf-8"
    marker = "charset="
    if marker in ctype:
        charset = ctype.split(marker, 1)[1].split(";", 1)[0].strip(" \"'")
    return final, raw.decode(charset, errors="replace")


def _merge_discovered(
    sources: list[str],
    args: dict[str, Any],
    limit: int,
    fetch_html: Callable[[str], tuple[str, str]],
) -> tuple[list[str], bool]:
    from iris.knowledge.wiki_import_ops import collect_same_origin_links

    merged = list(sources)
    if _truthy(args.get("discover")):
        root = next(
            (item for item in sources if item.lower().startswith(("http://", "https://"))),
            "",
        )
        if root:
            try:
                final, html = fetch_html(root)
            except (OSError, TimeoutError, ValueError):
                final, html = "", ""
            if html:
                extra = collect_same_origin_links(final or root, html, limit=limit)
                merged = _dedupe_sources([*sources, *extra])
    return merged[:limit], len(merged) > limit

def register_wiki_actions(window: WikiHost, reg: ActionRegistry) -> None:
    from iris.ui.control_bindings import (
        Path,
        _log,
        err_result,
        ok_result,
    )

    def wiki_list(_a: dict[str, Any]) -> dict[str, Any]:
        notes = [
            {"rel_path": n.rel_path, "title": n.title, "folder": n.folder, "source": n.source}
            for n in window._iris_wiki.list_notes()
        ]
        return ok_result("wiki.list_notes", {"notes": notes, "count": len(notes)})

    def wiki_open(args: dict[str, Any]) -> dict[str, Any]:
        rel = str(args.get("rel_path") or args.get("path") or "").strip()
        if not rel:
            return err_result("wiki.open_note", "rel_path required")
        window._on_obsidian_icon()
        window._obsidian_page.show_note(rel)
        window._left_sidebar.obsidian_detail.reload()
        _log(window, "wiki.open_note", True)
        return ok_result("wiki.open_note", {"rel_path": rel})

    def wiki_reload(_a: dict[str, Any]) -> dict[str, Any]:
        if window._workspace_mode != "obsidian":
            window._on_obsidian_icon()
        else:
            window._left_sidebar.obsidian_detail.reload()
            window._obsidian_page.reload_graph()
        _log(window, "wiki.reload", True)
        return ok_result("wiki.reload", {})

    def wiki_write(args: dict[str, Any]) -> dict[str, Any]:
        title = str(args.get("title") or "").strip()
        content = str(args.get("content") or args.get("body") or "").strip()
        source_url = str(args.get("source_url") or args.get("url") or "").strip()
        rel_in = str(args.get("rel_path") or args.get("path") or "").strip() or None
        open_note = bool(args.get("open", True))
        if not title and rel_in:
            stem = Path(rel_in.replace("\\", "/")).stem
            title = stem or "untitled"
        if not title:
            return err_result("wiki.write_user_note", "title required")
        if not content:
            return err_result("wiki.write_user_note", "content required")
        try:
            path, rel = window._iris_wiki.write_inbox_note(
                title,
                content,
                source_url=source_url,
                rel_path=rel_in,
            )
        except ValueError as exc:
            return err_result("wiki.write_user_note", str(exc))
        except OSError as exc:
            return err_result("wiki.write_user_note", str(exc))
        wiki_rel = f"user/{rel}"
        window._on_obsidian_icon()
        window._obsidian_page.reload_graph()
        window._left_sidebar.obsidian_detail.reload()
        if open_note:
            window._obsidian_page.show_note(wiki_rel)
        _log(window, "wiki.write_user_note", True)
        return ok_result(
            "wiki.write_user_note",
            {
                "rel_path": wiki_rel,
                "path": str(path),
                "title": title,
                "opened": open_note,
            },
        )

    def content_extract(args: dict[str, Any]) -> dict[str, Any]:
        from iris.knowledge.content_extract import (
            UnsupportedAttachmentTypeError,
            extract_from_source,
        )

        source = str(args.get("source") or args.get("path") or args.get("url") or "").strip()
        if not source:
            return err_result("content.extract", "source required (file path or http(s) URL)")
        try:
            data = extract_from_source(source)
        except UnsupportedAttachmentTypeError as exc:
            return err_result(
                "content.extract",
                str(exc),
                {
                    "error_code": exc.code,
                    "help_url": "https://iris-light-site.vercel.app/#install",
                    "scope": "attachment_extract",
                },
            )
        except (ValueError, OSError, RuntimeError) as exc:
            return err_result("content.extract", str(exc))
        _log(window, "content.extract", True)
        return ok_result(
            "content.extract",
            {
                "kind": data["kind"],
                "title": data["title"],
                "text": data["text"],
                "source": data["source"],
                "truncated": data["truncated"],
                "chars": len(str(data["text"])),
            },
        )

    def wiki_import_content(args: dict[str, Any]) -> dict[str, Any]:
        from iris.knowledge.content_extract import UnsupportedAttachmentTypeError
        from iris.knowledge.wiki_import_ops import import_to_wiki
        from iris.knowledge.wiki_summarize import summarize_for_wiki

        source = str(args.get("source") or args.get("path") or args.get("url") or "").strip()
        title_in = str(args.get("title") or "").strip() or None
        rel_in = str(args.get("rel_path") or "").strip() or None
        open_note = bool(args.get("open", True))
        mode = str(args.get("mode") or "raw").strip().lower()
        if mode not in ("raw", "summarize"):
            mode = "raw"
        if not source:
            return err_result("wiki.import_content", "source required (file path or http(s) URL)")
        summarize_fn = None
        if mode == "summarize":
            model = str(
                args.get("model")
                or window._chat.current_model()
                or getattr(window, "_saved_model", "")
                or window._settings.ollama_model
                or ""
            ).strip()
            if not model:
                return err_result("wiki.import_content", "model required for summarize mode")
            base = (window._settings.ollama_base_url or "http://127.0.0.1:11434/v1").strip()

            def _sum(text: str) -> str:
                return summarize_for_wiki(text, model=model, ollama_base_url=base)

            summarize_fn = _sum
        try:
            result = import_to_wiki(
                window._iris_wiki,
                source=source,
                title=title_in,
                mode=mode,
                rel_path=rel_in,
                summarize_fn=summarize_fn,
            )
        except UnsupportedAttachmentTypeError as exc:
            return err_result(
                "wiki.import_content",
                str(exc),
                {
                    "error_code": exc.code,
                    "help_url": "https://iris-light-site.vercel.app/#install",
                    "scope": "attachment_extract",
                },
            )
        except (ValueError, OSError, RuntimeError) as exc:
            return err_result("wiki.import_content", str(exc))
        wiki_rel = str(result["rel_path"])
        window._on_obsidian_icon()
        window._obsidian_page.reload_graph()
        window._left_sidebar.obsidian_detail.reload()
        if open_note:
            window._obsidian_page.show_note(wiki_rel)
        _log(window, "wiki.import_content", True)
        result = {**result, "opened": open_note}
        return ok_result("wiki.import_content", result)

    def wiki_import_pages(args: dict[str, Any]) -> dict[str, Any]:
        from iris.knowledge.wiki_import_ops import import_pages
        from iris.knowledge.wiki_summarize import summarize_for_wiki

        sources = _page_sources(args)
        if not sources:
            return err_result("wiki.import_pages", "sources or source required")
        mode = str(args.get("mode") or "raw").strip().lower()
        if mode not in ("raw", "summarize"):
            mode = "raw"
        summarize_fn = None
        if mode == "summarize":
            model = str(
                args.get("model")
                or window._chat.current_model()
                or getattr(window, "_saved_model", "")
                or window._settings.ollama_model
                or ""
            ).strip()
            if not model:
                return err_result("wiki.import_pages", "model required for summarize mode")
            base = (window._settings.ollama_base_url or "http://127.0.0.1:11434/v1").strip()

            def _sum(text: str) -> str:
                return summarize_for_wiki(text, model=model, ollama_base_url=base)

            summarize_fn = _sum
        limit = _page_limit(args.get("limit"))
        merged, truncated = _merge_discovered(sources, args, limit, _fetch_html)
        data = import_pages(
            window._iris_wiki,
            merged,
            mode=mode,
            summarize_fn=summarize_fn,
        )
        data["truncated"] = truncated
        last = next(
            (str(item["rel_path"]) for item in reversed(data["items"]) if item.get("ok")),
            "",
        )
        if data["saved"] and last:
            window._on_obsidian_icon()
            window._obsidian_page.show_note(last)
        _log(
            window,
            f"wiki.import_pages saved={data['saved']} failed={data['failed']}",
            True,
        )
        return ok_result("wiki.import_pages", data)

    reg.register("wiki.list_notes", wiki_list, summary="List Iris Wiki note paths")

    reg.register(
        "wiki.open_note",
        wiki_open,
        summary="Open Iris Wiki workspace and show note by rel_path",
    )

    reg.register("wiki.reload", wiki_reload, summary="Reload Iris Wiki graph/detail")

    reg.register(
        "wiki.write_user_note",
        wiki_write,
        summary="Save markdown to Iris Wiki user/ (default inbox/{slug}.md) and show it",
        risk="medium",
    )

    reg.register(
        "content.extract",
        content_extract,
        summary="Extract text from PDF, text file, or http(s) URL",
        risk="low",
    )

    reg.register(
        "wiki.import_content",
        wiki_import_content,
        summary="Extract PDF/URL/file text and save to Iris Wiki inbox, then open in UI (mode=raw|summarize)",
        risk="medium",
    )

    reg.register(
        "wiki.import_pages",
        wiki_import_pages,
        summary="Save many pages to Iris Wiki in one call (sources or source, discover=true, limit<=80). Do not loop import_content per page.",
        risk="medium",
    )
