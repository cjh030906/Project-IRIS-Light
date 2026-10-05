# Hermes 채팅 `HTTP 400` — `options` 필드 거부

> **작성**: 2026-09-29  
> **증상**: 설정에서 무료 LLM(Gemini, NVIDIA NIM 등)을 등록하고 연결 테스트는 통과하는데, Iris 채팅은 실패한다.  
> **오류**: `Hermes: HTTP 400` — Google `Unknown name "options": Cannot find field` / NVIDIA `Unsupported parameter(s): options`  
> **관련**: `docs/code-review/completed/Hermes채팅401-클라우드미로그인-원인과-개선안.md` (게이트웨이·클라우드 로그인 401 — **이번 400과 별개**)  
> **구현 프롬프트**: `docs/code-review/completed/Hermes채팅400-options필드-구현프롬프트.md`

---

## 1. 결론

| # | 판정 | 내용 |
|---|------|------|
| A | **확정 원인** | 채팅은 Hermes를 거친다. Hermes `provider=custom` 은 `model.ollama_num_ctx`가 있으면 업스트림 JSON에 `options.num_ctx`를 넣는다. Gemini OpenAI 호환 엔드포인트와 NVIDIA NIM은 그 필드를 거부해 HTTP 400이 난다 |
| B | **테스트가 통과한 이유** | 설정 연결 테스트는 Hermes를 타지 않고 제공자에 `model`·`messages`·`max_tokens`만 보낸다. `options`가 없으므로 같은 키·같은 모델이 성공한다 |
| C | **키가 남는 이유** | 실행 프로토콜이 로컬 Ollama 64K 하한용으로 `ollama_num_ctx: 64000`을 기록한다. 이후 API 모델로 바꿔도 Iris·Hermes 모두 이 키를 지우지 않는다 |
| D | **수정 위치** | 근본은 Hermes `CustomProfile`이 Ollama가 아닌 URL에도 `options`를 싣는 것. Iris는 비-Ollama로 바꿀 때 그 키를 빼는 완화와, 테스트 문구가 채팅 성공을 의미하지 않게 하는 표시가 필요하다 |

**한줄:** API 키와 모델 등록은 됐다. 실패는 Hermes가 Ollama 전용 `options`를 Gemini·NVIDIA 요청에 붙인 결과다.

---

## 2. 두 경로

```
설정 「연결 테스트」
  openai_compat_client.chat_smoke
  POST {base}/chat/completions
  body: model, messages, max_tokens, stream=false
  → options 없음 → 200 → 화면 「통과」

Iris 채팅 (Hermes ON, 기본)
  HermesClient.stream_chat
  body: model, messages, stream=true          ← Iris는 options를 넣지 않음
  → Hermes CustomProfile이 extra_body.options.num_ctx 를 추가
  → Gemini / NVIDIA 가 400
```

Iris가 Hermes를 쓰는 조건은 `main_window`의 채팅 분기이다. Hermes가 켜져 있으면 Ollama·API 모델을 가리지 않고 게이트웨이로 보낸다. 직접 호출(`OpenAICompatChatWorker`)은 Hermes가 꺼져 있을 때만 탄다.

실측한 Hermes 설정(`%LOCALAPPDATA%\hermes\config.yaml`, 키 값은 기록하지 않음):

| 항목 | 값 |
|------|-----|
| `model.provider` | `custom` |
| `model.ollama_num_ctx` | `64000` |
| `model.api_key` | 존재 (길이 70) |

`64000`은 Iris `HERMES_MIN_OLLAMA_NUM_CTX`와 같다. 로컬 모델이 Hermes 최소 컨텍스트(64K)에 걸리던 문제를 막기 위해 `_ollama_provider_model`이 넣는 값이다.

---

## 3. 주입 지점

Hermes 설치본 `plugins/model-providers/custom/__init__.py`의 `CustomProfile.build_api_kwargs_extras`:

- `ollama_num_ctx`가 있으면 `extra_body["options"] = {"num_ctx": ollama_num_ctx}` 를 **항상** 넣는다.
- 같은 파일의 `_looks_like_ollama_endpoint`(포트 11434 또는 호스트에 `ollama`)는 `think` 플래그에만 쓰인다. `options`에는 이 가드가 없다.
- OpenAI SDK는 `extra_body`를 요청 JSON에 합친다. 업스트림이 보는 필드는 `options`이다.
- 네이티브 Gemini URL이면 `extra_body`를 `thinking_config`만 남기도록 거르지만, 무료 목록의 Base URL은 `https://generativelanguage.googleapis.com/v1beta/openai` 라 그 분기를 타지 않는다. NVIDIA(`https://integrate.api.nvidia.com/v1`)도 동일하다.

`agent_init._configure_ollama_num_ctx`는 설정에 `ollama_num_ctx`가 있으면 베이스 URL이 원격이어도 `_ollama_num_ctx`에 올린다. 자동 탐지만 로컬 엔드포인트로 제한된다. 주석(“Ollama로 판정된 서버에서만 설정”)과 동작이 어긋난다.

Iris `set_inference_model`이 보내는 본문은 `provider`·`model`·`base_url`·`api_key`뿐이다. `ollama_num_ctx`를 내리지 않는다. Hermes `POST /api/model/set`도 기존 `model` 딕셔너리를 고치므로 키가 남는다.

