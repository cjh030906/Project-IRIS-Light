# _check_chat_render_ide_trigger

`iris/ui/_check_chat_render_ide_trigger.py`

연번 11 자검 — IDE 개방 트리거(도구 호출)와 채팅 표시(렌더러)의 계층 독립성.

## 주요 정의

- `class _ChatStub`
- `class _TriggerProbe`
- `def _detect`
- `def _check_render_layer_is_independent`
- `def _check_tool_write_suppresses_fence`
- `def _check_fence_fallback_still_works`
- `def main`

## 내부 의존성

- [[chat_renderer]]
- [[main_window]]
- [[project_ops]]
