# 채팅 다이어그램 카드 — 현황과 archify

작성: 2026-10-01

## 결론

다이어그램 렌더는 코드에 등록되어 있으나 채팅이 부르지 않아 쓰이지 않았다. 표시는 아이리스 채팅 밖 별도 창이었다. 이번 구현은 그 창을 없애고, 채팅 칸 너비의 카드 하나에 archify 뷰어를 넣는다. 호출은 사용자가 구조를 부탁할 때와, 여러 모듈에 걸친 큰 구조 변경을 설명·요약할 때로 한정한다.

## 현재 구조

| 구간 | 역할 |
|---|---|
| `integrations/archify/` | 업스트림 복사. 커밋 `72c750bb`, MIT. 출처 https://github.com/tt-a1i/archify. 원류는 Cocoon-AI/architecture-diagram-generator |
| `iris/system/archify_render.py` | Node로 `archify.mjs deliver` 1회. HTML은 `~/.iris-light/runtime/diagrams/` |
| `diagram.render` | `iris/ui/control_actions/project.py`. MCP `iris_invoke`로 도달 |
| `iris/ui/window/diagram_preview.py` | 변경 전: 부모 있는 최상위 `QWebEngineView` 창(제목 IRIS Diagram, 1280×820) |
| 채팅 로그 | `ChatPanel`의 `QTextEdit` 하나. 자바스크립트 페이지를 문서 안에 넣을 수 없음 |
| 시스템 프롬프트 | `diagram.render`를 언급하지 않음 |
| Hermes 스킬 | 이 PC에 `architecture-diagram`(Cocoon, HTML을 직접 작성)과 `excalidraw`가 설치됨. 아이리스 카드와 연결되어 있지 않음 |

컴패니언에서 아이리스 칸은 작업 영역 너비의 약 20%다. archify 산출은 가로 1440px 전후를 전제로 하고, 폭이 줄어도 SVG 배치는 유지한다.

이 PC의 `~/.iris-light/runtime/diagrams/`는 없고, 채팅 DB에도 다이어그램 호출이 없다.

## 업스트림이 하는 일

종류는 `architecture`, `workflow`, `sequence`, `dataflow`, `lifecycle`. 입력은 스키마를 통과한 JSON이고, 출력은 외부 CDN 없는 HTML이다. 뷰어에는 테마(`#btn-theme`), 경로 따라가기(`#btn-route-probe`), 포커스, 보내기가 있다.

쿼리 두 개가 표시를 가른다.

- `embed=1`은 툴바·경로·테마 버튼을 숨긴다. 카드에 쓰면 요청한 뷰어 기능이 사라진다.
- `present=1`은 SVG를 뷰포트에 맞추고(`preserveAspectRatio`로 비율 유지), 테마·경로·포커스·보내기는 남긴다. 하단 요약 카드는 숨긴다.

`present` 모드 헤더는 `padding-right: 23rem`이라 좁은 칸에서 제목이 밀린다. 호스트가 로드 후 그 패딩만 0으로 덮는다. archify 소스는 수정하지 않는다.

## 채팅에 넣는 방식

`QTextEdit` 메시지 사이에 웹뷰를 끼우지 않는다. 로그와 입력창 사이에 카드 하나를 둔다.

- 너비는 채팅 칸과 같다. 높이는 패널의 절반, 180~420px.
- `QWebEngineView`는 첫 표시 때 카드의 자식으로 하나 만들고 재사용한다. `Window` 플래그 없음.
- 주소는 로컬 HTML에 `present=1`.
- 닫으면 카드만 숨긴다. 로그의 `다시 보기`(`iris-diagram://`)가 같은 파일을 다시 연다.
- 한 턴에 여러 번 호출되면 카드 내용이 바뀐다. 웹뷰는 늘 하나다.

호출 조건은 프롬프트와 카탈로그 요약에 적는다. 앱이 문장을 분류해 자동으로 그리지는 않는다.

- 사용자가 구조·흐름·시퀀스·아키텍처를 보여 달라고 할 때
- 여러 모듈에 걸친 큰 구조 변경을 설명하거나 요약할 때
- 한 파일·한 함수 수정, 버그 수정, 실행 결과에는 호출하지 않음
- Hermes `architecture-diagram` 스킬로 HTML 파일을 쓰지 않음
