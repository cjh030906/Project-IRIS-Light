"""채팅 워커의 모델 자동 전환 — 실패하면 다음 후보로, 맥락은 그 후보용으로 새로 조립."""

from __future__ import annotations

import sys
from unittest import TestCase
from unittest.mock import patch

from PyQt6.QtWidgets import QApplication

_APP = QApplication.instance() or QApplication(sys.argv)

from iris.ui.workers.ollama_workers import ChatAttempt, OllamaChatWorker  # noqa: E402


class _FakeClient:
    """모델 이름별로 정해진 결과를 돌려주는 가짜 Ollama."""

    def __init__(self, script: dict[str, object]) -> None:
        self.script = script
        self.seen: list[tuple[str, list[dict[str, str]]]] = []

    def __call__(self, base_url: str) -> "_FakeClient":
        return self

    def stream_chat(self, model: str, messages, *, think: bool = True):
        self.seen.append((model, list(messages)))
        outcome = self.script.get(model)
        if isinstance(outcome, Exception):
            raise outcome
        for piece in str(outcome or ""):
            yield {"thinking": None, "content": piece, "done": False}
        yield {"thinking": None, "content": None, "done": True}


class _Collector:
    def __init__(self, worker: OllamaChatWorker) -> None:
        self.content: list[str] = []
        self.switches: list[tuple[str, str, bool]] = []
        self.ok: list[str] = []
        self.failed: list[str] = []
        self.connecting: list[str] = []
        worker.content_chunk.connect(self.content.append)
        worker.switched.connect(lambda m, r, had: self.switches.append((m, r, had)))
        worker.finished_ok.connect(self.ok.append)
        worker.failed.connect(self.failed.append)
        worker.connecting.connect(lambda m, h: self.connecting.append(m))


def _run(worker: OllamaChatWorker, client: _FakeClient) -> _Collector:
    out = _Collector(worker)
    with patch("iris.ui.workers.ollama_workers.OllamaClient", client):
        worker.run()  # 스레드를 띄우지 않고 본문만 동기 실행
    return out


