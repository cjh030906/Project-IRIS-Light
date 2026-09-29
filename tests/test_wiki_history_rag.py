"""위키 History 기록과 하이브리드 RAG 검색."""

from __future__ import annotations

import tempfile
from pathlib import Path
from unittest import TestCase

from iris.knowledge.history_index import (
    build_fts_query,
    chunk_text,
    embed_entry,
    ensure_index_schema,
    format_hits_for_prompt,
    index_entry,
    reindex_all,
    search,
    unembedded_ids,
)
from iris.knowledge.history_store import (
    KIND_ACTION,
    KIND_ARTIFACT,
    KIND_CHAT,
    KIND_EPISODE,
    KIND_INPUT,
    count_entries,
    delete_entry,
    list_entries,
    record_entry,
    record_turn,
    write_episode,
)
from iris.knowledge.iris_wiki import IrisWiki
from iris.storage.database import Database


class _StubEmbedder:
    """단어 포함 여부를 좌표로 쓰는 결정적 임베더 — Ollama 없이 의미검색을 흉내낸다."""

    model = "stub-embed"
    VOCAB = ("설치", "권한", "일정", "회의", "커피", "결제")

    def __init__(self) -> None:
        self.calls = 0

    def embed(self, texts: list[str]) -> list[list[float]]:
        self.calls += 1
        return [[1.0 if w in t else 0.0 for w in self.VOCAB] for t in texts]


