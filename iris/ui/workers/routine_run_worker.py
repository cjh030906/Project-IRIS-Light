"""예약 루틴 실행 워커 — 백그라운드로 모델에 물어보고 결과만 돌려준다.

루틴은 사용자가 보고 있지 않을 때 돌 수 있다. UI 스레드에서 부르면 아침 9시에
창이 몇 초씩 얼어붙으므로 반드시 여기서 돈다.

근거 모으기(웹 검색·History 의미검색)도 여기서 한다. 둘 다 네트워크 왕복이라
UI 스레드에서 하면 창이 멈춘다. `prepare` 로 받아 모델 호출 직전에 부르고,
진행 문구는 `note` 로 올린다(UI 위젯은 이 스레드에서 만지면 안 된다).
준비 시간은 모델 호출 제한 시간에 포함되지 않는다.

한 번에 하나만 돌린다(MainWindow 가 직렬화). 여러 루틴이 같은 시각에 걸려도
모델을 동시에 때리지 않게 하려는 것이다.
"""

from __future__ import annotations

from collections.abc import Callable

from PyQt6.QtCore import QThread, pyqtSignal

from iris.ui.workers.backend_call import BackendRoute, collect_reply

# 루틴은 검색·요약까지 할 수 있어 대화 한 턴보다 넉넉히 준다.
DEFAULT_TIMEOUT_SEC = 180.0

# note 콜백을 받아 모델에 보낼 messages 를 만든다. 워커 스레드에서 불린다.
Prepare = Callable[[Callable[[str], None]], list[dict[str, str]]]


class RoutineRunWorker(QThread):
    """루틴 하나를 실행한다."""

    # (routine_id, 결과 텍스트)
    finished_ok = pyqtSignal(int, str)
    # (routine_id, 오류 문구)
    failed = pyqtSignal(int, str)
    # 진행 문구(검색 실패 등) — UI 스레드에서 활동 창에 찍는다
    note = pyqtSignal(str)

    def __init__(
        self,
        routine_id: int,
        route: BackendRoute,
        messages: list[dict[str, str]] | None = None,
        *,
        prepare: Prepare | None = None,
        timeout_sec: float = DEFAULT_TIMEOUT_SEC,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._routine_id = int(routine_id)
        self._route = route
        self._messages = list(messages or [])
        self._prepare = prepare
        self._timeout_sec = float(timeout_sec)
        self._cancel = False

    @property
    def routine_id(self) -> int:
        return self._routine_id

    def request_cancel(self) -> None:
        self._cancel = True

    def run(self) -> None:
        if self._prepare is not None:
            try:
                self._messages = list(self._prepare(self.note.emit) or [])
            except Exception as exc:  # noqa: BLE001
                if not self._cancel:
                    self.failed.emit(self._routine_id, f"근거 준비 실패: {exc}")
                return
            if self._cancel:
                return
        try:
            text = collect_reply(
                self._route,
                self._messages,
                timeout_sec=self._timeout_sec,
                cancelled=lambda: self._cancel,
                think=False,
            )
        except Exception as exc:  # noqa: BLE001
            if not self._cancel:
                self.failed.emit(self._routine_id, str(exc))
            return
        if self._cancel:
            return
        cleaned = (text or "").strip()
        if not cleaned:
            self.failed.emit(self._routine_id, "모델이 빈 응답을 주었습니다")
            return
        self.finished_ok.emit(self._routine_id, cleaned)


if __name__ == "__main__":
    w = RoutineRunWorker(7, BackendRoute(backend="ollama", model="m"), [])
    assert w.routine_id == 7 and w._timeout_sec == DEFAULT_TIMEOUT_SEC
    w.request_cancel()
    assert w._cancel is True

    # prepare 는 run() 안에서 불리고, note 로 문구를 올린다
    notes: list[str] = []
    got: list[tuple[int, str]] = []
    w2 = RoutineRunWorker(
        8,
        BackendRoute(backend="ollama", model="m"),
        prepare=lambda note: (note("검색 중"), [{"role": "user", "content": "x"}])[1],
    )
    w2.note.connect(notes.append)
    w2.failed.connect(lambda rid, msg: got.append((rid, msg)))
    w2.request_cancel()  # 모델 호출까지는 가지 않게
    w2.run()
    assert notes == ["검색 중"] and w2._messages[0]["content"] == "x" and got == []

    def _boom(note):
        raise RuntimeError("serpapi down")

    w3 = RoutineRunWorker(9, BackendRoute(backend="ollama", model="m"), prepare=_boom)
    w3.failed.connect(lambda rid, msg: got.append((rid, msg)))
    w3.run()
    assert got and got[0][0] == 9 and "serpapi down" in got[0][1]
    print("routine_run_worker self-check ok")
