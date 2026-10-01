"""Explorer → Iris 파일 드롭 — 메인 HWND OLE가 침묵할 때의 Qt 우회.

원인: frameless 메인 HWND에 Explorer IDropTarget.DragEnter가 도달하지 않음.
금지: nativeEvent / QAbstractNativeEventFilter / WNDPROC.

우회: 외부 LMB 드래그가 Iris 위에 있을 때만 별도 Qt Tool 창을 띄운다.
Companion/Opening IDE 중에는 overlay를 올리지 않는다 — Tool+embedded IDE HWND가
0xC0000409 즉사를 유발.
"""

from __future__ import annotations

import sys

from PyQt6.QtCore import QEvent, QObject, QPoint, QRect, Qt, QTimer
from PyQt6.QtGui import QColor, QCursor, QDragEnterEvent, QDropEvent, QPalette
from PyQt6.QtWidgets import QLabel, QVBoxLayout, QWidget

from iris.ui.window.file_drop import log_drop_event, mime_has_attachable, paths_from_mime

_POLL_MS = 16
_VK_LBUTTON = 0x01
# 불투명 색만 쓴다. setWindowOpacity / rgba는 WS_EX_LAYERED가 되어 OLE 드롭이 죽는다.
_IDLE_BG = "#121c30"
_ACTIVE_BG = "#1a2944"
_HINT_TEXT = "파일을 여기에 놓아주세요"


def _lmb_down() -> bool:
    if sys.platform != "win32":
        from PyQt6.QtWidgets import QApplication

        app = QApplication.instance()
        return bool(app is not None and app.mouseButtons() & Qt.MouseButton.LeftButton)
    try:
        import ctypes

        return bool(ctypes.windll.user32.GetAsyncKeyState(_VK_LBUTTON) & 0x8000)
    except Exception:
        return False


def _qt_modal_blocking() -> bool:
    """네이티브 QFileDialog 중 overlay를 올리면 기동 즉사(0xC0000409)."""
    from PyQt6.QtGui import QGuiApplication
    from PyQt6.QtWidgets import QApplication

    app = QApplication.instance()
    if app is None:
        return False
    return app.activeModalWidget() is not None or QGuiApplication.modalWindow() is not None


def _iris_ide_root_hwnd(host: QWidget) -> int:
    win = getattr(host, "_iris_ide_window", None)
    if win is None or not win.isVisible():
        return 0
    try:
        return int(win.winId() or 0)
    except RuntimeError:
        return 0


def _drop_guard_paused(host: QWidget) -> bool:
    """IDE 기동·Opening 화면 중 overlay 금지."""
    worker = getattr(host, "_iris_ide_launch_worker", None)
    if worker is not None and worker.isRunning():
        return True
    win = getattr(host, "_iris_ide_window", None)
    if win is not None and win.isVisible():
        try:
            if win.is_opening():
                return True
        except (AttributeError, RuntimeError):
            pass
    return False


def _widget_global_rect(widget: QWidget | None) -> QRect:
    if widget is None:
        return QRect()
    try:
        if not widget.isVisible() or widget.width() < 40 or widget.height() < 40:
            return QRect()
        return QRect(widget.mapToGlobal(QPoint(0, 0)), widget.size())
    except RuntimeError:
        return QRect()


def drop_target_global_rect(host: QWidget) -> QRect:
    """채팅 패널만. Companion에서는 IDE HWND를 덮지 않는다."""
    chat = _widget_global_rect(getattr(host, "_chat", None))
    if not chat.isEmpty():
        return chat
    if getattr(host, "_iris_ide_unified", False):
        shell = getattr(host, "_unified_shell", None)
        if shell is not None:
            iris = _widget_global_rect(shell.iris_host())
            if not iris.isEmpty():
                return iris
        return QRect()
    try:
        return host.frameGeometry()
    except RuntimeError:
        return QRect()


