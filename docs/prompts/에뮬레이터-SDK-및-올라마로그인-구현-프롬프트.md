# 구현 프롬프트: 에뮬레이터 SDK 자동 설치 + Ollama 로그인 버튼 멈춤

> **작성**: 2026-09-30
> **범위**: 실행 프로토콜 optional `emulator`, 채팅/설정 마법사의 Ollama 클라우드 「로그인」.
> **하지 말 것**: WHPX/Hyper-V 켜기, 시스템 이미지 ID 변경, Android Studio를 설치의 본체로 두기, UI 스레드에서 프로세스 대기.

구현 전에 아래 줄 번호 근처가 아직 같은 구조인지 확인하고, 어긋나면 그 함수를 기준으로 고친다.

---

## 0. 수용 기준

1. 에뮬레이터·adb·cmdline-tools·시스템 이미지가 없으면, 프로토콜 「설치」가 Android Studio 마법사에 맡기지 않고 `sdkmanager`로 그 패키지를 받는다. 받은 뒤 기존 `ensure_avd()`로 `IrisLight_Pixel`을 만든다.
2. Studio만 깔린 상태, winget이 0이 아닌 종료 코드(이미 설치됨 포함)인 상태에서도 `can_install=True`가 유지되어 다시 설치할 수 있다.
3. 클라우드 미로그인 카드의 「로그인」(라벨은 `Ollama 열기` 또는 `로그인`)을 누르면 Ollama 데스크톱 앱이 뜨고, **Iris 창은 응답 없음으로 바뀌지 않는다.** 클릭 핸들러는 수백 ms 안에 UI 스레드로 돌아온다.
4. 앱 실행 파일을 찾지 못하면 지금처럼 브라우저 `https://ollama.com/signin` 폴백을 유지한다.

---

## 1. 에뮬레이터 / SDK

### 현행 (설계된 한계, 버그 아님 + 재시도가 막힘)

`iris/system/setup_protocol.py` `_install_emulator()`:

- 하는 일: `winget install -e --id Google.AndroidStudio` 뿐.
- winget 성공 후 `is_emulator_available()`이 실패하면 `needs_user` + **`can_install=False`**. 메시지: "Studio를 열어 SDK Platform-Tools·Emulator를 받은 뒤 「완료했어요」".
- winget 종료 코드가 0이 아니면 "자동 설치를 할 수 없습니다" + **`can_install=False`**. winget "이미 설치됨"(`-1978335189` / `0x8A15002B`)도 여기로 떨어진다.
- 저장소에 `sdkmanager` 호출은 없다. `ensure_avd()` 오류 문자열에만 안내가 있다.

`iris/system/android_emulator.py` `prepare_emulator()` / `is_emulator_available()` 통과 조건:

