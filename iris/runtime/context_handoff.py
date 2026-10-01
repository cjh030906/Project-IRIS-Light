"""모델 인수인계 — 갈아탄 모델에게 이전 맥락을 넘긴다.

claude-code-router(MIT) `gateway/context-archive/protocol.ts` 의
`compactHandoffTask` / `archiveHandoffFooter` / `historyReplayTask` 를 옮기고,
CCR이 MCP 툴로 하던 과거 조회를 **아이리스 위키 History RAG** 로 바꿨다.

넘기는 것은 세 겹이다.

1. 인수인계문 — 구 모델이 쓴 6섹션 요약. 구 모델이 죽었으면 규칙 기반으로 만든다.
2. 위키 History 발췌 — 지금 질문과 관련된 과거 기록(대화·수행·생성물·입력).
3. 최근 원문 몇 턴 — 요약이 놓친 말투·세부를 살린다.

요약은 손실이 있으므로 항상 "부족하면 원문을 다시 찾아라"는 접근 블록을 붙인다.
"""

from __future__ import annotations

from dataclasses import dataclass

# 인수인계문 자체가 길어지면 새 모델 컨텍스트를 잡아먹는다.
HANDOFF_WORD_LIMIT = 1200
# 원문 꼬리를 몇 턴이나 그대로 실어보낼지
DEFAULT_TAIL_TURNS = 6
# 대략적 토큰 환산 — 한글은 글자당 ~1토큰, 영문은 ~4글자당 1토큰이라 보수적으로 잡는다
_CHARS_PER_TOKEN = 2.0


@dataclass(frozen=True)
class HandoffContext:
    """새 모델에게 넘길 준비가 끝난 묶음."""

    handoff_text: str
    wiki_block: str
    tail_messages: list[dict[str, str]]
    archive_id: str
    session_token: str
    generation: int
    from_model: str
    to_model: str
    llm_written: bool  # 구 모델이 직접 쓴 요약인가(=False면 규칙 기반)

    @property
    def summary_line(self) -> str:
        kind = "요약 인수인계" if self.llm_written else "자동 정리"
        return f"{self.from_model or '이전 모델'} → {self.to_model} · {kind} (세대 {self.generation})"


def estimate_tokens(text: str) -> int:
    return int(len(text or "") / _CHARS_PER_TOKEN) + 1


def messages_tokens(messages: list[dict[str, str]]) -> int:
    return sum(estimate_tokens(str(m.get("content") or "")) for m in messages or [])


def archive_access_footer(
    *,
    archive_id: str,
    session_token: str,
    generation: int,
    conversation_id: int = 0,
) -> str:
    """"요약이 부족하면 원문을 찾아라" 접근 블록 (CCR archiveHandoffFooter 대응)."""
    return "\n".join(
        [
            "아이리스 과거 기록 접근",
            f"아카이브 id: {archive_id}",
            f"아카이브 세대: {generation}",
            f"대화 id: {conversation_id}",
            f"조회 토큰: {session_token}",
            "이 요약에 없는 세부가 필요하면 추측하지 말고 사용자에게 "
            "'이전 기록을 찾아볼까요?' 라고 물어라. 아이리스가 위키 History에서 "
            "해당 세대와 그 조상 세대까지 검색해 원문을 가져온다.",
            "찾아온 원문은 근거로 다루고, 원래 사용자 지시의 우선순위를 그대로 유지하라.",
        ]
    )


