"""Voice runtime 상태 표시 문자열·점 종류 계약."""

from __future__ import annotations

from iris.ui.settings.voice_runtime_status import format_runtime_status, status_dot_kind


def main() -> None:
    assert format_runtime_status(phase="checking") == "확인 중…"
    assert "기동 중" in format_runtime_status(phase="connecting")
    assert format_runtime_status(phase="disconnected").startswith("꺼짐")
    connected = format_runtime_status(phase="connected", pid=42, mock_mode=False)
    assert "연결됨" in connected and "실모델" in connected and "42" in connected
    mock = format_runtime_status(phase="connected", pid=1, mock_mode=True)
    assert "mock" in mock
    err = format_runtime_status(phase="error", detail="boom")
    assert err.startswith("오류") and "boom" in err
    assert status_dot_kind("connected") == "ok"
    assert status_dot_kind("connecting") == "partial"
    assert status_dot_kind("disconnected") == "error"
    assert status_dot_kind("error") == "error"
    print("voice_runtime_status ok")


if __name__ == "__main__":
    main()
