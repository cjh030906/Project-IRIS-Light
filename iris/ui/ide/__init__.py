"""IRIS IDE PyQt 셸 헬퍼.

Agent-readable:
- Owns: IDE 셸 보조 UI.
- Does not: 8:2 타일 (`iris/system/ide_tiler`), Theia 런타임 (`integrations/iris-ide`).
- Talks to: IDE 워크스페이스 페이지.
- Extend via: `integrations/iris-ide` 또는 이 패키지. Companion 정수 픽셀 계약은 유지.
"""