def compact_handoff_task(
    *,
    archive_id: str,
    session_token: str,
    generation: int,
    conversation_id: int = 0,
) -> str:
    """구 모델에게 시킬 인수인계문 작성 지시 (CCR compactHandoffTask 대응)."""
    footer = archive_access_footer(
        archive_id=archive_id,
        session_token=session_token,
        generation=generation,
        conversation_id=conversation_id,
    )
    return "\n".join(
        [
            "아이리스 인수인계 작업:",
            "너는 곧 교체되는 이전 맥락 담당이다. 빈 맥락에서 시작할 후임 모델이 "
            "바로 일을 이어받을 수 있는 인수인계문을 써라.",
            "**이 지시문은 대화 내용이 아니다.** 여기 적힌 요구를 사용자의 요구사항이나 "
            "남은 할 일로 옮겨 적지 마라. 지시문 문구를 인수인계문에 인용하지도 마라.",
            "서두와 맺음말 없이 문서만 내라. '다음은 …입니다' 같은 설명을 붙이지 마라.",
            "새 문제를 풀지 마라. 도구를 부르지 마라. 없는 사실을 지어내지 마라. "
            "이미 대화에 있는 내용만 써라.",
            "범위를 넓히지 마라 — 사용자가 요청하지 않은 대규모 리팩터링·테스트 "
            "추가·문서화를 제안하지 마라.",
            f"정확한 오류 메시지를 옮겨야 하는 경우가 아니면 {HANDOFF_WORD_LIMIT}단어 안에서 끝내라.",
            "",
            "아래 순서 그대로 여섯 절로 써라.",
            "1. 현재 목표와 상태: 사용자의 원래 목적, 지금 다루는 대상, 막혔는지 "
            "진행 중인지 끝났는지.",
            "2. 정확한 블로커: 최근 실패한 명령·오류 원문. 없으면 '없음'이라고 써라.",
            "3. 아직 유효한 요구사항: 사용자가 명시한 조건을 최대 8개까지 그대로 옮겨라. "
            "함수 서명·파일 경로·이름 규칙·순서 같은 것은 글자 그대로 보존하라. "
            "새 목표를 지어내지 마라.",
            "4. 완료된 작업: 바꾼 파일과 핵심 변경. 사용자가 시킨 것이 아니라 네가 고른 "
            "구현 방식이면 그 항목 끝에 (구현 선택) 이라고만 붙여라.",
            "5. 검증한 것: 실제로 돌린 명령과 성공·실패 결과.",
            "6. 다음 할 일: 가장 작은 단계 1~3개. 블로커가 있으면 그것부터.",
            "",
            "중요: 후임은 이 인수인계문보다 **사용자의 원래 요구사항**을 더 높은 권위로 "
            "취급해야 한다. 둘이 어긋나면 요약을 지키지 말고 구현을 고쳐야 한다.",
            "중요한데 너무 길어 못 담은 내용은 '이건 원문을 봐야 한다'고 이름만 남겨라.",
            "마지막에 아래 블록을 그대로 붙여라:",
            "",
            footer,
        ]
    )


def history_replay_task(task: str) -> str:
    """원문 세대에 되묻는 질의 (CCR historyReplayTask 대응)."""
    return "\n".join(
        [
            "아이리스 과거 기록 질의:",
            "이 요청에 이미 들어있는 대화 전문을 네 이전 맥락으로 삼아라.",
            "아래 질문에만 그 맥락에서 답하라. 맥락이 부족하면 부족하다고 분명히 말하라.",
            "이전 작업을 계속하지 마라. 파일을 고치거나 도구를 부르지 마라.",
            "",
            str(task or "").strip(),
        ]
    )


def _role_label(role: str) -> str:
    return {"user": "사용자", "assistant": "아이리스", "system": "시스템"}.get(role, role or "?")