class ChatWorkerFailoverTests(TestCase):
    def setUp(self) -> None:
        self.primary_msgs = [{"role": "user", "content": "원래 질문"}]
        self.fallback_msgs = [
            {"role": "system", "content": "인수인계문 + History 발췌"},
            {"role": "user", "content": "원래 질문"},
        ]

    def _worker(self, attempts: list[ChatAttempt]) -> OllamaChatWorker:
        return OllamaChatWorker(
            "http://127.0.0.1:11434", attempts[0].model, attempts[0].messages,
            attempts=attempts,
        )

    def test_no_fallback_when_primary_succeeds(self) -> None:
        client = _FakeClient({"paid:big": "답"})
        worker = self._worker([ChatAttempt("paid:big", self.primary_msgs)])
        out = _run(worker, client)

        self.assertEqual(out.ok, ["답"])
        self.assertEqual(out.switches, [])
        self.assertEqual(worker.final_model, "paid:big")

    def test_quota_exhaustion_moves_to_the_free_model(self) -> None:
        client = _FakeClient({
            "paid:big": RuntimeError("Ollama HTTP 429: rate limit"),
            "free:small": "무료 모델 답",
        })
        worker = self._worker([
            ChatAttempt("paid:big", self.primary_msgs),
            ChatAttempt("free:small", self.fallback_msgs, free=True),
        ])
        out = _run(worker, client)

        self.assertEqual(out.ok, ["무료 모델 답"])
        self.assertEqual(len(out.switches), 1)
        self.assertEqual(out.switches[0][0], "free:small")
        self.assertEqual(out.switches[0][1], "할당량 소진")
        self.assertEqual(worker.final_model, "free:small")

    def test_fallback_gets_its_own_messages_not_the_primary_body(self) -> None:
        """CCR #1615 — 후보마다 요청을 다시 만들어야 한다."""
        client = _FakeClient({
            "paid:big": RuntimeError("Ollama HTTP 429: rate limit"),
            "free:small": "답",
        })
        worker = self._worker([
            ChatAttempt("paid:big", self.primary_msgs),
            ChatAttempt("free:small", self.fallback_msgs),
        ])
        _run(worker, client)

        self.assertEqual([m for m, _ in client.seen], ["paid:big", "free:small"])
        self.assertEqual(client.seen[0][1], self.primary_msgs)
        self.assertEqual(client.seen[1][1], self.fallback_msgs)
        self.assertIn("인수인계문", client.seen[1][1][0]["content"])

    def test_chain_walks_past_several_dead_models(self) -> None:
        client = _FakeClient({
            "a": RuntimeError("Ollama HTTP 429: rate limit"),
            "b": RuntimeError("Ollama HTTP 503: upstream down"),
            "c": "세 번째가 받았다",
        })
        worker = self._worker([
            ChatAttempt("a", self.primary_msgs),
            ChatAttempt("b", self.fallback_msgs),
            ChatAttempt("c", self.fallback_msgs),
        ])
        out = _run(worker, client)

        self.assertEqual(out.ok, ["세 번째가 받았다"])
        self.assertEqual([s[0] for s in out.switches], ["b", "c"])
        self.assertEqual(out.connecting, ["a", "b", "c"])

    def test_connection_refused_also_falls_over(self) -> None:
        """Ollama가 꺼져 있으면 상태 코드가 없다 — 문구로 판정해야 한다."""
        client = _FakeClient({
            "local:model": RuntimeError("Ollama 연결 실패: [WinError 10061]"),
            "cloud:model": "클라우드가 받았다",
        })
        worker = self._worker([
            ChatAttempt("local:model", self.primary_msgs),
            ChatAttempt("cloud:model", self.fallback_msgs),
        ])
        out = _run(worker, client)
        self.assertEqual(out.ok, ["클라우드가 받았다"])

    def test_unclassifiable_error_does_not_switch_models(self) -> None:
        """원인을 모르는 실패로 모델을 바꾸면 사용자만 헷갈린다."""
        client = _FakeClient({
            "a": RuntimeError("알 수 없는 문제"),
            "b": "안 불려야 한다",
        })
        worker = self._worker([
            ChatAttempt("a", self.primary_msgs),
            ChatAttempt("b", self.fallback_msgs),
        ])
        out = _run(worker, client)

        self.assertEqual(out.switches, [])
        self.assertEqual(out.ok, [])
        self.assertEqual([m for m, _ in client.seen], ["a"])
        self.assertTrue(out.failed)

    def test_all_candidates_dead_reports_the_last_error(self) -> None:
        client = _FakeClient({
            "a": RuntimeError("Ollama HTTP 429: rate limit"),
            "b": RuntimeError("Ollama HTTP 500: boom"),
        })
        worker = self._worker([
            ChatAttempt("a", self.primary_msgs),
            ChatAttempt("b", self.fallback_msgs),
        ])
        out = _run(worker, client)

        self.assertEqual(out.ok, [])
        self.assertEqual(len(out.failed), 1)
        self.assertIn("500", out.failed[0])

    def test_switch_reports_whether_text_was_already_shown(self) -> None:
        """중간에 끊겼으면 화면에 남은 글자를 지우고 다시 받아야 한다."""

        class _HalfwayClient(_FakeClient):
            def stream_chat(self, model, messages, *, think=True):
                self.seen.append((model, list(messages)))
                if model == "a":
                    yield {"thinking": None, "content": "앞부분", "done": False}
                    raise RuntimeError("Ollama HTTP 429: rate limit")
                yield {"thinking": None, "content": "다시 씀", "done": True}

        client = _HalfwayClient({})
        worker = self._worker([
            ChatAttempt("a", self.primary_msgs),
            ChatAttempt("b", self.fallback_msgs),
        ])
        out = _run(worker, client)

        self.assertEqual(out.switches[0][2], True)  # 이미 흘려보낸 글자가 있었다
        self.assertIn("앞부분", out.content)

    def test_cancel_stops_the_chain(self) -> None:
        client = _FakeClient({
            "a": RuntimeError("Ollama HTTP 429: rate limit"),
            "b": "불리면 안 된다",
        })
        worker = self._worker([
            ChatAttempt("a", self.primary_msgs),
            ChatAttempt("b", self.fallback_msgs),
        ])
        worker.request_cancel()
        out = _run(worker, client)

        self.assertEqual(out.switches, [])
        self.assertEqual(out.failed, [])
        self.assertEqual(out.ok, [])

    def test_single_attempt_constructor_still_works(self) -> None:
        """attempts 를 안 넘기는 기존 호출부가 그대로 동작해야 한다."""
        client = _FakeClient({"solo": "예전 방식"})
        worker = OllamaChatWorker("http://127.0.0.1:11434", "solo", self.primary_msgs)
        out = _run(worker, client)

        self.assertEqual(out.ok, ["예전 방식"])
        self.assertEqual(worker.final_model, "solo")


