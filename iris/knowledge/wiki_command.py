"""사용자 문장 → 위키 명령.

raw/summarize 모드 스위치가 아니다. 동작과 제약(원문 유지, 문단 번역)을 읽어
execute_wiki_command 가 파일을 다룬다.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from iris.knowledge.wiki_save_intent import (
    extract_source_candidates,
    is_wiki_save_intent,
    parse_wiki_save_request,
)

_NOT_NOTE = ("코드", "함수", "버그", "에러", "error", "스크립트", "파일")
_SCREEN_OPEN = re.compile(
    r"^(위키|iris\s*wiki|옵시디언|obsidian)\s*(화면)?\s*"
    r"(켜|열어|열|보여|보여줘|실행|시작)(줘|라|요)?[.!?]*$",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class WikiCommand:
    op: str  # save | reprocess | open | delete | create | update | list
    source: str = ""
    rel_path: str = ""
    title: str = ""
    body: str = ""
    content: str = ""
    keep_original: bool = False
    summarize: bool = False
    translate: bool = False

    def needs_model(self) -> bool:
        if self.op == "reprocess":
            return True
        if self.op != "save":
            return False
        if self.keep_original and (self.summarize or self.translate):
            return True
        return self.summarize or self.translate


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip().lower())


def _wants_summary(text: str) -> bool:
    return any(w in text for w in ("요약", "정리", "핵심", "개요", "summarize", "summary"))


def _wants_translate(text: str) -> bool:
    return any(w in text for w in ("번역", "한국어", "문단", "translate", "paragraph"))


def _wants_replace_only(text: str) -> bool:
    return any(
        p in text
        for p in ("요약만", "원문은 빼", "원문 없이", "원문 삭제", "원문 빼고", "summary only")
    )


def _wants_keep(text: str) -> bool:
    if _wants_replace_only(text):
        return False
    return any(p in text for p in ("원문", "남기", "유지", "없애지", "지우지", "keep the original", "keep original"))


def _wants_delete(text: str) -> bool:
    if any(n in text for n in ("없애지", "지우지", "삭제하지")):
        return False
    return any(v in text for v in ("삭제", "지워", "없애", "delete"))


def _delete_context(text: str, target: str) -> bool:
    if any(w in text for w in ("위키", "노트", "문서", "wiki")):
        return True
    return bool(target) and any(w in text for w in ("이거", "그거", "방금", "이 노트", "그 노트"))


def _wants_list(text: str) -> bool:
    if "목록" not in text and "리스트" not in text and "list" not in text:
        return False
    return any(w in text for w in ("위키", "노트", "wiki"))


def _wants_open_note(text: str) -> bool:
    if _SCREEN_OPEN.fullmatch(text.strip()):
        return False
    if not any(v in text for v in ("열어", "보여", "open")):
        return False
    if any(w in text for w in ("노트", "정리된", "문서", "방금")):
        return True
    return "위키" in text and "정리" in text


def _wants_create(text: str) -> bool:
    if not any(v in text for v in ("만들", "생성", "작성", "create")):
        return False
    return any(p in text for p in ("새 노트", "노트 만들", "노트 생성", "새 위키", "위키 노트"))


def _quoted(text: str) -> str:
    match = re.search(r"[\"'「](.+?)[\"'」]", text or "")
    return match.group(1).strip() if match else ""


def _create_fields(text: str) -> tuple[str, str]:
    title = ""
    titled = re.search(
        r"제목(?:은|을|는)?\s*[:：]?\s*[\"'「](.+?)[\"'」]",
        text or "",
    )
    if titled:
        title = titled.group(1).strip()
    if not title:
        title = _quoted(text)
    body = ""
    bodied = re.search(r"내용\s*[:：]\s*(.+)", text or "", re.S)
    if bodied:
        body = bodied.group(1).strip()
    if not body:
        body = title or "새 노트"
    return title or "새 노트", body


def _update_title(text: str) -> str:
    match = re.search(
        r"제목(?:을|은|는)?\s*[\"'「](.+?)[\"'」]\s*(?:으로|로)",
        text or "",
    )
    if match:
        return match.group(1).strip()
    match = re.search(
        r"제목(?:을|은|는)?\s+(.+?)\s*(?:으로|로)\s*(?:바꿔|변경|수정|고쳐)",
        text or "",
    )
    return match.group(1).strip() if match else ""


def _update_body(text: str) -> str:
    match = re.search(r"본문(?:을|은)?\s*[:：]\s*(.+)", text or "", re.S)
    return match.group(1).strip() if match else ""


def _about_note(text: str) -> bool:
    if any(w in text for w in _NOT_NOTE):
        return False
    if any(w in text for w in ("원문", "문단", "번역", "덮어", "위키", "노트")):
        return _wants_keep(text) or _wants_summary(text) or _wants_translate(text)
    if len(text) <= 80 and (_wants_summary(text) or _wants_translate(text) or _wants_keep(text)):
        return True
    return False


def _save_flags(text: str) -> tuple[bool, bool, bool]:
    summarize = _wants_summary(text)
    translate = _wants_translate(text)
    replace = _wants_replace_only(text)
    keep = _wants_keep(text) or ((summarize or translate) and not replace)
    if replace:
        return False, True, translate
    return keep, summarize, translate


def parse_wiki_command(
    text: str,
    attachments: list[str] | tuple[str, ...] = (),
    history: list[dict[str, str]] | tuple[dict[str, str], ...] = (),
    target: str = "",
) -> WikiCommand | None:
    raw = text or ""
    folded = _norm(raw)
    if not folded:
        return None
    target = (target or "").replace("\\", "/").strip()
    sources = extract_source_candidates(raw, attachments)
    source = sources[0] if sources else ""

    if _wants_delete(folded) and _delete_context(folded, target):
        return WikiCommand(op="delete", rel_path=target, title=_quoted(raw))

    if _wants_list(folded):
        return WikiCommand(op="list")

    if _wants_open_note(folded):
        return WikiCommand(op="open", rel_path=target)

    if _wants_create(folded):
        title, body = _create_fields(raw)
        return WikiCommand(op="create", title=title, body=body)

    if source and is_wiki_save_intent(raw, attachments):
        keep, summarize, translate = _save_flags(folded)
        return WikiCommand(
            op="save",
            source=source,
            keep_original=keep,
            summarize=summarize,
            translate=translate,
        )

    if target and not source:
        new_title = _update_title(raw)
        new_body = _update_body(raw)
        retitle = any(v in folded for v in ("바꿔", "수정", "변경", "고쳐", "제목"))
        if retitle and (new_title or new_body) and not _about_note(folded):
            return WikiCommand(
                op="update",
                rel_path=target,
                title=new_title,
                body=new_body,
            )
        if _about_note(folded):
            keep, summarize, translate = _save_flags(folded)
            if not summarize and not translate:
                summarize = True
            return WikiCommand(
                op="reprocess",
                rel_path=target,
                keep_original=True,
                summarize=summarize or keep,
                translate=translate or _wants_translate(folded),
            )

    legacy = parse_wiki_save_request(raw, attachments, history)
    if legacy is not None and legacy.content:
        return WikiCommand(
            op="save",
            title=legacy.title or "",
            content=legacy.content,
        )
    return None


def _check() -> None:
    url = "https://example.com/agents 를 위키에 저장해줘"
    save = parse_wiki_command(url)
    assert save is not None and save.op == "save" and save.source.startswith("https://")
    assert not save.keep_original and not save.summarize and not save.needs_model()

    kept = parse_wiki_command("https://example.com/agents 문서 정리해서 위키에 저장")
    assert kept is not None and kept.op == "save" and kept.keep_original and kept.summarize
    assert not kept.translate

    only = parse_wiki_command("https://example.com/a 요약만 위키에 저장")
    assert only is not None and only.summarize and not only.keep_original

    target = "user/inbox/building-effective-ai-agents-anthropic.md"
    follow = parse_wiki_command(
        "원문은 남기고 위에 정리, 문단 아래 한국어",
        target=target,
    )
    assert follow is not None and follow.op == "reprocess" and follow.rel_path == target
    assert follow.keep_original and follow.translate

    # 「저장한」은 출처가 없으면 저장 명령이 아니다.
    said = parse_wiki_command("저장한 원문은 남기고 정리해줘", target=target)
    assert said is not None and said.op == "reprocess"

    opened = parse_wiki_command("정리된 위키를 열어", target=target)
    assert opened is not None and opened.op == "open"
    assert parse_wiki_command("위키 화면 열어") is None
    assert parse_wiki_command("위키 열어") is None

    assert parse_wiki_command("이 함수 정리해줘", target=target) is None
    assert parse_wiki_command("오늘 날씨 알려줘", target=target) is None

    deleted = parse_wiki_command("이 노트 삭제해줘", target=target)
    assert deleted is not None and deleted.op == "delete"
    assert parse_wiki_command("원문은 없애지 말고 정리해줘", target=target).op == "reprocess"

    created = parse_wiki_command('새 노트 만들어. 제목은 "실험" 내용: 본문이다')
    assert created is not None and created.op == "create" and created.title == "실험"
    assert "본문이다" in created.body

    updated = parse_wiki_command('제목을 "에이전트"로 바꿔', target=target)
    assert updated is not None and updated.op == "update" and updated.title == "에이전트"

    listed = parse_wiki_command("위키 노트 목록 보여줘")
    assert listed is not None and listed.op == "list"
    print("wiki_command ok")


if __name__ == "__main__":
    _check()
