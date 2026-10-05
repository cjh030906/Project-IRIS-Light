# Prompt: 마켓플레이스 설치는 VSIX를 Theia에 넣는다

배경: `docs/code-review/completed/IDE-마켓플레이스설치-핀만되고-뷰어미적용-원인.md`.
`ide.marketplace_install` 은 `.vscode/extensions.json` 과 `.iris/marketplace.json` 만 고친다. VSIX를 받지 않고 `deployedPlugins` 도 없다. 채팅은 설치 완료라고 하고 PDF는 안 열린다.

Theia 1.74 는 기동 때 `THEIA_CONFIG_DIR/deployedPlugins` 를 `local-dir:` 로 읽는다 (`PluginVSCodeDeployerParticipant`). 이미 켜진 프로세스는 그 폴더를 다시 보지 않는다.

---

```text
Context:
- pin_extension 은 추천 목록과 .iris/marketplace.json 만 쓴다.
- ide.marketplace_install 은 그 함수만 부르고 ok 를 반환한다.
- 카탈로그 요약은 「VSIX를 받지 않는다」인데, 성공 JSON과 15f·메인 창 문장에는 그 말이 없다.
- Theia 사용자 데이터는 iris_ide_config_dir() = ~/.iris-light/iris-ide/user-data.
- 배포 폴더는 그 아래 deployedPlugins/<publisher.name>/ 이고, 안에 extension/package.json 과 engines.vscode 가 있어야 디렉터리 핸들러가 확장으로 받는다.
- ide.marketplace_install 은 UI 스레드 밖이다. Qt 위젯은 _call_on_ui 로만 건드린다.

Goal:
1. ide.marketplace_install 은 Open VSX에서 그 id의 VSIX를 받아 deployedPlugins 에 푼다. extension/package.json 이 디스크에 있을 때만 ok.
2. 추천 목록과 .iris/marketplace.json 은 그대로 남긴다. 기록에 version 과 deployed 경로를 적는다.
3. IDE 프로세스가 켜져 있으면 stop 후 같은 워크스페이스로 start 하고, 화면은 새 URL로 다시 연다. 꺼져 있으면 파일을 두고 reload=not_running.
4. 모델은 package.json 이 없으면 설치했다고 말하지 않는다. PDF 탭이 이미 열렸다고 말하지 않는다. reload=reloaded 이면 IDE를 다시 읽는 중이라고 말한다.

Constraints:
- publisher.name 이 아닌 id 는 거절한다.
- VSIX 밖 경로는 풀지 않는다. 다운로드는 40MB, 압축 해제 합은 80MB에서 자른다.
- 번들 plugins 디렉터리(~/.iris-light/runtimes/iris-ide/plugins)는 건드리지 않는다.
- Qt 슬롯 밖으로 예외를 보내지 않는다. 재기동 실패는 err_result.
- 검색 액션은 목록만 반환한다.

Interface:
install_extension(project_root, extension_id, deploy_root, *, fetch=None, download=None)
- Open VSX GET /api/{namespace}/{name} 의 files.download 를 받는다.
- zip 을 deploy_root/<id>/ 에 푼다. 기존 폴더가 있으면 지우고 다시 푼다.
- extension/package.json 에 name, version, engines.vscode 가 없으면 폴더를 지우고 오류.
- pin_extension 을 먼저 호출하고, marketplace.json 행에 version, deployed 를 넣는다.
- 반환: id, version, recommendations, record, deployed, package, installed=true.

ide.marketplace_install
- 열린 프로젝트가 없으면 오류.
- deploy_root = iris_ide_config_dir()/deployedPlugins.
- 런타임 pid 가 있으면 stop → start(workspace) → UI 스레드에서 _load_theia_after_launch.
- 반환에 reload = reloaded | not_running. start 실패는 ok false.

안내
- action_catalog 요약, hermes_memory_nudge 15f, 메인 창 마켓플레이스 문장:
  설치는 VSIX를 deployedPlugins 에 푼 뒤이다.
  package.json 없이 설치라고 말하지 말 것.
  PDF가 이미 보인다고 말하지 말 것.
  reload=reloaded 이면 IDE를 다시 여는 중이다.
  reload=not_running 이면 다음 IDE 기동 때 적용된다.

Output:
- iris/system/project_marketplace.py
- iris/ui/control_actions/ide.py
- iris/system/control_surface.py (이 액션 대기 180초)
- action_catalog.json, hermes_memory_nudge.py, main_window.py 문장
- 자검: .venv\Scripts\python.exe -m iris.ui._check_ide_request_tools
  가짜 VSIX로 package.json 생성, 경로 이탈 zip 은 오류, 빈 검색어는 기존과 같다.
```
