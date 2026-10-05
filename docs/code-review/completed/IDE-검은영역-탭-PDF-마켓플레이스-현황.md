# IDE 검은 영역·탭·PDF·마켓플레이스 현황

조사일: 2026-10-03. 코드 기준. 이번 턴은 고치지 않았다.

마지막 요청 문장(`조사하면서`)은 여기서 끊겨 있다. 아래는 조사와 보고서까지다.

## 확인한 사실

1. 아이리스 창 안의 IDE는 Qt 레이아웃 자식이 아니다. 검은 `ide_host` 위에 `IrisIdeWindow`라는 별도 창을 좌표만 맞춰 올려 둔다. 그 창을 줄여도 검은 칸과 채팅 폭은 80:20으로 고정이다.
2. IDE 본문(Theia)은 그 창 안에서도 사방 8px 검은 테두리 안에 들어 있다. 검은 칸과 IDE 픽셀이 처음부터 같지 않다.
3. 에디터 탭을 누르는 클릭은 문서 캡처 단계에서 끊긴다. Theia 탭 전환 코드까지 이벤트가 가지 않는다.
4. 브리지가 기억하는 열린 편집기는 현재 탭 하나뿐이다. 탭이 여러 개여도 아이리스는 나머지를 목록으로 받지 못한다.
5. Hermes가 켜져 있으면 `PDF로 저장` 로컬 저장은 돌지 않는다. 모델이 `note.export_pdf`를 불러야 파일이 생긴다. 기본 위치는 프로젝트 폴더가 아니라 `Documents/IRIS/iris-note.pdf`다. `저장했습니다`는 파일 실재 검사 문장에 없다.
6. Open VSX 마켓플레이스 화면은 Theia 안에 있다. 채팅이 그 목록을 검색하거나 확장을 설치하는 액션은 없다.
7. MCP·Skill 자동 설치는 GitHub 주소가 있을 때만 `extension.install_github`다. 이름만으로 저장소를 찾거나, IDE 마켓플레이스 확장과 Hermes MCP를 이어 주는 경로는 없다.

## 구조

### 1. 검은 영역과 IDE 크기

```
아이콘 / ide.enter_companion
  → MainWindow._activate_iris_ide_companion_tile
      → _apply_iris_ide_unified_layout
          → IdeUnifiedShell.mount(ide=None)     ← 좌측은 빈 검은 칸
          → apply_ratio(0.8)                    ← 80:20 고정
      → IrisIdeWindow.set_embedded(host=메인창) ← Qt 자식 임베드 아님
      → _sync_docked_iris_ide_geometry          ← 창 좌표 = ide_host 사각형
  → 사용자가 IDE 창 가장자리를 드래그
      → FramelessShell 그립 → startSystemResize(IrisIdeWindow)
      → ide_host / 채팅 스플리터는 그대로
  → 메인 창을 움직이거나 크기를 바꾸면
      → resizeEvent/moveEvent → apply_ratio(0.8) → 다시 80:20으로 덮음
```

갈라지는 곳: IDE 창 크기와 `ide_host` 폭이 한 값이 아니다. 줄이는 쪽은 IDE 창, 검은 칸과 채팅 길이를 가진 쪽은 잠긴 스플리터다.

### 2. 탭이 안 바뀌는 경로

```
Theia 탭 pointerdown
  → document 캡처: IrisIdeFrontendContribution.onTabPointerDown
      → stopPropagation()          ← 여기서 끊김
  → Lumino TabBar (버블)           ← 도달 안 함, 에디터 위젯 전환 없음
  → onCurrentEditorChanged         ← 안 탐
  → syncEditor → setEditorState    ← 이전 탭만 유지
  → 브리지 getOpenEditors          ← editorState 하나뿐
```

채팅이 파일을 여는 경로는 따로 있다. `ide.open_file` → 브리지 `openFile` → `iris-ide-bridge-poller.openInEditor` (`mode: 'activate'`). 사람이 탭을 누르는 경로와 섞이지 않는다.

### 3. PDF

