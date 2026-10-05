# _check_iris_ide_bridge_state

`iris/system/_check_iris_ide_bridge_state.py`

IRIS IDE 브리지 상태연동 자체점검 — 총괄표 #1·#2·#3.

## 주요 정의

- `def _post`
- `def _check_empty_editor_state`
- `class _HalfDeadHandler`
- `def _check_context_budget`
- `class _BadRequestHandler`
- `def _check_error_body_preserved`
- `def _check_no_blocking_bridge_calls`
- `def _check_bridge_identity`
- `def _self_check`

## 내부 의존성

- [[ide_link]]
- [[iris_ide_client]]
- [[iris_ide_runtime]]
- [[ui]]
- [[win_subprocess]]
