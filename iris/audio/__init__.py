"""오디오 유틸 (마이크·VAD·PCM·Voice Runtime 클라이언트).

Agent-readable:
- Owns: 마이크, VAD, PCM, Voice Runtime HTTP 클라이언트.
- Does not: STT/TTS 모델 가중치 (`services/voice_runtime`).
- Talks to: Voice Runtime `:18765`, UI 파형.
- Extend via: 모델·서버는 `services/voice_runtime`. 클라이언트는 이 패키지.
"""
