"""고정 창 감시 — 창 찾기, 화면 모델 선택, 알림 발생."""

from __future__ import annotations

from types import SimpleNamespace
from unittest import TestCase, mock

from iris.automation.window_controller import WindowInfo
from iris.infrastructure import local_vision
from iris.monitoring import pinned_monitor
from iris.monitoring.models import DetectionResult, StatusCategory
from iris.monitoring.pin_store import PinnedTarget, PinStore
from iris.monitoring.pinned_monitor import PinnedMonitorService, locate_window


def _win(title: str, hwnd: int, minimized: bool = False) -> WindowInfo:
    return WindowInfo(title=title, left=0, top=0, width=800, height=600, hwnd=hwnd, minimized=minimized)


class LocateWindowTests(TestCase):
    def test_same_hwnd_wins_even_if_title_changed(self) -> None:
        pin = PinnedTarget(title="문서 A - Google Chrome", hwnd=42)
        wins = [_win("문서 B - Google Chrome", 42), _win("문서 A - Google Chrome", 7)]
        self.assertEqual(locate_window(pin, wins).hwnd, 42)

    def test_exact_title_when_hwnd_gone(self) -> None:
        pin = PinnedTarget(title="빌드 로그", hwnd=99)
        self.assertEqual(locate_window(pin, [_win("빌드 로그", 5)]).hwnd, 5)

    def test_last_seen_title(self) -> None:
        pin = PinnedTarget(title="원래 제목", hwnd=0, current_title="바뀐 제목")
        self.assertEqual(locate_window(pin, [_win("바뀐 제목", 3)]).hwnd, 3)

    def test_single_window_of_same_app(self) -> None:
        """IRIS 를 다시 켜 hwnd 가 없고 탭도 바뀐 경우 — 같은 앱 창이 하나면 그것."""
        pin = PinnedTarget(title="문서 A - Google Chrome")
        wins = [_win("메모장", 1), _win("뉴스 - Google Chrome", 2)]
        self.assertEqual(locate_window(pin, wins).hwnd, 2)

    def test_ambiguous_same_app_is_not_guessed(self) -> None:
        pin = PinnedTarget(title="문서 A - Google Chrome")
        wins = [_win("뉴스 - Google Chrome", 2), _win("메일 - Google Chrome", 3)]
        self.assertIsNone(locate_window(pin, wins))


class _FakeOllama:
    def __init__(self, names: list[str], caps: dict[str, list[str]] | None = None) -> None:
        self.base_url = "http://fake"
        self._names = names
        self._caps = caps or {}

    def list_models(self):
        return [SimpleNamespace(name=n, is_cloud=False) for n in self._names]

    def show_model(self, name: str, timeout_sec: float = 0):
        return {"capabilities": self._caps.get(name, [])}


class ResolveVisionModelTests(TestCase):
    def setUp(self) -> None:
        local_vision.forget_cache()

    def test_prefers_default_vision_model(self) -> None:
        client = _FakeOllama(["gemma4:e4b", "qwen2.5vl:3b"])
        model, why = local_vision.resolve_vision_model(client, "gemma4:e4b")
        self.assertEqual(model, "qwen2.5vl:3b")
        self.assertEqual(why, "")

    def test_chat_model_without_vision_capability_is_rejected(self) -> None:
        """이름은 비전처럼 보여도 Ollama가 vision 을 안 주면 쓰지 않는다 (gemma4 실제 사례)."""
        client = _FakeOllama(["gemma4:e4b"], {"gemma4:e4b": ["completion", "tools"]})
        model, why = local_vision.resolve_vision_model(client, "gemma4:e4b")
        self.assertIsNone(model)
        self.assertIn("설치", why)

    def test_chat_model_with_vision_capability_is_used(self) -> None:
        client = _FakeOllama(["llava:7b"], {"llava:7b": ["completion", "vision"]})
        model, _ = local_vision.resolve_vision_model(client, "llava:7b")
        self.assertEqual(model, "llava:7b")

    def test_ollama_down_is_reported_not_cached(self) -> None:
        client = _FakeOllama([])
        client.list_models = mock.Mock(side_effect=RuntimeError("연결 거부"))
        model, why = local_vision.resolve_vision_model(client, "")
        self.assertIsNone(model)
        self.assertIn("Ollama", why)
        client.list_models = lambda: [SimpleNamespace(name="qwen2.5vl:3b", is_cloud=False)]
        model, _ = local_vision.resolve_vision_model(client, "")
        self.assertEqual(model, "qwen2.5vl:3b")


