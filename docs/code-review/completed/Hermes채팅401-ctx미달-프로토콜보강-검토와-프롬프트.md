# Hermes 채팅 401 · ctx 미달 — 실행 프로토콜 보강 검토 · 구현 프롬프트

> **작성**: 2026-09-24  
> **증상**: Core 프로토콜 통과 후 채팅에서  
> (1) `context window … 32,768 … below … 64,000`  
> (2) `HTTP 401: Unauthorized`  
> **관련**: `setup_protocol.py` (`hermes_env` / `hermes_provider` / `hermes_gateway` / `core_smoke`)

---

## 1. 검토 결론

| 항목 | 판정 | 이유 |
|------|------|------|
| **API 키 자동 맞춤** | **적합 (강화)** | 이미 `hermes_env` + `core_smoke` 401 재시도가 있음. 다만 **기존 키를 무조건 보존**하고, gateway가 **이미 떠 있으면 재기동 안 함** → 플레이스홀더·프로세스 불일치가 남음 |
| **ctx 64K 자동 상향** | **적합 (제한적)** | Hermes 업스트림이 `model.ollama_num_ctx`로 64K+를 허용. `_ollama_provider_model`에 넣기 자연스러움. **Modelfile 전면 재작성·전역 Ollama 서비스 재설치는 비적합** (VRAM·시간·부작용) |
| **새 Core 스텝 추가** | **비권장** | 기존 4스텝(`env`→`provider`→`gateway`→`smoke`)에 계약을 넣는 편이 YAGNI |

**한줄:** “프로토콜에서 자동으로”는 맞다. **신규 마법사가 아니라 기존 Core 스텝의 구멍만 메운다.**

---

## 2. 현재 PC에서 관측된 구멍

| # | 관측 | 영향 |
|---|------|------|
| A | `%LOCALAPPDATA%\hermes\.env` 의 `API_SERVER_KEY` 가 **짧은 플레이스홀더 형태** (`change-me…`, len≈18). `token_urlsafe(32)` 가 아님 | `_step_hermes_env`가 **비어 있을 때만** 생성 → 약한 키를 Iris·Hermes에 **그대로 동기화** |
| B | `_step_hermes_gateway`: gateway 이미 실행 중이면 **유지** (의도적 최적화) | `hermes_env`가 키를 바꿔도 **프로세스 메모리의 옛 키**와 불일치 → 채팅 401 |
| C | `core_smoke` 401 복구가 다시 `_step_hermes_env()`만 호출 → **같은 플레이스홀더 유지** | 재시도가 no-op |
| D | `_ollama_provider_model`에 `ollama_num_ctx` 없음. 사용자 `config.yaml`에 exaone 32K 모델 | Hermes `MINIMUM_CONTEXT_LENGTH`(64K)에 걸려 첫 발화 실패 |
| E | Ready=`quick`은 채팅 auth·ctx 미검사 | `last=full/OK`여도 이후 모델 변경·gateway 잔존으로 재발 가능 |

---

## 3. 적합 / 부적합 범위

### 적합 (프로토콜에 넣을 것)

1. **약한/플레이스홀더 키 감지 → 강제 재발급** 후 Hermes `.env` + `IRIS_HERMES_API_KEY` 동기화  
2. **키가 바뀌었거나 401이면 gateway 필수 restart** (`already running — 유지` 예외 해제)  
3. **`hermes_provider`에 `ollama_num_ctx: 64000`(또는 업스트림 상수와 동일) 명시**  
4. **`core_smoke`**: 401 시 **force rotate** + restart 후 재검증; 가능하면 ctx 미달 메시지를 실패 원인으로 분류  
5. (선택) `ollama_model` 단계에서 **native ctx ≥ 64K 모델 우선** 안내/선택 — 강제 pull은 네트워크 비용 있어 옵션

### 부적합 (넣지 말 것)

1. Ollama 전역 `OLLAMA_CONTEXT_LENGTH`를 설치마다 시스템 환경변수로 강제 (다른 앱·VRAM 영향)  
2. 모든 로컬 모델을 Modelfile로 64K 재빌드  
3. Hermes 업스트림 `MINIMUM_CONTEXT_LENGTH` 패치(포크)  
4. Ready=`quick`에 MCP·긴 채팅 추론을 넣기 (부팅 지연) — auth probe 짧은 것만 검토 가능  
5. 키가 이미 강하고 chat auth OK인데도 매번 rotate (세션 끊김)

