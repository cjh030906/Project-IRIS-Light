"""재사용 leaf 위젯 (drag_tab, mic_*, particle_visualizer, context_ring, ide_icons 등).

Agent-readable:
- Owns: 부모 기능에 붙는 작은 위젯.
- Does not: 세션, Gateway, 워크스페이스 상태.
- Talks to: chat · window · sidebar.
- Extend via: 재사용 조각만 여기. 화면 흐름은 해당 기능 패키지.
"""
