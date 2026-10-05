# Prompt: IRIS IDE를 요청대로 읽고 고친다

배경: `docs/code-review/IDE-컨트롤-커서수준-현황.md`.
채팅은 Hermes `iris_invoke` → 컨트롤 → `standalone-bridge.js` 다. 폴더·파일·디스크 쓰기·통합 터미널 입력·Open VSX 배포까지는 간다. `getDiagnostics`·`gotoSymbol`·`findReferences`·`saveFile`·`startDebug` 는 Theia를 부르지 않고 성공처럼 답한다. `insertText` / `replaceSelection` 은 선택 영역이 아니라 파일 끝에 붙인다. `runTerminalCommand` 는 `queued: true` 만 돌려 종료 코드가 없다.

Theia 1.74 업그레이드와 `@theia/ai-mcp` 는 하지 않는다. 이미 있는 편집기·마커·언어 기능·태스크·디버그를 폴러가 호출한다.

---

```text
Context:
- 프런트 폴러가 실행하는 명령은 openFile, gotoFile, createTerminal, runTerminalCommand 뿐이다.
- pushBridge 는 편집기 URI와 커서만 setEditorState 로 올린다. 문제 마커는 안 올린다.
- 브리지 dispatch 가 프런트 큐 없이 JSON을 만드는 분기가 모델에게 ok 로 보인다.
- project.run 은 통합 터미널에 보낸 뒤 .iris/last_run.log 의 IRIS_EXIT 로 종료를 확정한다.
- ide.marketplace_install 은 VSIX를 deployedPlugins 에 푼 뒤 프로세스를 재기동한다. 플러그인 호스트 로드는 보지 않는다.
- 진단·심볼·디버그가 생기기 전에는 iris-vibe-code 에 그 단계를 넣지 않는다. 이번 구현 다음에 넣는다.

Goal:
1. 브리지가 하지 않은 명령은 saved:true, hooked:true, items:[], diagnostics:[] 를 주지 않는다. 프런트가 처리했거나, 못 하면 오류다.
2. getDiagnostics 는 프런트가 문제 마커를 읽어 setDiagnostics 로 올린 목록이다. reported 가 false 이면 문제가 없다는 뜻이 아니다. 빈 배열은 마커를 읽었고 문제가 없을 때만이다.
3. gotoSymbol, findReferences, gotoDefinition, formatDocument 는 폴러가 Monaco 언어 기능을 호출한 결과만 반환한다.
4. insertText, replaceSelection, saveFile, saveAll 은 열린 편집기 버퍼 명령이다. 그 탭이 없을 때만 디스크에 쓰고 via:disk 를 붙인다. 디스크에 붙인 경우는 applied 로 구분한다.
5. runTerminalCommand 는 터미널에 넣은 뒤 last_run.log 의 IRIS_EXIT 와 출력을 반환에 넣는다. queued:true 만으로 끝나지 않는다.
6. runTask, startDebug, stopDebug, continueDebug 는 TaskService / DebugSessionManager 를 호출한다. 세션이나 태스크가 없으면 성공이 아니다.
7. 확장 설치 뒤 plugin host 가 그 id 를 로드했는지를 한 번 묻는다. loaded 가 true 가 아니면 뷰어가 열렸다고 말하지 않는다.
8. 채팅은 ide.diagnostics, ide.symbols, ide.references, ide.definition, ide.edit, ide.save, ide.task, ide.debug, ide.plugin_status 로 이 결과를 본다.

Constraints:
- 통로는 iris_invoke 다. IDE 브리지를 별도 MCP로 쪼개지 않는다.
- execSync 로 터미널 명령을 대신 돌리지 않는다.
- 프런트 폴이 없으면 오래 기다리지 않고 오류다. 파일 열기·선택 바꾸기의 디스크 폴백만 예외다.
- Qt 슬롯 밖으로 예외를 보내지 않는다. 프론트를 기다리는 액션은 UI 스레드 밖이다.
- Theia 버전은 1.74.0 그대로다.

Interface:
setDiagnostics { diagnostics }
- reported true. 목록은 마커를 읽은 결과.

getDiagnostics
- { reported:false, diagnostics:null } 또는 { reported:true, diagnostics:[...] }.

편집
- 탭이 있으면 via:editor. 없으면 via:disk 와 applied.

runTerminalCommand
- via:theia_terminal, queued:false, completed, exit_code, output.

startDebug { name }
- 설정 이름이 있고 세션이 생겼을 때만 started:true.

pluginLoaded { id }
- { id, loaded }.

Output:
- integrations/iris-ide/bridge/standalone-bridge.js
- integrations/iris-ide/src/browser/iris-ide-bridge-poller.ts
- integrations/iris-ide/src/browser/iris-ide-bridge-ops.ts
- integrations/iris-ide/src/browser/iris-ide-frontend-contribution.ts
- integrations/iris-ide/src/common/iris-ide-protocol.ts
- integrations/iris-ide/src/node/iris-ide-bridge-server.ts
- iris/infrastructure/iris_ide_client.py
- iris/system/ide_link.py
- iris/ui/control_actions/ide.py
- iris/ui/control_actions/action_catalog.json
- iris/system/control_surface.py
- iris/system/hermes_memory_nudge.py
- iris/ui/window/main_window.py
- integrations/hermes-skills/iris-control/iris-vibe-code/SKILL.md
- 자검: .venv\Scripts\python.exe -m iris.system._check_iris_ide_bridge
  .venv\Scripts\python.exe -m iris.system._check_iris_ide_bridge_state
  .venv\Scripts\python.exe -m iris.ui._check_control_action_split
  프런트 없이 diagnostics.reported 는 false, saveAll·startDebug 는 오류, 있는 파일 saveFile 은 via:disk.
  그 다음 sync_workspace_build. 번들에 setDiagnostics 가 있어야 한다.
```