```
Hermes 켜짐 (일반 사용)
  → hermes_owns_local_intents == True
  → _try_local_pdf_save 는 호출되지 않음
  → 모델이 note.export_pdf(content, path?) 를 부름
      → pdf_export.save_pdf (자식 프로세스, PyMuPDF)
      → ok 이고 dest 파일이 있을 때만 성공
  → 모델이 도구 없이 "저장했습니다" 라고 씀
      → _gate_chat_completion / settle_completion_claim
      → 문장에 "작성했습니다|처리 완료|파일을 열었습니다" 가 없으면 통과
```

Hermes가 꺼져 있을 때만 `_execute_user_turn` → `_try_local_pdf_save` → `PdfExportWorker`가 직전 비서 문장을 PDF로 쓴다. 경로 지정이 없으면 `Documents/IRIS`.

### 4. 마켓플레이스 · MCP · Skill

```
IDE 화면에서 사람이 검색
  View → Extensions Marketplace
    → iris.ide.openMarketplace
    → VSXCommands.TOGGLE_EXTENSIONS
    → Open VSX (ovsx-router-config.json)

채팅에서 "찾아 설치"
  액션 목록에 vsx 검색/설치 없음
  GitHub URL이 있으면
    → extension.install_github
    → Hermes config.yaml mcp_servers / skills/
    → IDE plugins/ 와 user-data/plugins 는 건드리지 않음
  URL이 없으면
    → 웹 검색은 Hermes 자체 도구에 맡김
    → 설치로 이어지는 아이리스 액션은 URL이 생긴 뒤뿐
```

## 코드 리뷰

### 검은 영역

| 지점 | 한 일 | 요청을 막지 못한 이유 |
|---|---|---|
| `IdeUnifiedShell` (`ide_companion_page.py`) | 좌 `ide_host` 배경을 `void_black`으로 칠하고, 스플리터 핸들 폭을 0으로 둔 뒤 `_lock_ratio`로 80:20을 되돌린다. | 경계 드래그로 채팅을 늘리는 일을 막아 두었다. |
| `_activate_iris_ide_companion_tile` | IDE를 `set_embedded`로 메인 창의 자식 창으로만 붙인다. 주석대로 `QWidget` 임베드는 WebEngine 입력 때문에 금지다. | 시각적으로는 한 창이지만 크기 주인은 둘이다. |
| `_sync_docked_iris_ide_geometry` | `ide_host`의 화면 좌표에 IDE 창을 맞춘다. | IDE 창이 먼저 줄어든 뒤에는 호출되지 않는다. 메인 창 크기 변경 때만 다시 맞춘다. |
| `MainWindow.resizeEvent` | 컴패니언이면 `apply_ratio` 후 sync. | 사용자가 맞춘 비율이 있으면 그것도 80:20으로 덮는다. |
| `IrisIdeWindow` + `FramelessShell(inset_content=True)` | Theia를 가장자리에서 8px 들여 그리고, 셸 배경은 검정이다. 그립은 `startSystemResize(IDE 창)`. | 들여쓰기가 검은 테두리를 만든다. 그립은 스플리터를 움직이지 않는다. |
| `_embed_viz_in_companion_slot` | 메인 창 그립은 좌·하단만 숨기고, `set_ide_insets(0,0,0,0)`로 호스트 레이아웃 여백만 없앤다. | IDE 창 안의 8px 들여쓰기와 IDE 창 자체 그립은 그대로다. |

하지 않은 일: IDE 창 `resizeEvent`에서 스플리터 비율을 갱신하지 않는다. 검은 칸 폭 = IDE 창 폭인 구속은 없다.

### 탭

| 지점 | 한 일 | 요청을 막지 못한 이유 |
|---|---|---|
| `onTabPointerDown` | 탭에서 채팅으로 끌어 첨부하려고, 캡처 단계에서 `stopPropagation` 하고 `draggable`을 켠다. | 클릭과 드래그를 구분하지 않는다. 짧은 클릭도 Theia에 안 간다. |
| `onTabPointerUp` / `pointerup` 리스너 | `tabDrag`만 지운다. | 클릭한 탭을 `activate` 하지 않는다. |
| `syncEditor` | `editorManager.currentEditor` 하나만 `setEditorState`로 보낸다. | 탭 바가 바뀌지 않으면 상태도 안 바뀐다. |
| 브리지 `getOpenEditors` | `editorState`가 있으면 길이 1인 배열, 없으면 빈 배열. | Theia에 탭이 여러 개여도 목록이 하나다. |
| `openInEditor` | 채팅·브리지가 연 파일은 `mode: 'activate'`로 연다. | 사람이 이미 열린 다른 탭을 누르는 경우와 무관하다. |

