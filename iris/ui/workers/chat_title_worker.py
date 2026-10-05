"""채팅 목록 제목 — 답변에 쓴 모델에게 한 줄만 받는다.

결과는 사이드바 제목으로만 쓴다. 채팅 로그에 넣지 않는다.
"""

from __future__ import annotations

from PyQt6.QtCore import QThread, pyqtSignal

from iris.ui.workers.backend_call import BackendRoute, collect_reply


class ChatTitleWorker(QThread):
    finished_ok = pyqtSignal(str, int, int)
    failed = pyqtSignal(str)

    def __init__(
        self,
        route: BackendRoute,
        messages: list[dict[str, str]],
        *,
        conversation_id: int,
        generation: int,
        timeout_sec: float = 25.0,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._route = route
        self._messages = list(messages or [])
        self._conversation_id = int(conversation_id)
        self._generation = int(generation)
        self._timeout_sec = float(timeout_sec)
        self._cancel = False

    def request_cancel(self) -> None:
        self._cancel = True

    def run(self) -> None:
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
                self.failed.emit(str(exc))
            return
        if self._cancel:
            return
        self.finished_ok.emit((text or "").strip(), self._conversation_id, self._generation)


if __name__ == "__main__":
    route = BackendRoute(backend="ollama", model="m")
    worker = ChatTitleWorker(
        route,
        [{"role": "user", "content": "제목:"}],
        conversation_id=3,
        generation=1,
    )
    assert worker._conversation_id == 3 and worker._generation == 1
    worker.request_cancel()
    assert worker._cancel is True
    print("chat_title_worker self-check ok")
