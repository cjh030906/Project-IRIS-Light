"""모델을 바꿔도 대화 맥락이 이어지는지 — 아카이브·인수인계·자동 전환.

claude-code-router 에서 옮겨온 부분은 그 저장소에 보고된 결함(#1615, #1804,
#1831)을 되풀이하지 않는지까지 확인한다.
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from unittest import TestCase

from iris.knowledge.iris_wiki import IrisWiki
from iris.runtime.context_archive import (
    ArchiveRetention,
    STATUS_FAILED,
    STATUS_READY,
    create_snapshot,
    get_snapshot,
    latest_snapshot,
    lineage,
    lineage_messages,
    new_session_token,
    prune,
    verify_token,
)
from iris.runtime.context_handoff import (
    archive_access_footer,
    build_successor_messages,
    compact_handoff_task,
    deterministic_handoff,
    select_tail_messages,
)
from iris.runtime.model_failover import (
    MODE_MODEL_CHAIN,
    MODE_OFF,
    MODE_RETRY,
    RouteTarget,
    build_execution_plan,
    classify_failure,
    parse_retry_after_ms,
    retry_delay_after_status,
    should_preempt,
)
from iris.runtime.model_switch import ModelSwitchService
from iris.storage.database import Database
from iris.storage.failover_prefs import (
    FallbackEntry,
    save_failover_settings,
    save_history_settings,
)


class _Quota:
    def __init__(self, key: str, label: str, percent: float) -> None:
        self.key, self.label, self.percent = key, label, percent


class FailureClassificationTests(TestCase):
    def test_quota_exhaustion_triggers_switch(self) -> None:
        decision = classify_failure(429, MODE_MODEL_CHAIN)
        self.assertTrue(decision.should_fallback)
        self.assertEqual(decision.reason, "할당량 소진")

    def test_retry_mode_does_not_chase_client_errors(self) -> None:
        """같은 모델로 400을 다시 쏴봐야 또 400이다."""
        self.assertFalse(classify_failure(400, MODE_RETRY).should_fallback)
        self.assertFalse(classify_failure(401, MODE_RETRY).should_fallback)
        self.assertTrue(classify_failure(503, MODE_RETRY).should_fallback)

    def test_model_chain_retries_client_errors_on_a_different_model(self) -> None:
        """모델이 바뀌면 404(모델 없음)·400(미지원 파라미터)은 풀릴 수 있다."""
        self.assertTrue(classify_failure(404, MODE_MODEL_CHAIN).should_fallback)
        self.assertTrue(classify_failure(400, MODE_MODEL_CHAIN).should_fallback)

    def test_server_retry_after_wins_over_backoff(self) -> None:
        self.assertEqual(retry_delay_after_status("3"), 3000)
        self.assertEqual(retry_delay_after_status(None, 0), 1000)
        self.assertEqual(retry_delay_after_status(None, 4), 16000)
        self.assertEqual(retry_delay_after_status(None, 50), 30000)  # 상한

    def test_absurd_retry_after_is_capped(self) -> None:
        self.assertEqual(retry_delay_after_status("86400"), 60000)

    def test_garbage_retry_after_is_ignored(self) -> None:
        self.assertIsNone(parse_retry_after_ms("곧"))
        self.assertEqual(retry_delay_after_status("곧", 1), 2000)


class ExecutionPlanTests(TestCase):
    def setUp(self) -> None:
        self.primary = RouteTarget(model="qwen3:8b", backend="ollama", label="qwen3")
        self.free = RouteTarget(model="gemma4:free", backend="ollama", free=True)

    def test_chain_leaves_the_dead_provider(self) -> None:
        """CCR #1804/#1831 — 체인이 죽은 provider 로 계속 쏘면 안 된다."""
        other_backend = RouteTarget(model="qwen3:8b", backend="api", label="같은 모델 다른 곳")
        plan = build_execution_plan(self.primary, [other_backend, self.free])
        backends = [a.target.backend for a in plan.attempts]
        self.assertEqual(backends, ["ollama", "api", "ollama"])
        # 첫 시도 이후 후보들은 primary 와 (모델, 백엔드) 조합이 다르다
        for attempt in plan.attempts[1:]:
            self.assertNotEqual(attempt.target.key, self.primary.key)

    def test_every_attempt_carries_its_backend(self) -> None:
        """CCR #1615 — 프로토콜이 바뀌면 요청을 다시 만들어야 한다.

        시도가 백엔드를 들고 있어야 호출부가 body 를 재조립할 수 있다.
        """
        plan = build_execution_plan(self.primary, [RouteTarget(model="m", backend="hermes")])
        self.assertTrue(all(a.target.backend for a in plan.attempts))

    def test_identical_target_is_not_duplicated(self) -> None:
        dup = RouteTarget(model="qwen3:8b", backend="ollama")
        plan = build_execution_plan(self.primary, [dup])
        self.assertEqual(len(plan.attempts), 1)

    def test_modes(self) -> None:
        self.assertEqual(len(build_execution_plan(self.primary, [self.free], mode=MODE_OFF).attempts), 1)
        retry = build_execution_plan(self.primary, [self.free], mode=MODE_RETRY, retry_count=3)
        self.assertEqual(len(retry.attempts), 4)
        self.assertTrue(all(a.target.model == "qwen3:8b" for a in retry.attempts))

    def test_preempt_only_watches_chat_quotas(self) -> None:
        self.assertTrue(should_preempt([_Quota("week", "WEEK", 96.0)])[0])
        self.assertFalse(should_preempt([_Quota("serp", "SERP", 100.0)])[0])
        self.assertFalse(should_preempt([_Quota("week", "WEEK", 80.0)])[0])


