# 아이리스가 IRIS IDE를 요청대로 다루는가

| 항목 | 내용 |
|---|---|
| 문서 번호 | IRIS-REV-2026-1003-04 |
| 작성일 | 2026-10-03 |
| 대상 | 채팅 요청으로 IRIS IDE를 파악하고 조작하는 경로 |
| 목적 | 커서의 에이전트처럼, 요청에 따라 IDE의 편집기·진단·실행·확장을 읽고 다루는지 |
| 조사 범위 | `iris_invoke` IDE 액션, `standalone-bridge.js`, 프런트 폴러, `iris-vibe-code` 스킬, Theia 1.74 플러그인 배포 |
| 하지 않은 일 | Theia 업그레이드, 진단·디버그 브리지 구현, 실행 중인 IDE 재기동 |

같은 날의 마켓플레이스 빈 자리는 `ide.marketplace_install` 이 VSIX를 `deployedPlugins` 에 풀도록 바꿔 두었다. 그 변경은 이 문서의 「확장 설치」 한 칸만 메운다.

---

## 1. 결론

요청만으로 IRIS IDE를 커서처럼 다루지는 못한다. 폴더를 열고, 파일을 편집기에 띄우고, 디스크에 쓰고, 통합 터미널에서 명령을 돌리고, Open VSX 확장을 받아 두는 곳까지는 간다. 편집기가 지금 보여주는 버퍼, 문제 목록, 심볼, 참조, 디버그, 태스크는 브리지가 성공처럼 답하거나 빈 값을 돌려준다. Theia 안의 그 서비스까지 닿지 않는다.

---

## 2. 확인한 사실

채팅의 IDE 조작은 Hermes `iris_invoke` → Iris 컨트롤 HTTP → 액션이다. IDE 프로세스와 말하는 쪽은 `integrations/iris-ide/bridge/standalone-bridge.js` 다. 기동 때 `IRIS_IDE_STANDALONE_BRIDGE=1` 이라 Theia 안의 같은 이름 서버는 포트를 다시 잡지 않는다.

프런트 폴러 `iris-ide-bridge-poller.ts` 가 실행하는 명령은 네 개다. `openFile`, `gotoFile`, `createTerminal`, `runTerminalCommand`.

`iris-ide-frontend-contribution.ts` 의 `pushBridge` 는 열린 편집기 목록과 커서 정보를 `setEditorState` 로 올린다. 문제 목록은 올리지 않는다.

`getDiagnostics` 는 항상 `[]` 다. `gotoSymbol` 과 `findReferences` 는 `{ items: [] }` 다. `formatDocument` 는 `{ formatted: false }` 다. `runTask` 는 `{ started: false }` 다. `startDebug` / `stopDebug` / `continueDebug` 는 `{ hooked: true }` 이고 디버그 세션을 만들지 않는다.

`saveFile` / `saveAll` 은 디스크와 편집기를 보지 않고 `{ saved: true }` 다. `insertText` 와 `replaceSelection` 은 파일 끝에 바이트를 붙인다. Monaco 버퍼의 선택 영역이 아니다.

스킬 `integrations/hermes-skills/iris-control/iris-vibe-code/SKILL.md` 는 `project.write_file` 과 `project.run` 만 안내한다. 진단·심볼·디버그 스킬은 없다.

Theia 버전은 `iris/system/iris_ide_runtime.py` 의 `THEIA_VERSION = "1.74.0"` 이다. 1.75의 `@theia/ai-mcp` 와 Agent Plugin 은 이 실행본에 없다.

---

## 3. 구조

「이 오류 고쳐서 실행해줘」는 파악과 조작이 갈라진다. 파악은 브리지가 빈 성공을 주는 지점에서 멈춘다.

```
채팅
  → Hermes iris_invoke
      → 컨트롤 /v1/invoke
          → ide.open_folder / ide.open_file / project.write_file / project.run
          → ide.marketplace_search / ide.marketplace_install
  → IrisIdeClient
      → standalone-bridge.js
          → 디스크 (createFile, deleteFile, replaceRange, git)
          → enqueueFrontend
              → 폴러 dispatch
                  → openFile, gotoFile, createTerminal, runTerminalCommand
                  → 그 외 명령은 unsupported frontend command
          → 메모리만 (saveFile, getDiagnostics, gotoSymbol, debug, task)

Theia가 이미 갖고 있는 쪽 (이번 경로가 호출하지 않음)
  EditorManager / Monaco 버퍼
  문제 마커
  언어 서버 심볼·참조
  TaskService
  DebugService
  PluginDeployer (기동 때 deployedPlugins 스캔)
```

갈라지는 곳: 브리지 `dispatch` 가 프런트 큐로 넘기지 않고 즉시 JSON을 만드는 분기. 모델은 `ok` 와 그 JSON만 본다.

