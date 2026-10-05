"""채팅 답의 근거 게이트. 오늘 사실·저장 자료·실행 보고만 묶는다.

문장 전체를 대조하지 않는다. 한글 고유명(조사 포함)은 못 본다.
ponytail: 숫자·영문 대문자 토큰·따옴표 안만. 한글 이름은 NER이 다음 단계.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

_TODAY = re.compile(
    r"뉴스|날씨|기온|미세먼지|환율|주가|시세|코스피|코스닥|비트코인|경기\s*결과|스코어|속보"
)
_NOT_TODAY = re.compile(r"계산|코드|의견|소설|번역|설계")
_STORED = re.compile(r"위키|노트|inbox|첨부|저장(?:해\s*둔|된\s*자료|한\s*자료)")
_SAVE_ACT = re.compile(r"저장해|넣어\s*줘|기록해|옮겨|삭제해|보내\s*줘|실행해|만들어")
_CODE_WORK = re.compile(r"고쳐|구현|코드|리팩터|짜\s*줘|작성")
_IRIS_NAME = re.compile(r"아이리스|iris", re.IGNORECASE)
_IRIS_HOW = re.compile(r"어떻게\s*(?:짜|되|고치|바꾸)")
_IRIS_TOPIC = re.compile(r"구조|커스텀|타일|화면|비율|노트|위키")
_CODE_REQUEST = re.compile(r"짜\s*줘|작성해|구현해|만들어\s*줘|고쳐\s*줘")
_ACTION_CLAIM = re.compile(
    r"(?:저장|검색|전송|실행|처리|작업|완료).{0,6}(?:했|완료)|보냈|처리\s*완료|작업\s*완료"
)
_NUM = re.compile(r"\d+(?:[.,]\d+)*")
_LATIN = re.compile(r"\b[A-Z][A-Za-z0-9]{1,}\b")
_QUOTED = re.compile(r"[「『\"']([^」』\"']{2,30})[」』\"']")
_SPLIT = re.compile(r"\n+|(?<=[.!?。])\s+")
_URL = re.compile(r"https?://[^\s<>\]\"')]+")
_MARKERS = ("[자료 본문]", "BEGIN ATTACHMENT TEXT")
_FAIL_EXTRA = 80

_COUNTS = {"search_fail_long": 0, "claim_without_ok": 0, "unknown_url": 0}


def counts() -> dict[str, int]:
    return dict(_COUNTS)


def reset_counts() -> None:
    for key in _COUNTS:
        _COUNTS[key] = 0


def _bump(key: str, n: int = 1) -> None:
    _COUNTS[key] = _COUNTS.get(key, 0) + n


def classify_turn(text: str) -> str:
    raw = text or ""
    if _TODAY.search(raw) and not _NOT_TODAY.search(raw):
        return "today"
    if _STORED.search(raw) and not _SAVE_ACT.search(raw):
        return "stored"
    if _SAVE_ACT.search(raw):
        return "action"
    return "other"


def turn_has_grounding_material(text: str, history: list | None, attachments: list | None) -> bool:
    """첨부가 있는데 글·코드 작업이 아니면 저장 자료 질문으로 본다."""
    if _CODE_WORK.search(text or ""):
        return False
    if attachments:
        return True
    return bool(material_from_history(history).strip())


def wants_wiki_lookup(text: str) -> bool:
    raw = text or ""
    if _SAVE_ACT.search(raw):
        return False
    return bool(re.search(r"위키|노트|inbox|저장(?:해\s*둔|된|한)", raw))


def wants_iris_structure(text: str) -> bool:
    """아이리스 구조·커스텀을 묻는 말. 코드 작성·저장·오늘 사실은 아니다."""
    raw = text or ""
    if _SAVE_ACT.search(raw) or _CODE_REQUEST.search(raw) or _TODAY.search(raw):
        return False
    if _IRIS_HOW.search(raw):
        return True
    if re.search(r"타일\s*비율", raw):
        return True
    return bool(_IRIS_NAME.search(raw) and _IRIS_TOPIC.search(raw))


def search_failure_reply(error: str, query: str) -> str:
    return (
        f"검색을 하지 못했습니다 — {error or '알 수 없음'}\n"
        f"(검색어: {query or '(없음)'})"
    )


def search_timeout_reply(query: str) -> str:
    return search_failure_reply("검색 시간 초과", query)


def long_after_search_fail(answer: str, failure: str) -> bool:
    extra = (answer or "").replace(failure or "", "").strip()
    return len(extra) > _FAIL_EXTRA


@dataclass(frozen=True)
class TodaySearch:
    ok: bool
    evidence: str
    reply: str
    urls: list[str]


def today_search(query: str) -> TodaySearch:
    from iris.runtime.routine_search import format_evidence, run_search

    text = " ".join((query or "").split())[:180]
    engine = "google_news" if any(word in text for word in ("뉴스", "속보")) else "google"
    outcome = run_search(text, engine=engine)
    if not outcome.ok:
        return TodaySearch(False, "", search_failure_reply(outcome.error, outcome.query or text), [])
    urls = [hit.link for hit in outcome.hits if hit.link]
    return TodaySearch(True, format_evidence(outcome), "", urls)


def evidence_corpus(*, web: str = "", wiki: str = "", material: str = "", code: str = "") -> str:
    return "\n".join(part for part in (web, wiki, material, code) if (part or "").strip())


def material_from_history(history: list | None) -> str:
    last = ""
    for item in reversed(history or []):
        if not isinstance(item, dict) or item.get("role") != "user":
            continue
        last = "\n".join(
            str(item.get(key) or "") for key in ("model_content", "content") if item.get(key)
        )
        break
    chunks: list[str] = []
    for marker in _MARKERS:
        if marker in last:
            chunks.append(last.split(marker, 1)[1])
    return "\n".join(chunks)


def _tokens(text: str) -> set[str]:
    found = set(_NUM.findall(text or ""))
    found.update(_LATIN.findall(text or ""))
    found.update(piece.strip() for piece in _QUOTED.findall(text or "") if piece.strip())
    return found


def constrain_to_evidence(answer: str, evidence: str, *, missing: str) -> str:
    allowed = _tokens(evidence)
    folded = (evidence or "").casefold()
    kept: list[str] = []
    dropped = False
    for piece in _SPLIT.split(answer or ""):
        sentence = piece.strip()
        if not sentence:
            continue
        bad = False
        for token in _tokens(sentence):
            if token in allowed or token.casefold() in folded:
                continue
            bad = True
            break
        if bad:
            dropped = True
            continue
        kept.append(sentence)
    if not dropped:
        return answer
    if not kept:
        return missing
    return "\n".join(kept) + "\n" + missing


def tool_result_line(tool_lines: list[str]) -> str:
    names: list[str] = []
    for raw in tool_lines or []:
        parts = (raw or "").strip().split()
        if not parts or "." not in parts[0]:
            continue
        if parts[0] not in names:
            names.append(parts[0])
    shown = ", ".join(names) if names else "없음"
    return f"이번 턴 도구 결과: {shown} · ok 없음"


_ACTION_NO_SEARCH = re.compile(
    r"(?:저장|전송|실행|처리|작업|완료).{0,6}(?:했|완료)|보냈|처리\s*완료|작업\s*완료"
)


def rewrite_unbacked_claims(text: str, tool_lines: list[str], *, search_backed: bool = False) -> str:
    raw = text or ""
    claim = _ACTION_NO_SEARCH if search_backed else _ACTION_CLAIM
    line = tool_result_line(tool_lines)
    kept: list[str] = []
    replaced = False
    changed = False
    for piece in _SPLIT.split(raw):
        sentence = piece.strip()
        if not sentence:
            continue
        if claim.search(sentence):
            changed = True
            if not replaced:
                kept.append(line)
                replaced = True
            continue
        kept.append(sentence)
    if not changed:
        return raw
    return "\n".join(kept)


def urls_in(text: str) -> set[str]:
    found: set[str] = set()
    for match in _URL.finditer(text or ""):
        url = match.group(0).rstrip(").,;]}>\"'")
        if url:
            found.add(url.casefold().rstrip("/"))
    return found


def strip_unknown_urls(text: str, allowed: set[str]) -> tuple[str, int]:
    removed = 0

    def repl(match: re.Match[str]) -> str:
        nonlocal removed
        url = match.group(0).rstrip(").,;]}>\"'")
        if url.casefold().rstrip("/") in allowed:
            return match.group(0)
        removed += 1
        return ""

    out = _URL.sub(repl, text or "")
    out = re.sub(r"!\[([^\]]*)\]\(\s*\)", "", out)
    out = re.sub(r"\[([^\]]*)\]\(\s*\)", r"\1", out)
    return out, removed


def settle_grounded_answer(
    text: str,
    *,
    kind: str,
    evidence: str,
    web_failed: bool,
    failure_reply: str,
    tool_ok: int,
    tool_lines: list[str],
) -> str:
    out = text or ""
    if web_failed:
        failure = (failure_reply or "").strip() or search_failure_reply("", "")
        if long_after_search_fail(out, failure):
            _bump("search_fail_long")
            return failure
        return out
    if kind in ("today", "stored", "iris") and (evidence or "").strip():
        missing = {
            "today": "검색 결과에 없다.",
            "stored": "발췌에 없다.",
            "iris": "노트에 없다.",
        }[kind]
        out = constrain_to_evidence(out, evidence, missing=missing)
    if int(tool_ok or 0) <= 0:
        # 앱이 이미 검색 블록을 넣었으면 "검색했습니다"는 거짓 보고가 아니다.
        rewritten = rewrite_unbacked_claims(
            out,
            tool_lines,
            search_backed=kind == "today" and bool((evidence or "").strip()),
        )
        if rewritten != out:
            _bump("claim_without_ok")
            out = rewritten
    if (evidence or "").strip():
        stripped, n = strip_unknown_urls(out, urls_in(evidence))
        if n:
            _bump("unknown_url", n)
            out = stripped
    return out


def _check() -> None:
    reset_counts()
    assert classify_turn("오늘 날씨 알려줘") == "today"
    assert classify_turn("주가 알려줘") == "today"
    assert classify_turn("오늘 뉴스 3개") == "today"
    assert classify_turn("환율 계산해줘") == "other"
    assert classify_turn("위키에 강화학습 있어?") == "stored"
    assert classify_turn("위키에 저장해줘") == "action"
    assert classify_turn("함수 짜줘") == "other"
    assert turn_has_grounding_material("요약해줘", [], ["a.pdf"])
    assert not turn_has_grounding_material("코드 짜줘", [], ["a.py"])
    assert wants_wiki_lookup("위키에 있어")
    assert not wants_wiki_lookup("위키에 저장해줘")
    assert not wants_wiki_lookup("첨부 pdf 요약")
    assert wants_iris_structure("타일 비율이 어떻게 되지")
    assert wants_iris_structure("이 화면을 어떻게 고치지")
    assert wants_iris_structure("아이리스는 어떻게 짜여 있어")
    assert not wants_iris_structure("함수 짜줘")
    assert not wants_iris_structure("위키에 저장해줘")
    assert not wants_iris_structure("오늘 날씨")

    evidence = "삼성전자 12\nhttps://example.com/a"
    kept = constrain_to_evidence("삼성전자 12입니다. 애플 3입니다.", evidence, missing="검색 결과에 없다.")
    assert "12" in kept and "애플" not in kept and "검색 결과에 없다." in kept
    assert constrain_to_evidence("삼성전자 12입니다.", evidence, missing="검색 결과에 없다.") == "삼성전자 12입니다."

    assert "ok 없음" in rewrite_unbacked_claims("실행했습니다. 설계는 이렇게입니다.", ["project.run completed"])
    assert "설계는 이렇게입니다." in rewrite_unbacked_claims("실행했습니다. 설계는 이렇게입니다.", [])
    same = rewrite_unbacked_claims("설계만 말합니다.", [])
    assert same == "설계만 말합니다."
    backed = rewrite_unbacked_claims("검색했습니다. 삼성 12.", [], search_backed=True)
    assert backed == "검색했습니다. 삼성 12."

    stripped, n = strip_unknown_urls("출처 [가짜](https://fake.example/x) 와 https://example.com/a", urls_in(evidence))
    assert n == 1 and "fake.example" not in stripped and "example.com/a" in stripped

    fail = search_failure_reply("SerpApi 키가 없습니다", "오늘 날씨")
    long = fail + "\n" + ("맑음입니다. " * 30)
    assert long_after_search_fail(long, fail)
    shown = settle_grounded_answer(
        long, kind="today", evidence="", web_failed=True, failure_reply=fail, tool_ok=0, tool_lines=[]
    )
    assert shown == fail
    assert counts()["search_fail_long"] == 1

    claimed = settle_grounded_answer(
        "메일을 보냈습니다.",
        kind="action",
        evidence="",
        web_failed=False,
        failure_reply="",
        tool_ok=0,
        tool_lines=["email.send running"],
    )
    assert "ok 없음" in claimed and counts()["claim_without_ok"] == 1
    untouched = settle_grounded_answer(
        "메일을 보냈습니다.",
        kind="action",
        evidence="",
        web_failed=False,
        failure_reply="",
        tool_ok=1,
        tool_lines=["email.send ok"],
    )
    assert untouched == "메일을 보냈습니다."

    cited = settle_grounded_answer(
        "본문은 그대로다 https://nope.example/z",
        kind="stored",
        evidence="본문만 있다",
        web_failed=False,
        failure_reply="",
        tool_ok=1,
        tool_lines=[],
    )
    assert "nope.example" not in cited and counts()["unknown_url"] >= 1

    ratio = settle_grounded_answer(
        "비율은 70:30이다. 배치만 말한다.",
        kind="iris",
        evidence="80:20 타일",
        web_failed=False,
        failure_reply="",
        tool_ok=1,
        tool_lines=[],
    )
    assert "70" not in ratio and "노트에 없다." in ratio
    kept_ratio = settle_grounded_answer(
        "비율은 80:20이다.",
        kind="iris",
        evidence="80:20 타일",
        web_failed=False,
        failure_reply="",
        tool_ok=1,
        tool_lines=[],
    )
    assert kept_ratio == "비율은 80:20이다."

    corpus = evidence_corpus(web="검색", wiki="", material="", code="80:20")
    assert "예전 대화" not in corpus and "80:20" in corpus
    history = [{"role": "user", "content": "질문\n\n[자료 본문]\n원문 42"}]
    assert "42" in material_from_history(history)

    from iris.runtime.past_chats import _HEADER

    assert "참고용" in _HEADER and "이전 대화에서" in _HEADER
    from iris.ui.chat.file_write_claim import _CLAIM_RE

    assert "처리 완료" in _CLAIM_RE.pattern and "검색했" not in _CLAIM_RE.pattern
    print("answer_grounding self-check ok", counts())


if __name__ == "__main__":
    _check()
