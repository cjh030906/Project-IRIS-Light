# source_launch

`iris/system/source_launch.py`

개발 소스 우선 실행 — frozen EXE도 저장소 .venv가 있으면 최신 코드로 넘긴다.

## 주요 정의

- `def _env_truthy`
- `def looks_like_repo`
- `def resolve_repo_root_from_frozen`
- `def resolve_venv_python`
- `def should_prefer_source`
- `def reexec_to_source_if_available`