확장 설치만 따로 갈라진다. `ide.marketplace_install` → `install_extension` 이 VSIX를 `~/.iris-light/iris-ide/user-data/deployedPlugins/<id>/` 에 푼다. 프로세스가 켜져 있으면 `stop` 후 `start` 하고 화면 URL을 다시 연다. 꺼져 있으면 `reload=not_running` 이고 다음 기동 때 `PluginVSCodeDeployerParticipant` 가 그 폴더를 읽는다.

---

## 4. 코드 리뷰

### 4.1 요청이 IDE에 닿는 곳 — 한 일

`iris/mcp/iris_control_stdio.py` 의 `iris_invoke` 는 컨트롤 `/v1/invoke` 로 액션 이름과 인자를 넘긴다. IDE 액션은 `iris/ui/control_actions/ide.py` 에 있다. 폴더 열기, 파일 열기, 마켓플레이스, 프로젝트 로그가 여기 있다. 파일 내용과 실행은 `project.write_file`, `project.run` 이다. `iris-vibe-code` 는 그 둘만 순서로 적는다.

`openFile` 은 `standalone-bridge.js` 가 프런트 큐에 넣는다. 폴러가 3.5초 안에 편집기를 열지 못하면 브리지가 `opened: true, via: bridge_fallback` 을 돌려 준다. 편집기가 안 떠도 성공으로 읽힐 수 있다.

### 4.2 파악 — 한 일, 못 막은 이유

`pushBridge` 는 편집기 URI와 커서를 브리지 메모리에 넣는다. `getActiveEditor` / `getOpenEditors` / `getCursorPosition` / `getSelection` 은 그 메모리다. 프런트가 밀기 전에는 비어 있다.

`getDiagnostics` 는 Theia 마커를 읽지 않는다. 반환이 빈 배열이라 「문제 없음」과 「아직 안 읽음」이 같다. `gotoSymbol`, `findReferences` 도 같은 형식의 빈 목록이다. 언어 서버를 호출하지 않아서 못 막는다.

`getGitStatus` / `getGitDiff` 는 워크스페이스에서 `git` 을 실행한다. 이 둘은 디스크 기준이라 IDE 소스 컨트롤 뷰와 어긋날 수 있지만, 빈 성공은 아니다.

### 4.3 조작 — 한 일, 못 막은 이유

`createFile`, `deleteFile`, `renameFile`, `replaceRange`, `applyTextEdit` 는 브리지 프로세스의 `fs` 다. 열려 있는 편집기 버퍼를 바꾸지 않는다. 사용자가 그 탭에 저장하지 않은 내용이 있으면 디스크 쓰기가 그 내용과 따로 논다.

`insertText` / `replaceSelection` 은 선택 영역을 지우지 않고 파일 끝에 붙인다. 이름과 동작이 다르다.

`saveFile` 은 저장하지 않고 `saved: true` 다. 저장 안 된 버퍼를 디스크로 내리지 못한다.

`runTerminalCommand` 는 폴러가 Theia 통합 터미널에 키 입력을 보낸다. `execSync` 폴백은 없다. 실행 결과는 터미널 위젯 안이고, 브리지 반환은 `queued: true` 다. 종료 코드와 출력 전문은 이 JSON에 없다. `project.run` 이 그 위를 요약한다.

`createTerminal` 은 프런트 대기가 끝나면 `created: false, via: bridge_fallback` 일 수 있다.

디버그 세 명령은 `hooked: true` 만 반환한다. `DebugService` 를 부르지 않아서 브레이크포인트와 계속 실행을 못 막는다. `runTask` 는 시작하지 않았다고 정직하게 `started: false` 를 준다. 디버그만 성공으로 보인다.

### 4.4 확장 — 한 일

`install_extension` (`iris/system/project_marketplace.py`) 은 Open VSX 메타의 `files.download` 로 VSIX를 받아 `deployedPlugins/<publisher.name>/` 에 푼다. `extension/package.json` 의 `name`, `version`, `engines.vscode` 가 없으면 폴더를 지우고 오류다. 압축 경로에 `..` 가 있으면 오류다. 추천 목록과 `.iris/marketplace.json` 은 남고, 기록에 `version` 과 `deployed` 가 붙는다.

켜진 런타임은 `_reload_ide_if_running` 이 `stop` 후 같은 워크스페이스로 `start` 한다. Theia 1.74 는 `deployedPlugins` 를 기동 때 한 번 읽기 때문이다 (`PluginVSCodeDeployerParticipant.onWillStart`). 화면은 UI 스레드의 `_load_theia_after_launch` 로 새 URL을 연다. 프로세스가 없으면 `reload=not_running` 이다.

이 반환은 패키지가 디스크에 있다는 뜻이다. PDF 탭이 열렸다는 뜻이 아니다. 안내 문장(15f, 카탈로그, 메인 창)이 그 둘을 나누라고 적는다.

