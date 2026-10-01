# Prompt: IRIS IDE 설치 실패 (drivelist / yarn) 구현

스펙: `docs/code-review/IRIS-IDE설치실패-yarn-drivelist-원인과-개선안.md`

---

```text
Context:
- 저장소: Project-IRIS-Light (Windows)
- 스펙: docs/code-review/IRIS-IDE설치실패-yarn-drivelist-원인과-개선안.md
- 핵심 파일:
  - iris/system/iris_ide_runtime.py (install, _run_cmd, _yarn_needs_native_bypass)
  - integrations/iris-ide/package.json (resolutions)
  - integrations/iris-ide/scripts/stub-windows-ca-certs.js
  - integrations/iris-ide/vendor/theia-ffmpeg-stub (같은 방식의 선례)
  - iris/system/_check_iris_ide_ffmpeg_stub.py

Goal:
Visual Studio C++가 없는 PC에서 IRIS IDE yarn install이 drivelist node-gyp로
중단되지 않게 한다. 실패 UI는 마지막 스택 240자가 아니라 실제 오류 줄을 보여 준다.

Constraints:
- YAGNI: 스펙 §3의 1–5만. yarn.lock 생성·커밋, Node 버전 고정, VS 설치 안내는 하지 않는다.
- Surgical: 위 파일과 drivelist 스텁·체크만. Theia 프론트 번들, 타일, 브리지는 건드리지 않는다.
- drivelist 스텁의 list()는 Theia getDrives가 읽는 mountpoints[].path 만 채우면 된다.
  Win32는 A–Z 중 fs.accessSync가 되는 드라이브. 그 외 OS는 "/".
- bindings / node-gyp / prebuild-install 을 스텁에서 호출하지 않는다.
- --ignore-scripts 성공 뒤 스크립트를 켠 yarn install이 다시 drivelist를 컴파일해도,
  스텁이 남아 있고 @theia/core가 있으면 그 실패로 install()을 실패 처리하지 않는다.
- 실패 반환 문자열은 240자 안에서 원인 줄로 시작한다 (setup_protocol이 [:240]으로 자른다).

Interface:
- package.json resolutions에 "drivelist": "file:./vendor/drivelist-stub"
- 스텁 package name은 drivelist, version은 12.0.2-iris-stub, main은 js/index.js, scripts.install 없음
- _yarn_needs_native_bypass(msg) — 기존 VS/ffmpeg/node-gyp에 더해
  "no prebuilt binaries found", "node_modules\\drivelist", "node_modules/drivelist"
- _yarn_registry_flake(msg) — "malformed response", "registry may be down"
- _command_failure_text(text) — 전체 로그에서 error/VS/prebuild/malformed 줄을 앞에 붙이고 최대 12KB
- _yarn_user_message(log) — 사용자에게 줄 한 줄 (최대 240자)
- install() yarn 순서:
  1. yarn.lock이 있을 때만 --frozen-lockfile, 없으면 install
  2. 레지스트리 flake면 같은 인자를 한 번만 재시도
  3. lock이 있었고 아직 네이티브 실패가 아니면 frozen 없이 install 한 번 (lock 불일치용)
  4. 지금까지 로그를 합쳐 네이티브면 --ignore-scripts, stub 스크립트, 그 다음 install
  5. 4의 마지막 install이 네이티브로 실패하고 drivelist가 스텁이며 @theia/core가 있으면 성공으로 진행

Output:
- 체크: .venv\Scripts\python.exe -m iris.system._check_iris_ide_ffmpeg_stub
  - resolution·스텁 파일·iris-stub 버전
  - 끝 240자에 VS 문장이 없는 긴 로그도 _command_failure_text 뒤에는 bypass가 참
  - 네이티브 로그 + 이후 malformed 로그를 합치면 bypass가 참
  - malformed만 있으면 bypass가 거짓, registry flake는 참
  - node로 스텁 list()가 mountpoints[0].path 를 출력
- yarn.lock이 없으면 lock 내용 단정은 건너뛴다. 있으면 ffmpeg·drivelist file: 스텁 경로를 확인한다.
```
