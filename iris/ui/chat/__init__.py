"""채팅 패널 (chat_panel, chat_display, composer_plus_menu).

Agent-readable:
- Owns: 메시지 표시, 입력, 첨부 칩.
- Does not: 턴 큐 (`iris/runtime`), 모델 HTTP.
- Talks to: MainWindow 턴 실행, TTS 등록.
- Extend via: 이 패키지. Hermes 액션은 `iris/ui/control_actions/chat.py`.
"""
