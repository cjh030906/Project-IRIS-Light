"""위키 History 백그라운드 색인 워커.

키워드 색인(FTS5)은 기록할 때 바로 들어간다 — 로컬 SQLite라 즉시 끝난다.
임베딩은 Ollama에 HTTP를 때리므로 UI 스레드에서 하면 창이 멈춘다. 그래서
아직 벡터가 없는 기록만 모아 여기서 따로 처리한다.

Ollama가 꺼져 있거나 임베딩 모델이 없으면 조용히 아무것도 하지 않는다 —
그 상태로도 키워드 검색은 이미 동작하기 때문이다.
"""

from __future__ import annotations

from PyQt6.QtCore import QThread, pyqtSignal

from iris.infrastructure.ollama_client import OllamaClient
from iris.knowledge.history_index import embed_entry, unembedded_ids
from iris.knowledge.history_store import KINDS, get_entry
from iris.knowledge.iris_wiki import IrisWiki
from iris.runtime.model_switch import resolve_embedder
from iris.storage.database import Database
from iris.storage.failover_prefs import load_history_settings

# 한 번에 처리할 건수 — 너무 크면 Ollama를 오래 점유한다.
_BATCH = 40


class HistoryEmbedWorker(QThread):
    """밀린 History 기록을 임베딩하고 위키 History 표지를 갱신한다."""

    # (임베딩한 건수, 쓴 모델) — 모델이 빈 문자열이면 키워드 검색만 도는 중
    finished_ok = pyqtSignal(int, str)
    failed = pyqtSignal(str)

    def __init__(
        self,
        db: Database,
        wiki: IrisWiki,
        base_url: str,
        *,
        batch: int = _BATCH,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._db = db
        self._wiki = wiki
        self._base_url = base_url
        self._batch = max(1, int(batch))
        self._cancel = False

    def request_cancel(self) -> None:
        self._cancel = True

    def run(self) -> None:
        try:
            settings = load_history_settings(self._db)
            if not settings.enabled:
                self.finished_ok.emit(0, "")
                return

            embedder = resolve_embedder(settings, OllamaClient(self._base_url))
            done = 0
            if embedder is not None:
                for history_id in unembedded_ids(self._db, embedder.model, limit=self._batch):
                    if self._cancel:
                        break
                    entry = get_entry(self._db, history_id)
                    if entry is None:
                        continue
                    if embed_entry(self._db, entry, embedder) > 0:
                        done += 1

            self._sync_index_note(embedder.model if embedder is not None else "")
            self.finished_ok.emit(done, embedder.model if embedder is not None else "")
        except Exception as exc:  # noqa: BLE001
            self.failed.emit(str(exc))

    def _sync_index_note(self, embed_model: str) -> None:
        """History 표지(`history/index.md`) — 종류별 건수와 최근 날짜."""
        counts: dict[str, int] = {}
        for row in self._db._execute(
            "SELECT kind, COUNT(*) AS n FROM wiki_history GROUP BY kind"
        ).fetchall():
            kind = str(row["kind"])
            if kind in KINDS:
                counts[kind] = int(row["n"])
        days = [
            str(row["day"])
            for row in self._db._execute(
                "SELECT DISTINCT substr(created_at, 1, 10) AS day "
                "FROM wiki_history ORDER BY day DESC LIMIT 14"
            ).fetchall()
        ]
        self._wiki.sync_history_index(
            counts=counts, embed_model=embed_model, recent_days=days
        )
