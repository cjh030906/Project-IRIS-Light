"""설정창 — Voice runtime 연결 상태 표시 + 기동/재연결."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from PyQt6.QtCore import Qt, QThread, QTimer, pyqtSignal
from PyQt6.QtGui import QColor, QPainter
from PyQt6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QWidget

from iris.audio.voice_runtime_client import VoiceRuntimeClient
from iris.audio.voice_runtime_manager import VoiceRuntimeProcessManager
from iris.audio.workers import TTSRuntimeBootstrapWorker
from iris.ui.shared.theme_tokens import TOKENS


def format_runtime_status(
    *,
    phase: str,
    pid: int = 0,
    mock_mode: bool = False,
    detail: str = "",
) -> str:
    """phase: checking | connecting | connected | disconnected | error."""
    if phase == "checking":
        return "확인 중…"
    if phase == "connecting":
        return "기동 중… (첫 연결은 수십 초 걸릴 수 있음)"
    if phase == "connected":
        mode = "mock" if mock_mode else "실모델"
        pid_bit = f" · pid {pid}" if pid else ""
        return f"연결됨 · {mode}{pid_bit}"
    if phase == "error":
        tip = (detail or "알 수 없는 오류").strip()
        if len(tip) > 160:
            tip = tip[:157] + "…"
        return f"오류 · {tip}"
    return "꺼짐 · 연결되어 있지 않음"


def status_dot_kind(phase: str) -> str:
    return {
        "connected": "ok",
        "connecting": "partial",
        "checking": "unknown",
        "error": "error",
        "disconnected": "error",
    }.get(phase, "unknown")


class _Dot(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._kind = "unknown"
        self.setFixedSize(10, 10)

    def set_kind(self, kind: str) -> None:
        self._kind = kind if kind in ("ok", "partial", "error", "unknown") else "unknown"
        self.update()

    def paintEvent(self, _event) -> None:  # noqa: N802
        colors = {
            "ok": QColor("#22c55e"),
            "partial": QColor("#f59e0b"),
            "error": QColor("#ef4444"),
            "unknown": QColor("#94a3b8"),
        }
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(colors.get(self._kind, colors["unknown"]))
        painter.drawEllipse(1, 1, 8, 8)
        painter.end()


class _HealthProbeWorker(QThread):
    finished_ok = pyqtSignal(object)
    failed = pyqtSignal(str)

    def __init__(self, base_url: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._base_url = (base_url or "").rstrip("/") or "http://127.0.0.1:18765"

    def run(self) -> None:
        try:
            health = VoiceRuntimeClient(base_url=self._base_url, timeout_sec=2.0).health(
                timeout=1.5
            )
            self.finished_ok.emit(
                {
                    "status": health.status,
                    "pid": health.pid,
                    "mock_mode": health.mock_mode,
                }
            )
        except Exception as exc:  # noqa: BLE001
            self.failed.emit(str(exc))


class VoiceRuntimeStatusWidget(QWidget):
    """상태 점 + 라벨 + 확인/연결 버튼. UI 스레드를 블로킹하지 않는다."""

    connected_changed = pyqtSignal(bool)

    def __init__(
        self,
        *,
        runtime: VoiceRuntimeProcessManager,
        url_provider: Callable[[], str],
        mock_provider: Callable[[], bool],
        model_provider: Callable[[], str],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._runtime = runtime
        self._url_provider = url_provider
        self._mock_provider = mock_provider
        self._model_provider = model_provider
        self._phase = "disconnected"
        self._connected = False
        self._probe: _HealthProbeWorker | None = None
        self._bootstrap: TTSRuntimeBootstrapWorker | None = None

        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(8)
        self._dot = _Dot(self)
        self._label = QLabel(format_runtime_status(phase="disconnected"), self)
        self._label.setWordWrap(True)
        self._label.setStyleSheet(f"color: {TOKENS.text_secondary};")
        self._refresh_btn = QPushButton("확인", self)
        self._refresh_btn.setFixedWidth(56)
        self._refresh_btn.clicked.connect(self.probe_now)
        self._connect_btn = QPushButton("연결", self)
        self._connect_btn.setFixedWidth(72)
        self._connect_btn.clicked.connect(self.connect_or_reconnect)
        row.addWidget(self._dot, 0, Qt.AlignmentFlag.AlignVCenter)
        row.addWidget(self._label, 1)
        row.addWidget(self._refresh_btn, 0)
        row.addWidget(self._connect_btn, 0)

        self._poll = QTimer(self)
        self._poll.setInterval(5000)
        self._poll.timeout.connect(self.probe_now)

    def start_watching(self) -> None:
        self.probe_now()
        if not self._poll.isActive():
            self._poll.start()

    def stop_watching(self) -> None:
        self._poll.stop()
        if self._probe is not None and self._probe.isRunning():
            self._probe.requestInterruption()
            self._probe.wait(200)
        self._probe = None
        if self._bootstrap is not None and self._bootstrap.isRunning():
            self._bootstrap.request_cancel()
            self._bootstrap.wait(400)
        self._bootstrap = None

    def _set_phase(
        self,
        phase: str,
        *,
        pid: int = 0,
        mock_mode: bool = False,
        detail: str = "",
    ) -> None:
        self._phase = phase
        connected = phase == "connected"
        if connected != self._connected:
            self._connected = connected
            self.connected_changed.emit(connected)
        self._dot.set_kind(status_dot_kind(phase))
        self._label.setText(
            format_runtime_status(
                phase=phase, pid=pid, mock_mode=mock_mode, detail=detail
            )
        )
        busy = phase in {"checking", "connecting"}
        self._refresh_btn.setEnabled(not busy)
        self._connect_btn.setEnabled(not busy)
        self._connect_btn.setText("재연결" if connected else "연결")

    def probe_now(self) -> None:
        if self._bootstrap is not None and self._bootstrap.isRunning():
            return
        if self._probe is not None and self._probe.isRunning():
            return
        if self._phase != "connecting":
            self._set_phase("checking")
        url = (self._url_provider() or "").strip() or "http://127.0.0.1:18765"
        worker = _HealthProbeWorker(url, parent=self)
        self._probe = worker
        worker.finished_ok.connect(self._on_probe_ok)
        worker.failed.connect(self._on_probe_failed)
        worker.finished.connect(lambda: setattr(self, "_probe", None))
        worker.finished.connect(worker.deleteLater)
        worker.start()

    def _on_probe_ok(self, payload: object) -> None:
        data = payload if isinstance(payload, dict) else {}
        status = str(data.get("status") or "")
        if status == "ok":
            self._set_phase(
                "connected",
                pid=int(data.get("pid") or 0),
                mock_mode=bool(data.get("mock_mode")),
            )
            return
        if self._phase == "connecting":
            return
        self._set_phase("disconnected", detail=f"status={status or 'unknown'}")

    def _on_probe_failed(self, _err: str) -> None:
        if self._phase == "connecting":
            return
        self._set_phase("disconnected")

    def connect_or_reconnect(self) -> None:
        if self._bootstrap is not None and self._bootstrap.isRunning():
            return
        force = self._connected or self._phase == "connected"
        url = (self._url_provider() or "").strip() or "http://127.0.0.1:18765"
        mock = bool(self._mock_provider())
        model = (self._model_provider() or "").strip() or "Qwen/Qwen3-TTS-12Hz-0.6B-Base"
        self._runtime.set_base_url(url)
        if force:
            try:
                self._runtime.shutdown(timeout_sec=5.0)
            except Exception:
                pass
        self._set_phase("connecting")
        worker = TTSRuntimeBootstrapWorker(
            runtime=self._runtime,
            runtime_url=url,
            model_name=model,
            mock_mode=mock,
            warmup=not mock,
            parent=self,
        )
        self._bootstrap = worker
        worker.finished_ok.connect(self._on_bootstrap_ok)
        worker.failed.connect(self._on_bootstrap_failed)
        worker.finished.connect(lambda: setattr(self, "_bootstrap", None))
        worker.finished.connect(worker.deleteLater)
        worker.start()

    def _on_bootstrap_ok(self, result: object) -> None:
        payload: dict[str, Any] = result if isinstance(result, dict) else {}
        if not payload.get("running"):
            self._set_phase("error", detail="런타임이 시작되지 않았습니다.")
            return
        mock = bool(self._mock_provider())
        self._set_phase("connected", mock_mode=mock)
        self.probe_now()

    def _on_bootstrap_failed(self, err: str) -> None:
        self._set_phase("error", detail=str(err or "기동 실패"))
