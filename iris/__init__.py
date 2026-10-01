"""IRIS Light — 클라우드/API 중심 Iris UI 셸.

Agent-readable:
- Owns: 앱 패키지 루트와 `__version__`.
- Does not: 창, Gateway, 모델 호출.
- Talks to: `python -m iris` → `iris.ui`.
- Extend via: 하위 패키지. 절차는 `docs/guides/extending-iris.md`.
"""

__version__ = "0.1.0-light"
