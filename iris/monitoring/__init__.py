"""창·화면 모니터와 알림 정책.

Agent-readable:
- Owns: 모니터 상태, 알림 정책, 핀, 통화 모니터.
- Does not: 채팅 추론, 메일 전송.
- Talks to: `iris/ui/monitor`, 음성 낭독(옵션).
- Extend via: 정책·모델은 이 패키지. 패널은 `iris/ui/monitor`.
"""