class _FakeOaiStream:
    """모델별 결과를 돌려주는 가짜 OpenAI 호환 엔드포인트."""

    def __init__(self, script):
        self.script = script
        self.seen = []

    def __call__(self, base_url, api_key, model, messages, *, auth_style="bearer", timeout=120.0):
        self.seen.append((base_url, api_key, model, list(messages), auth_style))
        outcome = self.script.get(model)
        if isinstance(outcome, Exception):
            raise outcome
        for piece in str(outcome or ""):
            yield {"content": piece, "done": False}
        yield {"content": None, "done": True}


class OpenAICompatFailoverTests(TestCase):
    """Hermes 를 끈 상태의 커스텀 API 경로도 같은 방식으로 전환돼야 한다."""

    def setUp(self) -> None:
        from iris.ui.workers.chat_attempt import ApiCall

        self.msgs = [{"role": "user", "content": "원래 질문"}]
        self.handoff = [{"role": "system", "content": "인수인계문"}]
        self.paid = ApiCall(base_url="https://paid/v1", api_key="k1", model="paid-x")
        self.free = ApiCall(
            base_url="https://free/v1", api_key="k2", model="free-y", auth_style="x-api-key"
        )

    def _run(self, attempts, stream):
        from iris.ui.workers.api_provider_workers import OpenAICompatChatWorker

        worker = OpenAICompatChatWorker(
            self.paid.base_url, self.paid.api_key, self.paid.model, self.msgs,
            attempts=attempts,
        )
        ok, switches, failed = [], [], []
        worker.finished_ok.connect(ok.append)
        worker.switched.connect(lambda m, r, had: switches.append((m, r, had)))
        worker.failed.connect(failed.append)
        with patch("iris.infrastructure.openai_compat_client.stream_chat", stream):
            worker.run()
        self.worker = worker
        return ok, switches, failed

    def test_falls_over_to_another_provider(self) -> None:
        stream = _FakeOaiStream({
            "paid-x": RuntimeError("HTTP 429: quota exceeded"),
            "free-y": "무료 쪽이 받았다",
        })
        attempts = [
            ChatAttempt("api:p1:paid-x", self.msgs, target=self.paid),
            ChatAttempt("api:p2:free-y", self.handoff, free=True, target=self.free),
        ]
        ok, switches, _ = self._run(attempts, stream)

        self.assertEqual(ok, ["무료 쪽이 받았다"])
        self.assertEqual([s[0] for s in switches], ["api:p2:free-y"])
        self.assertEqual(self.worker.final_model, "api:p2:free-y")

    def test_each_candidate_uses_its_own_credentials(self) -> None:
        stream = _FakeOaiStream({
            "paid-x": RuntimeError("HTTP 429: quota"),
            "free-y": "답",
        })
        self._run(
            [
                ChatAttempt("api:p1:paid-x", self.msgs, target=self.paid),
                ChatAttempt("api:p2:free-y", self.handoff, target=self.free),
            ],
            stream,
        )
        first, second = stream.seen
        self.assertEqual((first[0], first[1], first[4]), ("https://paid/v1", "k1", "bearer"))
        self.assertEqual((second[0], second[1], second[4]), ("https://free/v1", "k2", "x-api-key"))
        self.assertEqual(second[3], self.handoff)

    def test_legacy_call_without_attempts_still_works(self) -> None:
        from iris.ui.workers.api_provider_workers import OpenAICompatChatWorker

        stream = _FakeOaiStream({"solo": "예전 방식"})
        worker = OpenAICompatChatWorker(
            "https://x/v1", "k", "solo", self.msgs, display_model="Prov/solo"
        )
        ok = []
        worker.finished_ok.connect(ok.append)
        with patch("iris.infrastructure.openai_compat_client.stream_chat", stream):
            worker.run()
        self.assertEqual(ok, ["예전 방식"])