| 필요 | 경로 |
|---|---|
| `emulator.exe` | `%LOCALAPPDATA%\Android\Sdk\emulator\` (`ANDROID_SDK_ROOT` / `ANDROID_HOME` 우선) |
| `adb.exe` | `...\platform-tools\` |
| AVD 설정이 없을 때 | `cmdline-tools\latest\bin\avdmanager.bat` |
| AVD 설정이 있을 때 | `_SYSTEM_IMAGE` = `system-images;android-36;google_apis_playstore_ps16k;x86_64` |

winget Android Studio는 IDE만 넣는다. 위 파일은 Studio 첫 실행 SDK Manager가 받기 때문에, winget이 성공해도 직후 검사는 실패하는 것이 현재 코드의 정상 결과다. 안내 문구는 platform-tools·emulator만 말하고 cmdline-tools와 시스템 이미지 ID를 빠뜨린다.

### 구현

`android_emulator.py`에 `ensure_sdk(progress=None) -> tuple[bool, str]` 를 추가한다.

1. 이미 emulator, adb, avdmanager, `system_image_dir()`이 있으면 즉시 `(True, 짧은 설명)`.
2. 없으면 SDK 루트(`_sdk_root()`)에 공식 command-line tools zip을 받아 `cmdline-tools/latest/`에 푼다. 사용자 폴더라 관리자 권한은 요구하지 않는다. zip URL은 코드에 한 곳만 둔다 (Google `commandlinetools-win` 최신 고정 URL). 사용자 PC 경로를 하드코딩하지 않는다.
3. `sdkmanager.bat --sdk_root=<root>` 로 아래만 설치한다. 패키지 문자열은 `_SYSTEM_IMAGE` / `_AVD_TARGET`에서 만든다. 다른 API 이미지로 바꾸지 않는다. 바꾸면 기존 AVD가 arm으로 떨어져 `CPU Architecture 'arm' is not supported`로 죽는다.
   - `platform-tools`
   - `emulator`
   - `platforms;android-36` (`_AVD_TARGET`과 동일)
   - `_SYSTEM_IMAGE`
4. 라이선스는 `sdkmanager --licenses`에 `yes`를 넣어 비대화로 처리한다. 프로토콜 「설치」 클릭이 그 동의다.
5. 진행 한 줄은 `progress` 콜백으로 올린다. `_install_emulator`는 기존 `_emit_stream`에 연결한다.
6. 성공 후 기존 `ensure_avd()`를 호출한다. AVD 생성 로직을 복제하지 않는다.

`_install_emulator()` 순서:

1. `is_emulator_available()` 성공 → 지금처럼 `ensure_avd()` 후 `done`.
2. 실패 → **먼저 `ensure_sdk()`**. 성공하고 재검사도 성공하면 `ensure_avd()` 후 `done`.
3. `ensure_sdk()` 실패 시에만 winget `Google.AndroidStudio`를 보조로 시도할 수 있다. Studio 설치만으로 `done` 처리하지 않는다. 그 뒤에도 SDK 재검사를 하고, 실패하면 `needs_user`.
4. 실패 메시지는 패키지 ID 네 개를 그대로 적는다. **`can_install=True`를 유지**한다. winget 비-0도 재시도를 끄지 않는다.
5. 시간 한도는 기존 `_INSTALL_IDLE_SEC`(600) / `_INSTALL_HARD_SEC`(3600)을 쓴다. sdkmanager 출력은 스트림해서 유휴 타임아웃이 다운로드 중에 끊기지 않게 한다.

하지 말 것:

- Windows Hypervisor Platform / Hyper-V 기능을 켜거나 재부팅을 유도하는 설치 단계. 패키지가 깔려도 WHPX가 꺼져 있으면 부팅은 별도 실패다. 그 안내는 한 줄이면 충분하고, 자동 활성화는 하지 않는다.
- 신규 AVD 디스크 검사(`_MIN_FREE_BYTES_FRESH`, 40GB)를 낮추지 않는다.

### 검증

네트워크 없이 도는 self-check 하나 (`android_emulator.py` 하단 또는 기존 `setup_protocol.py` `_self_check`에 추가):

- sdkmanager/다운로드를 가짜로 두고, 패키지가 생기기 전에는 `ensure_sdk`가 실패하고 메시지에 `_SYSTEM_IMAGE`가 포함된다.
- 가짜로 emulator·adb·avdmanager·시스템 이미지 디렉터리가 있으면 `ensure_sdk`는 다운로드를 호출하지 않고 성공한다.
- `_install_emulator`에서 winget 종료 코드를 0이 아닌 값으로 줬을 때 결과의 `can_install`이 True다.

실제 zip 다운로드·수 GB 이미지 설치는 self-check에 넣지 않는다.

---

## 2. Ollama 클라우드 로그인 버튼이 응답 없음

### 현행 (실측)

미로그인이면 카드/채팅에 로그인 안내가 뜬다. 버튼은 앱을 연다. 앱은 실행된다. Iris가 「응답 없음」이 되는 이유는 클릭 핸들러가 Qt UI 스레드에서 블로킹하기 때문이다.

호출부 두 곳 모두 UI 스레드:

- `iris/ui/window/setup_wizard.py` `_StepCard._open_url` — `open_local_app == "ollama"` 일 때 `open_ollama_app()` 다음 `ensure_ollama_running(..., wait_sec=8.0)`.
- `iris/ui/window/main_window.py` `_on_ollama_cloud_login_clicked` — 같은 순서, 대기는 `wait_sec=2.0`. 그 다음 안내 문구를 붙인다.

`iris/system/ollama_server.py` `open_ollama_app()`이 UI 스레드에서 하는 일:

1. `_has_visible_ollama_window()` — `EnumWindows` + `GetWindowTextLengthW` / `GetWindowTextW`. 이 API는 대상 창에 `WM_GETTEXT`를 보낸다. Ollama UI 스레드가 기동 중이면 **Iris UI 스레드가 그 응답을 기다리며 멈춘다.** Windows는 약 5초 뒤 창 제목에 응답 없음을 붙인다.
2. 프로세스는 있는데 보이는 창이 없으면 `reset_stuck_ollama_apps()`(taskkill, 최대 약 3초) 후 **`ensure_ollama_running(wait_sec=8.0)`**. 방금 뜨는 앱을 죽이고, 서버 대기를 UI 스레드에서 돈다.
3. `Popen(["ollama app.exe"])` 뒤 `time.sleep(1.0)` 그리고 `_foreground_ollama_windows()`.
4. 포그라운드만 1.2초 스레드로 감싸 두었다. 주석: "숨은 OllamaClass ShowWindow는 멈출 수 있음". 감지(`GetWindowText`)와 `sleep`·`ensure_ollama_running`은 그대로 호출 스레드에 있다.
5. 설정 카드는 그 다음에 서버 대기를 **한 번 더** 8초 한다.

`_maybe_refresh_ollama_quota`는 워커라 이 멈춤의 원인이 아니다. 손대지 않는다.

### 구현

로그인 클릭의 계약: **UI 스레드에서는 프로세스만 띄우고 즉시 return.**

- `open_ollama_app()`에서 호출 스레드의 `time.sleep`, `ensure_ollama_running`, `GetWindowText*`, `taskkill`을 제거한다.
- Windows 기동은 `ollama_app_candidates()`의 GUI 실행 파일만 사용한다 (`ollama app.exe`. CLI `ollama.exe`는 serve라 창이 안 뜬다 — 이 구분은 유지).
- `DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP`으로 띄운다. `CREATE_NO_WINDOW` / `SW_HIDE`는 쓰지 않는다 (창이 숨는다).
- 보이는 창을 앞으로 보내는 일이 필요하면 UI 스레드 밖에서 하고, `GetWindowText`로 Ollama 창을 동기 조회하지 않는다. 기동 직후 포그라운드에 실패해도 성공으로 본다. 앱이 떴으면 충분하다.
- 로그인 클릭 경로에서 `reset_stuck_ollama_apps()`를 호출하지 않는다. 같은 클릭에서 방금 실행한 앱을 죽이지 않는다.
- 서버 기동 대기(`ensure_ollama_running`)는 로그인 버튼 성공 조건에서 뺀다. 클라우드 로그인은 앱 UI에서 하고, 로컬 서버 대기는 기존 기동 워커에 맡긴다.
- 두 호출부(`_open_url`, `_on_ollama_cloud_login_clicked`)가 같은 비동기 진입점을 쓴다. 한쪽만 고치고 다른 쪽을 8초 대기로 두지 않는다.
- 실행 파일이 없을 때만 지금처럼 브라우저 폴백 + 짧은 힌트.
- 성공 힌트 문구는 유지해도 된다: 앱에서 ollama.com 계정으로 로그인, 웹사이트만 로그인하면 Iris에 반영되지 않음.

### 검증

self-check:

- `open_ollama_app`(또는 분리한 launch 함수)가 후보 파일이 있을 때 `Popen`만 하고, `ensure_ollama_running`과 `time.sleep`을 호출하지 않은 채 반환한다. 가짜 `Popen`으로 확인.
- 후보 파일이 없으면 `(False, ...)` 이고 예외를 올리지 않는다.

수동 (다른 PC): 클라우드 미로그인 → 「로그인」 → Iris 제목에 응답 없음이 붙지 않고 Ollama 앱 창이 뜬다. 설정 마법사 카드와 채팅 프롬프트 둘 다.

---

## 3. 손대지 않는 것

- `_SYSTEM_IMAGE`, `_AVD_TARGET`, AVD 이름 `IrisLight_Pixel`, userdata 40GB 검사.
- Ollama 클라우드 판별 `ollama_cloud_signed_in()`, 최소 모델 설치 버튼, `ollama_cloud` 카드 문구의 의미.
- 에뮬레이터 GUI 기동 플래그 (`CREATE_NO_WINDOW` 금지, `ide`/`no-console-windows` 규칙).
- 할당량 갱신 워커.

## 4. 완료 조건

- 위 self-check가 통과한다.
- `iris/system/setup_protocol.py`와 `iris/system/android_emulator.py`를 고쳤으면, 세션 끝에 `dist\IRIS.exe` 바로가기가 thin launcher인지 한 번 확인한다. 소스만 바뀐 경우 풀번들 재빌드는 하지 않는다.