class ContextArchiveTests(TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.db = Database(Path(self._tmp.name) / "a.db")

    def tearDown(self) -> None:
        self.db.close()
        self._tmp.cleanup()

    def test_generations_chain_to_their_parent(self) -> None:
        msgs = [{"role": "user", "content": "처음"}]
        g1 = create_snapshot(self.db, 1, msgs, model="a")
        g2 = create_snapshot(self.db, 1, msgs + [{"role": "user", "content": "둘째"}], model="b")
        g3 = create_snapshot(self.db, 1, msgs, model="c")

        self.assertEqual([g1.generation, g2.generation, g3.generation], [1, 2, 3])
        self.assertEqual(g3.parent_archive_id, g2.archive_id)
        self.assertEqual([s.generation for s in lineage(self.db, g3.archive_id)], [3, 2, 1])

    def test_oldest_generation_holds_the_fullest_original(self) -> None:
        first = [{"role": "user", "content": "원래 요구사항"}]
        g1 = create_snapshot(self.db, 1, first)
        g2 = create_snapshot(self.db, 1, [{"role": "user", "content": "요약된 뒤"}])
        self.assertEqual(lineage_messages(self.db, g2.archive_id), first)
        self.assertEqual(g1.messages, first)

    def test_conversations_have_independent_generations(self) -> None:
        create_snapshot(self.db, 1, [])
        other = create_snapshot(self.db, 2, [])
        self.assertEqual(other.generation, 1)
        self.assertEqual(other.parent_archive_id, "")

    def test_token_gates_archive_access(self) -> None:
        token = new_session_token()
        snap = create_snapshot(self.db, 1, [], session_token=token)
        self.assertTrue(verify_token(self.db, snap.archive_id, token))
        self.assertFalse(verify_token(self.db, snap.archive_id, "추측"))

    def test_pruning_never_breaks_the_live_chain(self) -> None:
        """용량이 모자라도 지금 쓰는 대화의 조상은 남아야 복원이 된다."""
        tight = ArchiveRetention(max_snapshots=3, max_bytes=500, retention_days=30)
        big = [{"role": "user", "content": "채움" * 200}]
        for _ in range(8):
            create_snapshot(self.db, 1, big, retention=tight)

        live = latest_snapshot(self.db, 1)
        assert live is not None
        chain = lineage(self.db, live.archive_id)
        for snap in chain:
            self.assertIsNotNone(get_snapshot(self.db, snap.archive_id))

    def test_expired_unprotected_snapshots_are_removed(self) -> None:
        stale = create_snapshot(self.db, 5, [])
        live = create_snapshot(self.db, 6, [])
        self.db._execute(
            "UPDATE context_archives SET expires_at = ? WHERE conversation_id = 5",
            ("2000-01-01T00:00:00",),
        )
        self.db._commit()
        prune(self.db, protect_archive_id=live.archive_id)
        self.assertIsNone(get_snapshot(self.db, stale.archive_id))
        self.assertIsNotNone(get_snapshot(self.db, live.archive_id))


class HandoffTextTests(TestCase):
    def setUp(self) -> None:
        self.convo = [
            {"role": "system", "content": "시스템 지시"},
            {"role": "user", "content": "설치 프로그램 고쳐줘"},
            {"role": "assistant", "content": "권한 문제입니다"},
            {"role": "user", "content": "0.1.16으로 올려줘"},
            {"role": "assistant", "content": "올렸습니다"},
        ]

    def test_task_demands_the_six_sections(self) -> None:
        task = compact_handoff_task(archive_id="a", session_token="t", generation=1)
        for section in ("1. 현재 목표와 상태", "2. 정확한 블로커", "3. 아직 유효한 요구사항",
                        "4. 완료된 작업", "5. 검증한 것", "6. 다음 할 일"):
            self.assertIn(section, task)

    def test_task_forbids_scope_creep_and_invention(self) -> None:
        task = compact_handoff_task(archive_id="a", session_token="t", generation=1)
        self.assertIn("없는 사실을 지어내지 마라", task)
        self.assertIn("범위를 넓히지 마라", task)

    def test_deterministic_handoff_survives_a_dead_model(self) -> None:
        """구 모델이 429면 요약을 시킬 수 없다 — 그래도 요구사항은 넘어가야 한다."""
        text = deterministic_handoff(self.convo, archive_id="a1", session_token="t", generation=2)
        self.assertIn("설치 프로그램 고쳐줘", text)
        self.assertIn("0.1.16으로 올려줘", text)
        self.assertIn("a1", text)
        self.assertNotIn("시스템 지시", text)

    def test_footer_tells_successor_how_to_reach_the_original(self) -> None:
        footer = archive_access_footer(
            archive_id="abc", session_token="tok", generation=3, conversation_id=9
        )
        self.assertIn("abc", footer)
        self.assertIn("추측하지 말고", footer)

    def test_tail_keeps_the_most_recent_turns(self) -> None:
        tail = select_tail_messages(self.convo, turns=2)
        self.assertEqual([m["content"] for m in tail], ["0.1.16으로 올려줘", "올렸습니다"])
        self.assertTrue(all(m["role"] != "system" for m in select_tail_messages(self.convo, turns=99)))

    def test_successor_prompt_subordinates_the_summary(self) -> None:
        """요약이 사용자 원문을 이기면 안 된다 — CCR 이 특히 강조하는 부분."""
        from iris.runtime.context_handoff import HandoffContext

        built = build_successor_messages(
            HandoffContext(
                handoff_text="요약문", wiki_block="", tail_messages=[], archive_id="a",
                session_token="t", generation=1, from_model="old", to_model="new",
                llm_written=True,
            )
        )
        self.assertIn("사용자가 직접 말한 요구사항이 이것들보다 우선", built[0]["content"])


class ModelSwitchServiceTests(TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        root = Path(self._tmp.name)
        self.db = Database(root / "s.db")
        self.wiki = IrisWiki(docs_root=root / "docs", user_root=root / "wiki")
        self.svc = ModelSwitchService(self.db, wiki=self.wiki)
        self.old = RouteTarget(model="qwen3:8b", backend="ollama", label="qwen3")
        self.new = RouteTarget(model="gemma4:free", backend="ollama", label="gemma4", free=True)
        self.convo = [
            {"role": "user", "content": "설치 프로그램에서 권한 오류가 납니다"},
            {"role": "assistant", "content": "venv 소유권을 고치세요"},
            {"role": "user", "content": "고쳤는데 또 납니다"},
        ]

    def tearDown(self) -> None:
        self.db.close()
        self._tmp.cleanup()

    def test_switch_carries_context_when_old_model_is_alive(self) -> None:
        def summarizer(model: str, messages: list[dict[str, str]]) -> str:
            self.assertEqual(model, "qwen3:8b")
            self.assertIn("아이리스 인수인계 작업", messages[-1]["content"])
            return "## 1. 현재 목표와 상태\n설치 권한 문제 해결 중"

        result = self.svc.switch(
            7, self.convo, self.new, from_target=self.old, reason="수동 전환",
            summarizer=summarizer,
        )
        self.assertTrue(result.context.llm_written)
        self.assertIn("설치 권한 문제 해결 중", result.messages[0]["content"])
        self.assertEqual(result.messages[-1]["content"], "고쳤는데 또 납니다")

    def test_switch_still_carries_context_when_old_model_is_dead(self) -> None:
        """할당량이 바닥나 전환하는 상황 — 요약을 부탁할 모델이 이미 죽어 있다."""

        def dead(model: str, messages: list[dict[str, str]]) -> str:
            raise RuntimeError("HTTP 429 rate limit")

        result = self.svc.switch(
            7, self.convo, self.new, from_target=self.old, reason="할당량 소진",
            summarizer=dead,
        )
        self.assertFalse(result.context.llm_written)
        self.assertIn("설치 프로그램에서 권한 오류가 납니다", result.messages[0]["content"])
        self.assertIn("할당량 소진", result.notice)

    def test_empty_summary_falls_back_instead_of_shipping_nothing(self) -> None:
        result = self.svc.switch(
            7, self.convo, self.new, from_target=self.old, summarizer=lambda m, x: "   "
        )
        self.assertFalse(result.context.llm_written)
        self.assertIn("고쳤는데 또 납니다", result.messages[0]["content"])

    def test_wiki_history_is_attached_as_evidence(self) -> None:
        self.svc.record_turn(1, "user", "예전에도 권한 오류로 설치가 막혔었다")
        result = self.svc.switch(7, self.convo, self.new, from_target=self.old)
        self.assertIn("History 발췌", result.messages[0]["content"])
        self.assertIn("예전에도 권한 오류", result.messages[0]["content"])

    def test_switch_is_itself_recorded_in_history(self) -> None:
        self.svc.switch(7, self.convo, self.new, from_target=self.old, reason="할당량 소진")
        switches = [
            h for h in self.svc.retrieve("모델 전환", limit=10)
            if h.entry.tags == "model-switch"
        ]
        self.assertTrue(switches)
        self.assertIn("gemma4", switches[0].entry.body)

    def test_original_stays_recoverable_after_several_switches(self) -> None:
        first = self.svc.switch(7, self.convo, self.new, from_target=self.old)
        later = self.convo + [{"role": "user", "content": "세 번째 요청"}]
        second = self.svc.switch(7, later, self.old, from_target=self.new)

        self.assertEqual(second.context.generation, first.context.generation + 1)
        replay = self.svc.replay_request(second.archive_id, "맨 처음 뭐라고 했지?")
        assert replay is not None
        self.assertEqual(replay[0]["content"], "설치 프로그램에서 권한 오류가 납니다")
        self.assertIn("맨 처음 뭐라고 했지?", replay[-1]["content"])

    def test_archive_is_marked_ready_then_failed(self) -> None:
        result = self.svc.switch(7, self.convo, self.new, from_target=self.old)
        snap = get_snapshot(self.db, result.archive_id)
        assert snap is not None
        self.assertEqual(snap.status, STATUS_READY)
        self.assertEqual(snap.model, "gemma4:free")

        self.svc.abandon(result.archive_id)
        self.assertEqual(get_snapshot(self.db, result.archive_id).status, STATUS_FAILED)

    def test_plan_reflects_saved_chain(self) -> None:
        settings = self.svc.failover_settings
        settings.chain = [
            FallbackEntry(model="gemma4:free"),
            FallbackEntry(model="llama4:free", backend="api"),
        ]
        save_failover_settings(self.db, settings)
        plan = self.svc.plan_for(self.old)
        self.assertEqual(
            [a.target.model for a in plan.attempts],
            ["qwen3:8b", "gemma4:free", "llama4:free"],
        )

        settings.enabled = False
        save_failover_settings(self.db, settings)
        self.assertEqual(len(self.svc.plan_for(self.old).attempts), 1)

    def test_history_can_be_turned_off_entirely(self) -> None:
        settings = self.svc.history_settings
        settings.enabled = False
        save_history_settings(self.db, settings)

        self.assertIsNone(self.svc.record_turn(1, "user", "남지 않아야 한다"))
        self.assertEqual(self.svc.retrieve("남지"), [])
        # 기록을 꺼도 전환 자체는 동작해야 한다
        result = self.svc.switch(7, self.convo, self.new, from_target=self.old)
        self.assertIn("고쳤는데 또 납니다", result.messages[-1]["content"])

    def test_lineage_summary_is_human_readable(self) -> None:
        self.svc.switch(7, self.convo, self.new, from_target=self.old)
        second = self.svc.switch(7, self.convo, self.old, from_target=self.new)
        text = self.svc.lineage_summary(second.archive_id)
        self.assertIn("2세대", text)
        self.assertIn("세대 1", text)
        self.assertEqual(
            self.svc.lineage_summary("없는아카이브"), "보존된 이전 맥락이 없습니다."
        )