무료 목록의 Groq·OpenRouter·Mistral 등도 채팅 시 같은 `custom` 경로다. 이번 로그에 찍힌 것은 Gemini와 NVIDIA이지만, Ollama가 아닌 제공자는 같은 400 대상이다.

---

## 4. 개선

### 4.1 근본 — Hermes (설치본)

`CustomProfile.build_api_kwargs_extras`에서 `options`는 `_looks_like_ollama_endpoint(base_url)`일 때만 넣는다. `think=False`와 같은 조건이다.

- 로컬 `:11434`는 `num_ctx`가 유지되어 64K 하한이 깨지지 않는다.
- Gemini·NVIDIA·그 외 OpenAI 호환 URL에서는 `options`가 빠진다.
- 설치본 직접 수정은 `hermes update`에 덮인다. 업스트림 패치가 본체이고, Iris가 Hermes를 깔 때 같은 가드를 적용할 수 있으면 재발하지 않는다.

### 4.2 완화 — Iris

`set_inference_model`로 비-Ollama `base_url`을 쓸 때 `config.yaml`의 `model.ollama_num_ctx`를 제거한다. `:11434` 또는 `ollama` 호스트로 돌아올 때 `64000` 이상을 다시 넣는다.

게이트웨이 프로세스가 기동 시 읽은 `_ollama_num_ctx`를 모델 전환 후에도 유지하면, 키를 지운 뒤에도 400이 난다. 그 경우 모델 전환이 에이전트를 다시 만드는지 확인하고, 아니면 게이트웨이를 한 번 재시작한다.

이 완화만으로는 Hermes가 URL을 보지 않고 메모리 값을 실으면 불완전하다. 4.1과 같이 간다.

### 4.3 테스트 표시

연결 테스트 성공 문구는 “제공자 직접 호출 성공”으로 한정한다. Hermes가 켜져 있으면 채팅과 같은 게이트웨이로 짧은 요청을 한 번 더 보내 `options` 400을 등록 단계에서 보이게 하는 편이 맞다. 테스트 본문에 `options`를 흉내 내는 방식은 채팅 경로가 바뀌면 다시 어긋난다.

### 4.4 고친 뒤 확인

1. Gemini 또는 NVIDIA를 고르고 Iris에서 `안녕` → 400 `options`가 없어야 한다.
2. 로컬 `exaone3.5:2.4b` 채팅은 그대로 되고, Hermes 로그에 로컬 요청의 `num_ctx`는 남아 있어야 한다.
3. Ollama로 되돌린 뒤 `config.yaml`의 `ollama_num_ctx`가 64000 이상이어야 한다.

---

## 5. 같이 보인 것

| 항목 | 이번 400과의 관계 |
|------|-------------------|
| `reasoning_effort` | `CustomProfile` 기본값이 켜지면 본문에 `reasoning_effort: medium`이 같이 나간다. NVIDIA 문구는 `options`만 거부했다. Gemini 본문은 잘려 있어, `options`를 뺀 뒤 같은 400이 `reasoning_effort`로 바뀌는지 한 번 더 본다. Groq는 Hermes가 이미 별도 어휘로  clamped 한다 |
| `gemma4:31b-cloud` 동기화 로그 | 같은 Google `options` 400이 앞에 있다. 확정 재현은 Gemini·NVIDIA 직접 URL이다. Ollama 클라우드가 `options`를 Google로 넘기는지는 이번 패킷으로 단정하지 않는다 |
| `클라우드 모델 확인 시간 초과` | 모델 목록 프로브 시간 초과다. 채팅 400의 원인이 아니다 |
| 로그의 `NDIVIA/...` | 채팅 표시는 `{등록 이름}/{모델}`이다. 코드 프리셋 이름은 `NVIDIA NIM`이라, 이 문자열은 등록 시 입력값이다 |
| 401 `Unauthorized` | 이전 문서의 Ollama 클라우드 미로그인이다. 이번 본문 검증 오류와 다르다 |

---

## 6. 근거 위치

| 위치 | 역할 |
|------|------|
| `iris/ui/window/main_window.py` 채팅 분기 | Hermes ON이면 API 모델도 게이트웨이로 보냄 |
| `iris/infrastructure/hermes_client.py` `stream_chat` | Iris 요청 본문에 `options` 없음 |
| `iris/infrastructure/hermes_client.py` `set_inference_model` | `ollama_num_ctx`를 지우지 않음 |
| `iris/infrastructure/openai_compat_client.py` `chat_smoke` / `probe` | 설정 테스트. `options` 없음 |
| `iris/system/setup_protocol.py` `_ollama_provider_model` | `ollama_num_ctx`를 64000 이상으로 기록 |
| `%LOCALAPPDATA%\hermes\hermes-agent\plugins\model-providers\custom\__init__.py` | `options.num_ctx` 주입. URL 가드 없음 |
| 같은 트리 `agent/agent_init.py` `_configure_ollama_num_ctx` | 설정값이 있으면 원격 URL에도 적용 |
| `iris/storage/api_providers.py` `FREE_LLM_OFFERS` | Gemini·NVIDIA Base URL |
