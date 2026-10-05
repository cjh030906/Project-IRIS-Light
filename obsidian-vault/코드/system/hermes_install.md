# hermes_install

`iris/system/hermes_install.py`

Hermes Windows 설치 우회 — uv managed Python junction(WinError 448) 회피.

## 주요 정의

- `def looks_like_uv_python_mount_failure`
- `def _no_window`
- `def _run`
- `def python_version`
- `def is_supported_hermes_python`
- `def find_bootstrap_python`
- `def ensure_system_python_winget`
- `def _kill_hermes_tree_holders`
- `def force_retire_hermes_agent`
- `def _user_path_prepend`
- `def combined_install_log_tail`
- `def last_bypass_log_path`
- `def new_bypass_pip_log_path`
- `def write_bypass_pip_log`
- `def format_pip_failure`
- `def format_runtime_failure`
- `def clip_needs_user_message`
- `def should_skip_official_installer`
- `def _run_pkg_install`
- `def _try_uv_sync`
- `def _guard_installed_agent`
- `def _swap_staging_into_place`
- `def install_hermes_with_system_python`

## 내부 의존성

- [[hermes_iris_control_sync]]
- [[hermes_ollama_guard]]
- [[system]]