def cursor_targets_iris_window(
    root_hwnd: int,
    *,
    host_hwnd: int,
    overlay_hwnd: int = 0,
    ide_hwnd: int = 0,
) -> bool:
    """커서가 이미 Iris 사각형 안일 때, 그 클릭이 Iris 것인지.

    root 0 = 히트 없음(드래그 고스트만). 좌표 폴백으로 True.
    다른 앱 창이 커서 아래면 False — 뒤에 있는 Iris를 띄우면 안 된다.
    """
    if root_hwnd == 0:
        return True
    if ide_hwnd and root_hwnd == ide_hwnd:
        return False
    if overlay_hwnd and root_hwnd == overlay_hwnd:
        return True
    if host_hwnd and root_hwnd == host_hwnd:
        return True
    return False


def _front_window_at_cursor() -> int:
    """커서 아래 실제 탑레벨 HWND. 투명·드래그 고스트는 건너뛴다. 없으면 0."""
    if sys.platform != "win32":
        return 0
    try:
        import ctypes
        from ctypes import wintypes

        class POINT(ctypes.Structure):
            _fields_ = (("x", wintypes.LONG), ("y", wintypes.LONG))

        class RECT(ctypes.Structure):
            _fields_ = (
                ("left", wintypes.LONG),
                ("top", wintypes.LONG),
                ("right", wintypes.LONG),
                ("bottom", wintypes.LONG),
            )

        user32 = ctypes.WinDLL("user32", use_last_error=True)
        user32.GetCursorPos.argtypes = [ctypes.POINTER(POINT)]
        user32.GetCursorPos.restype = wintypes.BOOL
        user32.GetTopWindow.argtypes = [wintypes.HWND]
        user32.GetTopWindow.restype = wintypes.HWND
        user32.GetWindow.argtypes = [wintypes.HWND, wintypes.UINT]
        user32.GetWindow.restype = wintypes.HWND
        user32.IsWindowVisible.argtypes = [wintypes.HWND]
        user32.IsWindowVisible.restype = wintypes.BOOL
        user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(RECT)]
        user32.GetWindowRect.restype = wintypes.BOOL
        get_exstyle = user32.GetWindowLongPtrW if ctypes.sizeof(ctypes.c_void_p) >= 8 else user32.GetWindowLongW
        get_exstyle.argtypes = [wintypes.HWND, ctypes.c_int]
        get_exstyle.restype = ctypes.c_ssize_t
        user32.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
        user32.GetClassNameW.restype = ctypes.c_int
        user32.GetAncestor.argtypes = [wintypes.HWND, wintypes.UINT]
        user32.GetAncestor.restype = wintypes.HWND

        pt = POINT()
        if not user32.GetCursorPos(ctypes.byref(pt)):
            return 0

        gwl_exstyle = -20
        ws_ex_transparent = 0x00000020
        gw_hwndnext = 2
        ga_root = 2

        def passthrough(hwnd: int) -> bool:
            ex = int(get_exstyle(hwnd, gwl_exstyle)) & 0xFFFFFFFF
            if ex & ws_ex_transparent:
                return True
            buf = ctypes.create_unicode_buffer(64)
            user32.GetClassNameW(hwnd, buf, 64)
            return (buf.value or "").lower() == "sysdragimage"

        def contains(hwnd: int) -> bool:
            rc = RECT()
            if not user32.GetWindowRect(hwnd, ctypes.byref(rc)):
                return False
            return rc.left <= pt.x < rc.right and rc.top <= pt.y < rc.bottom

        hwnd = user32.GetTopWindow(None)
        # ponytail: 탑레벨 z-order 한 바퀴. 천장 256 — 넘으면 히트 없음으로 좌표 폴백.
        for _ in range(256):
            if not hwnd:
                break
            cur = int(hwnd)
            nxt = user32.GetWindow(hwnd, gw_hwndnext)
            if user32.IsWindowVisible(hwnd) and contains(cur) and not passthrough(cur):
                root = int(user32.GetAncestor(hwnd, ga_root) or cur)
                return root
            hwnd = nxt
        return 0
    except Exception:
        return 0


