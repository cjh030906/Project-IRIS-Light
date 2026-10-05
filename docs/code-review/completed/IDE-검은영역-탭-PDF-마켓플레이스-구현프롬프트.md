# Prompt: IDE 비율·탭·PDF 도구·프로젝트 확장·위키 기록

배경: `docs/code-review/IDE-검은영역-탭-PDF-마켓플레이스-현황.md`.
검은 칸과 채팅은 80:20으로 잠겨 있고, 탭 클릭은 드래그 캡처에 끊긴다. PDF는 헤르메스가 꺼졌을 때만 직전 문장을 저장한다. 마켓플레이스·MCP·Skill은 열린 프로젝트와 아이리스 본체를 구분하지 않는다.

PDF의 기획은 제출·종합처럼 사용자가 PDF가 필요할 때 만드는 것이다. 헤르메스 켜짐/꺼짐이 조건이 아니다.

---

```text
Context:
- IRIS IDE는 Qt 자식이 아니다. ide_host 위에 IrisIdeWindow를 좌표로 올린다.
- IdeUnifiedShell 스플리터 핸들 폭은 0이고, 움직이면 apply_ratio(0.8)로 되돌린다.
- 메인 창 리사이즈와 companion 폴링도 0.8로 덮는다.
- IrisIdeWindow는 inset_content 8px 검정 테두리와 자체 리사이즈 그립을 가진다.
- 탭 pointerdown 캡처가 항상 stopPropagation 한다. getOpenEditors는 현재 편집기 하나다.
- note.export_pdf는 content 문자열만 받고, 경로를 비우면 Documents/IRIS/iris-note.pdf다.
- 헤르메스가 꺼져 있을 때만 _try_local_pdf_save가 직전 비서 문장을 PDF로 쓴다.
- 완료 게이트는 「저장했습니다」를 보지 않는다. project.write_file은 .pdf 문자열을 거절하지 않는다.
- extension.install_github는 항상 Hermes config.yaml / skills/에 넣는다.
- Open VSX 검색·설치 액션은 없다.
- 위키에 아이리스 IDE 프로젝트 기록 폴더는 없다.

Goal:
1. 기본 비율은 8:2다. 사용자가 IDE와 채팅 사이 경계를 드래그하면 그 비율이 남고, 메인 창을 줄여도 그 비율을 유지한다. 컴패니언에 다시 들어갈 때만 8:2로 시작한다.
2. IDE 창 그립으로 IDE 창만 줄이지 않는다. 도킹 중에는 8px 검정 여백을 뺀다. HWND는 ide_host에 맞추고, 스플리터 핸들은 IDE 창에 가리지 않는다.
3. 탭을 짧게 누르면 그 편집기가 활성화된다. 움직인 뒤에만 채팅 드래그다. 브리지는 열린 편집기 목록을 기억한다.
4. PDF는 note.export_pdf 하나다. 사용자가 코드·메모·제출용 문서를 종합해 달라고 하면 content와 sources(파일 경로)로 PDF를 만든다. 헤르메스가 켜져 있어도 이 도구가 저장한다. 상대 경로는 열린 프로젝트 기준이다. 경로를 비우면 열린 프로젝트에 iris-note.pdf, 프로젝트가 없으면 Documents/IRIS다.
5. 「저장했습니다」「PDF로 저장했습니다」는 그 턴에 PDF 파일이 디스크에 있을 때만 남긴다. .pdf를 project.write_file 문자열로 쓰는 호출은 거절한다.
6. 아이리스 IDE에서 연 프로젝트에만 마켓플레이스 확장·오픈소스 MCP·Skill을 둔다. 파일은 그 프로젝트의 .vscode/extensions.json, .iris/marketplace.json, .iris/mcp.json, .iris/skills/다.
7. 아이리스 본체(Hermes config.yaml·skills)에 붙이는 요청은 IDE 컴패니언이 아닐 때만 받는다. IDE 안에서는 거절하고 기본 화면으로 안내한다. 이름만으로 설치했다고 말하지 않는다. 비밀 값은 만들지 않는다. Theia 확장과 Hermes MCP를 한 번에 설치했다고 합치지 않는다.
8. 위키 폴더 「아이리스 IDE」에, IDE에서 열거나 만든 프로젝트마다 노트를 둔다. 기획·진행·예정·문제를 개발이 진행될 때 고친다. 비밀 값은 노트에 넣지 않는다.

Constraints:
- QWidget으로 Theia를 삼키지 않는다. set_embedded는 top-level HWND다.
- PDF 바이트는 자식 프로세스 save_pdf만 만든다. 본체에서 PyMuPDF를 부르지 않는다.
- Open VSX는 검색과 프로젝트 목록 고정만 한다. VSIX를 받아 실행하지 않는다.
- 프로젝트 MCP를 Hermes 전역 config.yaml에 복사하지 않는다. 아이리스 본체 설치는 전역 설정을 그대로 쓴다.
- Qt 슬롯 밖으로 예외를 보내지 않는다.
- 두 창 타일(Cursor HWND)의 8:2 계약은 바꾸지 않는다. 조절은 단일 창 IdeUnifiedShell만이다.

Interface:

1) 비율 (iris/ui/workspaces/ide_companion_page.py, main_window.py, frameless_chrome.py, iris_ide_window.py)
   IdeUnifiedShell
   - 핸들 폭 6. splitterMoved는 현재 폭으로 비율을 기억하고 sync 콜백만 부른다. 0.8으로 되돌리지 않는다.
   - apply_ratio(total, ratio=None): ratio가 없으면 기억한 비율, 없으면 0.8. 비율은 0.5~0.88.
   - reset_user_ratio(): 컴패니언에 새로 들어갈 때만.
   - split_handle_width()
   MainWindow._activate_iris_ide_companion_tile
   - 아직 컴패니언이 아니면 reset_user_ratio() 후 배치.
   resizeEvent / 단일 창 폴링
   - apply_ratio(width)는 기억한 비율을 쓴다. 0.8을 인자로 넘기지 않는다.
   _sync_docked_iris_ide_geometry
   - IDE 폭 = iris 왼쪽 - host 왼쪽 - 핸들 폭.
   도킹 중 IrisIdeWindow
   - inset_content 끄기, 리사이즈 그립 숨김.
   - 도킹을 풀면 inset과 그립을 되돌린다.

2) 탭 (iris-ide-frontend-contribution.ts, standalone-bridge.js, iris-ide-bridge-server.ts)
   onTabPointerDown은 stopPropagation 하지 않는다.
   포인터가 6px 넘게 움직이면 chat 드래그로 보고, 손 떼면 drag_end.
   움직이지 않고 손 떼면 editorManager.open(uri, { mode: 'activate' }).
   syncEditor는 EditorManager.all 의 편집기를 editors로 setEditorState에 넣는다.
   getOpenEditors는 그 목록이다. editors가 없으면 현재 편집기 하나. {}는 빈 목록.

3) PDF (iris/knowledge/pdf_job.py, agent_turn.py, file_write_claim.py, project.py)
   compose_pdf_text(content, sources, project_root) -> str
   - sources는 존재하는 파일만. 파일당 20만 자, 최대 8개. 비밀 형태 줄은 [redacted].
   resolve_pdf_dest(raw, project_root) -> Path
   - 상대 경로는 프로젝트 아래. 비우면 프로젝트/iris-note.pdf 또는 Documents/IRIS/iris-note.pdf.
   note.export_pdf
   - content 또는 sources 중 하나. 저장 후 파일이 있을 때만 ok. 그 경로를 턴의 PDF 경로로 남긴다.
   settle_completion_claim
   - 저장했습니다 를 완료 문장으로 본다.
   - .pdf 파일이 확인되면 「PDF로 저장했습니다」와 경로만 남긴다.
   project.write_file
   - 확장자 .pdf 는 거절.
   헤르메스가 꺼진 로컬 저장도 resolve_pdf_dest를 쓴다. 도구와 같은 파일 규칙이다.

4) 설치 대상 (iris/system/extension_scope.py, github_extension_install.py, agent_turn.py)
   choose_extension_scope(ui_mode, project_root, asked) -> (scope, error)
   - IDE 컴패니언 + 폴더: 기본 project. asked=iris 이면 오류.
   - 기본 화면: 기본 iris. asked=project 이면 오류.
   project 설치
   - home = <project>/.iris 이고 PROJECT 마커가 있다.
   - MCP는 .iris/mcp.json 의 mcpServers. config.yaml에 쓰지 않는다.
   - Skill은 .iris/skills/custom/<name>/.
   - 게이트웨이 재시작은 iris 범위일 때만.
   iris 설치는 지금 Hermes 경로 그대로.

5) 마켓플레이스 (iris/system/project_marketplace.py)
   search_extensions(query) -> Open VSX 검색 결과. 빈 검색어는 오류.
   pin_extension(project_root, extension_id)
   - id는 publisher.name.
   - .vscode/extensions.json recommendations 와 .iris/marketplace.json 에만 넣는다.
   액션 ide.marketplace_search, ide.marketplace_install.
   IDE에서 프로젝트가 열려 있을 때만. 아니면 오류.

6) 위키 (iris/knowledge/ide_project_log.py)
   폴더 user/아이리스 IDE/<프로젝트슬러그>.md
   절: 기획, 진행, 예정, 문제.
   note_opened(wiki, root): 없으면 만들고 진행에 「프로젝트를 열었습니다」.
   note_file_written(window, root, rel): IDE 컴패니언에서 파일을 쓴 뒤 진행에 상대 경로 한 줄.
   note_update(wiki, root, plan, decision, issue, progress): 빈 값이 아닌 절만 고친다.
   액션 ide.project_log. IDE에서 프로젝트가 열려 있을 때만.
   ide.open_folder 성공 시 note_opened.
   is_sensitive 인 문장은 저장하지 않는다.

7) 모델 안내
   hermes_memory_nudge 15b·15c 와 메인 창 도구 문장:
   PDF는 note.export_pdf (content 및/또는 sources, path).
   IDE에서는 extension.install_github scope=project, 기본 화면에서만 scope=iris.
   마켓플레이스는 ide.marketplace_search / ide.marketplace_install.
   기획·예정·문제는 ide.project_log.
   ok와 파일이 없으면 저장·설치를 말하지 않는다.

Output:
- 위 파일과 action_catalog.json (레지스트리와 같은 목록. 이번 액션 3개 포함).
- 자검: python -m iris.ui._check_ide_request_tools
- 기존: python -m iris.ui._check_file_write_claim , python -m iris.ui._check_agent_turn_tools , python -m iris.ui._check_control_action_split
- iris-ide 소스를 고쳤으면 sync_workspace_build.
```
