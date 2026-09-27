"""모니터링 패널 (unified_monitor_panel, system_metrics_panel, live_activity_panel, chat_history_panel).

Agent-readable:
- Owns: 모니터·라이브 액티비티·채팅 기록 패널.
- Does not: 창 감지·알림 정책 (`iris/monitoring`).
- Talks to: `iris/monitoring`, MainWindow.
- Extend via: 패널은 여기. 정책은 `iris/monitoring`.
"""
