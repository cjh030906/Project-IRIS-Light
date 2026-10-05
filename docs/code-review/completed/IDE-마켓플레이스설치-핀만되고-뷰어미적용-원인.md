# IDE 마켓플레이스 — 설치했다고 했는데 PDF가 안 열리는 이유

| 항목 | 내용 |
|---|---|
| 문서 번호 | IRIS-REV-2026-1003-03 |
| 작성일 | 2026-10-03 |
| 대상 | 아이리스 IDE 채팅에서 `mathematic.vscode-pdf` 설치를 요청한 턴 |
| 목적 | 도구는 성공인데 에디터에서 PDF가 안 보이는 이유, 그리고 확장이 다른 프로젝트에도 남는지 |
| 조사 범위 | `ide.marketplace_install`, Open VSX 핀 파일, Theia 플러그인 디렉터리, `THEIA_CONFIG_DIR` |
| 하지 않은 일 | 코드 수정, VSIX 다운로드, 확장 설치 |

관련: `docs/code-review/completed/IDE-검은영역-탭-PDF-마켓플레이스-구현프롬프트.md` (검색·목록 고정만 하고 VSIX는 받지 않는다고 적힌 구현 계약).

---

## 1. 결론

설치 도구는 실패하지 않았다. 열린 프로젝트에 확장 ID를 **추천 목록으로만** 적었다. VSIX를 받지 않았고, Theia가 PDF를 그리는 플러그인도 없다. 그래서 채팅은 「설치 완료, 더블클릭하면 보인다」고 했고, 화면의 PDF는 그대로다.

같은 동작은 다른 프로젝트를 열어도 PDF 뷰어가 따라가지 않는다. 지금 채팅이 쓰는 기록은 그 프로젝트 폴더 안이다. Theia가 마켓플레이스 화면에서 실제로 깔면 그 파일은 프로젝트 밖 사용자 데이터에 남고, 그때는 다른 프로젝트를 열어도 같은 IDE에 남는다. 이번 턴은 그 경로를 타지 않았다. 사용자 데이터 아래 `deployedPlugins` 폴더도 없다.

---

## 2. 확인한 사실

지금 IDE가 연 폴더는 `c:\Users\kwakm\Desktop\동양미래대학교 2학년 2학기\딥러닝응용프로그래밍` 이다. `%USERPROFILE%\.iris-light\runtime\iris_ide_state.json` 의 `workspace`와 같다.

그 폴더에 이번 요청의 결과만 있다.

`.vscode/extensions.json`

```json
{
  "recommendations": [
    "mathematic.vscode-pdf"
  ]
}
```

`.iris/marketplace.json`

```json
[
  {
    "id": "mathematic.vscode-pdf",
    "source": "open-vsx"
  }
]
```

실행 중인 Theia가 읽는 플러그인 디렉터리 `%USERPROFILE%\.iris-light\runtimes\iris-ide\plugins` 에는 플러그인 88개가 있고, 이름에 `pdf`가 들어간 항목은 없다.

`%USERPROFILE%\.iris-light\iris-ide\user-data` 에는 `globalStorage`, `logs`, `plugin-storage`, `workspace-storage`, `settings.json` 만 있다. Theia가 사용자가 깐 확장을 푸는 `deployedPlugins` 는 없다.

채팅 로그의 `iris_invoke` 두 번(검색, 설치)은 둘 다 completed다. 검색 결과에 나온 ID 목록과 디스크의 핀이 맞다. 도구가 빈 성공을 돌려서 모델이 지어낸 상태가 아니다. 성공의 내용이 핀이다.

---

## 3. 구조

이번 문장은 검색과 설치가 갈라진다. 검색은 Open VSX 목록만 돌려준다. 설치는 프로젝트 파일 두 개에서 끝난다. PDF를 여는 플러그인 호스트까지 가지 않는다.

