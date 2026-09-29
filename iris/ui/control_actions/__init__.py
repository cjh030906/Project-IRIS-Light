"""기능별 Control 액션. 호스트는 Protocol이고 MainWindow를 import하지 않는다.

Agent-readable:
- Owns: `register_*` 가 `ActionRegistry`에 올리는 액션 이름.
- Does not: HTTP 서버 (`iris/system/control_surface`).
- Talks to: Host Protocol (`hosts.py`), Control Surface.
- Extend via: 기능 파일의 `register_*`. 가능하면 기존 액션을 스킬에서만 호출.
"""
