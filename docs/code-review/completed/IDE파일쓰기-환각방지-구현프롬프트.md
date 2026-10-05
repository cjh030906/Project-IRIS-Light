# Prompt: IDE 파일 쓰기 환각 방지 (1·2·3)

아래 블록을 Cursor Agent에 그대로 붙여 넣으면 됩니다.

가져올 동작은 두 가지뿐이다. 앱으로 설치하지 않는다.

- 완료 문장은 도구 ok와 디스크의 파일이 있을 때만 보여 준다. (Cline이 하는 검증)
- 모델은 코드 텍스트만 내고, 파일에 넣고 확인하는 일은 아이리스가 한다. (Aider가 하는 적용)

Instructor, Outlines, Tesseract, Aider, Cline, MCP filesystem 서버, 새 Hermes 스킬은 설치·연결하지 않는다. 무료 클라우드 모델에게 도구를 더 주면 미호출이 늘어난다.

---

```text
Context:
- 저장소: Project-IRIS-Light (Windows / PyQt6)
- 재현 (2026-09-29 11:14, chat_messages id 46·47):
  사용자: @c:Users/kwakm/Desktop/동양미래대학교 이 사진속 코드를 이 스크립트 안에 작성해줘
  + 첨부 C:\Users\kwakm\.iris-light\paste\paste_20260929_111346_39980.png
  Iris 문장: 없는 폴더라고 단정하고 interpolation_test.py 를 만들겠다고 한 뒤 "처리 완료".
  디스크: interpolation_test.py 없음. Desktop\동양미래대학교 폴더 없음.
  실제 project_root 는 Desktop\동양미래대학교 2학년 2학기\컴퓨터비전.
  사진 속 코드(rose.png, cv.INTER_*)는 말풍선 안에만 있고 파일로 저장되지 않음.
- 원인:
  1) 완료 문장을 project.write_file ok 와 파일 존재로 거르지 않음. 위키만 "ok 없이 성공이라고 말하지 말라"가 있다 (main_window.py 의 wiki 문장).
  2) 사진+작성을 모델 계획에 맡김. 사용자 턴은 이미지 경로 문자열만 붙인다 (_format_user_turn_content). hermes_client 는 이미지 바이트를 싣지 않는다.
  3) @c:Users/... 는 c:\ 가 아니다. resolve_at_path 는 is_file() 만 반환해서 폴더는 무시하고, 실패를 사용자에게 말하지 않는다 (iris/ui/chat/at_path_refs.py).
- 바이브 코딩 쪽 기존 경로 (이번 사진 파이프와 별개로, 완료 검증은 여기도 적용):
  - _pending_local_vibe_prompt / _feed_live_vibe_stream / _try_reveal_local_vibe_code
  - extract_first_code_block 는 ```lang 다음 줄바꿈이 없으면 None. 이번 답은 ```python 직후 한 줄이라 자동 쓰기가 시작되지 않았다.
  - 쓰기는 기존 project.write_file (iris/ui/control_actions/project.py). 작업 폴더 밖 경로는 resolve_under_root 가 거부한다.
  - 열린 탭: iris/infrastructure/iris_ide_client.py get_open_editors().
- 스킬 integrations/hermes-skills/iris-control/iris-vibe-code/SKILL.md 는 이미 "invoke 결과의 visible 을 확인하라"고 적혀 있다. 모델이 호출하지 않았다. 스킬 문장을 늘리지 말 것.

Goal:
1) 파일을 만들었다는 채팅 문장은 project.write_file 이 ok 이고, 반환 경로에 그 파일이 있을 때만 남긴다. 도구가 없거나 실패하거나 경로가 없으면 "채팅에만 있고 파일은 만들지 않았다"만 보여 준다. interpolation_test.py 같은 임의 완료 문장을 성공으로 두지 않는다.
2) 이미지 첨부 + 파일에 써 달라는 요청(작성/넣어/써줘/이 스크립트)은 모델이 계획을 세우기 전에 앱이 처리한다.
   순서: @경로 판정 → (필요하면) 이미지에서 코드만 추출 → 열린 편집 파일에 project.write_file → 채팅에는 실제 절대경로만.
   열린 파일이 없으면 파일명을 물어 보고 중단한다. 이름을 지어 만들지 않는다.
   모델 호출은 "코드만 텍스트로" 한 번뿐이다. 그 호출이 도구를 고르거나 완료를 말하지 않게 한다.
3) @경로는 앱이 먼저 판정한다.
   - c:Users → c:\Users (드라이브 문자 뒤 구분자가 없으면 삽입).
   - 폴더면 연다. 파일이면 연다. 없으면 쓰지 않고, project_parents·최근 폴더에서 이름가 가까운 후보만 물어 본다.
   - 판정이 끝나기 전에 모델이 그 경로로 파일을 만들겠다고 답하지 못하게, 이 경우는 2) 파이프가 모델 계획 턴을 타지 않는다.

Constraints:
- 새 pip 패키지·MCP 서버·Hermes 스킬·exe 설치 금지.
  설치하지 말 것: Aider, Cline, Instructor, Outlines, Tesseract, modelcontextprotocol/servers 의 filesystem.
  가져오는 것은 동작뿐이다. 완료 게이트(1), 모델은 코드만·적용은 앱(2).
- tool_choice 강제는 하지 않는다. Hermes·무료 Gemini 경로에 새 파라미터를 넣으면 400 이 난다. 게이트와 고정 절차로 대체한다.
- Surgical: 아래 파일과 그 테스트만. 무관 리팩터·포맷·테마 금지.
- 기존 project.write_file·resolve_under_root 의 작업 폴더 탈출 거부를 풀지 말 것. 바탕화면 임의 폴더에 절대경로로 쓰지 말 것.
- 사용자 학교 폴더(동양미래대학교*)와 ~/.iris-light/iris_light.db 를 테스트에서 수정하지 말 것. tmp 만.
- API 키·토큰은 로그·예외·채팅에 남기지 말 것.
- 콘솔 창 깜빡임 금지.
- 위키 ok 문장, Companion 80:20, IDE new-window 계약은 유지.

Interface (구현 계약):
1) 경로 (iris/ui/chat/at_path_refs.py 또는 같은 모듈의 작은 함수)
   - normalize_at_path("c:Users/kwakm/Desktop/foo") → Windows 에서 c:\Users\kwakm\Desktop\foo.
   - 이미 c:\ 또는 c:/ 이면 유지. mcp: 는 그대로 제외.
   - resolve 결과: file | folder | missing.
   - missing 이면 쓰기 함수를 호출하지 않는 값(후보 문자열 목록 가능, 최대 5).
   - 폴더는 is_file() 실패로 버리지 말 것.
   - 단위 테스트: c:Users 정규화, 있는 파일, 있는 폴더, 없는 경로, @mcp:foo 제외.

2) 코드 블록 (iris/system/project_ops.py extract_first_code_block)
   - ```python\ncode\n``` 기존 동작 유지.
   - ```pythonimport cv2 as cv\nimg = 1\n``` 처럼 언어 태그 직후 줄바꿈이 없어도 code 를 반환.
   - 펜스가 없으면 None. 빈 펜스는 None.
   - 라이브 바이브(_live_vibe_try_start)도 같은 규칙으로 시작하게 맞춘다. 줄바꿈만 기다리며 영영 시작 안 하는 상태를 없앤다.

3) 완료 게이트
   - 파일 쓰기 성공 문구를 만드는 곳(_try_reveal_local_vibe_code 의 "IDE에 파일을 열었습니다" 및 모델 본문에 "처리 완료"·"생성하겠습니다"·"작성했습니다"가 있고 이번 턴에 write ok+파일 존재가 없는 경우)은 성공으로 보여 주지 않는다.
   - 모델이 코드 펜스와 함께 완료를 말했고 게이트가 실패면, 펜스에서 코드를 꺼내 기존 write 경로로 한 번 시도한 뒤, 그 결과 파일이 있을 때만 성공 문구(실제 경로 포함).
   - 시도도 실패하면 실패 한 줄. 모델의 "처리 완료" 문장은 저장·표시에서 뺀다.
   - 단위 테스트: ok+파일 있음 → 경로가 문구에 있음. ok 인데 파일 없음 → 성공 문구 없음. 도구 없음+완료 문장 → 성공 문구 없음.

4) 사진→열린 파일 파이프 (모델 턴 시작 전, _on_user_text 이후 채팅 워커를 띄우기 전)
   - 조건: 첨부 확장자가 png/jpg/jpeg/webp/gif/bmp 이고, 본문에 작성|넣어|써|스크립트|코드 가 있음.
   - 조건 불일치면 기존 채팅 그대로.
   - @가 있고 missing 이면 후보만 묻고 return. write 호출 0.
   - @가 폴더면 그 폴더를 연 뒤, 열린 에디터가 없으면 파일명을 묻고 return. write 호출 0.
   - 대상 파일: get_open_editors() 로 작업 폴더 안의 열린 파일 1개. 0개 또는 2개 이상이면 쓰지 않고 물어 본다.
   - 추출: 이미지 파일을 읽어, 선택된 채팅 모델에 "코드만 출력. 설명·파일명·완료 문장 금지" 한 번. 이미지 바이트를 실을 수 있는 기존 클라이언트만 사용 (ollama_client 의 images, 또는 이미 있는 OpenAI 호환 content). 새 SDK 금지. Hermes 스트림에 options·tool_choice 를 추가하지 말 것.
   - 추출 결과가 비거나 코드가 아니면 파일을 쓰지 않고 실패 한 줄.
   - 추출이 되면 project.write_file(open=true) 로 그 열린 상대경로에 쓴다. 새 rel_path 를 만들지 말 것.
   - 채팅 성공 문구는 게이트를 통과한 절대경로 한 줄. "interpolation_test.py" 를 앱이 생성하지 말 것.
   - 파이프가 처리한 턴은 Hermes에 계획 프롬프트를 보내지 않는다.
   - 테스트: 가짜 추출 함수로 "print(1)" 을 받게 하고, tmp 작업 폴더의 열린 파일 경로에 그 내용이 쓰이는지, missing @ 에서는 write 가 0인지, 열린 파일 0개면 write 가 0인지.

5) 테스트 실행 (에이전트가 직접)
   - unittest 로 1)·2)·3)·4)를 고정. Qt 없이 도는 함수 테스트로 둘 것. 기존 _check_*.py 스타일이 있으면 그 모듈의 새 함수로 넣고 `python -m` 으로 실행.
   - 라이브 비전·실 IDE 창은 필수가 아니다. 불가하면 "단위 테스트만 했고 라이브 채팅은 안 했다"고 결과에 적는다.
   - 학교 폴더와 실사용 db 는 건드리지 말 것.

Implementation order:
  Phase A: normalize/resolve + extract_first_code_block + 테스트
  Phase B: 완료 게이트를 바이브 쓰기 문구와 모델 완료 문장에 연결 + 테스트
  Phase C: 사진→열린 파일 파이프. 추출은 주입 가능한 함수로 두고 테스트는 가짜 추출
  Phase D: 테스트 실행 후 이 문서 상태 표의 코드 구현을 완료로 고치고, 아래 Output 형식의 한국어만 보고

Output (이것만 사용자에게 보고. 과정 나열 금지):
- 고친 파일 목록
- 테스트 명령과 pass/fail 한 줄
- 1 완료 문장 / 2 사진 파이프 / 3 @경로 가 각각 어떻게 막히는지 한 줄씩
- 설치하지 않은 것: Aider, Cline, Instructor, Outlines, Tesseract, MCP filesystem
- 라이브 채팅을 안 했으면 그 한 줄

Do not:
- Aider·Cline·Instructor·Outlines·Tesseract·MCP 서버 설치 또는 스킬 md 추가
- tool_choice, extra_body.options, ollama_num_ctx 변경
- 모델에게 파일명을 짓게 두기. 앱이 interpolation_test.py, iris_generated.py 를 이 파이프의 기본 이름으로 쓰기
- 작업 폴더 밖 절대경로 쓰기
- 열린 파일이 여러 개일 때 첫 파일에 조용히 덮어쓰기
- 추출 실패 시 빈 파일·잘린 파일 남기기
- 사용자 Desktop 의 동양미래대학교 자료를 테스트 입력으로 수정
```

---

## 상태

| 항목 | 상태 |
|------|------|
| 구현 프롬프트 | 작성됨 |
| 코드 구현 | 완료 |

1 완료 게이트, 2 사진에서 열린 파일로 쓰는 고정 절차, 3 `@c:Users` 정규화와 없는 경로 중단만 구현한다. Aider·Cline의 동작만 가져오고 제품은 설치하지 않는다.