def _cursor_on_drop_surface(host: QWidget, overlay: QWidget | None = None) -> bool:
    if _drop_guard_paused(host):
        return False
    rect = drop_target_global_rect(host)
    pos = QCursor.pos()
    if not rect.contains(pos):
        return False
    overlay_hwnd = 0
    if overlay is not None and overlay.isVisible():
        try:
            overlay_hwnd = int(overlay.winId() or 0)
        except RuntimeError:
            overlay_hwnd = 0
    try:
        host_hwnd = int(host.winId() or 0)
    except RuntimeError:
        host_hwnd = 0
    return cursor_targets_iris_window(
        _front_window_at_cursor(),
        host_hwnd=host_hwnd,
        overlay_hwnd=overlay_hwnd,
        ide_hwnd=_iris_ide_root_hwnd(host),
    )


class ExplorerDropOverlay(QWidget):
    """탐색기 파일만 받는 독립 Qt Drop Target. 부모는 항상 MainWindow."""

    def __init__(self, host: QWidget) -> None:
        super().__init__(host)
        self._host = host
        self._armed = False
        self._active = False
        self._logged_move = False
        self._windowed = False
        self._leave_gen = 0
        self.setObjectName("ExplorerDropOverlay")
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        # 생산 경로에서는 숨긴 자식이다. acceptDrops를 켜면 별도 HWND가
        # 탐색기 CF_HDROP을 메인 창 타깃보다 먼저 가져간다.
        self.setAcceptDrops(False)
        self.setAutoFillBackground(True)
        pal = self.palette()
        pal.setColor(self.backgroundRole(), QColor(_IDLE_BG))
        pal.setColor(QPalette.ColorRole.Window, QColor(_IDLE_BG))
        self.setPalette(pal)
        lay = QVBoxLayout(self)
        hint = QLabel(_HINT_TEXT)
        hint.setObjectName("ExplorerDropHint")
        hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        # 자식이 드롭을 받으면 QLabel 기본 ignore()가 탐색기 드롭을 거절한다.
        hint.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        hint.setAcceptDrops(False)
        lay.addWidget(hint)
        self._hint = hint
        self._apply_chrome(False)
        self.hide()

    def _ensure_windowed(self) -> None:
        if self._windowed:
            return
        self.setWindowTitle("")
        self.setWindowFlags(
            Qt.WindowType.Tool
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowDoesNotAcceptFocus
            | Qt.WindowType.NoDropShadowWindowHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, False)
        self.setAttribute(Qt.WidgetAttribute.WA_NativeWindow, True)
        self._windowed = True

    def _event_pos(self, event) -> QPoint:
        try:
            p = event.position()
            return QPoint(int(p.x()), int(p.y()))
        except Exception:
            try:
                return event.pos()
            except Exception:
                return QPoint(-1, -1)

    def _accept_if_files(self, event) -> bool:
        if not mime_has_attachable(getattr(event, "mimeData", lambda: None)()):
            return False
        try:
            event.setDropAction(Qt.DropAction.CopyAction)
            event.accept()
        except Exception:
            event.accept()
        return True

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:  # noqa: N802
        log_drop_event("DragEnter", event.mimeData(), watched=self, pos=self._event_pos(event))
        self._logged_move = False
        self._leave_gen += 1
        if self._accept_if_files(event):
            self._set_active(True)
            return
        event.ignore()

    def dragMoveEvent(self, event) -> None:  # noqa: N802
        if not self._logged_move:
            log_drop_event("DragMove", event.mimeData(), watched=self, pos=self._event_pos(event))
            self._logged_move = True
        if self._accept_if_files(event):
            return
        event.ignore()

    def dragLeaveEvent(self, event) -> None:  # noqa: N802
        log_drop_event("DragLeave", None, watched=self)
        self._set_active(False)
        # Drop 직전에 Leave가 오는 플랫폼이 있다. 잠시 기다렸다가 아직 안이면 끈다.
        self._leave_gen += 1
        gen = self._leave_gen
        QTimer.singleShot(80, lambda g=gen: self._disarm_if_left(g))
        super().dragLeaveEvent(event)

    def _disarm_if_left(self, gen: int) -> None:
        if gen != self._leave_gen or self._active or not self._armed:
            return
        pos = self.mapFromGlobal(QCursor.pos())
        if self.rect().contains(pos) and _lmb_down():
            return
        self.disarm()

    def dropEvent(self, event: QDropEvent) -> None:  # noqa: N802
        self._leave_gen += 1
        mime = event.mimeData()
        log_drop_event("Drop", mime, watched=self, pos=self._event_pos(event))
        paths = paths_from_mime(mime)
        attach = getattr(self._host, "_attach_os_drop_paths", None)
        ok = bool(paths) and callable(attach) and bool(attach(paths))
        if ok:
            try:
                event.setDropAction(Qt.DropAction.CopyAction)
                event.accept()
            except Exception:
                event.accept()
        else:
            event.ignore()
            log_drop_event("DropIgnored", mime, watched=self, pos=self._event_pos(event))
        self.disarm()

    def arm(self) -> None:
        if _drop_guard_paused(self._host):
            self.disarm()
            return
        if self._armed:
            self._sync_geom()
            return
        self._armed = True
        self._logged_move = False
        self.setAcceptDrops(True)
        self._ensure_windowed()
        self._set_active(False)
        self._sync_geom()
        self.show()
        self.raise_()
        try:
            from iris.ui.window.win_shell_drop import ensure_ole_drop_surface

            ensure_ole_drop_surface(int(self.winId()))
        except Exception:
            pass
        try:
            from iris.ui.window.win_shell_drop import hwnd_drop_debug, _log

            r = drop_target_global_rect(self._host)
            _log(
                f"overlay_arm {hwnd_drop_debug(int(self.winId()))} "
                f"rect={r.x()},{r.y()},{r.width()}x{r.height()}"
            )
        except Exception:
            pass

    def disarm(self) -> None:
        self._armed = False
        self._active = False
        self._logged_move = False
        self._leave_gen += 1
        self.hide()

    def _apply_chrome(self, active: bool) -> None:
        bg = _ACTIVE_BG if active else _IDLE_BG
        self.setStyleSheet(
            "QWidget#ExplorerDropOverlay {"
            f" background-color: {bg}; border: none;"
            "}"
            "QLabel#ExplorerDropHint {"
            " color: #e8eef7; font-size: 13px; background: transparent; border: none;"
            "}"
        )

    def _set_active(self, active: bool) -> None:
        # 창 투명도(setWindowOpacity)는 WS_EX_LAYERED라 탐색기 OLE가 거부된다.
        self._active = bool(active)
        self._apply_chrome(self._active)

    def _sync_geom(self) -> None:
        try:
            self.setGeometry(drop_target_global_rect(self._host))
        except RuntimeError:
            pass


