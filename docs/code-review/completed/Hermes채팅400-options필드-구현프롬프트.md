# Prompt: Hermes 채팅 `options` 400 수정

아래 블록을 Cursor Agent에 그대로 붙여 넣으면 됩니다.  
근거: `docs/code-review/completed/Hermes채팅400-options필드-원인과-개선안.md`

---

```text
Context:
- 저장소: Project-IRIS-Light (Windows / PyQt6)
- 스펙: docs/code-review/completed/Hermes채팅400-options필드-원인과-개선안.md (필독. 이 문서의 원인만 고친다)
- 증상: 설정에서 Gemini·NVIDIA 등 무료 API를 넣고 연결 테스트는 통과하는데, Iris 채팅은
  Hermes: HTTP 400 — Unknown name "options" / Unsupported parameter(s): options
- 원인: 채팅은 Hermes ON이면 게이트웨이로 간다. 실행 프로토콜이 로컬 Ollama 64K용으로
  config.yaml model.ollama_num_ctx=64000 을 남긴다. Hermes CustomProfile은 이 값이 있으면
  provider=custom 요청마다 extra_body.options.num_ctx 를 싣는다. Ollama가 아닌 URL
  (generativelanguage.googleapis.com/v1beta/openai, integrate.api.nvidia.com/v1, Groq 등)은
  그 필드를 400으로 거부한다. 설정 테스트(openai_compat_client.chat_smoke)는 options를 안 보낸다.
- 설치본: %LOCALAPPDATA%\hermes\hermes-agent\plugins\model-providers\custom\__init__.py
  build_api_kwargs_extras 의 `if ollama_num_ctx:` 분기. think 는 이미
  _looks_like_ollama_endpoint 로 막혀 있고 options 만 가드가 없다.
- 핵심 Iris 파일:
  - iris/system/hermes_install.py (설치 성공 직후)
  - iris/system/hermes_gateway.py (ensure_hermes_gateway_running / restart_hermes_gateway)
  - iris/system/setup_protocol.py (_ollama_provider_model, HERMES_MIN_OLLAMA_NUM_CTX)
  - iris/infrastructure/hermes_client.py (set_inference_model, stream_chat)
  - iris/ui/settings/settings_dialog.py (_on_api_probe_done 상태 문구)
  - tests/test_hermes_auth.py (로컬 ollama_num_ctx>=64000 계약 유지)

Goal:
설치가 끝난 뒤에도, 나중에 설정에서 API를 추가한 뒤에도, Iris 채팅이 Hermes를 통해
그 모델을 쓸 수 있게 한다.
- 로컬 Ollama(:11434 또는 호스트에 ollama) 요청에는 options.num_ctx 가 남는다. 64K 하한 유지.
- Gemini·NVIDIA·그 외 비-Ollama custom URL 요청에는 options 가 없다.
- 이미 깔린 Hermes, 이번 설치, 이후 hermes update 로 가드가 지워진 경우 모두 다음 Iris 기동·채팅에서 가드가 다시 들어간다.
- 설정 테스트 문구는 제공자 직접 호출 성공을 채팅 성공으로 말하지 않는다.

Constraints:
- YAGNI: options 가드 + 비-Ollama 일 때 ollama_num_ctx 제거/Ollama 복귀 시 64000 복원 + 가드가 디스크에 새로 쓰였으면 게이트웨이 1회 재시작 + 설정 상태 문구. 그 외 금지.
- reasoning_effort 는 일괄 제거하지 말 것. NVIDIA 오류는 options 만 거부했다. options 를 뺀 요청을 단위 테스트로 고정한 뒤, 라이브 400 본문에 reasoning_effort 가 다시 나오면 그때 그 호스트만 빼고 다시 패치한다. 이번 구현의 완료 조건에 넣지 말 것.
- Surgical: 위 파일과 가드 적용 헬퍼, 그 테스트만. 무관 리팩터·포맷·UI 테마 금지.
- 로컬 설치 계약 유지: _ollama_provider_model 이 Ollama 타깃에 ollama_num_ctx>=64000 을 넣는 기존 동작과 tests/test_hermes_auth.py 를 깨지 말 것.
- API 키·토큰 원문은 로그·상태 문구·예외에 남기지 말 것.
- 콘솔 창 깜빡임 금지 (no-console-windows.mdc). 게이트웨이 재시작은 기존 restart_hermes_gateway 만 사용.
- 새 의존성 금지. unittest 만.
- Hermes 업스트림 전체에 손대지 말 것. 고치는 설치본 파일은 custom/__init__.py 의 options 한 분기뿐이다.
- 가드가 없는 소스를 못 찾으면 파일을 추측해서 덮어쓰지 말고, 적용 실패를 반환하고 채팅 쪽 완화(키 제거)는 계속 동작하게 할 것.

Interface (구현 계약):
1) Ollama URL 판별 (Iris, Hermes와 같은 규칙)
   - 포트 11434 이거나 호스트가 ollama / *.ollama.com / 라벨에 ollama.
   - 빈 문자열·깨진 포트는 False.
   - 단위 테스트: :11434 True, ollama.com True, generativelanguage.googleapis.com False, integrate.api.nvidia.com False, api.groq.com False.

2) 설치본 가드 `apply_ollama_options_guard(agent_root) -> bool`
   - 대상: {agent_root}/plugins/model-providers/custom/__init__.py
   - 이미 `ollama_num_ctx` 와 `_looks_like_ollama_endpoint` 가 같은 if 에 있으면 no-op, False(변경 없음).
   - `if ollama_num_ctx:` 다음이 options 대입이면 그 조건을
     `if ollama_num_ctx and _looks_like_ollama_endpoint(ctx.get("base_url")):` 로 바꾼다.
     마커 주석 한 줄: iris: ollama-options-guard
   - 패턴이 없으면 파일을 수정하지 않고 실패로 알린다. True 는 이번에 내용이 바뀐 경우만.
   - 멱등. 두 번 호출해도 두 번째  diffs 는 없다.

3) 호출 시점
   - hermes 설치(공식·우회)가 hermes-agent 트리를 만든 직후 1회.
   - ensure_hermes_gateway_running 이 프로세스를 띄우기 직전. 이미 살아 있고 가드가 이번에 새로 쓰였으면(True) restart_hermes_gateway 1회. 매 채팅·매 기동마다 재시작 금지.
   - 이미 깔린 PC는 다음 Iris 실행의 ensure 에서 같은 함수가 적용한다. 설치 마법사를 다시 돌리지 않아도 된다.

4) config.yaml 의 ollama_num_ctx 는 활성 타깃에 맞춘다
   - set_inference_model 이 custom base_url 을 쓴 뒤(API 성공 또는 CLI 폴백 성공):
     - 비-Ollama base_url → model.ollama_num_ctx 키 삭제.
     - Ollama base_url → 없거나 64000 미만이면 64000. 더 크면 유지.
   - 이 기록은 API 키를 argv 에 넣지 말 것. 기존 _write_model_api_key 와 같이 yaml 직접 수정.
   - 설치 프로토콜이 로컬 Ollama를 기본으로 쓸 때는 기존처럼 64000 이상을 남긴다. API를 기본 모델로 덮어쓰는 설치 경로가 있으면 그 쓰기에서도 같은 규칙.
   - 메모리에 옛 _ollama_num_ctx 가 남아도, 가드가 로드된 프로세스에서는 base_url 로 options 가 빠진다. 가드를 새로 썼으면 3)의 재시작으로 그 프로세스를 바꾼다.

5) 설정 연결 테스트 문구 (settings_dialog._on_api_probe_done)
   - 직접 호출 ok 는 「제공자 직접 연결 정상」처럼 말한다. 「채팅 가능」으로 단정하지 말 것.
   - Hermes가 이 앱의 채팅 백엔드로 켜져 있고 게이트웨이가 이미 떠 있을 때만, 저장 직후 그 제공자의 모델 1개로 Hermes 채팅과 같은 경로(resolve_hermes_inference → set_inference_model → 짧은 chat)를 1회 보낸다.
   - 그 결과가 options 400 이면 상태 문구에 Hermes 채팅 실패와 options 를 남긴다. 제공자 저장 자체는 롤백하지 말 것.
   - 게이트웨이가 꺼져 있으면 직접 연결 결과만 보이고, 채팅 경로 미확인이라고 한 줄 붙인다. 테스트를 위해 게이트웨이를 새로 설치하거나 오래 기다리지 말 것.
   - 직접 probe 본문에 options 를 흉내 내지 말 것.

6) 테스트
   - URL 판별.
   - 가드: 샘플 custom/__init__.py 조각에 options 무조건 삽입이 있으면 적용 후 비-Ollama 조건이 생기고, 재적용은 불변. 패턴이 없는 파일은 원문 유지.
   - config 동기화: Gemini·NVIDIA base_url 이면 ollama_num_ctx 키가 없고, http://127.0.0.1:11434/v1 이면 >=64000.
   - 기존 tests.test_hermes_auth 의 ollama_num_ctx 테스트는 그대로 초록.

Implementation order:
  Phase A: URL 판별 + apply_ollama_options_guard + unittest (파일 시스템 tmp)
  Phase B: 설치 성공 직후와 ensure_hermes_gateway_running 에서 적용. 변경됐을 때만 게이트웨이 1회 재시작
  Phase C: set_inference_model 이후 ollama_num_ctx 삭제/복원 + 설치 쪽 Ollama 기본값 유지
  Phase D: 설정 상태 문구 + (게이트웨이 살아 있을 때만) Hermes 1회 스모크
  Phase E: 이 프롬프트 문서 상태 표를 완료로 고치고 한국어로 요약

Output:
- 위 범위 diff만
- 초록:
  .venv\Scripts\python.exe -m unittest tests.test_hermes_auth -v
  (이번 가드·URL·config 동기화 테스트 모듈 포함)
- 짧은 한국어: 설치본 가드가 어디에 걸렸는지 / API 추가 후 채팅이 options 를 안 보내는 이유 / 로컬 Ollama 64K는 유지되는지 / 게이트웨이를 재시작한 조건

Do not:
- reasoning_effort·think·tools 스키마를 비-Ollama에서 통째로 빼기
- HERMES_MIN_OLLAMA_NUM_CTX 를 낮추거나 로컬 Ollama에서 ollama_num_ctx 제거
- CORE_STEP_IDS 에 새 스텝 추가
- hermes-agent 통째 포크 또는 IRIS-Setup.exe 에 Hermes 소스 번들
- 매 채팅마다 게이트웨이 재시작
- 클라우드 모델 목록 시간 초과, 401 Unauthorized, 표시 이름 NDIVIA 를 이 작업에서 고치기
- 설정 테스트를 실패로 바꿔 제공자 저장을 막기
```

---

## 상태

| 항목 | 상태 |
|------|------|
| 원인 문서 | `Hermes채팅400-options필드-원인과-개선안.md` |
| 구현 프롬프트 | 작성됨 |
| 코드 구현 | 완료 |

비-Ollama custom URL 에는 `options` 를 넣지 않는다. 로컬 Ollama(`:11434`)는 `ollama_num_ctx` 64K 이상을 유지한다. 가드가 디스크에 새로 쓰인 뒤 게이트웨이가 이미 떠 있을 때만 1회 재시작한다.