```
채팅 "PDF 보이게 하는 확장을 찾아줘"
  → Hermes iris_invoke
      → ide.marketplace_search
          → _ide_project()                         ← IDE 컴패니언 + 열린 폴더
          → search_extensions(query)
              → https://open-vsx.org/api/-/search
          → ok, extensions[]                       ← 설치 없음
  → 모델이 목록을 말하고 설치를 묻는다

채팅 "mathematic.vscode-pdf 설치해서 적용해줘"
  → Hermes iris_invoke
      → ide.marketplace_install
          → _ide_project()
          → pin_extension(root, id)
              → <프로젝트>/.vscode/extensions.json   recommendations 에 id 추가
              → <프로젝트>/.iris/marketplace.json    {id, source: open-vsx} 추가
          → ok_result status=success
              result = {id, recommendations 경로, record 경로}
  → 모델이 "설치 완료, 더블클릭하면 보인다" 로 말한다

PDF를 여는 데 필요한 경로 (이번 턴은 여기로 안 감)
  Theia 기동
    → --plugins=local-dir:<runtime>/plugins        ← 번들 플러그인만
    → THEIA_CONFIG_DIR = ~/.iris-light/iris-ide/user-data
  마켓플레이스 화면에서 Install
    → pluginServer.install
    → user-data/deployedPlugins/<확장 id>/         ← 이번 디스크에는 없음
  .vscode/extensions.json 을 Theia가 읽는 경우
    → 워크스페이스 추천 목록
    → 기동 직후 한 번 "추천 확장을 설치할까요?" 토스트
    → 사용자가 Install 을 눌러야 pluginServer.install
```

갈라지는 곳: `pin_extension` 이 파일을 쓴 뒤 `ok`를 반환하는 지점. 그 다음에 VSIX를 받거나 Theia에 다시 로드하라고 알리는 단계가 없다. `.iris/marketplace.json` 을 다시 읽는 코드도 없다. Theia가 보는 쪽은 `.vscode/extensions.json` 의 추천 목록뿐이고, 그것도 설치가 아니라 질문이다.

---

## 4. 코드 리뷰

### 4.1 검색 — 한 일

`ide_marketplace_search` (`iris/ui/control_actions/ide.py`) 는 열린 프로젝트 경로를 확인한 뒤 `search_extensions` 를 호출한다. `project_marketplace.search_extensions` 는 Open VSX 검색 JSON에서 `namespace.name`, 버전, 표시 이름만 고른다. 카탈로그 요약에 「Does not install. Do not claim installed.」가 있다. 이번 첫 답변의 표는 이 반환과 맞다.

### 4.2 설치 — 한 일, 못 막은 이유

`ide_marketplace_install` 은 `pin_extension` 만 호출하고, 예외가 없으면 `ok_result` 로 `status: success` 를 돌려준다.

`pin_extension` (`iris/system/project_marketplace.py`) 은 ID가 `publisher.name` 인지 검사한 다음 두 파일만 고친다. 모듈 첫 줄이 「VSIX는 받지 않는다」다. 네트워크로 Open VSX에서 패키지를 받는 호출이 없다. Theia 프로세스, `plugins` 디렉터리, `user-data` 를 건드리지 않는다.

카탈로그와 레지스트리 요약은 「Does not download a VSIX. Does not install into Iris.」라고 적혀 있다. 모델이 본 성공 JSON에는 그 문장이 없고, `ok: true` 와 파일 경로만 있다. 메모리 안내 `hermes_memory_nudge` 15f 와 메인 창 도구 문장(`main_window.py`)은 액션 이름을 `ide.marketplace_install` 이라고만 하고, VSIX를 받지 않는다는 말과 「PDF가 열린다고 말하지 말 것」이 없다. 그래서 도구는 핀에 성공했고, 답변은 에디터 적용까지 말했는데, 그 문장을 지우는 완료 게이트는 없다. 완료 게이트는 PDF **파일 저장** 문장용이다.

자검 `_check_ide_request_tools` 도 추천 목록 문자열만 확인한다. 플러그인 디렉터리에 패키지가 있는지는 보지 않는다.

