"""Iris 정적 자산 (앱 아이콘, IDE 로고 등).

Agent-readable:
- Owns: 아이콘·로고 경로 (`branding`, `setup_logos`, `windows_taskbar`).
- Does not: 창 배치, 런타임 설치.
- Talks to: UI와 설치 마법사가 경로를 읽음.
- Extend via: 자산은 이 패키지, 노출은 `branding`.
"""