class ServiceTests(TestCase):
    def _service(self, store: PinStore) -> PinnedMonitorService:
        settings = SimpleNamespace(ollama_base_url="http://fake/v1")
        return PinnedMonitorService(store, settings, lambda: "gemma4:e4b")  # type: ignore[arg-type]

    def _run(self, svc, windows, model=("qwen2.5vl:3b", ""), result=None):
        result = result or DetectionResult(
            StatusCategory.ERROR_DETECTED, 0.9, "빨간 에러", "로그 확인", summary="터미널"
        )
        with mock.patch(
            "iris.automation.window_controller.list_visible_windows", return_value=windows
        ), mock.patch(
            "iris.infrastructure.local_vision.resolve_vision_model", return_value=model
        ), mock.patch.object(
            pinned_monitor, "capture_window_by_hwnd", return_value=object()
        ), mock.patch.object(
            pinned_monitor, "capture_result_to_png_bytes", return_value=b"png"
        ), mock.patch.object(
            pinned_monitor, "detect_window_state", return_value=result
        ) as detect:
            svc._analyze_all("gemma4:e4b")
        return detect

    def test_alert_when_title_changed_but_same_window(self) -> None:
        store = PinStore()
        store.pin("문서 A - Google Chrome", 42)
        svc = self._service(store)
        reports: list[tuple] = []
        svc.report.connect(lambda *a: reports.append(a))

        detect = self._run(svc, [_win("문서 B - Google Chrome", 42)])

        self.assertEqual(detect.call_args.args[1], "qwen2.5vl:3b")
        pin = store.get("문서 A - Google Chrome")
        self.assertEqual(pin.status, StatusCategory.ERROR_DETECTED)
        self.assertEqual(pin.summary, "터미널")
        self.assertEqual(pin.current_title, "문서 B - Google Chrome")
        self.assertEqual(len(reports), 1)
        self.assertEqual(reports[0][1], "ERROR_DETECTED")

    def test_same_state_twice_alerts_once(self) -> None:
        store = PinStore()
        store.pin("빌드", 5)
        svc = self._service(store)
        reports: list[tuple] = []
        svc.report.connect(lambda *a: reports.append(a))
        self._run(svc, [_win("빌드", 5)])
        self._run(svc, [_win("빌드", 5)])
        self.assertEqual(len(reports), 1)

    def test_no_vision_model_explains_and_asks_once(self) -> None:
        store = PinStore()
        store.pin("빌드", 5)
        svc = self._service(store)
        asked: list[str] = []
        svc.vision_missing.connect(asked.append)
        why = "화면을 볼 수 있는 모델이 없어요 — qwen2.5vl:3b 설치가 필요해요."
        detect = self._run(svc, [_win("빌드", 5)], model=(None, why))
        self._run(svc, [_win("빌드", 5)], model=(None, why))

        detect.assert_not_called()
        self.assertEqual(store.get("빌드").reason, why)
        self.assertEqual(len(asked), 1)

    def test_status_lines_for_chat(self) -> None:
        store = PinStore()
        store.pin("빌드", 5)
        svc = self._service(store)
        self.assertEqual(svc.status_lines(), ["- 빌드: 아직 분석 전"])
        self._run(svc, [_win("빌드", 5)])
        line = svc.status_lines()[0]
        self.assertIn("에러 발생", line)
        self.assertIn("화면: 터미널", line)