class ExplorerDropGuard(QObject):
    """파일 드롭 타깃은 미리 있는 채팅 창이다.

    마우스 버튼을 누르고 있기만 해도 위에 창을 띄우면 두 가지가 깨진다.
    클릭만으로 「파일을 여기에 놓아주세요」가 나오고, 그 창은 드래그 도중에
    만들어져 탐색기 OLE가 금지 커서로 거절한다.
    안내는 실제 DragEnter에서만 채팅 힌트가 연다.
    """

    def __init__(self, host: QWidget) -> None:
        super().__init__(host)
        self._host = host
        self._overlay = ExplorerDropOverlay(host)
        self._press_inside = False
        self._timer = QTimer(self)
        self._timer.setInterval(_POLL_MS)
        self._timer.timeout.connect(self._tick)
        host.installEventFilter(self)

    def start(self) -> None:
        try:
            from iris.ui.window.win_shell_drop import hwnd_drop_debug, _log

            _log(f"overlay_guard_start host={hwnd_drop_debug(int(self._host.winId()))} poll=off")
        except Exception:
            pass
        self._timer.stop()
        self._overlay.disarm()

    def stop(self) -> None:
        self._timer.stop()
        self._overlay.disarm()

    def overlay(self) -> ExplorerDropOverlay:
        return self._overlay

    def eventFilter(self, watched: object, event: QEvent) -> bool:  # noqa: N802
        if watched is self._host:
            et = event.type()
            if et in (QEvent.Type.Move, QEvent.Type.Resize, QEvent.Type.WindowStateChange):
                if self._overlay._armed:
                    self._overlay._sync_geom()
        return False

    def _tick(self) -> None:
        # 왼쪽 버튼·커서 위치로는 열지 않는다. 파일 드래그와 클릭을 구분하지 못한다.
        if self._overlay._armed:
            self._overlay.disarm()
