"""프레임리스 창 가장자리 리사이즈."""

from __future__ import annotations

import sys

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QCursor, QMouseEvent
from PyQt6.QtWidgets import QApplication, QWidget

from iris.ui.shared.theme_tokens import TOKENS

_RESIZE_MARGIN = 8

# 가장자리 그립 배치 순서: TL, T, TR, L, R, BL, B, BR
_GRIP_EDGES: tuple[Qt.Edge, ...] = (
    Qt.Edge.TopEdge | Qt.Edge.LeftEdge,
    Qt.Edge.TopEdge,
    Qt.Edge.TopEdge | Qt.Edge.RightEdge,
    Qt.Edge.LeftEdge,
    Qt.Edge.RightEdge,
    Qt.Edge.BottomEdge | Qt.Edge.LeftEdge,
    Qt.Edge.BottomEdge,
    Qt.Edge.BottomEdge | Qt.Edge.RightEdge,
)


def _cursor_for_edges(edges: Qt.Edge) -> Qt.CursorShape:
    has_l = bool(edges & Qt.Edge.LeftEdge)
    has_r = bool(edges & Qt.Edge.RightEdge)
    has_t = bool(edges & Qt.Edge.TopEdge)
    has_b = bool(edges & Qt.Edge.BottomEdge)
    if has_t and has_l or has_b and has_r:
        return Qt.CursorShape.SizeFDiagCursor
    if has_t and has_r or has_b and has_l:
        return Qt.CursorShape.SizeBDiagCursor
    if has_l or has_r:
        return Qt.CursorShape.SizeHorCursor
    if has_t or has_b:
        return Qt.CursorShape.SizeVerCursor
    return Qt.CursorShape.ArrowCursor


def suppress_native_window_border(window: QWidget) -> None:
    """Windows DWM 1px 테두리 제거 — frameless 창."""
    if sys.platform != "win32":
        return
    try:
        hwnd = int(window.winId())
    except (AttributeError, TypeError, RuntimeError):
        return
    if hwnd == 0:
        return
    try:
        import ctypes

        dwm = ctypes.windll.dwmapi
        # DWMWA_BORDER_COLOR — Win11 기본 리사이즈 테두리 숨김
        border_color = ctypes.c_uint(0xFFFFFFFE)  # DWMWA_COLOR_NONE
        dwm.DwmSetWindowAttribute(
            hwnd,
            34,
            ctypes.byref(border_color),
            ctypes.sizeof(border_color),
        )
        # DWMWA_NCRENDERING_POLICY = DWMNCRP_DISABLED
        policy = ctypes.c_int(1)
        dwm.DwmSetWindowAttribute(
            hwnd,
            2,
            ctypes.byref(policy),
            ctypes.sizeof(policy),
        )
    except (OSError, AttributeError):
        pass


def _colorref(hex_color: str) -> int:
    """Qt hex(#RRGGBB) → Win32 COLORREF(0x00BBGGRR)."""
    c = QColor(hex_color)
    return (c.blue() << 16) | (c.green() << 8) | c.red()


def force_dark_titlebar(window: QWidget) -> None:
    """네이티브 타이틀바(설정/프로필/시작 프로토콜 등 QDialog용)를 앱 다크 테마로 고정.

    프레임리스가 아닌 대화상자는 Windows가 타이틀바를 직접 그리므로, 사용자의
    OS 라이트모드·강조색 설정에 따라 PC마다 맨 위쪽 색이 달라 보였다. 이 설정과
    무관하게 항상 동일하게 보이도록 DWM에 다크모드 + 앱 색상을 강제한다.
    """
    if sys.platform != "win32":
        return
    try:
        hwnd = int(window.winId())
    except (AttributeError, TypeError, RuntimeError):
        return
    if hwnd == 0:
        return
    try:
        import ctypes

        dwm = ctypes.windll.dwmapi
        use_dark = ctypes.c_int(1)
        for attr in (20, 19):  # DWMWA_USE_IMMERSIVE_DARK_MODE — 신/구 빌드 호환
            dwm.DwmSetWindowAttribute(hwnd, attr, ctypes.byref(use_dark), ctypes.sizeof(use_dark))
        # Win11 22000+ 전용 — 실패해도 위 다크모드 설정으로 대부분 충분히 일관됨
        caption = ctypes.c_uint(_colorref(TOKENS.space_deep))
        dwm.DwmSetWindowAttribute(hwnd, 35, ctypes.byref(caption), ctypes.sizeof(caption))  # DWMWA_CAPTION_COLOR
        text_color = ctypes.c_uint(_colorref(TOKENS.text_primary))
        dwm.DwmSetWindowAttribute(hwnd, 36, ctypes.byref(text_color), ctypes.sizeof(text_color))  # DWMWA_TEXT_COLOR
    except (OSError, AttributeError):
        pass