---

## 4. Prompt (Agent 붙여넣기용)

아래 블록을 Cursor Agent에 그대로 붙여 넣으면 됩니다.

---

```text
Context:
- 저장소: Project-IRIS-Light (Windows / PyQt6)
- 검토 문서: docs/code-review/completed/Hermes채팅401-ctx미달-프로토콜보강-검토와-프롬프트.md (§1–3 필독)
- 증상: Core 프로토콜 통과 후 채팅에서
  (1) Hermes: Model … context window of 32,768 … below minimum 64,000
  (2) Hermes HTTP 401 Unauthorized
- 이미 있는 것 (회귀 금지·강화만):
  - CORE: hermes_env → hermes_provider → iris_control_sync → hermes_gateway → core_smoke
  - _step_hermes_env: API_SERVER_KEY 없으면 생성, Hermes .env + IRIS_HERMES_API_KEY upsert
  - _step_core_smoke: verify_core 실패에 "401" 있으면 hermes_env + hermes_gateway 1회 재시도
  - resolve_hermes_api_key: Hermes .env API_SERVER_KEY 우선
- 구멍 (이번 범위):
  - hermes_env가 기존 키를 무조건 보존 → 플레이스홀더(change-me 등) 잔존
  - hermes_gateway가 already-running이면 재기동 안 함 → env 변경 후 401
  - 401 재시도도 force rotate가 아니라 동일 키 재기록
  - _ollama_provider_model에 ollama_num_ctx 없음 → Hermes 64K 하한 미충족
- 핵심 파일:
  - iris/system/setup_protocol.py
    (_step_hermes_env, _ollama_provider_model, _step_hermes_provider,
     _step_hermes_gateway, _step_core_smoke, verify_core)
  - iris/infrastructure/hermes_credentials.py (필요 시 weak-key 헬퍼)
  - iris/infrastructure/ollama_client.py (model_context_length — 읽기만/재사용)
  - tests: 기존 setup/hermes 관련 unittest 확장 (새 프레임워크 금지)
- 업스트림 힌트: %LOCALAPPDATA%\hermes\hermes-agent 의
  MINIMUM_CONTEXT_LENGTH(=64000) + model.ollama_num_ctx 오버라이드
  (metadata가 32K여도 config 64K+면 통과하는 경로가 있음)

Goal:
실행(시작) 프로토콜 Core가 끝나면, 사용자가 「모델테스트」를 보냈을 때
(1) 401이 나지 않고 (2) 로컬 Ollama 모델이 Hermes 64K 하한에 걸리며
바로 실패하지 않게 한다. 신규 Core 스텝 ID는 추가하지 않는다.

Constraints:
- YAGNI: 키 강제정렬 + ollama_num_ctx + 401/키변경 시 gateway restart 만.
  Ollama 전역 env 강제, Modelfile 재빌드, Hermes 소스 패치, 새 위저드 화면 금지.
- Surgical: 위 파일·테스트·이 문서 상태 표만. 무관 리팩터·포맷 금지.
- _step_hermes_env:
  - 키가 없거나 **약한 키**면 secrets.token_urlsafe(32)로 교체.
  - 약한 키 판별(최소): 길이 < 24, 또는 lower가 change-me / changeme / replace-me /
    your-api-key / todo / placeholder / test / secret 포함, 또는 공백.
  - 강한 기존 키는 보존(불필요 rotate 금지).
  - 반환/상태에 key_rotated: bool 을 남기거나, 호출부가 “바뀌었는지” 알 수 있게 할 것.
  - 메시지·로그에 키 원문 금지 (기존 redact_secrets 유지).
- _step_hermes_gateway:
  - hermes_env에서 키가 rotate 되었거나, 호출자가 force_restart=True 이면
    already-running이어도 restart_hermes_gateway 필수.
  - 그 외에는 기존 “살아 있으면 유지” 최적화 유지 (매 설치 1–2분 지연 회귀 금지).
- _ollama_provider_model / hermes_provider:
  - model.ollama_num_ctx 를 int(64000) 이상으로 명시 upsert
    (이미 더 크면 유지, 없거나 작으면 64000).
  - provider/base_url/default 기존 계약 유지 (stale openai 등 덮어쓰기).
  - native ctx < 64K 모델이어도 config 오버라이드가 1차 목표.
    (VRAM OOM은 메시지/로그에 soft warn 가능, Core failed로 막지 말 것 —
     사용자가 큰 모델로 바꿀 여지.)
- _step_core_smoke:
  - 401(또는 probe_chat_auth unauthorized) 시:
    hermes_env(force_rotate=True) → hermes_gateway(force_restart=True) → verify_core 1회.
  - 기존 "401" in detail 문자열 매칭만으로 부족하면 auth 코드를 직접 볼 것.
  - ctx 미달 문구가 verify/채팅 경로에 보이면 failed 메시지에
    「Hermes 64K: config ollama_num_ctx 확인」을 짧게 포함 (재발 진단용).
- verify_core_quick: 부팅 지연 금지. 긴 MCP/채팅 추론 넣지 말 것.
  (선택·최소) chat auth만 넣는 것은 OK이나 Goal 필수는 아님.
- 콘솔 창 깜빡임 금지 (no-console-windows.mdc).
- 새 의존성 금지. unittest만.

Interface (구현 계약):
1) is_weak_hermes_api_key(key: str) -> bool
   - hermes_credentials.py 또는 setup_protocol 모듈 레벨. 단위 테스트 필수.
2) _step_hermes_env(self, *, force_rotate: bool = False) -> SetupStepResult
   - force_rotate 또는 weak/empty → 새 키. 그 외 기존 강한 키 유지.
3) _step_hermes_gateway(self, *, force_restart: bool = False) -> SetupStepResult
   - force_restart 또는 key_rotated 시 restart.
4) _ollama_provider_model(...): ollama_num_ctx >= 64000 보장.
5) tests: weak key / rotate / ollama_num_ctx upsert / (가능하면) force_restart 호출 mock.

Implementation order:
  Phase A: is_weak_hermes_api_key + hermes_env force_rotate + unittest
  Phase B: hermes_gateway force_restart + core_smoke 401 경로 연결
  Phase C: ollama_num_ctx in _ollama_provider_model + provider 스텝 메시지
  Phase D: 문서 §5 상태 표 갱신 + 짧은 한국어 요약

Output:
- 위 범위 diff만
- 초록:
  .venv\Scripts\python.exe -m unittest tests.test_hermes_auth tests.test_hermes_install_bypass -v
  (관련 신규/확장 테스트 포함)
  .venv\Scripts\python.exe -c "from iris.system.setup_protocol import _ollama_provider_model; m=_ollama_provider_model({}, 'exaone3.5:2.4b'); assert m.get('ollama_num_ctx',0)>=64000"
- 짧은 한국어: 고친 구멍(A–D) / 검증 / 사용자가 프로토콜 다시 돌리면 기대 결과

Do not:
- CORE_STEP_IDS에 새 id 추가
- OLLAMA_CONTEXT_LENGTH 시스템 전역 강제
- Modelfile로 전 모델 재빌드
- Hermes-agent 업스트림 패치
- Ready quick에 MCP 핸드셰이크 재도입
- 강한 키를 매 실행마다 재발급
```

---

## 5. 상태

| 항목 | 상태 |
|------|------|
| 적합 여부 검토 | 완료 (§1–3) |
| 구현 프롬프트 | 작성됨 (§4) |
| 코드 구현 | **완료** (2026-09-24) — 약한 키 강제 재발급 · key_rotated 시 gateway restart · `ollama_num_ctx≥64000` · core_smoke 401 force_rotate |

---

## 6. 이력

| 날짜 | 내용 |
|------|------|
| 2026-09-24 | 채팅 401·32K ctx 증상 기준으로 프로토콜 보강 적합 판정 + Agent 프롬프트 작성. 실측: `.env` 플레이스홀더 키, gateway already-running 유지, ollama_num_ctx 미설정 |
| 2026-09-24 | §4 구현: `is_weak_hermes_api_key`, `_step_hermes_env(force_rotate)`, `_step_hermes_gateway(force_restart)`, `_ollama_provider_model` ctx, core_smoke 401 경로 |
