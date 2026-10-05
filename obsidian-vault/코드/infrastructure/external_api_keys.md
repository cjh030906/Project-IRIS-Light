# external_api_keys

`iris/infrastructure/external_api_keys.py`

검색·캘린더 외부 API 키 — Hermes/Iris .env 읽기·저장 + 발급 링크.

## 주요 정의

- `class SearchPreset`
- `class ApiKeyField`
- `def search_preset_by_id`
- `def parse_search_entry_ids`
- `def active_search_preset_id`
- `def search_env_keys`
- `def upsert_dotenv`
- `def load_search_api_keys`
- `def load_search_preset_id`
- `def load_search_entries`
- `def save_search_api_keys`
- `def apply_hermes_search_backend`
- `def load_calendar_api_key`
- `def save_calendar_api_key`
- `def _read_iris_env_key`
- `def _check_backend_splice`

## 내부 의존성

- [[hermes_credentials]]
- [[settings]]
