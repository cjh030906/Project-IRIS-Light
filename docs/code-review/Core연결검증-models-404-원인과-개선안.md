# Core「연결 검증」`/v1/models` HTTP 404 — 원인 분석 · 개선안

> **작성**: 2026-09-25  
> **재현**: START PROTOCOL Core 9/10 — `[READY] … (models_http, key_len=43)` + `/v1/models HTTP 404: 404: Not Found`  
> **진단 JSON**: `code=OK`, `message=gateway /health OK`, `models_ok=null`, Hermes 0.21.4  
> **관련**: 연번 24 (`Core연결검증-gateway_ready실패-원인과-개선안.md`) — **잔여**. 401 키 불일치·클라우드 로그인과 **별건**

---

## 1. 한줄 결론

| # | 판정 | 내용 |
|---|------|------|
| A | **확정** | 연번 24 이후에도 `ensure`/`restart` 성공 판정이 **`/health`만**이면, `/v1/models` 404인 채로 Core smoke만 실패한다 |
| B | **확정(실측)** | 정상 Hermes에서 `/models`( `/v1` 없음)·`/v1/v1/models`·`/v1/models/` → 본문 `404: Not Found` (사용자 문구와 동일) |
| C | **확정** | `key_len=43` + 404 → **키 rotate로 고칠 문제가 아님**. 이전 smoke 복구가 `models_http`에 키 점검을 섞어 오진 유도 |
| D | **조치** | base_url을 항상 `…/v1`로 정규화 · 기동 대기를 **ready(/v1/models)** 까지 · 404 전용 복구(키 재발급 금지)

**한줄:** health 생존과 OpenAI `/v1/models` 마운트를 같은 “기동 성공”으로 묶지 않으면 재시도가 영원히 no-op이다.

---

## 2. 사용자 스냅샷

| 관측 | 의미 |
|------|------|
| `/health` → hermes-agent 0.21.4 | api_server health 핸들러는 살아 있음 |
| `/v1/models` → **404** `404: Not Found` | 라우트 미매칭(또는 잘못된 URL). 401이 아님 |
| 진단 `message=gateway /health OK`, `models_ok=null` | `_wait_until_healthy` health-only 성공 스냅샷 |
| `key_len=43` | 약한 키/없음 아님 — rotate 금지 |

---

## 3. 이전(연번 24)과의 차이

| 항목 | 연번 24 | 이번(25) |
|------|---------|----------|
| 증상 코드 | 뭉뚱그린 models 실패 / 401 추정 | **명시적 HTTP 404** |
| 복구 | 키 정합 + restart(성공=/health) | **URL 정규화** + restart 성공=**/v1/models** |
| 진단 | health OK 메시지 | `MODELS_404` / `models_404` |

---

## 4. 적합 / 부적합

### 적합 (구현)

1. `normalize_hermes_openai_base_url` — 이중 `/v1`·꼬리 `/`·누락 `/v1` 제거  
2. `probe_gateway_ready` → `models_404` 코드 분리  
3. `_wait_until_healthy(require_ready=True)` — ensure/restart 공통  
4. ensure: health만 OK면 stop→재기동 (이미 실행 중 short-circuit 금지)  
5. smoke/gateway 스텝: 404 시 **force_rotate=False**

### 부적합

- 404에 API 키 강제 재발급  
- 클라우드 로그인 유도  
- Setup Access Denied / Hermes pip 설치 경로 재손대기  

---

## 5. 상태

| 항목 | 상태 |
|------|------|
| 원인 | 완료 |
| 코드 | **완료** (2026-09-25) |
| 테스트 | `tests.test_hermes_auth` · `tests.test_hermes_gateway_diagnostics` OK |
| 총괄표 | 연번 **25** |
| Setup | **0.1.16** (사이트 업로드) |

---

## 6. 이력

| 날짜 | 내용 |
|------|------|
| 2026-09-25 | 구현: URL 정규화·`models_404`·ensure/restart ready 대기·404 시 키 rotate 금지. unittest 통과. Setup 0.1.16. |