하지 않은 일: 탭 목록을 브리지에 올리는 코드, 클릭 후 `editorManager.open`으로 복구하는 코드.

### PDF

| 지점 | 한 일 | 요청을 막지 못한 이유 |
|---|---|---|
| `hermes_owns_local_intents` | Hermes가 켜지면 PDF 로컬 가로채기를 끈다. | 저장은 모델이 도구를 불렀는지에 달린다. |
| `note.export_pdf` | `content`가 있어야 하고, 자식 프로세스가 파일을 만든 뒤에만 ok. 경로 생략 시 `~/Documents/IRIS/iris-note.pdf`. | IDE에서 열린 파일을 읽지 않는다. 상대 경로는 프로세스 현재 폴더 기준이다. 프로젝트 탐색기에 없을 수 있다. |
| `_try_local_pdf_save` | Hermes가 꺼졌을 때 직전 비서 문장을 PDF로 쓰고 경로를 말한다. | 열린 에디터 원문이 아니다. Hermes 사용 중에는 이 함수가 안 돈다. |
| `settle_completion_claim` | `작성했습니다`, `처리 완료`, `파일을 열었습니다`만 디스크와 맞춘다. | `PDF로 저장했습니다`는 패턴 밖이라, 파일이 없어도 문장이 남는다. |
| `project.write_file` | 문자열을 프로젝트 파일로 쓴다. | `.pdf`로 쓰면 바이너리 PDF가 아니다. 이번 조사에서 PDF 전용 거부는 없다. |

하지 않은 일: `note.export_pdf`의 ok 경로를 채팅 문장 게이트에 연결하는 일. 에디터 버퍼를 PDF 바이트로 넘기는 일.

### 마켓플레이스 · MCP · Skill

| 지점 | 한 일 | 요청을 막지 못한 이유 |
|---|---|---|
| `ovsx-router-config.json` + `iris_ide_runtime` | Theia 기동에 `--ovsx-router-config`로 Open VSX를 붙인다. 설치분은 `~/.iris-light/iris-ide/user-data/plugins`. | 채팅 액션이 이 레지스트리를 조회하지 않는다. |
| `iris.ide.openMarketplace` | Extensions 뷰를 연다. | 검색어를 넣고 설치하는 명령이 아니다. |
| `action_catalog.json` | IDE 쪽은 폴더·파일 열기, 컴패니언 진입까지. 확장 검색/설치 이름은 없다. | 모델이 카탈로그에 없는 설치를 호출할 수 없다. |
| `extension.install_github` | URL의 README·`mcp.json`·`SKILL.md`를 읽어 Hermes `config.yaml` / `skills/`에만 넣는다. 비밀이 없으면 `needs_input`. 로컬 빌드가 필요한 서버는 거부. 깊이 3, 목록 25, 파일 40개 한도. | Open VSX와 무관하다. URL이 없으면 시작하지 못한다. |
| `skill_mcp_dialogs` | 이미 `config.yaml`에 있는 MCP와 로컬 스킬을 보여 주고, 이름·실행 파일을 손으로 추가한다. | 공개 목록 검색이 아니다. |
| `ui.open_mcp` / `ui.open_skills` | 그 대화상자만 연다. | 조사·설치를 대신하지 않는다. |

하지 않은 일: Open VSX 쿼리, VSIX 설치를 아이리스 액션으로 노출하는 일. Smithery·Glama·skills.sh 같은 목록을 고르는 일. 설치한 VS Code 확장과 Hermes MCP를 같은 요청으로 잇는 일.

## 지금 가능한 것 / 없는 것

