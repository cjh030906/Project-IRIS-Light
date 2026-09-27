# Hermes 채팅 `HTTP 401` — 원인 분석 · 개선안

> **작성**: 2026-09-25  
> **증상**: 설정 → 실행 프로토콜 「다시 설정」완료 후에도 채팅 시  
> `Error: Hermes: HTTP 401: Unauthorized` / `Iris: Hermes 오류: Hermes: HTTP 401: Unauthorized`  
> **선택 모델**: `gemma4:31b-cloud` (로그: `Hermes model synced: gemma4:31b-cloud`)  
> **관련**: `docs/code-review/Hermes채팅401-ctx미달-프로토콜보강-검토와-프롬프트.md` (게이트웨이 API 키 불일치 — **이번 증상과 별개**)

---

## 1. 한줄 결론

| # | 판정 | 내용 |
|---|------|------|
| A | **확정 원인** | 메시지는 Hermes **게이트웨이 Bearer 실패가 아님**. Ollama가 **클라우드 모델**(`*:cloud`)에 대해 인증 없이 401을 내고, Hermes가 그 문구를 SSE로 그대로 올린 것 |
| B | **프로토콜이 “통과”한 이유** | Core는 Hermes `.env` 키·gateway 생존·auth probe만 봄. 로컬 모델(`exaone3.5:2.4b`)이 있으면 `ollama_cloud` 로그인은 **선택** → 미로그인으로도 Ready |
| C | **오진 포인트** | 문구가 예전 게이트웨이 키 401과 비슷해 「다시 설정」만 반복하게 됨. 실제로는 **Ollama 클라우드 로그인 / 로컬 모델 전환**이 필요 |
| D | **부차** | 동일 PC에서 로컬 `exaone3.5:2.4b`를 Hermes로내면 `does not support tools` (HTTP 400) — 401과 별개, 도구 강제 이슈 |

**한줄:** 채팅 401의 본체는 **Ollama cloud Unauthorized**. Hermes API 키·실행 프로토콜 Core는 현재 정상.

---

## 2. 실측 (2026-09-25, 이 PC)

### 2.1 Hermes 게이트웨이 쪽 — 정상

| 검사 | 결과 |
|------|------|
| `%LOCALAPPDATA%\hermes\.env` `API_SERVER_KEY` | len=43, weak=False |
| 프로젝트 `.env` `IRIS_HERMES_API_KEY` | 동일 키 (일치) |
| `GET /health` | 200 |
| `probe_chat_auth()` (빈 chat POST) | `ok` |
| 올바른 Bearer로 `POST /v1/chat/completions` | 200 |
| 잘못된/빈 Bearer | 401 `Invalid gateway API key (API_SERVER_KEY)` |

→ 「다시 설정」으로 맞추려던 **게이트웨이 키 불일치** 시나리오는 **지금 재발 상태가 아님**.

### 2.2 사용자와 동일한 실패 — 재현

```text
HermesClient.set_inference_model("gemma4:31b-cloud")  → ok
HermesClient.stream_chat("gemma4:31b-cloud", …)       → RuntimeError: Hermes: HTTP 401: Unauthorized
```

메시지 포맷 구분:

| 출처 | 문자열 | 의미 |
|------|--------|------|
| HTTPError 401 (게이트웨이) | `Hermes HTTP 401 Unauthorized. 시작 프로토콜…` | Bearer ≠ `API_SERVER_KEY` |
| SSE `error.message` (업스트림) | **`Hermes: HTTP 401: Unauthorized`** ← 사용자 로그 | Ollama/모델 쪽 거부 |

코드: `iris/infrastructure/hermes_client.py` — `_sse_error_message` → `raise RuntimeError(f"Hermes: {err_msg}")`.

### 2.3 Ollama 직접 호출 — 동일 401

| 호출 | 결과 |
|------|------|
| `POST :11434/v1/chat/completions` model=`gemma4:31b-cloud` (키 없음) | **HTTP 401** `{"error":{"message":"Unauthorized",…}}` |
| `OLLAMA_API_KEY` 프로세스/`.env` | **없음** (len 0) |
| `ollama_cloud_signed_in()` | **False** |
| 로컬 목록 `GET /api/tags` | `exaone3.5:2.4b` 1개만 |
| 로컬 native `/api/chat` exaone | 정상 응답 |

### 2.4 프로세스 스냅샷 (참고)

- Iris: `pythonw -m iris` (포트 8765)
- Hermes gateway listen 8642: `.hermes-runtime\…\python.exe -m hermes_cli.main gateway run`  
  (추가로 `hermes-agent\venv\… gateway run` 프로세스도 보이지만 **8642 LISTEN은 runtime 쪽 1개**)
- Hermes `config.yaml`: `provider=custom`, `base_url=http://127.0.0.1:11434/v1`, `default`/`synced` 쪽 클라우드 모델명 잔존 가능
- `.env`의 `IRIS_OLLAMA_MODEL=exaone3.5:2.4b` 인데도 UI/동기화 로그는 `gemma4:31b-cloud` — **피커·Hermes default가 .env와 어긋날 수 있음**

---

## 3. 인과 사슬

