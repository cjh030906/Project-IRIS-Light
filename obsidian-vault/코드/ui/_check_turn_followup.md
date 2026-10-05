# _check_turn_followup

`iris/ui/_check_turn_followup.py`

같은 대화의 중지·오류·늦은 신호·재시작 복원·종료 시 워커 취소.

## 주요 정의

- `def _texts`
- `def _check_reopen`
- `class _SigWorker`
- `class _RunningWorker`
- `def _check_window`
- `def main`

## 내부 의존성

- [[chat_session]]
- [[database]]
- [[main_window]]