### 4.3 Theia가 추천 목록으로 하는 일

실행본 `@theia/vsx-registry` 의 `showRecommendedToast` 는 모델이 한 번 바뀐 뒤 5초 뒤 한 번만 뜬다. 추천 ID가 아직 설치돼 있지 않으면 「이 저장소의 추천 확장을 설치할까요?」를 묻고, 사용자가 Install 을 눌렀을 때만 `extension.install()` → `pluginServer.install` 이다. 파일을 쓰는 도중에 이미 그 한 번이 지났으면, 같은 프로세스에서는 다시 묻지 않는다.

`install()` 은 미검증 확장 확인 대화상자를 거칠 수 있다. 이번 채팅 경로는 이 함수까지 도달하지 않았다.

### 4.4 다른 프로젝트에 남는지

기록이 두 곳이다. 이번 액션은 첫 곳만 쓴다.

| 기록 | 위치 | 이번 턴 | 다른 프로젝트를 열면 |
|---|---|---|---|
| 추천 핀 | `<그 프로젝트>/.vscode/extensions.json` | 있음 | 그 폴더를 열 때만 Theia 추천 목록에 들어간다 |
| 아이리스 메모 | `<그 프로젝트>/.iris/marketplace.json` | 있음 | 아이리스가 다시 읽지 않는다. 다른 프로젝트로 복사되지 않는다 |
| 사용자 설치본 | `~/.iris-light/iris-ide/user-data/deployedPlugins/` | 폴더 없음 | Theia `getDeploymentDirUri` 가 `THEIA_CONFIG_DIR/deployedPlugins` 다. 기동 시 `THEIA_CONFIG_DIR` 은 프로젝트와 무관한 `iris_ide_config_dir()` 이다. 여기 풀린 확장은 워크스페이스를 바꿔도 같은 IDE 프로세스에 남는다 |
| 번들 플러그인 | `~/.iris-light/runtimes/iris-ide/plugins` | PDF 뷰어 없음 | `--plugins=local-dir` 로 항상 이 디렉터리를 읽는다. 프로젝트마다 바뀌지 않는다. 마켓플레이스 설치 위치가 아니다 |

구현 프롬프트의 계약은 「열린 프로젝트의 목록에만 고정하고 VSIX는 받지 않는다」였다. 코드는 그 계약대로다. 사용자가 기대한 「에디터 안에서 PDF가 열린다」와 「깔면 IDE에 남는다」는 `pluginServer.install` 쪽인데, 채팅 액션은 그 함수를 부르지 않는다.

### 4.5 하지 않은 일

- Open VSX에서 `mathematic.vscode-pdf` VSIX를 받아 `plugins` 또는 `deployedPlugins` 에 풀지 않았다.
- 설치 뒤 Theia를 다시 띄우거나 PDF 커스텀 에디터를 등록하지 않았다.
- `.iris/marketplace.json` 을 IDE가 열릴 때 읽어 자동 설치하지 않았다.
- 답변의 「더블클릭하면 보인다」를 플러그인 실재 여부로 막지 않았다.

---

## 5. 빈 자리

1. `pin_extension` 성공과 PDF가 열리는 상태 사이에 `pluginServer.install`(또는 같은 배포 디렉터리에 VSIX를 푸는 단계)이 없다. 성공 JSON이 핀 경로만 반환한다.
2. 모델 안내(15f, 메인 창 도구 문장)가 액션 이름만 「install」로 알려 주고, 카탈로그에 있는 「VSIX를 받지 않는다」를 반복하지 않는다. 핀만 된 성공을 PDF 뷰어 적용으로 말하지 못하게 하는 문장도 없다.
3. Theia 추천 토스트는 프로세스당 한 번이라, 이미 켜진 IDE에서 핀을 써도 설치 질문이 다시 나오지 않는다. 질문이 나와도 사용자가 Install 을 누르기 전에는 `deployedPlugins` 가 생기지 않는다.
