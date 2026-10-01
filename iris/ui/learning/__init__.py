"""학습 안내 UI (VLM 가이드 다이얼로그).

Agent-readable:
- Owns: 학습 관련 다이얼로그.
- Does not: 녹화·Aloha 실행 (`iris/learning`).
- Talks to: `LearningManager`, 학습 액션.
- Extend via: 동작은 `iris/learning`. 이 패키지는 안내 UI만.
"""