class HistoryStoreTests(TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        root = Path(self._tmp.name)
        self.db = Database(root / "h.db")
        self.wiki = IrisWiki(docs_root=root / "docs", user_root=root / "wiki")

    def tearDown(self) -> None:
        self.db.close()
        self._tmp.cleanup()

    def test_records_every_kind_the_user_asked_for(self) -> None:
        """대화·수행·생성물·입력이 모두 한 곳에 쌓인다."""
        record_turn(self.db, 1, "user", "내일 회의 잡아줘", wiki=self.wiki)
        record_turn(self.db, 1, "assistant", "10시로 잡았습니다", wiki=self.wiki)
        record_entry(self.db, kind=KIND_ACTION, body="캘린더에 일정 추가", conversation_id=1, wiki=self.wiki)
        record_entry(self.db, kind=KIND_ARTIFACT, body="회의록 초안.md 생성", conversation_id=1, wiki=self.wiki)
        record_entry(self.db, kind=KIND_INPUT, body="첨부된 PDF 본문", source="계약서.pdf", conversation_id=1, wiki=self.wiki)

        self.assertEqual(count_entries(self.db), 5)
        kinds = {e.kind for e in list_entries(self.db, conversation_id=1)}
        self.assertEqual(kinds, {KIND_CHAT, KIND_ACTION, KIND_ARTIFACT, KIND_INPUT})

    def test_wiki_file_is_a_view_not_the_source(self) -> None:
        """위키 파일을 지워도 DB 기록과 검색은 살아있다."""
        entry = record_turn(self.db, 2, "user", "설치 프로그램 권한 오류", wiki=self.wiki)
        assert entry is not None
        index_entry(self.db, entry)
        day_file = self.wiki.user_root / entry.rel_path
        self.assertTrue(day_file.is_file())

        day_file.unlink()
        self.assertIsNotNone(list_entries(self.db, conversation_id=2))
        self.assertTrue(search(self.db, "프로그램"))

    def test_long_body_is_truncated_in_wiki_but_whole_in_db(self) -> None:
        body = "가" * 9000
        entry = record_entry(self.db, kind=KIND_INPUT, body=body, wiki=self.wiki)
        assert entry is not None
        self.assertEqual(len(entry.body), 9000)
        text = (self.wiki.user_root / entry.rel_path).read_text(encoding="utf-8")
        self.assertIn("생략", text)
        self.assertLess(len(text), 9000)

    def test_episode_note_links_covered_records(self) -> None:
        a = record_turn(self.db, 4, "user", "첫 질문", wiki=self.wiki)
        b = record_turn(self.db, 4, "assistant", "첫 답변", wiki=self.wiki)
        assert a and b
        ep = write_episode(
            self.db, self.wiki, title="첫 대화 정리", summary="별 내용 없음",
            conversation_id=4, covers=(a.id, b.id),
        )
        assert ep is not None
        self.assertEqual(ep.kind, KIND_EPISODE)
        text = (self.wiki.user_root / ep.rel_path).read_text(encoding="utf-8")
        self.assertIn("별 내용 없음", text)
        self.assertIn(f"`#{a.id}`", text)

    def test_blank_body_is_not_recorded(self) -> None:
        self.assertIsNone(record_turn(self.db, 1, "user", ""))
        self.assertIsNone(record_turn(self.db, 1, "user", "   \n  "))
        self.assertEqual(count_entries(self.db), 0)


class HistorySearchTests(TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.db = Database(Path(self._tmp.name) / "h.db")
        ensure_index_schema(self.db)
        self.entries = {}
        seed = [
            ("installer", KIND_CHAT, "설치 프로그램이 권한 때문에 실패합니다"),
            ("venv", KIND_CHAT, "venv 폴더 권한을 고치면 해결됩니다"),
            ("meeting", KIND_ACTION, "내일 회의 일정을 캘린더에 넣었습니다"),
            ("coffee", KIND_INPUT, "커피 원두 결제 내역"),
        ]
        for key, kind, body in seed:
            e = record_entry(self.db, kind=kind, body=body, conversation_id=1)
            assert e is not None
            index_entry(self.db, e)
            self.entries[key] = e

    def tearDown(self) -> None:
        self.db.close()
        self._tmp.cleanup()

    def test_korean_particles_do_not_block_keyword_match(self) -> None:
        """`프로그램` 이 `프로그램이` 를 잡아야 한다 — trigram을 쓰는 이유."""
        hits = search(self.db, "프로그램")
        self.assertTrue(hits)
        self.assertEqual(hits[0].entry.id, self.entries["installer"].id)

    def test_two_character_query_falls_back_to_like(self) -> None:
        """trigram은 3글자 미만을 못 받는다 — LIKE 폴백이 받아야 한다."""
        self.assertEqual(build_fts_query("회의"), "")
        hits = search(self.db, "회의")
        self.assertEqual([h.entry.id for h in hits], [self.entries["meeting"].id])

    def test_search_works_without_any_embedder(self) -> None:
        """Ollama가 꺼져 있어도 검색은 돌아야 한다."""
        hits = search(self.db, "권한", embedder=None)
        self.assertTrue(hits)
        self.assertTrue(all(h.vector_rank is None for h in hits))
        self.assertEqual(hits[0].matched_by, "키워드")

    def test_embedder_adds_semantic_rank(self) -> None:
        emb = _StubEmbedder()
        for entry in self.entries.values():
            self.assertGreaterEqual(embed_entry(self.db, entry, emb), 1)
        hits = search(self.db, "설치 권한", embedder=emb)
        self.assertTrue(hits)
        self.assertEqual(hits[0].entry.id, self.entries["installer"].id)
        self.assertIsNotNone(hits[0].vector_rank)

    def test_broken_embedder_degrades_to_keyword(self) -> None:
        class _Broken:
            model = "broken"

            def embed(self, texts):
                raise RuntimeError("Ollama 연결 실패")

        self.assertEqual(embed_entry(self.db, self.entries["installer"], _Broken()), 0)
        hits = search(self.db, "프로그램", embedder=_Broken())
        self.assertTrue(hits)
        self.assertEqual(hits[0].entry.id, self.entries["installer"].id)

    def test_stale_vectors_of_other_dimension_are_ignored(self) -> None:
        """임베딩 모델을 바꾸면 차원이 달라진다 — 옛 벡터가 검색을 깨면 안 된다."""
        old = _StubEmbedder()
        for entry in self.entries.values():
            embed_entry(self.db, entry, old)

        class _WiderEmbedder:
            model = "stub-embed"  # 같은 이름, 다른 차원 (모델 교체 시나리오)

            def embed(self, texts):
                return [[0.5] * 12 for _ in texts]

        hits = search(self.db, "프로그램", embedder=_WiderEmbedder())
        self.assertTrue(hits)  # 키워드 쪽이 살아남는다

    def test_filters_narrow_results(self) -> None:
        other = record_entry(self.db, kind=KIND_CHAT, body="권한 관련 다른 대화", conversation_id=99)
        assert other is not None
        index_entry(self.db, other)

        scoped = search(self.db, "권한", conversation_id=99)
        self.assertEqual([h.entry.id for h in scoped], [other.id])

        by_kind = search(self.db, "일정", kinds=(KIND_ACTION,))
        self.assertTrue(all(h.entry.kind == KIND_ACTION for h in by_kind))

    def test_deleted_entry_disappears_from_results(self) -> None:
        delete_entry(self.db, self.entries["coffee"].id)
        hits = search(self.db, "원두")
        self.assertEqual(hits, [])

    def test_reindex_rebuilds_everything(self) -> None:
        emb = _StubEmbedder()
        self.assertEqual(reindex_all(self.db, embedder=emb), 4)
        self.assertEqual(unembedded_ids(self.db, emb.model), [])
        self.assertEqual(len(unembedded_ids(self.db, "다른모델")), 4)
        self.assertTrue(search(self.db, "프로그램"))

    def test_prompt_block_names_its_sources(self) -> None:
        block = format_hits_for_prompt(search(self.db, "프로그램"))
        self.assertIn("History 발췌", block)
        self.assertIn("설치 프로그램", block)
        self.assertEqual(format_hits_for_prompt([]), "")

    def test_empty_query_returns_nothing(self) -> None:
        self.assertEqual(search(self.db, ""), [])
        self.assertEqual(search(self.db, "   "), [])


class FtsQueryTests(TestCase):
    def test_operators_in_user_text_cannot_break_match(self) -> None:
        """사용자가 뭘 치든 FTS5 구문 오류가 나면 안 된다."""
        for raw in ('"; DROP TABLE x --', "a OR b NEAR(c)", "**", "설치*", "a:b"):
            query = build_fts_query(raw)
            if query:
                self.assertEqual(query.count('"') % 2, 0, raw)

    def test_short_tokens_are_dropped(self) -> None:
        self.assertEqual(build_fts_query("가 나 다"), "")
        self.assertEqual(build_fts_query("설치 프로그램"), '"프로그램"')

    def test_chunking_covers_whole_text(self) -> None:
        chunks = chunk_text("나" * 3000)
        self.assertGreater(len(chunks), 1)
        self.assertEqual(chunk_text("짧음"), ["짧음"])
        self.assertEqual(chunk_text(""), [])


class _SynonymOllama:
    """`pick_embedding_model`·`embed` 만 흉내내는 가짜 Ollama — 동의어를 같은 좌표로."""

    GROUPS = (("결제", "돈"), ("설치", "인스톨"))

    def __init__(self, *, installed: bool = True) -> None:
        self.installed = installed
        self.embedded: list[str] = []

    def pick_embedding_model(self, preferred: str = "") -> str:
        return "syn-embed" if self.installed else ""

    def embed(self, model: str, texts: list[str]) -> list[list[float]]:
        self.embedded.extend(texts)
        return [[1.0 if any(w in t for w in g) else 0.0 for g in self.GROUPS] for t in texts]


class SemanticEvidenceTests(TestCase):
    """`ModelSwitchService.semantic_evidence_block` — 루틴·인수인계 워커가 부르는 길."""

    def setUp(self) -> None:
        from iris.knowledge.history_index import OllamaEmbedder
        from iris.runtime.model_switch import ModelSwitchService

        self._tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.db = Database(Path(self._tmp.name) / "h.db")
        self.svc = ModelSwitchService(self.db)
        self.client = _SynonymOllama()
        emb = OllamaEmbedder(client=self.client, model_name="syn-embed")
        for body in ("커피 원두 결제 내역", "내일 회의 일정을 캘린더에 넣었습니다"):
            entry = record_entry(self.db, kind=KIND_INPUT, body=body)
            assert entry is not None
            index_entry(self.db, entry, embedder=emb)

    def tearDown(self) -> None:
        self.db.close()
        self._tmp.cleanup()

    def test_paraphrase_is_found_only_with_query_embedding(self) -> None:
        self.assertNotIn("결제 내역", self.svc.evidence_block("돈 나간 곳"))
        self.assertIn("결제 내역", self.svc.semantic_evidence_block("돈 나간 곳", self.client))
        self.assertIn("돈 나간 곳", self.client.embedded)

    def test_falls_back_to_keyword_without_an_embedding_model(self) -> None:
        block = self.svc.semantic_evidence_block("회의 일정", _SynonymOllama(installed=False))
        self.assertIn("회의 일정", block)
        self.assertEqual(
            self.svc.semantic_evidence_block("회의 일정", None), self.svc.evidence_block("회의 일정")
        )
