# IRIS IDE에서 프로젝트를 열면 Iris가 종료된다

| 항목 | 내용 |
| --- | --- |
| 작성 | 2026-10-03 |
| 대상 | IRIS IDE에서 폴더를 고른 직후 `pythonw.exe`가 사라지는 종료 |
| 근거 | Windows 응용 프로그램 이벤트, `iris_light.db`, `ide-recent-folders.json`, `logs/pdf.log`, 폴더 열기 슬롯 |

이번 종료는 Qt `qFatal`이다. 오류 창이 없고 `closeEvent`도 없다.

## 확인한 사실

| 시각 (로컬) | 사실 |
| --- | --- |
| 01:19:13–14 | 이전 프로세스는 정상 종료. `logs/pdf.log`에 `closeEvent` → `aboutToQuit` → `main window destroyed` |
| 01:19:18 | 새 프로세스. `chat_conversations` id 18, 제목 `새 채팅`, 메시지 없음. 히어로/웰컴 진입의 빈 채팅과 같다 |
| 01:19:27.384 UTC+0 | `ide-recent-folders.json` 맨 앞이 `컴퓨터비전` (`…\동양미래대학교 2학년 2학기\컴퓨터비전`) |
| 같은 초 | `user_preferences.user_profile_v1`의 `preferred_ide`는 `iris_ide`, `project_root`는 그 폴더 |
| 01:19:27 | 응용 프로그램 오류. `pythonw.exe` 3.13.7150.1013, PID `0x3478`. 모듈 `Qt6Core.dll` 6.11.1.0, 오프셋 `0x1cf68`, 코드 `0xc0000409` |
| 01:19:30 | Windows Error Reporting. 종류 `BEX64`, P8 `c0000409`, P9 `7` |
| 01:19:27 이후 | `pdf.log`에 `closeEvent`가 없다. 창을 닫은 종료가 아니다 |

`Qt6Core.dll+0x1cf68` + `c0000409` + `BEX64`는 Qt가 `qFatal`로 프로세스를 끊는 자리다. 슬롯 밖으로 나간 Python 예외도, frameless 창의 modal 자식도 이 주소로 모인다. 오프셋이 같다고 원인이 하나인 것은 아니다.

`launcher.log`는 없다. WER `ReportArchive` 폴더도 없다. Python traceback은 디스크에 남지 않았다.

대화 18은 비어 있다. `start_new_conversation`은 활성 대화가 비어 있으면 새로 만들지 않고 그 id를 돌려준다. 그래서 01:19:27에 새 행이 없다는 사실만으로 `_open_fresh_work_chat` 도달 여부를 가를 수 없다. 폴더 기록과 프로필 저장까지는 갔고, 그 초 안에 프로세스가 죽었다.

12:32–12:34의 `python.exe` 충돌은 같은 DLL·오프셋이지만 다른 프로세스다. 이번 건은 01:19:27 `pythonw.exe`다.

## 구조

폴더를 고르는 입구는 세 개이고, IRIS IDE일 때는 모두 `_open_iris_ide_folder`로 모인다. 이번 요청은 여기서 죽는다. Theia `start()` 콜백(`_on_iris_ide_launch_ok`)은 런타임이 뜬 뒤라 이번 초의 종료점이 아니다.

```
폴더 선택
├─ 히어로 Open folder / Recent
│    IrisIdeHeroOverlay._pick_open | _emit_folder
│    QFileDialog 부모 = 히어로 (frameless 메인 위 ui_overlay의 자식)
│    record_opened_folder
│    folder_opened
│    MainWindow._on_iris_ide_hero_folder
│
├─ IDE 창 웰컴 Open folder / Recent
│    IrisIdeWelcomeLayer._pick_open_folder | _emit_folder
│    QFileDialog 부모 = 웰컴 (frameless IrisIdeWindow 안)
│    IrisIdeWindow.folder_opened
│    MainWindow._on_iris_ide_welcome_folder
│
└─ Theia File → Open Folder
     IrisIdeFrontendContribution.openFolderDialog
     askIris("ide.pick_open_folder")
     ide_pick_open_folder
     QFileDialog 부모 = frameless MainWindow
     ide_open_folder
     _open_ide_folder
     preferred_ide == iris_ide 이면 아래로 위임

_open_iris_ide_folder                          ← 01:19:27 사망 구간
  save_user_profile                            ← project_root 기록됨
  record_opened_folder                         ← json 시각과 일치
  히어로면 패널 복구 (_ui_mode = normal)
  _ensure_iris_ide_window
  apply_frameless_chrome (winId)
  show_loading
  IrisIdeLaunchWorker.start                   ← 기동은 백그라운드. 콜백 전
  _activate_iris_ide_companion_tile
       _apply_iris_ide_unified_layout
       QApplication.processEvents
       place_qt_window (메인 = 작업 영역)
       IrisIdeWindow.set_embedded → setParent
       winId / show / raise
  _bind_ide_session
  _open_fresh_work_chat
  히어로면 40ms 뒤 _run_companion_panels_intro  ← 이것도 Qt 슬롯
```

최근 항목을 누르면 파일 대화상자는 없다. Open folder를 누르면 있다. 둘 다 기록 함수를 먼저 치고 같은 슬롯으로 들어간다. 클릭이 어느 쪽이었는지는 파일만으로 갈라지지 않는다.

## 코드 리뷰

### `IrisIdeHeroOverlay._pick_open` / `_emit_folder`

`iris/ui/ide/iris_ide_hero_overlay.py`

