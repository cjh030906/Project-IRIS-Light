"""구체 상태. 프로세스 CPU가 아니라 아이리스가 연 요청이 남았는지로 정한다."""

from __future__ import annotations


def orb_activity(
    *,
    speaking: bool,
    streaming: bool,
    request_open: bool,
    transcribing: bool,
    hearing: bool,
) -> str:
    """RESPONDING | PROCESSING | LISTENING | IDLE.

    글자·음성 출력 중이면 답변. 요청이 안 끝났으면 작업. 그 다음이 듣기·대기.
    """
    if speaking or streaming:
        return "RESPONDING"
    if request_open or transcribing:
        return "PROCESSING"
    if hearing:
        return "LISTENING"
    return "IDLE"


def _check() -> None:
    assert orb_activity(
        speaking=False, streaming=False, request_open=True, transcribing=False, hearing=True
    ) == "PROCESSING"
    assert orb_activity(
        speaking=False, streaming=True, request_open=True, transcribing=False, hearing=False
    ) == "RESPONDING"
    assert orb_activity(
        speaking=True, streaming=False, request_open=False, transcribing=False, hearing=False
    ) == "RESPONDING"
    assert orb_activity(
        speaking=False, streaming=False, request_open=False, transcribing=True, hearing=True
    ) == "PROCESSING"
    assert orb_activity(
        speaking=False, streaming=False, request_open=False, transcribing=False, hearing=True
    ) == "LISTENING"
    assert orb_activity(
        speaking=False, streaming=False, request_open=False, transcribing=False, hearing=False
    ) == "IDLE"
    print("orb_activity ok")


if __name__ == "__main__":
    _check()