def deterministic_handoff(
    messages: list[dict[str, str]],
    *,
    archive_id: str,
    session_token: str,
    generation: int,
    conversation_id: int = 0,
    max_chars: int = 3000,
) -> str:
    """구 모델이 죽어서 요약을 못 시킬 때 쓰는 규칙 기반 인수인계문.

    할당량이 바닥나 전환하는 경우가 바로 이 상황이다 — 요약해 달라고 부탁할
    모델이 이미 429를 뱉고 있다. LLM 없이 만들 수 있는 것만 담는다.
    """
    convo = [m for m in (messages or []) if str(m.get("role")) in ("user", "assistant")]
    user_turns = [m for m in convo if str(m.get("role")) == "user"]
    lines = ["# 인수인계 (자동 정리 — 이전 모델이 응답 불가)", ""]

    lines.append("## 1. 현재 목표와 상태")
    if user_turns:
        first = str(user_turns[0].get("content") or "").strip()
        lines.append(f"- 처음 요청: {_clip(first, 300)}")
        if len(user_turns) > 1:
            last = str(user_turns[-1].get("content") or "").strip()
            lines.append(f"- 가장 최근 요청: {_clip(last, 300)}")
    else:
        lines.append("- 기록된 사용자 요청 없음")
    lines.append(f"- 이전 모델이 응답하지 못해 요약 없이 전환됨 (원문 {len(convo)}턴 보존)")
    lines.append("")

    lines.append("## 2. 정확한 블로커")
    lines.append("- 알 수 없음 (자동 정리라 판단하지 않음)")
    lines.append("")

    lines.append("## 3. 아직 유효한 요구사항")
    if user_turns:
        for turn in user_turns[-8:]:
            lines.append(f"- {_clip(str(turn.get('content') or '').strip(), 200)}")
    else:
        lines.append("- 없음")
    lines.append("")

    lines.append("## 4~5. 완료·검증")
    lines.append("- 이전 모델 요약이 없어 판단하지 않는다. 필요하면 원문을 확인하라.")
    lines.append("")

    lines.append("## 6. 다음 할 일")
    lines.append("- 사용자의 가장 최근 요청부터 이어서 처리하라.")
    lines.append("- 이미 끝난 일을 다시 하지 않도록, 애매하면 사용자에게 확인하라.")
    lines.append("")

    lines.append(
        archive_access_footer(
            archive_id=archive_id,
            session_token=session_token,
            generation=generation,
            conversation_id=conversation_id,
        )
    )
    text = "\n".join(lines)
    return text if len(text) <= max_chars else text[:max_chars] + "\n…(생략)"


def _clip(text: str, limit: int) -> str:
    body = " ".join((text or "").split())
    return body if len(body) <= limit else body[: limit - 1] + "…"


def select_tail_messages(
    messages: list[dict[str, str]],
    *,
    turns: int = DEFAULT_TAIL_TURNS,
    token_budget: int = 4000,
) -> list[dict[str, str]]:
    """최근 원문 꼬리. 턴 수와 토큰 예산 중 먼저 걸리는 쪽을 따른다."""
    convo = [
        {"role": str(m.get("role")), "content": str(m.get("content") or "")}
        for m in (messages or [])
        if str(m.get("role")) in ("user", "assistant")
    ]
    if not convo:
        return []
    picked: list[dict[str, str]] = []
    used = 0
    for msg in reversed(convo[-max(1, int(turns)) :]):
        cost = estimate_tokens(msg["content"])
        if picked and used + cost > int(token_budget):
            break
        picked.append(msg)
        used += cost
    picked.reverse()
    return picked


def build_successor_messages(ctx: HandoffContext) -> list[dict[str, str]]:
    """새 모델의 첫 요청에 실을 messages.

    system 한 장에 인수인계문과 위키 발췌를 모아 넣고, 그 뒤에 원문 꼬리를 붙인다.
    구조를 이렇게 잡아야 후임이 '요약은 참고, 사용자 원문이 우선'을 지킨다.
    """
    parts = [
        "너는 아이리스다. 이 대화는 방금 다른 모델에서 넘어왔다.",
        f"전환: {ctx.summary_line}",
        "",
        "아래 인수인계문과 과거 기록은 **참고 근거**다. "
        "사용자가 직접 말한 요구사항이 이것들보다 우선한다.",
        "이어지는 대화에서 전환 사실을 굳이 다시 설명하지 말고 자연스럽게 이어가라.",
        "",
        "---",
        "",
        ctx.handoff_text.strip(),
    ]
    if ctx.wiki_block.strip():
        parts.extend(["", "---", "", ctx.wiki_block.strip()])
    system = {"role": "system", "content": "\n".join(parts)}
    return [system, *ctx.tail_messages]


