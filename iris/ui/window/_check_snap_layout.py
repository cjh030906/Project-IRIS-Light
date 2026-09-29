"""윈도우 11 스냅 레이아웃 — □ 히트테스트와 프레임 두께 0."""

from __future__ import annotations

import sys

from PyQt6.QtCore import QRect, Qt
from PyQt6.QtWidgets import QApplication, QWidget

from iris.ui.window.frameless_chrome import (
    cursor_on_maximize_button,
    enable_windows_snap_caption,
    refresh_snap_button_rect,
    windows_snap_native_reply,
)


class _Probe(QWidget):
    def nativeEvent(self, eventType, message):  # noqa: N802
        reply = windows_snap_native_reply(self, message)
        if reply is not None:
            return reply
        return False, 0


def main() -> None:
    assert cursor_on_maximize_button(15, 12, QRect(10, 8, 30, 26))
    assert not cursor_on_maximize_button(0, 0, QRect(10, 8, 30, 26))
    assert not cursor_on_maximize_button(15, 12, QRect())

    if sys.platform != "win32":
        print("snap_layout check ok")
        return

    import ctypes
    from ctypes import wintypes

    app = QApplication.instance() or QApplication(sys.argv)
    host = _Probe()
    host.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Window)
    host.resize(480, 320)
    host.show()
    app.processEvents()
    enable_windows_snap_caption(host)
    app.processEvents()
    frame, geom = host.frameGeometry(), host.geometry()
    assert frame.width() == geom.width() and frame.height() == geom.height()

    user32 = ctypes.WinDLL("user32", use_last_error=True)
    style = user32.GetWindowLongW(int(host.winId()), -16) & 0xFFFFFFFF
    assert style & 0x00010000  # WS_MAXIMIZEBOX

    class MSG(ctypes.Structure):
        _fields_ = [
            ("hwnd", wintypes.HWND),
            ("message", wintypes.UINT),
            ("wParam", wintypes.WPARAM),
            ("lParam", wintypes.LPARAM),
            ("time", wintypes.DWORD),
            ("pt", wintypes.POINT),
        ]

    class Drag:
        def maximize_button_global_rect(self) -> QRect:
            return QRect(10, 8, 30, 26)

    class Win:
        _drag = Drag()
        toggled = False

        def _toggle_maximize(self) -> None:
            self.toggled = True

    hit = MSG()
    hit.message = 0x0084  # WM_NCHITTEST
    hit.lParam = (12 << 16) | 15
    hovered = Win()
    refresh_snap_button_rect(hovered)
    assert windows_snap_native_reply(hovered, ctypes.addressof(hit)) == (True, 9)
    miss = MSG()
    miss.message = 0x0084
    miss.lParam = 0
    assert windows_snap_native_reply(Win(), ctypes.addressof(miss)) is None

    up = MSG()
    up.message = 0x00A2  # WM_NCLBUTTONUP
    up.wParam = 9
    up.lParam = (12 << 16) | 15
    win = Win()
    refresh_snap_button_rect(win)
    assert windows_snap_native_reply(win, ctypes.addressof(up)) == (True, 0)
    assert win.toggled
    host.close()
    print("snap_layout check ok")


if __name__ == "__main__":
    main()
