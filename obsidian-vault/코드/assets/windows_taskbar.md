# windows_taskbar

`iris/assets/windows_taskbar.py`

Windows 작업표시줄 아이콘 — AppUserModelID + shortcut 등록/복구.

## 주요 정의

- `def _project_root`
- `def _launcher_exe`
- `def _start_menu_lnk`
- `def _all_users_start_menu_lnk`
- `def _pinned_taskbar_dirs`
- `def apply_windows_app_id`
- `def _send_window_icons`
- `def apply_hwnd_branding`
- `def _read_shell_link`
- `def _is_blocked_foreign_target`
- `def _args_launch_iris_module`
- `def _is_iris_owned_shortcut`
- `def _write_shell_link`
- `def _set_lnk_app_id`
- `def _canonical_launch_target`
- `def write_branded_shortcut`
- `def repair_pinned_taskbar_shortcuts`
- `def ensure_windows_taskbar_branding`
- `def install_all_shortcuts`
- `def _self_check`

## 내부 의존성

- [[branding]]
