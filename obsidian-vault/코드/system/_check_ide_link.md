# _check_ide_link

`iris/system/_check_ide_link.py`

연번 14 — 명령과 편집기 상태를 나누는 IdeLink. 라이브 상태파일은 쓰지 않는다.

## 주요 정의

- `class _Runtime`
- `def _server`
- `def _stop`
- `class _Files`
- `class _Empty`
- `class _Junk`
- `def check_bad_json`
- `def check_commands`
- `def check_state_and_subscription`
- `class _EditorDown`
- `def check_empty_is_not_query_failure`
- `def check_listener_isolation`
- `def check_error_object_is_not_an_editor`
- `class _Flicker`
- `def check_failure_does_not_renotify`
- `def check_client_error_codes`
- `def check_reconnect_and_callers`
- `def main`

## 내부 의존성

- [[control_surface]]
- [[ide_link]]
- [[iris_control_stdio]]
- [[iris_ide_client]]
