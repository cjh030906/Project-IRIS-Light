# ide_link

`iris/system/ide_link.py`

IDE 연동 경계. 명령과 편집기 상태 알림을 나누고, 토큰·타임아웃·재연결은 여기만 안다.

## 주요 정의

- `def query_failure`
- `def editor_path`
- `class PageIdentity`
- `class IdeLink`
- `def _query_error`
- `def shared_ide_link`

## 내부 의존성

- [[iris_ide_client]]
- [[iris_ide_runtime]]
