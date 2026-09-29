"""History 백그라운드 색인 워커 — Ollama가 없어도 안전하게 넘어가야 한다."""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path
from unittest import TestCase
from unittest.mock import patch

from PyQt6.QtWidgets import QApplication

_APP = QApplication.instance() or QApplication(sys.argv)

from iris.knowledge.history_index import unembedded_ids  # noqa: E402
from iris.knowledge.history_store import (  # noqa: E402
    KIND_ACTION,
    record_entry,
    record_turn,
)
from iris.knowledge.iris_wiki import IrisWiki  # noqa: E402
from iris.storage.database import Database  # noqa: E402
from iris.storage.failover_prefs import save_history_settings  # noqa: E402
from iris.ui.workers.history_embed_worker import HistoryEmbedWorker  # noqa: E402


class _StubOllama:
    """임베딩 모델이 설치돼 있는 Ollama 흉내."""

    def __init__(self, model: str = "bge-m3:latest") -> None:
        self._model = model

    def __call__(self, base_url: str) -> "_StubOllama":
        return self

    def pick_embedding_model(self, preferred: str = "") -> str:
        return self._model

    def embed(self, model: str, texts: list[str]) -> list[list[float]]:
        return [[float(len(t) % 7), 1.0, 0.5] for t in texts]


class _DeadOllama:
    def __call__(self, base_url: str) -> "_DeadOllama":
        return self

    def pick_embedding_model(self, preferred: str = "") -> str:
        raise RuntimeError("Ollama 연결 실패")


class HistoryEmbedWorkerTests(TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        root = Path(self._tmp.name)
        self.db = Database(root / "h.db")
        self.wiki = IrisWiki(docs_root=root / "docs", user_root=root / "wiki")
        record_turn(self.db, 1, "user", "설치 권한 오류", wiki=self.wiki)
        record_turn(self.db, 1, "assistant", "소유권을 고치세요", wiki=self.wiki)
        record_entry(self.db, kind=KIND_ACTION, body="재설치 실행", conversation_id=1, wiki=self.wiki)

    def tearDown(self) -> None:
        self.db.close()
        self._tmp.cleanup()

    def _run(self, client) -> tuple[list[tuple[int, str]], list[str]]:
        worker = HistoryEmbedWorker(self.db, self.wiki, "http://127.0.0.1:11434")
        ok: list[tuple[int, str]] = []
        failed: list[str] = []
        worker.finished_ok.connect(lambda n, m: ok.append((n, m)))
        worker.failed.connect(failed.append)
        with patch("iris.ui.workers.history_embed_worker.OllamaClient", client):
            worker.run()
        return ok, failed

    def test_embeds_the_backlog(self) -> None:
        ok, failed = self._run(_StubOllama())
        self.assertEqual(failed, [])
        self.assertEqual(ok, [(3, "bge-m3:latest")])
        self.assertEqual(unembedded_ids(self.db, "bge-m3:latest"), [])

    def test_second_run_has_nothing_left_to_do(self) -> None:
        self._run(_StubOllama())
        ok, _ = self._run(_StubOllama())
        self.assertEqual(ok, [(0, "bge-m3:latest")])

    def test_dead_ollama_is_not_an_error(self) -> None:
        """임베딩이 안 되면 키워드 검색으로 계속 간다 — 사용자에게 알릴 일이 아니다."""
        ok, failed = self._run(_DeadOllama())
        self.assertEqual(failed, [])
        self.assertEqual(ok, [(0, "")])

    def test_index_note_reports_counts_and_mode(self) -> None:
        self._run(_StubOllama())
        note = (self.wiki.user_root / "history" / "index.md").read_text(encoding="utf-8")
        self.assertIn("bge-m3:latest", note)
        self.assertIn("대화: 2건", note)
        self.assertIn("수행: 1건", note)
        self.assertIn("합계: 3건", note)

    def test_index_note_tells_how_to_turn_on_semantic_search(self) -> None:
        self._run(_DeadOllama())
        note = (self.wiki.user_root / "history" / "index.md").read_text(encoding="utf-8")
        self.assertIn("ollama pull bge-m3", note)

    def test_disabled_history_skips_everything(self) -> None:
        settings = __import__(
            "iris.storage.failover_prefs", fromlist=["load_history_settings"]
        ).load_history_settings(self.db)
        settings.enabled = False
        save_history_settings(self.db, settings)

        ok, failed = self._run(_StubOllama())
        self.assertEqual(ok, [(0, "")])
        self.assertEqual(failed, [])
        self.assertFalse((self.wiki.user_root / "history" / "index.md").exists())