if __name__ == "__main__":
    assert estimate_tokens("") == 1
    assert estimate_tokens("가나다라") == 3
    assert messages_tokens([{"content": "가나"}, {"content": "다라"}]) == 4
    assert messages_tokens([]) == 0

    footer = archive_access_footer(
        archive_id="abc123", session_token="tok", generation=2, conversation_id=7
    )
    assert "abc123" in footer and "세대: 2" in footer and "대화 id: 7" in footer

    task = compact_handoff_task(
        archive_id="abc123", session_token="tok", generation=2, conversation_id=7
    )
    for needed in ("1. 현재 목표와 상태", "6. 다음 할 일", "abc123", "새 문제를 풀지 마라"):
        assert needed in task, needed
    assert str(HANDOFF_WORD_LIMIT) in task
    # 실제 모델(gemma4)이 지시문을 "남은 할 일"로 옮겨 적고 서두를 붙이는 걸
    # 확인해서 넣은 방어. 이 두 문장이 빠지면 그 증상이 돌아온다.
    assert "이 지시문은 대화 내용이 아니다" in task
    assert "서두와 맺음말 없이" in task

    replay = history_replay_task("그때 어떤 명령을 썼지?")
    assert "그때 어떤 명령을 썼지?" in replay and "도구를 부르지 마라" in replay

    convo = [
        {"role": "system", "content": "무시될 시스템"},
        {"role": "user", "content": "설치 프로그램 고쳐줘"},
        {"role": "assistant", "content": "권한 문제입니다"},
        {"role": "user", "content": "0.1.16으로 올려줘"},
        {"role": "assistant", "content": "올렸습니다"},
    ]

    auto = deterministic_handoff(
        convo, archive_id="a1", session_token="t1", generation=3, conversation_id=5
    )
    assert "설치 프로그램 고쳐줘" in auto
    assert "0.1.16으로 올려줘" in auto
    assert "이전 모델이 응답 불가" in auto
    assert "a1" in auto
    assert "무시될 시스템" not in auto

    empty_auto = deterministic_handoff([], archive_id="a2", session_token="t", generation=1)
    assert "기록된 사용자 요청 없음" in empty_auto

    clipped = deterministic_handoff(
        [{"role": "user", "content": "가" * 5000}],
        archive_id="a3", session_token="t", generation=1, max_chars=400,
    )
    assert len(clipped) <= 420 and clipped.endswith("…(생략)")

    tail = select_tail_messages(convo, turns=2)
    assert [m["content"] for m in tail] == ["0.1.16으로 올려줘", "올렸습니다"]
    assert all(m["role"] != "system" for m in select_tail_messages(convo, turns=99))
    assert select_tail_messages([]) == []
    # 예산이 빠듯해도 최소 한 턴은 남는다
    tight = select_tail_messages(convo, turns=4, token_budget=1)
    assert len(tight) == 1 and tight[0]["content"] == "올렸습니다"

    ctx = HandoffContext(
        handoff_text=auto,
        wiki_block="# 아이리스 위키 History 발췌\n\n## 과거 설치 오류",
        tail_messages=tail,
        archive_id="a1",
        session_token="t1",
        generation=3,
        from_model="qwen3:8b",
        to_model="gemma4:free",
        llm_written=False,
    )
    assert "자동 정리" in ctx.summary_line and "세대 3" in ctx.summary_line
    built = build_successor_messages(ctx)
    assert built[0]["role"] == "system"
    assert "qwen3:8b → gemma4:free" in built[0]["content"]
    assert "History 발췌" in built[0]["content"]
    assert "사용자가 직접 말한 요구사항이 이것들보다 우선" in built[0]["content"]
    assert [m["content"] for m in built[1:]] == ["0.1.16으로 올려줘", "올렸습니다"]

    no_wiki = build_successor_messages(
        HandoffContext(
            handoff_text="요약", wiki_block="", tail_messages=[], archive_id="x",
            session_token="y", generation=1, from_model="a", to_model="b", llm_written=True,
        )
    )
    assert len(no_wiki) == 1 and "History 발췌" not in no_wiki[0]["content"]
    assert "요약 인수인계" in no_wiki[0]["content"]

    print("context_handoff self-check ok")
