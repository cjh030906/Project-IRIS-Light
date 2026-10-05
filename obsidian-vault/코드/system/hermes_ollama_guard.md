# hermes_ollama_guard

`iris/system/hermes_ollama_guard.py`

Hermes custom 프로파일의 Ollama 전용 ``options.num_ctx`` 가드.

## 주요 정의

- `def looks_like_ollama_endpoint`
- `def apply_ollama_options_guard`
- `def sync_model_ollama_num_ctx`
- `def note_after_provider_direct_ok`
- `def _error_blob`
- `def _redact`
- `def _is_options_400`

## 내부 의존성

- [[api_providers]]
- [[hermes_client]]
- [[hermes_credentials]]
- [[hermes_gateway]]
- [[setup_protocol]]
