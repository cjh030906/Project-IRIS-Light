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
_ARMED_OPACITY = 0.06
_ACTIVE_OPACITY = 0.28
_VK_LBUTTON = 0x01


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


def drop_target_global_rect(host: QWidget) -> QRect:
    """Companion 8:2 — 우측 Iris(채팅)만. 전체 frame은 embedded IDE HWND를 덮는다."""
    if getattr(host, "_iris_ide_unified", False):
        shell = getattr(host, "_unified_shell", None)
        if shell is not None:
            iris = shell.iris_host()
            if iris is not None and iris.isVisible() and iris.width() > 0 and iris.height() > 0:
                top_left = iris.mapToGlobal(QPoint(0, 0))
                return QRect(top_left, iris.size())
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
        self._logged_move = False
        self._windowed = False
        self.setObjectName("ExplorerDropOverlay")
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setAcceptDrops(True)
        self.setAutoFillBackground(True)
        pal = self.palette()
        pal.setColor(self.backgroundRole(), QColor(8, 18, 36))
        pal.setColor(QPalette.ColorRole.Window, QColor(8, 18, 36))
        self.setPalette(pal)
        self.setStyleSheet(
            "QWidget#ExplorerDropOverlay { background-color: #081224; border: 2px dashed #38bdf8; }"
            "QLabel#ExplorerDropHint { color: #e8f0fe; font-size: 14px; }"
        )
        lay = QVBoxLayout(self)
        hint = QLabel("파일을 놓으면 첨부됩니다")
        hint.setObjectName("ExplorerDropHint")
        hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(hint)
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
        super().dragLeaveEvent(event)

    def dropEvent(self, event: QDropEvent) -> None:  # noqa: N802
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
        self._ensure_windowed()
        self._set_active(False)
        self._sync_geom()
        self.show()
        self.raise_()
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
        self._logged_move = False
        self.hide()

    def _set_active(self, active: bool) -> None:
        self.setWindowOpacity(_ACTIVE_OPACITY if active else _ARMED_OPACITY)

    def _sync_geom(self) -> None:
        try:
            self.setGeometry(drop_target_global_rect(self._host))
        except RuntimeError:
            pass


class ExplorerDropGuard(QObject):
    """외부 파일 드래그일 때만 overlay를 연다. IDE companion 드래그는 건드리지 않음."""

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

            _log(f"overlay_guard_start host={hwnd_drop_debug(int(self._host.winId()))}")
        except Exception:
            pass
        self._timer.start()

    def stop(self) -> None:
        self._timer.stop()
        self._overlay.disarm()

    def overlay(self) -> ExplorerDropOverlay:
        return self._overlay

    def eventFilter(self, watched: object, event: QEvent) -> bool:  # noqa: N802
        if watched is self._host:
            et = event.type()
            if et == QEvent.Type.MouseButtonPress and getattr(event, "button", lambda: None)() == Qt.MouseButton.LeftButton:
                self._press_inside = True
            elif et in (QEvent.Type.MouseButtonRelease, QEvent.Type.Leave):
                if et == QEvent.Type.MouseButtonRelease:
                    self._press_inside = False
            elif et in (QEvent.Type.Move, QEvent.Type.Resize, QEvent.Type.WindowStateChange):
                if self._overlay._armed:
                    self._overlay._sync_geom()
        return False

    def _tick(self) -> None:
        if _drop_guard_paused(self._host):
            self._overlay.disarm()
            return
        if not _lmb_down():
            self._press_inside = False
            if self._overlay._armed:
                self._overlay.disarm()
            return
        if self._press_inside:
            return
        if getattr(self._host, "_pending_ide_drag", None):
            return
        if _qt_modal_blocking():
            self._overlay.disarm()
            return
        try:
            if not self._host.isVisible() or self._host.isMinimized():
                self._overlay.disarm()
                return
            if not _cursor_on_drop_surface(self._host, self._overlay):
                self._overlay.disarm()
                return
        except RuntimeError:
            self._overlay.disarm()
            return
        self._overlay.arm()
