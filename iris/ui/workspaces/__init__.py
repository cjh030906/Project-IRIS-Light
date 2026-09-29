"""워크스페이스 페이지 (Assistant · Email · Calendar · Wiki · IDE).

Agent-readable:
- Owns: 워크스페이스 페이지 위젯.
- Does not: 메일/캘린더 HTTP (`iris/infrastructure`), Wiki 저장 (`iris/knowledge`).
- Talks to: MainWindow, 해당 인프라·저장 패키지.
- Extend via: 새 페이지는 이 패키지. Hermes 노출은 `iris/ui/control_actions`.
"""

from iris.ui.workspaces.assistant_workspace_page import AssistantWorkspacePage

__all__ = ["AssistantWorkspacePage"]
