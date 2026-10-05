# app_update

`iris/system/app_update.py`

GitHub main 대비 앱 소스 업데이트 감지·적용.

## 주요 정의

- `class UpdateStatus`
- `def revision_path`
- `def update_state_path`
- `def _load_state`
- `def _save_state`
- `def read_local_sha`
- `def write_local_sha`
- `def fetch_remote_sha`
- `def check_for_update`
- `def _git_ff_update`
- `def _should_preserve`
- `def _overlay_tree`
- `def _zip_overlay_update`
- `def apply_update`
- `def _self_check`

## 내부 의존성

- [[hermes_iris_control_sync]]