class _ResizeGrip(QWidget):
    """투명 리사이즈 핸들 — startSystemResize 위임."""

    def __init__(self, host: QWidget, edges: Qt.Edge, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._host = host
        self._edges = edges
        self.setCursor(QCursor(_cursor_for_edges(edges)))
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, False)
        self.setStyleSheet("background: transparent; border: none;")

    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton and not self._host.isMaximized():
            handle = self._host.windowHandle()
            if handle is not None and handle.startSystemResize(self._edges):
                event.accept()
                return
        super().mousePressEvent(event)


class FramelessShell(QWidget):
    """콘텐츠를 창 전체에 깔고 가장자리 리사이즈 그립만 겹친다."""

    def __init__(
        self,
        host: QWidget,
        margin: int = _RESIZE_MARGIN,
        parent: QWidget | None = None,
        *,
        inset_content: bool = False,
    ) -> None:
        super().__init__(parent)
        self._host = host
        self._margin = margin
        # QWebEngine 자식 HWND는 겹친 Qt 위젯 클릭을 삼킨다. IDE는 본문을 안으로 넣어 그립을 밖에 둔다.
        self._inset_content = inset_content
        self.setObjectName("FramelessShell")
        # ponytail: WA_TranslucentBackground면 Win32가 알파0 픽셀로 DnD 히트테스트를
        # 통과시켜 탐색기 드롭이 금지 커서만 보인다. 불투명 배경으로 OLE 타겟 유지.
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, False)
        self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent, True)
        self.setAutoFillBackground(True)
        pal = self.palette()
        pal.setColor(self.backgroundRole(), QColor(TOKENS.void_black))
        self.setPalette(pal)
        self.setStyleSheet(
            f"QWidget#FramelessShell {{ background-color: {TOKENS.void_black}; border: none; }}"
        )
        self._content: QWidget | None = None
        self._grips: list[_ResizeGrip] = []

    def set_center_widget(self, content: QWidget) -> None:
        """본문을 전체 영역에 배치하고 투명 리사이즈 그립을 가장자리에 겹친다."""
        self._content = content
        content.setParent(self)
        content.lower()

        for edges in _GRIP_EDGES:
            grip = _ResizeGrip(self._host, edges, self)
            self._grips.append(grip)

        self._sync_layout()

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._sync_layout()

    def set_left_grips_visible(self, visible: bool) -> None:
        """Companion 80:20 — IDE와 맞닿은 왼쪽 가장자리 리사이즈 그립 숨김."""
        if len(self._grips) < 6:
            return
        for idx in (0, 3, 5):
            self._grips[idx].setVisible(visible)

    def set_companion_grip_mode(self, active: bool) -> None:
        """Companion A: 좌·하단 전폭 grip 숨김 — Theia 터미널/채팅 입력 보호.

        indices: 0=TL 1=T 2=TR 3=L 4=R 5=BL 6=B 7=BR
        """
        if len(self._grips) < 8:
            return
        if active:
            for idx in (0, 3, 5, 6):
                self._grips[idx].setVisible(False)
            for idx in (1, 2, 4, 7):
                self._grips[idx].setVisible(True)
        else:
            for grip in self._grips:
                grip.setVisible(True)

    def _sync_layout(self) -> None:
        if self._content is not None:
            if self._inset_content:
                m = self._margin
                self._content.setGeometry(
                    m,
                    m,
                    max(1, self.width() - 2 * m),
                    max(1, self.height() - 2 * m),
                )
            else:
                self._content.setGeometry(0, 0, self.width(), self.height())

        if not self._grips:
            return

        m = self._margin
        w, h = max(self.width(), 1), max(self.height(), 1)
        inner_w = max(1, w - 2 * m)
        inner_h = max(1, h - 2 * m)
        rects = (
            (0, 0, m, m),
            (m, 0, inner_w, m),
            (w - m, 0, m, m),
            (0, m, m, inner_h),
            (w - m, m, m, inner_h),
            (0, h - m, m, m),
            (m, h - m, inner_w, m),
            (w - m, h - m, m, m),
        )
        for grip, (x, y, gw, gh) in zip(self._grips, rects, strict=True):
            grip.setGeometry(x, y, gw, gh)
            grip.raise_()


