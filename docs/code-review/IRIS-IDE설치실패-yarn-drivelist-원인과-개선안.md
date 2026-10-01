# IRIS IDE 설치 실패 — yarn / drivelist — 원인 · 개선안

> **작성**: 2026-10-01  
> **재현**: 노트북, Node v24.11.0, Visual Studio C++ 없음, `~/.iris-light/runtimes/iris-ide`  
> **화면**: `설치 실패` + `NpmResolver.findVersionInRegistryResponse` 스택 (`@theia/variable-resolver` malformed response)  
> **관련**: `iris/system/iris_ide_runtime.py`, `integrations/iris-ide/package.json`, `scripts/stub-windows-ca-certs.js`

---

## 1. 한줄 결론

| # | 판정 | 내용 |
|---|------|------|
| A | **확정 (설치를 멈춘 오류)** | `@theia/core`의 **필수** 의존성 `drivelist@12.0.2`가 Windows prebuild를 못 찾고 `node-gyp`로 넘어감. VS C++가 없어 `Could not find any Visual Studio`로 **yarn이 종료** |
| B | **화면에 보인 오류는 2차** | 1차 실패 뒤 무조건 `yarn install`을 한 번 더 돌리고, 그때 npm이 `@theia/variable-resolver`에 **malformed response**를 줌. 설치기는 **마지막 시도의 로그 끝 240자**만 봐서 레지스트리 스택을 실패 원인으로 표시 |
| C | **기존 우회가 안 탄 이유** | VS 우회(`--ignore-scripts`)는 ffmpeg/windows-ca-certs용인데, (1) 판별 문자열이 잘린 꼬리에 없고 (2) 판별 대상이 **마지막 시도만**이라 레지스트리 오류로 덮임. 우회에 들어가도 이어지는 `yarn install`(스크립트 켬)이 `drivelist`를 다시 컴파일함 |
| D | **부가** | 소스에 `yarn.lock`이 없어 `--frozen-lockfile`이 잠금을 못 쓰고 매번 레지스트리를 다시 해석함. `@vscode/windows-ca-certs` 실패는 optional이라 설치를 멈추지 않음 |

`windows-ca-certs`의 node-gyp 실패와 uuid/glob deprecation 경고는 이번 중단 원인이 아니다.

---

## 2. 설치기가 실제로 한 일

```
install()
  copy integrations/iris-ide → ~/.iris-light/runtimes/iris-ide
  yarn install --frozen-lockfile     ← lock 없음. 해석 후 [5/5]에서 drivelist 실패
  yarn install                       ← 무조건 재시도. 레지스트리 malformed로 실패
  _yarn_needs_native_bypass(마지막 240자)  ← VS 문구가 이미 없음 → 우회 안 함
  return 그 꼬리 → UI 「설치 실패」
```

`drivelist` 설치 스크립트는 `prebuild-install --runtime napi || node-gyp rebuild`이다.  
로그: `No prebuilt binaries found (target=8 runtime=napi arch=x64 platform=win32)` 다음 VS 탐색 실패.

Theia 백엔드는 `drivelist.list()`로 드라이브 문자만 쓴다 (`EnvVariablesServerImpl.getDrives`). 브라우저 타깃 IDE에는 네이티브 애드온이 필요 없다. `@theia/ffmpeg`는 이미 `vendor/theia-ffmpeg-stub`으로 빼 두었지만 `drivelist`는 빠져 있다.

---

## 3. 개선 (이번 구현 범위)

| # | 조치 |
|---|------|
| 1 | `drivelist`를 `vendor/drivelist-stub`으로 resolution. `list()`는 Win32에서 접근 가능한 드라이브 문자를 반환. install 스크립트·binding.gyp 없음 |
| 2 | yarn 실패 로그는 끝 240자가 아니라, 전체에서 고른 오류 줄을 앞에 두고 최대 12KB를 유지. 시도들을 합쳐 VS/`drivelist`면 우회 |
| 3 | lock 파일이 없으면 `--frozen-lockfile`과 무조건 재시도를 하지 않음. malformed/registry 오류만 한 번 재시도 |
| 4 | 우회 시 `--ignore-scripts` → 스텁 스크립트 → 스크립트 있는 `yarn install`. 그게 다시 네이티브에서 죽어도 `drivelist`가 스텁이고 `@theia/core`가 있으면 컴파일을 이유로 설치를 중단하지 않음 |
| 5 | 사용자에게 돌려주는 실패 문장은 스택 프레임이 아니라 `error` / Visual Studio / malformed 줄 |

검증용 `yarn install`이 `integrations/iris-ide/yarn.lock`을 만들었다. 이 파일이 설치본에 복사되면 `--frozen-lockfile`을 쓴다. lock이 없는 복사본은 레지스트리 오류만 한 번 재시도한다.
