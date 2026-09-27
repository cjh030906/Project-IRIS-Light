"""Human-Taught Computer-Use — ShowUI-Aloha 기반 업무 학습.

Agent-readable:
- Owns: 녹화, 워크플로, Aloha 학습·실행 (`LearningManager`).
- Does not: ShowUI-Aloha 프로세스 내부, PyQt 페이지.
- Talks to: `integrations/showui-aloha`, `aloha_adapter`, 학습 UI.
- Extend via: 이벤트 변환은 `aloha_adapter.py`. 새 학습 UI는 `iris/ui`.
"""

from __future__ import annotations

from iris.learning.models import LearningState, LearnedWorkflow, WorkflowRun
from iris.learning.manager import LearningManager

__all__ = [
    "LearningManager",
    "LearningState",
    "LearnedWorkflow",
    "WorkflowRun",
]