| 상황 | 지금 |
|---|---|
| IDE 가장자리를 당겨 채팅 칸이 그만큼 넓어짐 | 불가. 검은 `ide_host`와 채팅은 80:20 고정. IDE 창만 줄면 검정이 남음. |
| 열린 탭을 눌러 그 파일 내용이 보임 | 코드상 클릭이 Theia에 전달되지 않음. |
| 채팅으로 `ide.open_file` 해서 그 파일을 활성 탭으로 | 가능. 브리지 `openFile` → `activate`. |
| 열린 탭 전체를 아이리스가 알고 고름 | 불가. `getOpenEditors`는 현재 편집기 하나. |
| 채팅 문장을 PDF로 저장 (`note.export_pdf`가 실제로 ok) | 가능. 파일은 지정 경로 또는 `Documents/IRIS`. 프로젝트 트리에는 안 생김. |
| IDE에서 열린 xlsx·md·코드를 그대로 PDF로 | 불가에 가깝다. 도구는 넘어온 문자열만 그린다. 에디터 바이트를 읽지 않는다. |
| 도구 없이 "PDF로 저장했습니다" | 문장이 남을 수 있다. 완료 게이트가 그 말을 막지 않는다. |
| 사람이 Extensions에서 Open VSX 검색·설치 | 가능. Theia UI. QA-062는 아직 미실행으로 적혀 있다. |
| "마켓플레이스에서 ○○ 찾아서 설치해"를 채팅이 수행 | 불가. 검색·설치 액션 없음. |
| GitHub URL을 주고 MCP 또는 Skill 설치 | 가능. 비밀·작업 디렉터리가 필요하면 되묻고, 값은 만들지 않는다. |
| "노션 MCP 찾아줘", "슬라이드 스킬 조사해서 연결"처럼 이름만 | 목록 검색 액션 없음. 모델이 웹에서 URL을 찾은 뒤에야 `extension.install_github`. 못 찾으면 설치로 안 이어짐. |
| 설치한 Open VSX 확장을 Hermes 도구로 자동 연결 | 불가. 저장 위치가 다름 (`user-data/plugins` vs `%LOCALAPPDATA%/hermes`). |
| 이미 등록된 MCP를 채팅에 넣기 | 가능. `ui.open_mcp`와 컴포저 메뉴. 공개 레지스트리 검색은 아님. |

## 이 저장소에서 이미 겪었던 상황

아래는 이번 네 가지와 같은 종류의 빈자리거나, IDE를 쓰는 동안 다시 만나는 경로다.

| 상황 | 코드가 하는 일 |
|---|---|
| IDE를 줄였더니 검정만 남고 채팅은 그대로 | 이번 1번. 스플리터 잠금 + HWND 별도 리사이즈. |
| 탭이 여러 개인데 다른 파일이 안 보임 | 이번 2번. 클릭 차단 + 편집기 상태 1개. |
| PDF로 저장했다고 했는데 프로젝트에 파일이 없음 | 이번 3번. 기본 경로가 `Documents/IRIS`이거나, 도구 ok 없이 말만 함. |
| 파일을 썼다고 했는데 디스크에 없음 | `settle_completion_claim`은 `작성했습니다` 등만 막는다. 다른 완료 문장은 통과. `project.write_file` ok와 실제 파일이 있을 때만 경로를 남긴다. |
| 코드 실행이 IDE 터미널이 아니라 다른 곳으로 | 프롬프트는 `project.run`만 쓰라고 한다. Hermes 내장 터미널은 쓰지 말라고 적혀 있다. 모델이 어기면 IDE 통합 터미널에 안 나온다. |
| 탐색기 파일을 채팅으로 드래그 | 탭·트리 드래그를 Control Surface `chat.drag_start` / `chat.drag_end`로 넘기려고 탭 `pointerdown`을 끊는다. 그 부작용이 탭 클릭이다. |
| 폴더를 열기 전 시작 화면이 없거나 Open Folder가 없음 | 실행 중인 번들이 소스와 다르면 `iris.ide.showStartScreen` / `iris.ide.openFolder`가 없다. `sync_workspace_build` 없이 `lib/browser`만 고친 경우. |
| IDE 설치가 yarn `drivelist`에서 멈춤 | 마켓플레이스 UI 자체가 안 뜬다. 설치 실패 보고서는 `IRIS-IDE설치실패-yarn-drivelist`. |
| 확장이 네이티브 모듈을 요구 | `@theia/ffmpeg`는 스텁이다. 영상·일부 네이티브 확장은 설치돼도 동작 보장이 없다. |
| 위키에 저장하라는데 PDF로, 또는 그 반대 | PDF 의도 판별은 `위키`가 들어가면 PDF 로컬 저장을 포기한다. Hermes가 켜지면 둘 다 모델 도구다. 위키는 `wiki.import_content`, PDF 파일은 `note.export_pdf`. |
| 위키에 저장했다고 했는데 받은편지함만 | 분류가 애매하면 inbox. `ask_folder`가 true일 수 있다. 저장 성공은 도구의 saved 건수로만 말하게 되어 있다. |
| 긴 작업을 말만 하고 파일을 안 씀 | 턴 감독·일괄 저장은 별도 구현 프롬프트에 있다. PDF·확장 설치와 같이, ok 없는 완료 문장이 같은 구멍이다. |
| 다이어그램을 HTML 파일로 저장 | 안내문은 `diagram.render`만 쓰라고 한다. IDE에 html을 쓰는 경로는 그 요청의 구현이 아니다. |
| 사진 속 코드를 파일로 | `project.write_image_code`. 대상 파일명이 없으면 되묻고, ok 없이 썼다고 말하면 안 된다. |
| 메일·일정·에뮬 조작을 IDE 확장처럼 설치 | 이미 아이리스 액션이다 (`email.*`, `calendar.*`, `emulator.*`). 마켓플레이스에서 찾을 대상이 아니다. |
| 채팅이 여러 개일 때 IDE 탭도 세션마다 | IDE 창·`editorState`는 하나다. 채팅 세션이 늘어도 탭 목록 API는 그대로 하나다. |
| GitHub MCP인데 키가 필요 | `needs_input` 후 사용자가 값을 줘야 이어서 설치한다. 키를 추측해 넣지 않는다. |
| 주소 없는 "오픈소스 MCP/Skill 조사" | 설치 함수는 URL 파싱부터 시작한다. 조사 전용 카탈로그는 없다. |

