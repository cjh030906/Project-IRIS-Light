"""archify 다이어그램을 채팅 칸 카드에 연다.

Theia에는 HTML 프리뷰가 없어 에디터로 열면 소스만 보인다.
채팅 로그는 QTextEdit라 페이지를 문서 안에 넣지 않고, 로그와 입력창 사이 카드에 띄운다.
"""

from __future__ import annotations

from typing import Any


def open_diagram_preview(window: Any, html_path: str, title: str = "") -> bool:
    """채팅 카드에 HTML을 띄운다. 채팅이 없거나 파일이 없으면 False."""
    chat = getattr(window, "_chat", None)
    show = getattr(chat, "show_diagram", None)
    if not callable(show):
        return False
    if not show(html_path, title):
        return False
    note = getattr(chat, "append_diagram_note", None)
    if callable(note):
        note(html_path, title)
    return True