Open folder는 `QFileDialog.getExistingDirectory(self, …)`다. `self`는 `IrisIdeHeroOverlay(ui_overlay)`이고, 그 조상은 frameless `MainWindow`다. 경로가 돌아온 뒤에 `record_opened_folder`를 하고 `folder_opened`를 쏜다. 대화상자를 띄우기 전에 죽는 구조가 아니다. 이번 json은 경로를 받은 뒤에 쓰였다.

Recent 칩은 대화상자 없이 `_emit_folder`만 탄다.

하지 못한 일: 대화상자 부모를 frameless 트리 밖으로 빼지 않는다. 설정·첫 실행 위저드는 같은 종료를 피하려고 `parent=None`이다. 이 경로는 그 수정을 받지 않았다.

### `IrisIdeWelcomeLayer._pick_open_folder`

`iris/ui/ide/iris_ide_welcome_layer.py`

같은 호출이다. 부모만 웰컴 레이어다. 웰컴은 frameless `IrisIdeWindow` 안에 있다. 시그널은 창을 거쳐 `_on_iris_ide_welcome_folder`로 간다.

### `ide_pick_open_folder` → `ide_open_folder` → `_open_ide_folder`

`iris/ui/control_actions/ide.py`, `main_window.py`

Theia의 File → Open Folder가 `ide.pick_open_folder`를 부르면 대화상자 부모는 `MainWindow` 자신이다. 고른 뒤에는 `new_window=False`로 `ide_open_folder`가 돈다. `preferred_ide`가 `iris_ide`이면 `_open_ide_folder`는 곧바로 `_open_iris_ide_folder`를 반환한다. Cursor용 새 창 대기는 타지 않는다.

DB의 `preferred_ide`는 `iris_ide`다. 이번 프로필 저장은 `_open_iris_ide_folder` 안에 있다.

### `MainWindow._on_iris_ide_hero_folder` / `_on_iris_ide_welcome_folder`

`iris/ui/window/main_window.py`

둘 다 `_open_iris_ide_folder`를 호출하고, 문자열이 돌아올 때만 채팅이나 로그에 실패를 적는다. 예외를 슬롯 안에 가두지 않는다. PyQt6는 그 예외를 오류 창 없이 `qFatal`로 보낸다.

### `MainWindow._open_iris_ide_folder`

같은 파일.

여기까지 실행된 일이 디스크와 맞다.

- `save_user_profile` — `project_root`가 컴퓨터비전 폴더다.
- `record_opened_folder` — json `opened_at`이 종료 초와 같다.
- `IrisIdeLaunchWorker.start` — Theia가 준비된 뒤의 `_on_iris_ide_launch_ok`는 수 초 뒤다. `pdf.log`는 그 콜백의 `closeEvent`도 없다. 사망은 이 함수가 아직 스택에 있거나, 히어로일 때 40ms 뒤 인트로 슬롯이다.

그 다음 `_activate_iris_ide_companion_tile`은 `processEvents`를 여러 번 돌리고, IDE 창에 `setParent(host, FramelessWindowHint | Window)`를 하고, `winId()`로 네이티브 창을 만든다. 파일 대화상자를 쓴 클릭이면, 네이티브 대화상자 파괴가 이 `processEvents`에 실려 온다. frameless 메인의 modal 자식이 닫힐 때 같은 `qFatal`이 난 전례가 있다.

히어로에서 왔으면 마지막에 `QTimer.singleShot(40, _run_companion_panels_intro)`를 건다. 그 슬롯도 예외가 나가면 같은 코드로 죽는다. 40ms는 같은 초 안에 들어간다.

### `IrisIdeWindow.set_embedded` / `apply_frameless_chrome`

`iris/ui/workspaces/iris_ide_window.py`, `frameless_chrome.py`

`set_embedded(True)`는 주석대로 Qt 위젯 임베드 대신 owned `Window`로 붙인다. `apply_frameless_chrome`은 `winId()` 다음 `DwmSetWindowAttribute`와 스냅용 스타일을 바꾼다. 생성자 안의 `winId()`는 기동 즉사로 이미 빠져 있다. 이번 호출은 폴더 슬롯 안이라 그 케이스와 시각이 다르다. 네이티브 창을 만든 직후 `setParent`와 `processEvents`가 이어진다는 점이 이 슬롯에만 있다.

### 하지 않은 일

- `IrisIdeLaunchWorker.run`의 `shared_iris_ide_runtime().start` — 워커 스레드이고, 준비 콜백 전에 프로세스가 이미 없다.
- Theia `openFolderDialog`의 브라우저 파일 대화상자 — `askIris`가 실패할 때만 탄다. 프로필이 이미 바뀐 것은 Iris 쪽이 경로를 받았다는 뜻이다.
- 채팅 전송 슬롯, 위키 저장 슬롯 — 01:19:27에 새 메시지가 없다.
- `ide_snap_redirect` — IDE 창을 처음 만들 때 훅을 설치한다. 설치 실패는 예외가 아니라 `False`다. 훅이 키를 삼키는 조건은 Win+방향키라, 폴더를 고른 이 종료의 입력과 맞지 않는다.

## 빈 자리

폴더를 연 슬롯이 두 가지를 비워 둔다.

1. 파일 대화상자가 frameless 창(또는 그 자식)을 부모로 둔다. 설정·위저드는 이 부모를 빼 두었고, 히어로·웰컴·`ide.pick_open_folder`는 빼지 않았다. 경로를 받은 뒤 `processEvents`가 그 대화상자를 걷어 낸다.
2. `_open_iris_ide_folder`와 `_run_companion_panels_intro`는 슬롯인데, 예외가 슬롯 밖에 남아 `qFatal`이 된다. traceback이 없어 어느 줄인지는 이번 로그만으로 한 줄로 고정되지 않는다.
