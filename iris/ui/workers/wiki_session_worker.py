"""대화가 바뀔 때 세션 요약과 특성 노트를 백그라운드에서 남긴다."""

from __future__ import annotations

from PyQt6.QtCore import QThread

from iris.infrastructure.ollama_client import OllamaClient
from iris.knowledge.iris_wiki import IrisWiki
from iris.knowledge.wiki_session import SESSION_SYSTEM, close_session
from iris.storage.database import Database


class WikiSessionWorker(QThread):
    def __init__(
        self,
        db: Database,
        wiki: IrisWiki,
        conversation_id: int,
        messages: list,
        model: str,
        base_url: str,
        *,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._db = db
        self._wiki = wiki
        self._conversation_id = int(conversation_id or 0)
        self._messages = list(messages or [])
        self._model = model
        self._base_url = base_url

    def run(self) -> None:
        try:
            client = OllamaClient(self._base_url, timeout_sec=90.0)

            def summarize(prompt: str) -> str:
                return client.chat_once_with_images(
                    self._model, prompt, [], system=SESSION_SYSTEM, timeout_sec=90.0,
                )

            close_session(
                self._db,
                self._wiki,
                conversation_id=self._conversation_id,
                messages=self._messages,
                summarize=summarize,
                model=self._model,
            )
        except Exception:
            return
