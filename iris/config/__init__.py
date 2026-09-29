"""프로세스 설정.

Agent-readable:
- Owns: 설정 객체 (`settings.py`).
- Does not: SQLite 프로필·메일 계정 (`iris/storage`).
- Talks to: UI, Gateway, 인프라 클라이언트.
- Extend via: 설정 키는 `settings.py`. 비밀은 `.env` / `secret_store`.
"""
