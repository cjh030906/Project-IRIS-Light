"""Setup·Gateway·Control Surface·IDE 기동.

Agent-readable:
- Owns: 설치 프로토콜, Hermes/Ollama 기동, Control Surface `:8765`, 스킬 동기화, IDE 타일.
- Does not: 채팅 위젯, 모델 추론.
- Talks to: `iris/infrastructure` 클라이언트, Hermes config, UI.
- Extend via: 새 도구는 스킬/MCP. 새 UI 액션은 `ActionRegistry`와 `iris/ui/control_actions`. Gateway 수정은 버그·보안만.
"""
