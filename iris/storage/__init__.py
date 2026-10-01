"""로컬 SQLite 저장소.

Agent-readable:
- Owns: `~/.iris-light` 대화·프로필·설정·메일 계정·비밀.
- Does not: Hermes 메모리, 모델 가중치.
- Talks to: UI·시스템·인프라의 DB 헬퍼.
- Extend via: 헬퍼는 이 패키지. UI에서 SQL을 직접 열지 말 것.
"""
