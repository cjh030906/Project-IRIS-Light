"""History 근거 검색 워커 — 질의 임베딩을 UI 스레드 밖에서 한다.

키워드 검색은 로컬 SQLite라 즉시 끝나서 UI 스레드에서 해도 된다. 의미검색은
검색어를 Ollama로 임베딩해야 해서 한 번에 1~3초 걸린다(bge-m3 실측). 그래서
창은 키워드 결과를 먼저 걸어 두고, 이 워커가 의미검색까지 한 결과를 뒤에서
보내면 그것으로 갈아끼운다. 늦게 오면 버린다(`MainWindow._on_handoff_evidence_ready`).

같은 18개 질의 평가에서 바꿔 말한 질의의 재현율이 38% → 100% 였다
(`scripts/eval_history_search.py`).
"""

from __future__ import annotations

from PyQt6.QtCore import QThread, pyqtSignal

from iris.infrastructure.ollama_client import OllamaClient


class HistoryEvidenceWorker(QThread):
    """검색어 하나로 History 근거 묶음을 만든다."""

    # (근거 묶음, 호출부가 준 꼬리표 — 낡은 결과를 가려내는 데 쓴다)
    ready = pyqtSignal(str, str)
    failed = pyqtSignal(str)

    def __init__(
        self,
        service: object,
        base_url: str,
        query: str,
        *,
        tag: str = "",
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._service = service
        self._base_url = base_url
        self._query = query
        self._tag = tag

    def run(self) -> None:
        try:
            block = self._service.semantic_evidence_block(  # type: ignore[attr-defined]
                self._query, OllamaClient(self._base_url), conversation_id=None
            )
        except Exception as exc:  # noqa: BLE001
            self.failed.emit(str(exc))
            return
        self.ready.emit(block or "", self._tag)
