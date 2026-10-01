"""설정/프로필 다이얼로그 (settings_dialog, settings_service, user_profile_dialog).

Agent-readable:
- Owns: 설정·프로필 다이얼로그.
- Does not: SQLite 스키마 (`iris/storage`), 프로세스 기본값 (`iris/config`).
- Talks to: `iris/storage`, `iris/config/settings`.
- Extend via: 화면은 여기. 저장 헬퍼는 `iris/storage`.
"""
