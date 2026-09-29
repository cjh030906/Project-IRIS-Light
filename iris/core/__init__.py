"""채팅 텍스트 유틸.

Agent-readable:
- Owns: 블록 파싱, 인용, 마크다운 텍스트, 활동 싱크.
- Does not: HTTP, 위젯, 턴 디스패치.
- Talks to: UI 렌더.
- Extend via: 파서·텍스트만. 턴 큐는 `iris/runtime`.
"""
