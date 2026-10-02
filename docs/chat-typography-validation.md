# 채팅 폰트 설정 구현·검증 (2026-10-02)

## 변경 결과

설정창 첫 항목인 **채팅 폰트**에서 설치된 시스템 폰트를 검색·선택하고 본문/코드 크기를 각각 10–28 논리 px로 입력하거나 증감할 수 있다. 한글·영문·Markdown·코드·표 미리보기와 기본값 복원 버튼을 제공한다. 변경 즉시 채팅 문서에 적용하고 자동 저장한다. 이 항목은 설정창 아래의 저장/취소와 독립적으로 즉시 저장되며, 안내 문구로 표시한다. 설정창 자체의 UI 폰트는 변경하지 않는다.

기존 SQLite `C:\Users\serin\.iris-light\iris_light.db`의 `user_preferences` 테이블, `chat_typography_v1` 키에 `chat_font_family`, `chat_font_size`, `code_font_family`, `code_font_size`를 JSON으로 저장한다. MainWindow가 DB를 연 뒤 채팅을 생성하기 전에 불러온다. 없는 폰트·손상된 설정·범위 밖 크기는 설치된 기본 폰트와 제한 범위로 복구한다.

## 기존 폰트와 렌더링 조사

- QApplication: `Noto Sans KR`, 10pt.
- 채팅 QWidget/QTextDocument: `Noto Sans KR → Malgun Gothic → Segoe UI Variable → Segoe UI`, 15px.
- HTML 일부: `Segoe UI Variable → Segoe UI → Noto Sans KR → Malgun Gothic`. Qt 기본 폰트와 우선순위가 달라 라벨/코드/본문의 폰트 선택이 일관되지 않았다.
- 코드: `JetBrains Mono → Cascadia Code → Consolas`, 11px, weight 500. 본문은 400, 라벨/강조/제목은 600이었다.
- 제목: 기존 24/21/18/16/15/15px. Qt HTML heading의 `FontSizeAdjustment`가 명시한 CSS px에도 추가로 작용함을 실제 문자 포맷으로 확인했다. 이를 삽입 후 제거하고 본문 기준 +4/+3/+2/+2/+1/+1로 맞췄다.
- 실행 머신: 논리 DPI 96, DPR 2.0(200%). Windows 글꼴 다듬기 활성화. Qt 기본 hinting/style strategy를 유지하며 NoAntialias 경로는 없었다.
- 채팅 QTextDocument/QWidget을 transform/scale로 확대하는 코드는 발견하지 못했다. 크기는 정수 논리 px, Qt가 DPR을 처리한다. 채팅 외 이미지·시각화 배율은 텍스트 크기와 무관하다.

폰트 뭉개짐의 단일 원인을 확정하지는 않았다. 확인한 문제는 서로 다른 폰트 스택, 작은 코드 크기와 medium weight, Qt 제목 크기 보정이다. 현재 200% 환경에서 잘못된 텍스트 스케일링을 원인으로 볼 근거는 없었다. 영문 폰트를 선택하면 그 폰트에 없는 한글은 Qt/Windows의 글리프 fallback을 사용한다.

## 새로운 기본값

설치 여부를 검사해 `Pretendard → Noto Sans KR → Malgun Gothic/맑은 고딕 → SUIT → 시스템 UI 폰트` 순서로 선택한다. 코드 기본값은 `JetBrains Mono → Cascadia Mono → Consolas → 시스템 fixed font` 순서다.

본문 크기는 QApplication UI 폰트의 논리 px를 DPI로 계산한 뒤 +1, 권장 범위 14–16으로 제한한다. DPR을 다시 곱하지 않는다. 코드 기본값은 본문 −1이다. 테스트 환경 결과는 **Noto Sans KR 14px**, **Cascadia Mono 13px**였다. 본문/코드 weight 400, 라벨은 본문 −2(최소 10), 제목/명시적 강조는 600이다.

## 적용 방식

메인과 IDE 모드는 공통 ChatPanel/ChatLogTextEdit을 사용한다. WorkspaceIrisChatLog도 이를 상속한다. Markdown, 사용자 메시지, 라벨, 코드, 리스트, 표는 공통 typography manager를 참조한다. 기존 문서는 HTML을 통째로 다시 넣지 않고 문자 포맷을 직접 변경하여 문자 위치, 앵커, 이미지, 코드 복사 링크, 스트리밍 버퍼를 보존한다.

## 검증

Windows Qt 플러그인으로 아래 명령을 실행했고 **24개 테스트 통과**:

```powershell
$env:QT_QPA_PLATFORM='windows'
.venv/Scripts/python.exe -m unittest tests.test_chat_typography tests.test_chat_rendering_pipeline tests.test_settings_dialog_perf tests.test_settings_service
```

- 맑은 고딕 / Noto Sans KR / Arial × 12 / 14 / 16 / 18 / 22px.
- 메인 폭 800, IDE 폭 420의 실제 ChatPanel 각각 사용. 동일 설정 동시 반영 확인.
- 사용자·Iris 메시지, 제목, 목록, 코드, 표, 긴 문단 렌더링. 제목/코드의 실제 문자 크기와 폰트 검증.
- 줄 높이 및 레이아웃 경계, 문서 내용 유지, 스크롤 범위 검증. 채팅은 개별 고정 높이 bubble이 아니라 단일 문서이므로 문서가 새 크기로 다시 레이아웃된다.
- 스트리밍 중 크기 변경 후 커서 위치·앵커 유지 및 후속 청크 완료 확인.
- 컨트롤 변경 → DB 저장 → 연결 종료 → DB 재개방/manager 초기화 → 설정 로드 → 기본값 복원 확인.
- `.iris_light_test_tmp/typography-{main|ide}-{font index}-{size}.png`에 조합별 30개 캡처. 대표 12/14/18/22px 화면을 직접 확인했고 샘플 제목/코드/표 텍스트 잘림은 없었다. 화면 아래에서 문단이 일부 보이는 것은 정상 스크롤 viewport 경계다.

전체 IRIS 프로세스 종료·재기동과 외부 IDE 연결을 포함한 수동 종단 검증은 수행하지 않았다. 재실행 유지 경로는 DB 재개방과 초기 로드로 검증했다. Windows 125/150/175% fractional scaling 및 다른 모니터 이동은 미검증이다. 이번 샘플보다 폭이 넓은 복잡한 표/아주 긴 코드 토큰은 기존 Qt Rich Text 폭 제한을 별도로 점검할 필요가 있다. 배포 exe 재빌드는 수행하지 않았다.

## 수정 파일

- `iris/ui/chat/typography.py`: 공통 기본값, 검증, 저장/로드, 토큰, 기존 문서 갱신.
- `iris/ui/settings/typography_box.py`: 설치 폰트 검색, 크기 입력, 미리보기, 복원.
- `iris/ui/settings/settings_dialog.py`: 설정창 연결.
- `iris/ui/window/main_window.py`: 시작 시 기존 DB에서 불러오기.
- `iris/ui/chat/chat_panel.py`: 기본 폰트 및 즉시 갱신/Qt heading 보정.
- `iris/ui/chat/chat_renderer.py`: 본문·제목·표·코드 설정 연동.
- `iris/ui/chat/chat_blocks.py`, `chat_display.py`, `message_regions.py`: 블록/스트리밍/화자 라벨 공통 설정 연동.
- `tests/test_chat_typography.py`: 저장·복원·설정 검증·렌더링 조합·스트리밍 테스트.

작업 전 존재하던 첨부파일 처리 등 다른 변경은 유지했다.