### 4.5 하지 않은 일

- Monaco 버퍼의 선택 영역을 읽고 고치지 않았다.
- Theia 문제 마커, 아웃라인, 참조, 정의로 가지 않았다.
- 디버그 세션과 태스크를 시작하지 않았다.
- 저장 명령을 편집기 `save` 에 연결하지 않았다.
- 설치된 확장을 플러그인 호스트에 질의해서 `loaded` 를 확인하지 않았다. 재기동 성공으로 대신한다.
- Theia 1.75 Agent Plugin / `@theia/ai-mcp` 로 올리지 않았다.

---

## 5. 개선안

1. 브리지가 하지 않는 명령은 `hooked: true` 나 `saved: true` 를 주지 않는다. 프런트 큐로 Theia 서비스에 닿거나, 못 한다는 오류를 반환한다.
2. `getDiagnostics` 는 프런트가 마커를 읽어 `setEditorState` 와 같은 방식으로 올린 목록이다. 빈 배열은 문제가 없을 때만 쓴다.
3. `gotoSymbol`, `findReferences`, 정의 이동은 폴러가 Theia 언어 기능을 호출한 결과만 반환한다.
4. 선택 영역 바꾸기와 저장은 디스크 `fs` 가 아니라 열린 편집기 명령이다. 탭이 없으면 그때 디스크에 쓴다.
5. `runTerminalCommand` 반환에 터미널이 끝난 뒤의 출력과 종료 코드를 넣는다. `queued: true` 만으로 실행 완료라고 말하지 않게 한다.
6. 디버그와 태스크는 Theia `DebugService` / `TaskService` 를 폴러에서 호출한다. 세션이 없으면 성공이 아니다.
7. 확장 설치 뒤 플러그인 호스트가 그 id를 로드했는지 한 번 확인한다. 재기동만으로 뷰어가 열렸다고 하지 않는다.

---

## 6. 차용

| 이름 | 가져올 부분 | 이번에 가져오지 않은 이유 |
|---|---|---|
| Theia 1.74 `PluginVSCodeDeployerParticipant`, `unpackToDeploymentDir` | `THEIA_CONFIG_DIR/deployedPlugins/<id>/` 안에 `extension/package.json` 과 `engines.vscode`. 기동 때 `local-dir:` 로 읽는다. | 배포 레이아웃은 `install_extension` 에 반영했다. 실행 중 핫 리로드 API는 이 버전에 없어서 프로세스 재기동으로 대신한다. |
| Theia 1.75 `@theia/ai-mcp`, Agent Plugin (`plugin.json`, `skills/`, `mcp.json`, `~/.agents/plugins`) | Theia 채팅이 MCP와 스킬을 확장으로 다는 쪽. 2026-09 1.75 릴리스. | 방향이 반대다. Iris는 IDE 밖 Hermes가 IDE를 부른다. 실행본은 1.74라 업그레이드 없이 서비스를 연결하는 편이 맞다. |
| Theia `EditorManager`, 마커, `TaskService`, `DebugService` | 이미 프로세스 안에 있는 편집·진단·실행·디버그. 폴러 `dispatch` 에 명령을 추가하면 된다. | 이번 구현은 마켓플레이스 빈 자리만 메웠다. 새 편집기를 옆에 만들지 않는다. |
| `SemanticWorkbenchTeam.mcp-server-vscode` (`code_checker`, `focus_editor`) | 문제 패널을 MCP 도구로 내보내고, 파일을 포커스하는 도구 이름. | VS Code 확장이다. Theia 프런트 폴러에 같은 이름을 붙이는 참고만 된다. |
| `nabheet.vscode-ide-mcp` (디버그, 터미널, LSP, 파일, 약 50도구) | 커서 밖 에이전트가 에디터에 요구하는 도구 목록. 진단, 호버, 참조, 이름 바꾸기, 브레이크포인트. | 구현은 그 VSIX가 아니라 IRIS IDE 브리지다. 목록만 개선안 1–6의 체크리스트로 쓴다. |
| VS Code MCP 가이드 (tools / prompts / resources) | 도구 설명과 읽기 전용 힌트. Hermes가 이미 MCP 클라이언트다. | IDE 브리지를 별도 MCP 서버로 쪼개지 않는다. 지금 통로는 `iris_invoke` 다. |
| Continue 에이전트 모드의 MCP | 에이전트일 때만 도구를 쓰는 구분. | Iris는 이미 Hermes 도구 호출이다. Continue 설정 파일을 붙이지 않는다. |
| 스킬 `iris-vibe-code` | 파일 작성 후 `project.run` 으로 터미널에 보여주는 순서. | 진단·디버그 도구가 생기기 전에는 그 스킬에 단계를 더하지 않는다. 빈 성공을 안내하면 모델이 고쳤다고 말한다. |
