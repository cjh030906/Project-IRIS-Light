# Prompt: Hermes 설치 실패 개선 구현

아래 블록을 Cursor Agent에 그대로 붙여 넣으면 됩니다.

---

```text
Context:
- 저장소: Project-IRIS-Light (Windows / PyQt6)
- 스펙 문서: docs/code-review/completed/Hermes설치실패-원인과-개선안.md (필독, 이 문서의 연번·가설만 구현)
- 핵심 파일:
  - iris/system/hermes_install.py
  - iris/system/setup_protocol.py (_install_hermes, _install_hermes_bypass, _run_streamed)
  - iris/ui/window/setup_wizard.py (NeedsUser 카드)
  - tests/test_hermes_install_bypass.py
- 증상: Core 4/10 Hermes 설치 시 UI에
  `우회 설치도 실패: pip 설치 실패: Obtaining file:///…/hermes-agent` 만 보이고
  실제 pip ERROR 꼬리는 잘림. 공식 install.ps1은 uv WinError 448에 자주 걸림.

Goal:
Hermes Core 설치가 Windows에서 실패해도 (1) 원인을 꼬리 로그로 알 수 있고
(2) 우회 설치가 안정적으로 성공하며 (3) 448 환경에서 공식 재시도 루프에 안 갇히게 한다.
문서 §6 우선순위로 구현하고 §7 검증 체크리스트를 통과시킨다.

Constraints:
- YAGNI: 문서 연번 1–11만. Hermes Setup 사전 번들(연번 12) 금지.
- Surgical: hermes/setup 관련만. 무관한 리팩터·포맷·주석 정리 금지.
- 실패 메시지는 stdout/stderr **앞**이 아니라 **꼬리**만 사용자에게 보여 준다.
- 전체 pip 로그는 `%LOCALAPPDATA%\hermes\logs\iris-bypass-pip-<stamp>.log` 에 남긴다.
- 기존 `combined_install_log_tail` 헬퍼를 재사용하거나 동일 계약으로 확장.
- bootstrap Python은 Hermes `.python-version`(3.11)에 맞게 **3.11 → 3.12 → 3.13** 순.
  Iris `.venv`(3.13)를 맨 앞에 두지 말 것.
- 우회 설치: 가능하면 `uv sync`(lock) 우선, 실패 시 기존 pip -e 폴백.
  업스트림에 없는 `requirements.txt` 폴백은 제거하거나 lock export로 교체.
- clone은 `hermes-agent.staging-<stamp>` 에 받은 뒤 성공 시 rename swap (wipe 레이스 완화).
- `_install_hermes`: 공식 스크립트 rc≠0 이고 probe 실패면 **항상 우회 1회**
  (448 마커에만 의존하지 말 것). 이미 우회를 탄 직후엔 무한 루프 금지.
- NeedsUser UI: 「로그 열기」+「우회로 다시 설치」. 공식 설치만 반복하는 버튼만 두지 말 것.
- pip/`_run_streamed` quiet 구간: idle 오탐으로 중도 kill 되지 않게 heartbeat 또는
  Hermes pip 단계 idle 완화.
- 콘솔 창 깜빡임 금지: Windows 서브프로세스는 기존 no_window / CREATE_NO_WINDOW 계약 유지
  (`.cursor/rules/no-console-windows.mdc`).
- 새 의존성 추가 최소화. 테스트는 unittest 기존 파일 확장 우선.
- 완료 후 문서 §9 상태를 갱신(H1 등 착수/완료 표기).

Interface (구현 계약):
1) hermes_install.py
   - `format_pip_failure(stdout, stderr, *, log_path) -> str`  # 꼬리 + 로그 경로
   - `install_hermes_with_system_python(...)` : staging clone, py 우선순위, uv sync→pip,
     실패 시 전체 로그 파일 + 꼬리 메시지
   - dead requirements.txt 폴백 정리
2) setup_protocol.py
   - `_install_hermes`: probe 실패+공식 실패 → 우회 1회 (조건 단순화)
   - `_install_hermes_bypass`: detail head 절단 제거, 꼬리/로그 경로 전달
   - pip 단계 `_run_streamed` idle 완화 또는 on_stream heartbeat
3) setup_wizard.py
   - NeedsUser(hermes_install): 「로그 열기」(explorer/notepad), 「우회로 다시 설치」
4) setup state (선택·연번 7): last_error `{step, kind, log_path, tail}` 저장
5) tests/test_hermes_install_bypass.py
   - fake pip: 앞=Obtaining… / 뒤=ERROR: … → 사용자 메시지에 ERROR 포함, Obtaining만 있으면 실패

Implementation order (문서 §6):
  Phase A (필수): 연번 1 + 11
  Phase B: 연번 2 + 6
  Phase C: 연번 4 + 5
  Phase D: 연번 3 + 8 + 9
  Phase E (여유 시): 연번 7 + 10 (README/wizard hint 한 줄)

Output:
- 위 파일들의 diff만 (요청 범위 외 파일 금지)
- 실행해서 초록이어야 함:
  .venv\Scripts\python.exe -m unittest tests.test_hermes_install_bypass -v
  .venv\Scripts\python.exe -m iris.system.hermes_install
  (가능하면) .venv\Scripts\python.exe -m iris.ui._check_setup_hermes_live
- 짧은 한국어 요약: 무엇을 고쳤는지 / 어떻게 검증했는지 / 남은 Phase

Do not:
- IRIS-Setup.exe에 Hermes 소스 번들
- setup_protocol.py 전체 파일 분할 리팩터
- “개선”을 이유로 무관한 UI/테마 변경
```

---

## 사용 팁

| 상황 | 붙여 넣을 범위 |
|------|----------------|
| 급한 핫픽스만 | 위 프롬프트 + `Phase A만 구현하고 B–E는 하지 말 것` |
| 448 PC 안정화까지 | Phase A + B |
| 문서 전체 | 프롬프트 그대로 |

관련 스펙: [Hermes설치실패-원인과-개선안.md](./Hermes설치실패-원인과-개선안.md)  
총괄표: [조치-소요-사항-총괄표.md](../조치-소요-사항-총괄표.md) **연번 22**  
잔여: [Hermes설치실패-잔여리스크-구현프롬프트.md](./Hermes설치실패-잔여리스크-구현프롬프트.md)