## 개선안

구조에서 비어 있는 곳만 적는다.

1. **크기 한 값으로.** IDE 창 그립이 `IrisIdeWindow`를 `startSystemResize` 하지 않게 하고, 좌우 경계 드래그가 `IdeUnifiedShell` 스플리터 폭을 바꾸게 한다. 바꾼 뒤에는 `_sync_docked_iris_ide_geometry`만 호출해 HWND를 `ide_host`에 붙인다. `apply_ratio(0.8)`는 최초 진입에만 두고, 이후 메인 창 리사이즈는 마지막 비율을 유지한다. `inset_content`의 8px 검정 테두리는 호스트와 IDE를 다시 어긋나게 하므로, 그립을 호스트 경계로 옮기면 본문 들여쓰기는 빼는 쪽이 맞다. `QWidget`으로 Theia를 삼키는 방식은 터미널 입력 때문에 현재 주석이 금지한다.
2. **탭 클릭과 드래그 분리.** `pointerdown`에서 항상 `stopPropagation` 하지 않는다. 움직인 뒤에만 드래그로 보고, 클릭은 Lumino에 넘기거나 손 뗀 좌표의 탭을 `editorManager.open(..., activate)` 한다. 브리지 `getOpenEditors`는 `EditorManager`의 전체 위젯을 넣는다.
3. **PDF 문장은 파일만.** `저장했습니다`를 완료 게이트에 넣고, 그 턴의 `note.export_pdf` ok 경로가 디스크에 있을 때만 그 문장을 남긴다. 프로젝트에 두라는 말이면 `path`를 워크스페이스 절대경로로 만든다. 열린 파일 변환은 에디터 경로를 읽어 `content`로 넣는 액션이 따로 있어야 한다. `.pdf`를 `project.write_file` 문자열로 쓰는 호출은 거절한다.
4. **찾기와 설치를 액션으로.** IDE 확장은 Open VSX 검색 + 설치(또는 VSIX) 액션. MCP·Skill은 기존 `extension.install_github` 앞에, 사용자가 고른 GitHub URL을 확정하는 단계. 이름만 있는 요청은 URL을 만들기 전에는 설치했다고 말하지 않는다. 두 저장소(Theia plugins / Hermes)를 한 번에 설치했다고 합치지 않는다.
