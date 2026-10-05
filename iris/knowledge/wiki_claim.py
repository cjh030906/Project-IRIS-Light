"""위키 완료 문장은 이번 턴의 쓰기·열기가 있을 때만 보여 준다."""

from __future__ import annotations

import re

UNCHANGED = "노트는 그대로다"
NOT_OPENED = "노트를 열지 못했다."
ORIGINALS_LEFT = "새 요약 파일을 만들었고 inbox 원본은 그대로다"

_WRITE_CLAIM = re.compile(r"저장했|정리했|덮어|번역해\s*두|번역했|삭제했|변경했")
_OPEN_CLAIM = re.compile(r"열었|열어\s*드")
_MOVE_CLAIM = re.compile(r"옮겼|이동\s*완료|분류했|분류해\s*저장|inbox에서")


def relocate_goal(goal: str) -> bool:
    """이미 있는 노트를 폴더로 보내라는 목표. 새 글 저장과는 구분한다."""
    text = goal or ""
    folded = text.lower()
    place = any(word in text for word in ("학습자료", "폴더", "위키", "노트")) or "inbox" in folded
    if any(word in text for word in ("옮", "이동", "분류")) and place:
        return True
    return "학습자료" in text and "폴더" in text and "저장" in text


def wiki_work_goal(goal: str) -> bool:
    if relocate_goal(goal):
        return True
    text = goal or ""
    folded = text.lower()
    if any(word in text for word in ("원문", "문단", "번역", "덮어")):
        return True
    wiki = any(word in text for word in ("위키", "노트", "문서")) or "wiki" in folded or "가져오" in text
    work = any(word in text for word in ("저장", "가져오", "정리", "번역", "요약", "열", "삭제", "만들", "바꿔", "변경"))
    return wiki and work


def settle_wiki_claim(
    text: str,
    *,
    goal: str = "",
    wrote: bool = False,
    opened: bool = False,
    changed: bool | None = None,
    moved: bool = False,
) -> str:
    """거짓 완료는 경로 문장으로 바꾸지 않고, 파일이 그대로라는 한 줄만 남긴다."""
    raw = text or ""
    if not raw.strip() or not wiki_work_goal(goal):
        return raw
    if relocate_goal(goal) and _MOVE_CLAIM.search(raw) and not moved:
        return ORIGINALS_LEFT if wrote else UNCHANGED
    write_ok = bool(wrote) and changed is not False
    if _WRITE_CLAIM.search(raw) and not write_ok:
        return UNCHANGED
    if _OPEN_CLAIM.search(raw) and not opened:
        return NOT_OPENED
    return raw


def _check() -> None:
    goal = "원문은 남기고 위에 정리, 문단 아래 한국어"
    assert settle_wiki_claim("정리했습니다.", goal=goal, wrote=False) == UNCHANGED
    assert settle_wiki_claim("정리했습니다.", goal=goal, wrote=True, changed=False) == UNCHANGED
    assert "정리" in settle_wiki_claim(
        "정리했습니다. user/inbox/a.md",
        goal=goal,
        wrote=True,
        changed=True,
    )
    assert settle_wiki_claim("열어 드리겠습니다.", goal="정리된 위키를 열어", opened=False) == NOT_OPENED
    assert "열었" in settle_wiki_claim("열었습니다.", goal="정리된 위키를 열어", opened=True)
    # 코드 작성 목표는 위키 게이트가 건드리지 않는다.
    assert settle_wiki_claim("작성했습니다.", goal="스크립트 작성해줘") == "작성했습니다."
    assert not wiki_work_goal("오늘 날씨 알려줘")
    arrange = "학습자료 폴더를 만들어 강화학습으로 분류해서 저장"
    assert relocate_goal(arrange)
    assert settle_wiki_claim("분류해 저장했습니다.", goal=arrange, wrote=True, moved=False) == ORIGINALS_LEFT
    assert settle_wiki_claim("inbox에서 이동 완료", goal=arrange, wrote=False, moved=False) == UNCHANGED
    assert "옮겼" in settle_wiki_claim("옮겼습니다.", goal=arrange, wrote=True, moved=True)
    assert not relocate_goal("위키에 저장")
    print("wiki_claim ok")


if __name__ == "__main__":
    _check()