# 윈도우 11 스냅 레이아웃 — 커스텀 □ 위를 HTMAXBUTTON으로 알린다.
# ponytail: 탐색기 드롭 수신·창 프로시저 교체는 기동 즉사라 여기 두지 않는다.
_WM_NCCALCSIZE = 0x0083
_WM_NCHITTEST = 0x0084
_WM_NCLBUTTONDOWN = 0x00A1
_WM_NCLBUTTONUP = 0x00A2
_HTMAXBUTTON = 9
_GWL_STYLE = -16
_SNAP_STYLE = 0x00C00000 | 0x00040000 | 0x00010000 | 0x00020000 | 0x00080000  # CAPTION|THICKFRAME|MAX|MIN|SYSMENU
_SWP_FRAME = 0x0020 | 0x0002 | 0x0001 | 0x0004 | 0x0010


def _msg_type():
    import ctypes
    from ctypes import wintypes

    class MSG(ctypes.Structure):
        _fields_ = [
            ("hwnd", wintypes.HWND),
            ("message", wintypes.UINT),
            ("wParam", wintypes.WPARAM),
            ("lParam", wintypes.LPARAM),
            ("time", wintypes.DWORD),
            ("pt", wintypes.POINT),
        ]

    return MSG


_MSG = _msg_type() if sys.platform == "win32" else None


def _win_msg(message: int):
    return _MSG.from_address(int(message))


def _lparam_xy(lparam: int) -> tuple[int, int]:
    import ctypes

    x = ctypes.c_short(lparam & 0xFFFF).value
    y = ctypes.c_short((lparam >> 16) & 0xFFFF).value
    return int(x), int(y)


def cursor_on_maximize_button(x: int, y: int, rect) -> bool:
    return bool(rect.isValid() and not rect.isEmpty() and rect.contains(x, y))


def enable_windows_snap_caption(window: QWidget) -> None:
    """프레임은 그대로 두고, 스냅 레이아웃이 요구하는 최대화 버튼 스타일만 켠다."""
    if sys.platform != "win32":
        return
    try:
        hwnd = int(window.winId())
    except (AttributeError, TypeError, RuntimeError):
        return
    if hwnd == 0:
        return
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.WinDLL("user32", use_last_error=True)
    user32.GetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int]
    user32.GetWindowLongW.restype = ctypes.c_long
    user32.SetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_long]
    user32.SetWindowLongW.restype = ctypes.c_long
    user32.SetWindowPos.argtypes = [
        wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int,
        ctypes.c_int, ctypes.c_int, ctypes.c_uint,
    ]
    style = user32.GetWindowLongW(hwnd, _GWL_STYLE)
    if (style & _SNAP_STYLE) != _SNAP_STYLE:
        user32.SetWindowLongW(hwnd, _GWL_STYLE, style | _SNAP_STYLE)
        user32.SetWindowPos(hwnd, 0, 0, 0, 0, 0, _SWP_FRAME)
    suppress_native_window_border(window)


