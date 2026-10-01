"""History 검색 평가 — 키워드만으로 충분한가.

공정하게 재려고 지킨 것:
- 정답(relevant id)을 **검색 돌리기 전에** 못박는다.
- 질의를 세 갈래로 섞는다: 같은 말 반복 / 조사·어미 변형 / 다른 말로 바꿔 말하기.
  키워드에 불리한 것만 모으면 원하는 결론이 나오게 되어 있다.
- 코퍼스는 이 프로젝트에서 실제로 오간 주제로 만든다(설치·모델 전환·루틴·위키·공모전).

한계: 합성 데이터다. 실제 사용 기록이 쌓이면 다시 재야 한다.

실행:
    PYTHONPATH=. python scripts/eval_history_search.py
    PYTHONPATH=. python scripts/eval_history_search.py --embed bge-m3

2026-09-29 키워드 전용 기준선 (top-5 재현율):
    같은 말      5/5  (100%)
    조사 변형     4/5  (80%)
    바꿔 말하기    3/8  (38%)   ← 놓친 6개 중 4개는 결과 0건
    전체        12/18 (67%)

2026-09-29 키워드+의미 (bge-m3, 같은 18개 질의):
    같은 말      5/5  (100%)
    조사 변형     4/5  (80%)
    바꿔 말하기    8/8  (100%)   ← 키워드가 놓친 5개 전부 회복, 새로 놓친 것 없음
    전체        17/18 (94%)

남은 1개 '모델을 바꿨던 기록'은 두 방식 모두 놓친다. 정답 문장은 "갈아탔습니다"라
사실상 바꿔 말하기인데 '조사 변형'으로 분류돼 있다. 결과를 본 뒤 라벨을 고치면
채점을 맞추는 셈이라 그대로 둔다. 의미검색 1위는 "인수인계문을 … 새 모델에
넘겼습니다"로 주제상 틀리지 않다.

비용: 질의당 중앙값 8ms → 1.2s(최대 3.3s), 색인 건당 약 1.2s, VRAM 664MB.
그래서 질의 임베딩은 UI 스레드에서 하지 않는다(HistoryEvidenceWorker·
RoutineRunWorker). 벡터 결과는 관련 없는 것까지 늘 채워 오므로 코사인 하한·
1위 대비 폭으로 자른다(history_index._VEC_FLOOR/_VEC_MARGIN) — 재현율 그대로
94%, 딸려오는 오답은 질의당 3.3 → 1.0건.
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

os.environ["IRIS_DB_PATH"] = str(Path(tempfile.mkdtemp()) / "eval.db")

from iris.knowledge.history_index import index_entry, search  # noqa: E402
from iris.knowledge.history_store import (  # noqa: E402
    KIND_ACTION,
    KIND_ARTIFACT,
    KIND_CHAT,
    KIND_INPUT,
    record_entry,
)
from iris.storage.database import Database  # noqa: E402

# (키, 종류, 본문)
CORPUS: list[tuple[str, str, str]] = [
    ("install_perm", KIND_CHAT, "설치 프로그램이 venv 권한 오류로 자꾸 죽습니다"),
    ("install_fix", KIND_CHAT, "python.exe 가 잠겨 있어서 그렇습니다. 소유권을 바꾸고 재시도 로직을 넣었습니다"),
    ("install_long", KIND_CHAT, "긴 경로에서 롤백이 안 되는 문제가 남았어요"),
    ("install_robo", KIND_ACTION, "robocopy 로 교체하고 setup.ps1 재실행"),
    ("version_bump", KIND_ACTION, "제품 버전 표기를 0.1.16 으로 올림"),
    ("release_upload", KIND_CHAT, "릴리스 업로드는 친구가 해야 해서 제가 못 합니다"),
    ("model_switch", KIND_ACTION, "qwen3:8b 에서 gemma4:free 로 갈아탔습니다"),
    ("quota_gone", KIND_CHAT, "주간 한도를 다 써서 유료 모델이 막혔어요"),
    ("handoff", KIND_ARTIFACT, "인수인계문을 만들어 새 모델에 넘겼습니다"),
    ("wiki_history", KIND_CHAT, "대화 기록을 위키에 쌓고 나중에 찾아 쓰고 싶어요"),
    ("embed_model", KIND_CHAT, "임베딩 모델이 없어서 키워드 검색만 돌고 있습니다"),
    ("routine_news", KIND_ACTION, "매일 아침 아홉시에 뉴스 세 건을 정리하는 일을 등록"),
    ("routine_mail", KIND_ACTION, "금요일 저녁마다 받은 편지함을 훑어 정리하도록 예약"),
    ("toast_click", KIND_CHAT, "알림을 눌렀을 때 창이 앞으로 나오게 해주세요"),
    ("toast_aumid", KIND_ACTION, "시작 메뉴 바로가기에 AppUserModelID 를 심어 알림 등록"),
    ("schtasks", KIND_ACTION, "작업 스케줄러에 다섯 분 주기 마스터 작업을 걸었습니다"),
    ("contest_web", KIND_CHAT, "공모전은 exe 배포가 금지라 브라우저로 스트리밍해야 합니다"),
    ("site_split", KIND_ACTION, "소개 사이트를 별도 저장소로 떼어냈습니다"),
    ("email_setup", KIND_INPUT, "지메일 계정을 등록하고 앱 비밀번호를 넣었습니다"),
    ("calendar_add", KIND_ACTION, "다음 주 화요일 두시 발표 일정을 달력에 추가"),
    ("ide_open", KIND_ACTION, "커서 IDE 로 프로젝트 폴더를 열었습니다"),
    ("learning_demo", KIND_ARTIFACT, "화면 시연으로 업무를 학습시켰습니다"),
    ("voice_off", KIND_CHAT, "마이크를 꺼두고 싶어요"),
    ("pdf_import", KIND_INPUT, "계약서 PDF 본문을 추출해 위키에 저장"),
    ("card_refund", KIND_INPUT, "카드 결제 취소하고 환불받은 내역"),
]

# (질의, 갈래, 정답 키들) — 검색 전에 정한다
QUERIES: list[tuple[str, str, list[str]]] = [
    # A. 같은 말을 그대로 쓰는 경우 — 키워드가 잘해야 정상
    ("robocopy", "같은 말", ["install_robo"]),
    ("작업 스케줄러", "같은 말", ["schtasks"]),
    ("공모전", "같은 말", ["contest_web"]),
    ("인수인계문", "같은 말", ["handoff"]),
    ("임베딩 모델", "같은 말", ["embed_model"]),
    # B. 조사·어미가 달라지는 경우 — 한국어에서 가장 흔함
    ("권한을 어떻게 고쳤더라", "조사 변형", ["install_perm", "install_fix"]),
    ("버전을 올린 게 언제지", "조사 변형", ["version_bump"]),
    ("일정을 추가했던 거", "조사 변형", ["calendar_add"]),
    ("알림이 눌리면", "조사 변형", ["toast_click"]),
    ("모델을 바꿨던 기록", "조사 변형", ["model_switch"]),
    # C. 다른 말로 바꿔 말하는 경우 — 의미검색이 있어야 잡힌다는 가설
    ("인스톨 실패", "바꿔 말하기", ["install_perm", "install_fix"]),
    ("돈 관련 기록", "바꿔 말하기", ["card_refund"]),
    ("메일 계정 연결", "바꿔 말하기", ["email_setup"]),
    ("할당량 소진", "바꿔 말하기", ["quota_gone"]),
    ("아침마다 자동으로 해주는 일", "바꿔 말하기", ["routine_news"]),
    ("음성 입력 끄기", "바꿔 말하기", ["voice_off"]),
    ("웹으로 데모 보여주기", "바꿔 말하기", ["contest_web"]),
    ("에디터로 폴더 열기", "바꿔 말하기", ["ide_open"]),
]

TOP_K = 5


def _embedder(model_name: str):
    """`--embed <모델>` 이 주어지면 Ollama 임베더를 붙인다."""
    if not model_name:
        return None
    from iris.infrastructure.ollama_client import OllamaClient
    from iris.knowledge.history_index import OllamaEmbedder

    client = OllamaClient("http://127.0.0.1:11434/v1")
    picked = client.pick_embedding_model(model_name)
    if not picked:
        print(f"경고: 임베딩 모델 '{model_name}' 없음 — 키워드만 잽니다.")
        return None
    print(f"임베더: {picked}")
    return OllamaEmbedder(client=client, model_name=picked)


def main() -> None:
    want_embed = ""
    if "--embed" in sys.argv:
        idx = sys.argv.index("--embed")
        want_embed = sys.argv[idx + 1] if idx + 1 < len(sys.argv) else "bge-m3"

    db = Database()
    embedder = _embedder(want_embed)
    ids: dict[str, int] = {}
    for key, kind, body in CORPUS:
        entry = record_entry(db, kind=kind, body=body)
        assert entry is not None
        index_entry(db, entry, embedder=embedder)
        ids[key] = entry.id
    mode = f"키워드+의미 ({want_embed})" if embedder else "키워드만"
    print(f"코퍼스 {len(ids)}건 · 질의 {len(QUERIES)}개 · top-{TOP_K} · {mode}\n")

    by_bucket: dict[str, list[int]] = {}
    misses: list[tuple[str, str, list[str]]] = []

    for query, bucket, wanted_keys in QUERIES:
        wanted = {ids[k] for k in wanted_keys}
        hits = search(db, query, limit=TOP_K, embedder=embedder)
        got = [h.entry.id for h in hits]
        found = wanted & set(got)
        score = 1 if found else 0
        by_bucket.setdefault(bucket, []).append(score)
        mark = "O" if score else "X"
        rank = (got.index(next(iter(found))) + 1) if found else 0
        pos = f"{rank}위" if rank else "못 찾음"
        print(f"  {mark} [{bucket}] {query!r} → {pos}")
        if not score:
            top = hits[0].entry.body[:32] if hits else "(결과 없음)"
            misses.append((bucket, query, [top]))

    print("\n갈래별 재현율 (top-5 안에 정답이 하나라도 있으면 성공)")
    total = 0
    count = 0
    for bucket, scores in by_bucket.items():
        hit = sum(scores)
        total += hit
        count += len(scores)
        print(f"  {bucket:10s} {hit}/{len(scores)}  ({100*hit/len(scores):.0f}%)")
    print(f"  {'전체':10s} {total}/{count}  ({100*total/count:.0f}%)")

    if misses:
        print("\n놓친 것 (키워드 검색이 대신 올린 1위)")
        for bucket, query, top in misses:
            print(f"  [{bucket}] {query!r} → {top[0]}")

    db.close()


if __name__ == "__main__":
    sys.exit(main())
