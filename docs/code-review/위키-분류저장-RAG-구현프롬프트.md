# Prompt: 위키 분류 저장 · 노트 RAG · 특성 노트

아래 블록을 구현 계약으로 따른다. 보고서: `docs/code-review/위키-기획대비-구현수준과-개선안.md`

```text
Context:
- 저장소: Project-IRIS-Light (Windows / PyQt6)
- 사용자 위키 루트: ~/.iris-light/iris-wiki/  (UI 경로 접두사는 user/)
- 저장 진입점은 wiki.write_user_note, wiki.import_content, wiki.import_pages,
  채팅의 “위키에 저장”(save_answer_to_wiki / import_to_wiki) 이다.
  지금은 모두 IrisWiki.write_inbox_note → inbox/{slug}.md 이고, 그 파일은 검색·주입 대상이 아니다.
- 대화 원문 RAG는 History(FTS5 trigram + Ollama 임베딩 bge-m3, RRF)다.
  노트 지식과 소스를 섞지 않는다. 새 pip 패키지는 넣지 않는다.
- learning/ 은 GUI 시연 목록이다. 공부 자료를 여기 넣지 않는다.
- profile/profile.md 는 설정 폼 사본이다. 성장 노트는 profile/traits.md 로 따로 둔다.
- 그래프 _add_cluster 는 [[링크]]용 인덱스를 만들어 반환만 하고, build()가 버린다.
  hub_idx 가 None 인 간선은 그리지 않는다.
- 액션 카탈로그 스냅샷은 register() 요약과 같아야 한다.

Goal:
1) inbox 는 받는 함만 남긴다. 분류가 된 노트는 아래 트리로 옮긴다.
2) 분류는 키워드 표가 아니다. 임베딩 코사인(장소 설명 문장 + 그 폴더에 이미 있는 노트)이
   우선이고, 임베딩이 없거나 새 분야 이름이 필요할 때만 채팅 모델의 JSON 한 번이 고른다.
   둘 다 실패하거나 1·2위 점수 차가 0.04 미만이면 inbox 에 두고 ask_folder=true.
3) 노트 본문을 History 와 분리된 FTS+임베딩 색인에 올린다.
   채팅 전송 전 질문과 겹치는 노트 발췌만 넣고, 이전 대화 블록과 제목을 달리한다.
   키·주민등록번호 형태는 주입하지 않는다.
4) 대화를 떠나면 write_episode 로 요약한 뒤, 관심사·지금 수준·이번에 나아진 점만
   profile/traits.md 에 잇고 근거는 에피소드 링크다. 성격 점수는 적지 않는다.
   그 파일은 매 턴 짧은 블록으로 넣는다. 사용자가 마커 위에 고친 글은 유지한다.
5) 열린 project_root 가 있고 그 쪽 유사도가 이기면 projects/{slug}/ 에 둔다.
6) 그래프가 [[노트]] 를 실제로 잇고 화면에 그린다.
7) wiki.search 로 같은 색인을 연다.

폴더 (물리 경로, UI 에서는 user/ 가 붙는다):

  inbox/                     분류 실패·애매할 때만
  사용자/특징|취미|강점|약점|사고력|가치관/     대화에서 나온 사람 노트
  학습자료/{분야}/           공부. 분야는 기존 노트의 유사도가 높으면 그 폴더,
                             아니면 모델이 준 분야 이름
  인사이트/{주제}/           개발 자료·기술 개념 (한 프로젝트 결정이 아닌 것)
  projects/{열린 프로젝트}/  지금 연 프로젝트의 결정·작업 결론
  research/{주제}/           연구 질문·논문·실험
  profile/traits.md          세션 성장 얇은 노트
  history/ learning/ schedule/ IRIS/ profile/profile.md  는 이 분류가 쓰지 않는다

Constraints:
- 제목·본문에 단어가 있는지로 폴더를 고르지 않는다.
- 매 턴 볼트 전문을 넣지 않는다. 노트 3개, 발췌 800자, 합 2400자.
- 호출자가 inbox 가 아닌 rel_path 를 주면 그 경로를 존중한다.
- inbox/ 로 들어온 rel_path 는 예전 기본값으로 보고 다시 분류한다.
- 분류기(임베더·모델)를 넘기지 않은 기존 호출은 지금처럼 inbox 에 둔다.
- Companion 80:20, IDE new-window, learning/workflows.md 계약을 건드리지 않는다.

Interface:
1) iris/knowledge/wiki_places.py
   - Place 목록과 한국어 설명 문장(임베딩 앵커). 키워드 목록이 아니다.
   - PLACE_FLOOR=0.45, PLACE_MARGIN=0.04
   - is_sensitive(text) — api key / token / 주민번호 형태
   - project_prototype(slug), project_slug(root)

2) iris/knowledge/wiki_classify.py
   - note_embed_text(title, body)
   - classify_note(...) -> folder, place_id, ask_folder
   - 임베더가 있으면 코사인으로 장소를 고른다.
     동적 부모(학습자료·인사이트·research)가 이기고 기존 하위 폴더가 바닥 이상이면 그 폴더.
     아니면 namer 에게 {"field":"..."} 만 물어 하위 폴더를 만든다. 이름이 없으면 부모 바로 아래.
   - 임베더가 없으면 namer 에게 {"place":"<id>","field":""} 를 묻고 id 가 목록 밖이면 inbox.
   - 1위와 2위가 둘 다 바닥 이상이고 차가 MARGIN 미만이면 inbox + ask_folder.

3) iris/knowledge/wiki_note_index.py
   - wiki_notes / wiki_notes_fts / wiki_note_vectors. History 테이블과 분리.
   - sync_knowledge_notes: 위 트리와 profile/traits.md 만. mtime 이 같으면 건너뛴다.
   - 민감 노트는 검색 결과에서 뺀다.
   - wiki_prompt_for_query: 헤더에 "저장된 자료" 와 "이전 대화와 다른 출처" 를 적는다.
   - embed_pending_notes: 벡터가 없는 노트만 최대 N건.

4) iris/knowledge/wiki_filing.py
   - file_user_note(..., classify=False). classify 가 아니면 오늘과 같이 inbox.
   - classify 이면 분류 후 unique 경로로 write_inbox_note, db 가 있으면 색인.
   - open_classifier(base_url, history_settings, model): 임베더는 모델 목록 조회 4초,
     이름 짓기는 chat_once JSON. 실패하면 None. 키워드 폴백 없음.

5) iris/knowledge/wiki_session.py
   - close_session: 비어 있지 않은 말이 2개 미만이거나 요약이 비면 아무것도 쓰지 않는다.
   - write_episode 후 traits 섹션을 <!-- iris-traits --> 아래에 잇는다. 마커 위 글은 유지.
     섹션은 최근 12개. 근거는 에피소드 제목 위키링크.
   - traits_prompt_block: 매 턴. 민감하면 빈 문자열. 1500자.

6) iris/knowledge/wiki_links.py + WikiGraphView.build
   - _add_cluster 가 돌려준 인덱스를 제목·경로·stem 으로 보강한 뒤 [[대상]] 간선을 넣는다.
   - kind "link" 는 hub 색이 없어도 그린다.

7) 진입점
   - 컨트롤 액션·로컬 저장·import 워커는 classify=True 와 open_classifier 결과를 넘긴다.
   - wiki.search(query) 등록. 카탈로그 요약·건수를 register() 와 맞춘다.
   - 시스템 프롬프트·iris-wiki 스킬·Hermes nudge: inbox 기본 경로 안내를 지우고
     분류 트리와 wiki.search 를 적는다. 저장 성공은 여전히 ok 일 때만.
   - 채팅 전송: 4글자 이상이면 노트 발췌를 이전 대화와 따로 싣는다.
     임베딩은 기존 이전대화 워커의 제한 시간 안에서 하고, 넘기면 키워드 발췌로 보낸다.
   - 다른 대화로 옮기거나 새 채팅·대화 비우기 전에 close_session 을 백그라운드에서 호출한다.
   - History 임베딩 워커가 노트 색인 동기화와 밀린 노트 벡터도 처리한다.

8) 자검 iris/knowledge/_check_wiki_filing.py
   - 본문에 폴더 이름이 없는 노트도, 스크립트 임베더가 취미 축을 주면 사용자/취미 로 간다.
   - 취미·학습 축이 같이 높으면 inbox + ask_folder.
   - 학습 축 + namer 가 선형대수를 주면 학습자료/선형대수/. 다음 노트는 그 폴더 벡터로
     같은 곳에 가고 namer 를 다시 부르지 않는다.
   - 임베더 없이 {"place":"user.values"} 면 사용자/가치관/.
     JSON 이 아니면 inbox.
   - inbox 가 아닌 rel_path 는 그대로.
   - 민감 본문은 검색에 안 나오고, 일반 본문은 FTS 로 나온다.
   - traits 마커 위 문장은 유지되고 섹션은 12개로 잘린다.
   - [[제목]] 간선이 그래프에 생긴다.

검증:
.venv\Scripts\python.exe -m iris.knowledge._check_wiki_filing
.venv\Scripts\python.exe -m iris.ui._check_wiki
.venv\Scripts\python.exe -m iris.ui._check_control_action_split
.venv\Scripts\python.exe -m unittest tests.test_wiki_save_flow tests.test_wiki_save_notice
```
