# Prompt: Hermes 설치 실패 — 잔여 리스크 (연번 22 후속)

총괄표 **연번 22** 1차 조치 이후 남은 R1–R5용.  
1차 스펙·완료분: [Hermes설치실패-원인과-개선안.md](./Hermes설치실패-원인과-개선안.md) · [Hermes설치실패-개선-구현프롬프트.md](./Hermes설치실패-개선-구현프롬프트.md)

아래 블록을 Cursor Agent에 그대로 붙여 넣으면 됩니다.

---

```text
Context:
- 저장소: Project-IRIS-Light (Windows / PyQt6)
- 총괄표: docs/code-review/조치-소요-사항-총괄표.md 연번 22 (§3 자)
- 1차 완료분(건드리지 말 것 / 회귀 금지):
  - format_pip_failure + iris-bypass-pip-*.log + 꼬리 UI
  - 공식 rc≠0+probe 실패 → 우회 1회
  - NeedsUser「로그 열기」「우회로 다시 설치」+_hermes_prefer_bypass
  - py 3.11→3.12→3.13, staging clone, uv sync→pip, pip idle=timeout None
  - tests/test_hermes_install_bypass.py (기존 assert 유지·확장만)
- 핵심 파일:
  - iris/system/hermes_install.py
  - iris/system/setup_protocol.py (_install_hermes, _install_hermes_bypass, force_retire 호출부)
  - iris/ui/window/setup_wizard.py (_NeedsUserCard message 표시만 필요 시)
  - tests/test_hermes_install_bypass.py
- 잔여 리스크 (코드리뷰 확정):
  R1 첫 설치가 항상 공식 install.ps1 먼저 → 448 PC에서 수분 대기 후 우회
  R2 중단·예외 시 hermes-agent.staging-* 잔존 (force_retire는 trash/broken만)
  R3 「우회 설치 후 런타임 실패」는 pip 로그/log_path NeedsUser 계약과 불일치
  R4 NeedsUser message에 detail 상한 없음
  R5 §7 실기 미통과 (고의 pip 실패 UI · cold · 깨진 hermes wipe)

Goal:
연번 22를 「부분 조치」에서 **완료**에 가깝게 만든다.
(1) 448/이미 우회 선호 환경에서 공식 대기 시간을 줄이거나 건너뛰고
(2) staging 잔존을 정리하며
(3) 런타임 probe 실패도 로그/log_path/last_error 계약을 맞추고
(4) UI 메시지 길이를 제한하며
(5) §7 검증을 실제로 통과(또는 자동 스모크로 대체)시킨다.

Constraints:
- YAGNI: R1–R5만. Setup Hermes 소스 번들 금지. setup_protocol 전체 분할 금지.
- Surgical: hermes/setup/test/문서 연번 22·§9만. 무관 리팩터·포맷·테마 금지.
- 1차 계약 유지: 꼬리 메시지, CREATE_NO_WINDOW, prefer_bypass 무한 루프 금지,
  Iris .venv를 bootstrap 맨 앞에 두지 말 것.
- R1: 「항상 공식 스킵」으로 바꾸지 말 것. 기본은 공식 1회 시도 유지.
  단, 아래 중 하나 이상으로 448 PC 대기를 줄일 것:
  (a) 직전 세션/상태의 448 또는 prefer_bypass / last_error.kind 가 bypass면
      공식 생략하고 우회 직행
  (b) 공식 스크립트에 짧은 hard 상한(예: 180–300s) 후 probe 실패면 우회
      — 기존 _HERMES_HARD_SEC(3600)을 전역으로 줄이지 말고 Hermes 공식 경로만
  (c) 또는 looks_like_uv_python_mount_failure 가 스트림 중 보이면 조기 abort→우회
  구현은 (a)+(b) 또는 (a)+(c) 중 최소 조합. 문서에 선택한 조합을 한 줄로 명시.
- R2: force_retire_hermes_agent 또는 install 시작/종료에서
  hermes-agent.staging-* 도 trash와 같이 치우기 (최대 N개 잔존 규칙 동일·또는 전부 삭제).
  진행 중 staging은 현재 stamp만 보존.
- R3: install_hermes_with_system_python 이 probe/import 실패로 끝날 때도
  log_path를 남기고 format 또는 동일 계약 메시지 + SetupStepResult.log_path
  + _set_structured_last_error(kind=bypass_runtime 등).
- R4: NeedsUser/record에 넘기는 message는 꼬리 기준 상한
  (예: 전체 ≤800자 또는 마지막 12줄·이미 format_pip_failure와 정합).
  전체 로그는 파일에만.
- R5: 최소 하나 — (i) unittest/스모크로 §7-1·2를 자동화하거나
  (ii) `_check_setup_hermes_live` 가 조기 절단 없이 돌아가게 하고
  통과/스킵 사유를 문서 §9에 기록. 네트워크 cold는 환경 없으면
  「스킵 + 사유」허용하되 R1–R4 코드는 머지 가능해야 함.
- 콘솔 창 깜빡임 금지 (no-console-windows.mdc).
- 완료 후: 총괄표 연번 22 상태·§3 자·§6 이력, Hermes문서 §9 갱신.

Interface (구현 계약):
1) hermes_install.py
   - staging-* 정리 헬퍼 또는 force_retire 확장
   - 런타임 실패도 write_bypass_pip_log / last_bypass_log_path / 꼬리 메시지
2) setup_protocol.py
   - R1 조기 우회 또는 공식 hard 단축 (선택 조합 명시)
   - bypass 런타임 실패 → log_path + structured last_error
   - message 길이 상한 (R4)
3) setup_wizard.py — message 상한을 카드에서 또 자르지 말 것(프로토콜에서 이미 제한)
4) tests/test_hermes_install_bypass.py
   - staging 정리 assert
   - (가능하면) prefer_bypass/last_error 시 공식 미호출 mock
   - 런타임 실패 메시지에 로그 경로 포함 assert
5) 문서: 총괄표 22 + Hermes §9

Implementation order:
  Phase A: R2 + R3 + R4 (안전·관측, 반나절)
  Phase B: R1 (448 UX, 반나절–1일)
  Phase C: R5 검증·문서 상태 완료 표기

Output:
- 위 범위 diff만
- 초록:
  .venv\Scripts\python.exe -m unittest tests.test_hermes_install_bypass -v
  .venv\Scripts\python.exe -m iris.system.hermes_install
  (가능하면) .venv\Scripts\python.exe -m iris.ui._check_setup_hermes_live
- 짧은 한국어: R1 선택 조합 / 고친 것 / 검증 / 총괄표 22 상태(부분→완료 여부)

Do not:
- IRIS-Setup.exe에 Hermes 번들
- 공식을 기본 경로에서 영구 제거하고 우회만 쓰기 (R1 오해)
- setup_protocol.py 전체 분할
- httpx2 등 무관 의존성 “개선”
- 연번 9(Hermes tools 배관) 재논의
```

---

## 사용 팁

| 상황 | 붙여 넣을 범위 |
|------|----------------|
| 관측·정리만 | Phase A (R2+R3+R4) |
| 448 PC 체감 | Phase A + B (R1) |
| 연번 22 닫기 | 프롬프트 전체 + Phase C |

관련: [조치-소요-사항-총괄표.md](../조치-소요-사항-총괄표.md) §3 자 · [Hermes설치실패-원인과-개선안.md](./Hermes설치실패-원인과-개선안.md)
