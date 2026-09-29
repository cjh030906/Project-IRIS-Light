"""이전 대화 참고 워커 — 질의 임베딩을 UI 스레드 밖에서 한다.

채팅 한 턴을 보내기 직전에 돈다. 창은 멈추지 않지만 답변 시작은 이 결과를
기다린다. 그래서 MainWindow 가 제한 시간(기본 3초)을 두고, 넘기면 키워드
결과로 먼저 보낸다. 늦게 온 이 결과는 버린다.
"""

from __future__ import annotations

from PyQt6.QtCore import QThread, pyqtSignal

from iris.infrastructure.ollama_client import OllamaClient
from iris.runtime.past_chats import find_past_chats, warm_embedder


class PastChatsWorker(QThread):
    # list[SearchHit]
    ready = pyqtSignal(object)
    failed = pyqtSignal(str)

    def __init__(
        self,
        service: object,
        base_url: str,
        query: str,
        current_conversation_id: int,
        *,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._service = service
        self._base_url = base_url
        self._query = query
        self._conversation_id = int(current_conversation_id or 0)

    def run(self) -> None:
        try:
            hits = find_past_chats(
                self._service,
                self._query,
                self._conversation_id,
                OllamaClient(self._base_url),
            )
        except Exception as exc:  # noqa: BLE001
            self.failed.emit(str(exc))
            return
        self.ready.emit(list(hits))


class EmbedWarmupWorker(QThread):
    """입력하는 동안 임베딩 모델을 미리 깨운다. 실패해도 조용히 끝난다."""

    # (올린 모델 이름 — 비었으면 할 일이 없었다)
    finished_ok = pyqtSignal(str)

    def __init__(self, service: object, base_url: str, *, parent=None) -> None:
        super().__init__(parent)
        self._service = service
        self._base_url = base_url

    def run(self) -> None:
        try:
            model = warm_embedder(self._service, OllamaClient(self._base_url))
        except Exception:  # noqa: BLE001
            model = ""
        self.finished_ok.emit(model)
