# hermes_errors

`iris/infrastructure/hermes_errors.py`

Hermes 채팅 오류 분류 — 게이트웨이 Bearer vs Ollama 클라우드 401.

## 주요 정의

- `def is_cloud_runtime_name`
- `def looks_like_upstream_unauthorized`
- `def looks_like_no_tools_error`
- `def format_hermes_sse_error`
- `def format_hermes_http_401`
- `def is_cloud_auth_user_message`
- `def cloud_model_blocked_without_login`
- `def resolve_initial_model`

## 내부 의존성

- [[api_providers]]
- [[ollama_client]]
- [[ollama_usage]]
- [[setup_protocol]]