```
UI 모델 = gemma4:31b-cloud  (클라우드, 로그인 필요)
        │
        ▼
Hermes ON → resolve_hermes_inference → custom + :11434, api_key=""
        │
        ▼
Hermes gateway (Bearer OK) → Ollama OpenAI-compat
        │
        ▼
Ollama: 클라우드 미로그인 → 401 Unauthorized
        │
        ▼
Hermes SSE error.message = "HTTP 401: Unauthorized"
        │
        ▼
Iris: "Hermes: HTTP 401: Unauthorized"
        │
        ▼
사용자: 실행 프로토콜 재실행 (게이트웨이 키 경로) → Core OK, 채팅은 계속 실패
```

프로토콜이 막는 곳:

- `has_usable_inference_backend(["gemma4:31b-cloud"], cloud_signed_in=False) == False` 는 **코드에 있음**
- 그러나 `_opt_ollama_cloud`: 로컬 모델이 있으면 클라우드 로그인 **카드만 내고 Core 실패로 막지 않음**
- `core_smoke` / `probe_chat_auth`: 모델·클라우드 로그인 없이 **게이트웨이 키만** 검사

---

## 4. 적합 / 부적합 개선

### 적합 (우선)

1. **에러 분류·문구**  
   - `Hermes: HTTP 401: Unauthorized` + 선택 모델이 `*:cloud` + `not ollama_cloud_signed_in()`  
     → 「Ollama 클라우드에 로그인하거나 로컬 모델로 바꾸세요」  
   - 게이트웨이 Bearer 실패와 **문구를 절대 섞지 말 것** (이미 콜론 유무로 갈라져 있음 — UI에서 더 명시)

2. **클라우드 모델 선택 가드**  
   - 미로그인 시 `*:cloud` 선택/동기화 차단 또는 경고 후 로컬로 폴백  
   - `Hermes model synced: …-cloud` 직전에 동일 검사

3. **프로토콜 보강 (신규 Core 스텝 ID 없이)**  
   - Ready/`hermes_provider`/모델 sync 후: **현재(또는 Hermes default) 모델이 클라우드인데 미로그인이면** failed/needs_user  
   - 또는 Core 끝에서 “선택 모델로 짧은 chat smoke” (클라우드면 로그인 필수, 로컬이면 tools 이슈는 soft warn)

4. **피커 ↔ Hermes default ↔ `IRIS_OLLAMA_MODEL` 정합**  
   - 클라우드 불가 상태면 Hermes `model.default`를 로컬로 강제 sync

### 적합 (다음)

5. 로컬 모델 + Hermes tools: `does not support tools` → 모델 capabilities에 따라 tools 끄기 / 도구 지원 모델 우선  
6. 좀비 `gateway run` 중복 프로세스 정리 (포트는 하나여도 혼선·재시작 실패 원인)

### 부적합

- 게이트웨이 `API_SERVER_KEY` 강제 rotate를 이 증상에 또 적용 (이미 키 정상 — 세션만 끊김)  
- Hermes 업스트림 패치로 Ollama 401 삼키기  
- Core에 긴 클라우드 추론 smoke (부팅 지연)

---

## 5. 지금 당장 사용자가 할 일

1. **Ollama 앱에서 ollama.com 계정 로그인** 후 Iris에서 `gemma4:31b-cloud` 유지, 또는  
2. 모델 피커에서 **로컬 모델**만 선택 (클라우드 접미사 없는 것).  
3. 「실행 프로토콜 다시 설정」만 반복해도 **이 401은 안 고쳐짐** (이미 Core·게이트웨이 키는 OK).

---

## 6. 구현 시 건드릴 파일 (참고)

| 파일 | 역할 |
|------|------|
| `iris/infrastructure/hermes_client.py` | SSE 401 → 클라우드/게이트웨이 분기 메시지 |
| `iris/ui/workers/hermes_workers.py` / `main_window.py` | sync·채팅 전 `*:cloud` + signed_in 가드 |
| `iris/system/setup_protocol.py` | 선택/default 모델이 클라우드면 로그인 needs_user; smoke에 모델 인식 |
| `iris/infrastructure/ollama_usage.py` | `ollama_cloud_signed_in` (이미 존재) |

---

## 7. 상태

| 항목 | 상태 |
|------|------|
| 실측·원인 확정 | 완료 (2026-09-25) |
| 코드 수정 | **완료** (2026-09-25) — 에러 분류·로그인 버튼·클라우드 가드·프로토콜·orphan gateway prune·tools 문구 |
| 이전 게이트웨이 키 보강 | 별도 문서 — 이번 재발과 무관, 현재 PC에선 정상 |

---

## 8. 이력

| 날짜 | 내용 |
|------|------|
| 2026-09-25 | Iris/Hermes/Ollama 직접 재현. 사용자 문구=`Hermes: HTTP 401: Unauthorized` = Ollama cloud Unauthorized. 게이트웨이 키·probe_chat_auth OK. 프로토콜은 로컬 모델 있어 클라우드 로그인 스킵 가능. |
| 2026-09-25 | 우선·다음 개선 구현: `hermes_errors` 분류, 채팅 `로그인` 앵커→`open_ollama_app`, 미로그인 시 클라우드 선택/sync 폴백, `hermes_provider`/`core_smoke` `[CLOUD]` needs_user, orphan gateway prune, tools 미지원 문구. |
