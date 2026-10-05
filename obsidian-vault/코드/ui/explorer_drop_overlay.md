# explorer_drop_overlay

`iris/ui/window/explorer_drop_overlay.py`

Explorer → Iris 파일 드롭 — 메인 HWND OLE가 침묵할 때의 Qt 우회.

## 주요 정의

- `def _lmb_down`
- `def _qt_modal_blocking`
- `def _iris_ide_root_hwnd`
- `def _drop_guard_paused`
- `def drop_target_global_rect`
- `def cursor_targets_iris_window`
- `def _front_window_at_cursor`
- `def _cursor_on_drop_surface`
- `class ExplorerDropOverlay`
- `class ExplorerDropGuard`

## 내부 의존성

- [[file_drop]]
- [[win_shell_drop]]