def _fit_maximized_client(hwnd: int, lparam: int) -> None:
    import ctypes
    from ctypes import wintypes

    class RECT(ctypes.Structure):
        _fields_ = [
            ("left", ctypes.c_long),
            ("top", ctypes.c_long),
            ("right", ctypes.c_long),
            ("bottom", ctypes.c_long),
        ]

    class MONITORINFO(ctypes.Structure):
        _fields_ = [
            ("cbSize", wintypes.DWORD),
            ("rcMonitor", RECT),
            ("rcWork", RECT),
            ("dwFlags", wintypes.DWORD),
        ]

    user32 = ctypes.WinDLL("user32", use_last_error=True)
    user32.IsZoomed.argtypes = [wintypes.HWND]
    user32.IsZoomed.restype = wintypes.BOOL
    if not user32.IsZoomed(hwnd):
        return
    user32.MonitorFromWindow.argtypes = [wintypes.HWND, wintypes.DWORD]
    user32.MonitorFromWindow.restype = wintypes.HMONITOR
    user32.GetMonitorInfoW.argtypes = [wintypes.HMONITOR, ctypes.c_void_p]
    user32.GetMonitorInfoW.restype = wintypes.BOOL
    info = MONITORINFO()
    info.cbSize = ctypes.sizeof(MONITORINFO)
    mon = user32.MonitorFromWindow(hwnd, 2)
    if not user32.GetMonitorInfoW(mon, ctypes.byref(info)):
        return
    rect = RECT.from_address(int(lparam))
    work = info.rcWork
    if rect.top < work.top or rect.left < work.left or rect.right > work.right or rect.bottom > work.bottom:
        rect.left, rect.top, rect.right, rect.bottom = work.left, work.top, work.right, work.bottom


def refresh_snap_button_rect(window: QWidget) -> None:
    """□ 화면 좌표를 미리 저장. nativeEvent 안에서 mapToGlobal 하면 콜백이 죽는다."""
    direct = getattr(window, "maximize_button_global_rect", None)
    drag = getattr(window, "_drag", None)
    via = getattr(drag, "maximize_button_global_rect", None)
    fn = direct if callable(direct) else via
    if not callable(fn):
        window._snap_btn_rect = None
        return
    try:
        window._snap_btn_rect = fn()
    except Exception:
        window._snap_btn_rect = None


def _snap_button_rect(window: QWidget):
    return getattr(window, "_snap_btn_rect", None)


def windows_snap_native_reply(window: QWidget, message) -> tuple[bool, int] | None:
    """□ 위 커서는 HTMAXBUTTON. 그 외 메시지는 건드리지 않는다."""
    if sys.platform != "win32" or message is None:
        return None
    try:
        return _windows_snap_native_reply(window, message)
    except Exception:
        return None


def _windows_snap_native_reply(window: QWidget, message) -> tuple[bool, int] | None:
    try:
        msg = _win_msg(message)
    except (TypeError, ValueError, OverflowError):
        return None
    mid = int(msg.message)
    if mid == _WM_NCCALCSIZE and int(msg.wParam):
        _fit_maximized_client(int(msg.hwnd), int(msg.lParam))
        return True, 0
    if mid == _WM_NCHITTEST:
        rect = _snap_button_rect(window)
        if rect is None:
            return None
        x, y = _lparam_xy(int(msg.lParam))
        if cursor_on_maximize_button(x, y, rect):
            return True, _HTMAXBUTTON
        return None
    if mid in (_WM_NCLBUTTONDOWN, _WM_NCLBUTTONUP) and int(msg.wParam) == _HTMAXBUTTON:
        if mid == _WM_NCLBUTTONUP:
            rect = _snap_button_rect(window)
            x, y = _lparam_xy(int(msg.lParam))
            on_btn = rect is not None and cursor_on_maximize_button(x, y, rect)
            toggle = getattr(window, "_toggle_maximize", None)
            if on_btn and callable(toggle):
                toggle()
        return True, 0
    return None


def center_on_screen(widget: QWidget) -> None:
    """주 모니터 가용 영역 중앙에 배치."""
    try:
        screen = QApplication.primaryScreen()
        if screen is None:
            return
        area = screen.availableGeometry()
        widget.move(
            area.x() + max(0, (area.width() - widget.width()) // 2),
            area.y() + max(0, (area.height() - widget.height()) // 2),
        )
    except RuntimeError:
        pass
