"""Iris Wiki History 검색 — FTS5 키워드 + 임베딩 의미검색 하이브리드.

새 pip 의존성 없이 돌아간다.

- 키워드: SQLite FTS5 `trigram` 토크나이저. 한국어 조사가 붙어도 부분일치가 된다
  (`프로그램` 이 `프로그램에서` 를 잡는다). trigram이 놓치는 두 경우 — 3글자 미만
  질의(`권한`)와 반대 방향 굴절(`권한을` 로 `권한` 찾기) — 은 단어별 LIKE 로 보충한다.
- 의미: Ollama 임베딩 모델(`bge-m3` 등)이 설치돼 있을 때만. 없으면 키워드만 쓴다.
  벡터는 정규화해서 float32 BLOB 로 저장하고 내적으로 코사인을 낸다.

두 순위를 RRF(Reciprocal Rank Fusion)로 합친다. 한쪽이 없어도 결과가 나온다.
"""

from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

import numpy as np

from iris.knowledge.history_store import (
    EPISODE_DIR,
    HistoryEntry,
    ensure_history_schema,
    get_entry,
)
from iris.storage.database import Database

EMBED_MODEL_PREF_KEY = "wiki_history_embed_model_v1"

# trigram 토크나이저의 하한. 이보다 짧은 질의어는 MATCH로 못 찾는다.
_TRIGRAM_MIN = 3
_CHUNK_CHARS = 1200
_CHUNK_OVERLAP = 150
# RRF 상수 — 값이 클수록 상위권 쏠림이 완만해진다. 원 논문 권장치.
_RRF_K = 60
# 벡터 순위는 무엇이든 늘 채워 온다 — 관련 없는 기록이 프롬프트에 섞인다.
# 1위와 _VEC_MARGIN 이상 벌어졌거나 _VEC_FLOOR 미만이면 버린다.
# bge-m3 로 18개 질의를 재서 정했다(scripts/eval_history_search.py 코퍼스):
# 정답 코사인 최저 0.48·중앙 0.64, 오답 중앙 0.43. 이 조합에서 정답 유지
# 17/18 그대로, 딸려오는 오답은 질의당 3.3 → 1.0건. 폭 0.05 가 숫자는 조금
# 더 좋았지만 합성 18개에 맞추는 셈이라 넉넉한 쪽을 골랐다.
_VEC_FLOOR = 0.45
_VEC_MARGIN = 0.10
_FTS_TOKEN_RE = re.compile(r"[^\w가-힣]+", re.UNICODE)
_HANGUL_RE = re.compile(r"[가-힣]")


class Embedder(Protocol):
    """임베딩 제공자. Ollama가 꺼져 있으면 아무도 안 넘기면 된다."""

    @property
    def model(self) -> str: ...

    def embed(self, texts: list[str]) -> list[list[float]]: ...


@dataclass(frozen=True)
class OllamaEmbedder:
    """OllamaClient 를 Embedder 로 감싼다."""

    client: object
    model_name: str
    # 모델을 메모리에 붙잡아 둘 시간. None 이면 Ollama 기본(5분).
    keep_alive: str | None = None

    @property
    def model(self) -> str:
        return self.model_name

    def embed(self, texts: list[str]) -> list[list[float]]:
        if self.keep_alive:
            return list(self.client.embed(  # type: ignore[attr-defined]
                self.model_name, list(texts), keep_alive=self.keep_alive
            ))
        return list(self.client.embed(self.model_name, list(texts)))  # type: ignore[attr-defined]


@dataclass(frozen=True)
class SearchHit:
    entry: HistoryEntry
    score: float
    keyword_rank: int | None
    vector_rank: int | None
    # 질의와의 코사인 유사도. 벡터 검색을 안 했거나 컷에 걸렸으면 None.
    similarity: float | None = None

    @property
    def matched_by(self) -> str:
        if self.keyword_rank is not None and self.vector_rank is not None:
            return "키워드+의미"
        if self.vector_rank is not None:
            return "의미"
        return "키워드"


def fts5_available(db: Database) -> bool:
    try:
        db._execute(
            "CREATE VIRTUAL TABLE IF NOT EXISTS _fts_probe USING fts5(x, tokenize='trigram')"
        )
        db._execute("DROP TABLE IF EXISTS _fts_probe")
        return True
    except sqlite3.Error:
        return False


def ensure_index_schema(db: Database) -> bool:
    """색인 테이블 준비. FTS5를 못 쓰면 False (LIKE 검색으로 계속 동작)."""
    ensure_history_schema(db)
    db._execute(
        """
        CREATE TABLE IF NOT EXISTS wiki_history_vectors (
            history_id INTEGER NOT NULL,
            chunk_ix INTEGER NOT NULL,
            model TEXT NOT NULL,
            dim INTEGER NOT NULL,
            vector BLOB NOT NULL,
            created_at TEXT NOT NULL,
            PRIMARY KEY (history_id, chunk_ix)
        )
        """
    )
    ok = fts5_available(db)
    if ok:
        try:
            db._execute(
                "CREATE VIRTUAL TABLE IF NOT EXISTS wiki_history_fts "
                "USING fts5(title, body, tokenize='trigram')"
            )
        except sqlite3.Error:
            ok = False
    db._commit()
    return ok


def chunk_text(text: str, *, size: int = _CHUNK_CHARS, overlap: int = _CHUNK_OVERLAP) -> list[str]:
    """임베딩용 분할. 짧으면 한 덩어리."""
    body = (text or "").strip()
    if not body:
        return []
    if len(body) <= size:
        return [body]
    step = max(1, size - overlap)
    out: list[str] = []
    for start in range(0, len(body), step):
        piece = body[start : start + size].strip()
        if piece:
            out.append(piece)
        if start + size >= len(body):
            break
    return out


def _normalize(vec: list[float]) -> np.ndarray:
    arr = np.asarray(vec, dtype=np.float32)
    norm = float(np.linalg.norm(arr))
    if norm <= 0.0:
        return arr
    return arr / norm


def index_entry(db: Database, entry: HistoryEntry, *, embedder: Embedder | None = None) -> None:
    """한 기록을 키워드·벡터 색인에 넣는다. 벡터는 embedder가 있을 때만."""
    has_fts = ensure_index_schema(db)
    if has_fts:
        db._execute("DELETE FROM wiki_history_fts WHERE rowid = ?", (int(entry.id),))
        db._execute(
            "INSERT INTO wiki_history_fts(rowid, title, body) VALUES(?, ?, ?)",
            (int(entry.id), entry.title or "", entry.body or ""),
        )
    db._commit()
    if embedder is not None:
        embed_entry(db, entry, embedder)


def embed_entry(db: Database, entry: HistoryEntry, embedder: Embedder) -> int:
    """기록 하나를 벡터화해 저장. 반환: 저장한 청크 수(실패 시 0)."""
    ensure_index_schema(db)
    head = f"{entry.title}\n" if entry.title else ""
    chunks = chunk_text(head + (entry.body or ""))
    if not chunks:
        return 0
    try:
        vectors = embedder.embed(chunks)
    except Exception:
        # Ollama가 죽었거나 모델이 빠졌다 — 키워드 검색은 그대로 쓴다.
        return 0
    if len(vectors) != len(chunks):
        return 0
    stamp = datetime.now().isoformat(timespec="seconds")
    db._execute("DELETE FROM wiki_history_vectors WHERE history_id = ?", (int(entry.id),))
    saved = 0
    for ix, vec in enumerate(vectors):
        arr = _normalize(vec)
        if arr.size == 0:
            continue
        db._execute(
            """
            INSERT INTO wiki_history_vectors(history_id, chunk_ix, model, dim, vector, created_at)
            VALUES(?, ?, ?, ?, ?, ?)
            """,
            (int(entry.id), ix, embedder.model, int(arr.size), arr.tobytes(), stamp),
        )
        saved += 1
    db._commit()
    return saved


def unembedded_ids(db: Database, model: str, *, limit: int = 200) -> list[int]:
    """아직 이 모델로 벡터가 없는 기록 id — 백그라운드 색인용."""
    ensure_index_schema(db)
    rows = db._execute(
        """
        SELECT h.id AS id FROM wiki_history h
        WHERE NOT EXISTS (
            SELECT 1 FROM wiki_history_vectors v
            WHERE v.history_id = h.id AND v.model = ?
        )
        ORDER BY h.id DESC LIMIT ?
        """,
        (str(model), max(1, int(limit))),
    ).fetchall()
    return [int(r["id"]) for r in rows]


def reindex_all(db: Database, *, embedder: Embedder | None = None, limit: int = 5000) -> int:
    """전체 재색인. 위키 파일을 손으로 고쳤거나 임베딩 모델을 바꿨을 때."""
    has_fts = ensure_index_schema(db)
    rows = db._execute(
        "SELECT * FROM wiki_history ORDER BY id DESC LIMIT ?", (max(1, int(limit)),)
    ).fetchall()
    if has_fts:
        db._execute("DELETE FROM wiki_history_fts")
    count = 0
    for row in rows:
        entry = get_entry(db, int(row["id"]))
        if entry is None:
            continue
        if has_fts:
            db._execute(
                "INSERT INTO wiki_history_fts(rowid, title, body) VALUES(?, ?, ?)",
                (entry.id, entry.title or "", entry.body or ""),
            )
        if embedder is not None:
            embed_entry(db, entry, embedder)
        count += 1
    db._commit()
    return count


def build_fts_query(text: str) -> str:
    """사용자 질의 → FTS5 MATCH 식. 3글자 미만 토큰은 trigram이 못 받아 버린다."""
    terms = [t for t in _FTS_TOKEN_RE.split(text or "") if t]
    usable = [t for t in terms if len(t) >= _TRIGRAM_MIN]
    if not usable:
        return ""
    # 따옴표로 감싸 구문 검색 — 연산자(-, *, :, NEAR)가 섞여도 안전하다.
    return " OR ".join('"' + t.replace('"', '""') + '"' for t in usable)


def _keyword_ranked(db: Database, query: str, limit: int) -> list[int]:
    """FTS5 우선, 모자라면 단어별 LIKE로 보충.

    trigram은 두 가지를 놓친다 — 2글자 이하 단어(`권한`)와, 조사가 달라 substring이
    어긋나는 굴절형(`오류가` 로는 `오류로` 를 못 찾는다). 한국어에서는 이게 흔해
    FTS 결과가 있든 없든 LIKE 보충을 항상 돌린다.
    """
    has_fts = ensure_index_schema(db)
    ordered: list[int] = []
    seen: set[int] = set()

    def _add(ids: list[int]) -> None:
        for hid in ids:
            if hid not in seen:
                seen.add(hid)
                ordered.append(hid)

    if has_fts:
        match = build_fts_query(query)
        if match:
            try:
                rows = db._execute(
                    """
                    SELECT rowid AS id FROM wiki_history_fts
                    WHERE wiki_history_fts MATCH ?
                    ORDER BY bm25(wiki_history_fts, 2.0, 1.0)
                    LIMIT ?
                    """,
                    (match, int(limit)),
                ).fetchall()
                _add([int(r["id"]) for r in rows])
            except sqlite3.Error:
                pass

    if len(ordered) < int(limit):
        _add(_like_ranked(db, query, int(limit) - len(ordered)))
    return ordered[: int(limit)]


def _escape_like(term: str) -> str:
    """LIKE 와일드카드 무력화. `_` 는 \\w 라 토큰에 남을 수 있다."""
    out = term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return out


def like_terms(query: str, *, min_len: int = 2) -> list[str]:
    """LIKE 보충에 쓸 단어들. 1글자는 아무 데나 걸려 노이즈만 된다."""
    terms: list[str] = []
    for raw in _FTS_TOKEN_RE.split(query or ""):
        term = raw.strip()
        if len(term) >= min_len and term not in terms:
            terms.append(term)
    return terms


def like_variants(term: str) -> list[str]:
    """조사·어미를 떼어낸 축약형. `권한을` → `권한`, `고치는` → `고치`.

    형태소 분석기 없이 한국어 굴절을 흉내내는 값싼 방법이다. 정확하진 않지만
    본딧말보다 **낮은 가중치**로만 쓰므로 정확한 일치를 밀어내지 않는다.
    """
    base = (term or "").strip()
    if not _HANGUL_RE.search(base):
        return []  # 영문은 글자를 떼면 엉뚱한 것만 걸린다
    out: list[str] = []
    for cut in (1, 2):
        if len(base) - cut >= 2:
            piece = base[: len(base) - cut]
            if piece and piece not in out:
                out.append(piece)
    return out


def _like_ranked(db: Database, query: str, limit: int) -> list[int]:
    """단어별 부분일치. 많은 단어가 걸린 기록일수록 위로 온다.

    본딧말은 2점, 조사를 떼어낸 축약형은 1점 — 정확히 맞은 기록이 늘 위에 온다.
    """
    terms = like_terms(query)
    if not terms:
        needle = (query or "").strip()
        if len(needle) < 2:
            return []
        terms = [needle]

    weighted: list[tuple[str, int]] = []
    seen: set[str] = set()
    for term in terms:
        if term not in seen:
            seen.add(term)
            weighted.append((term, 2))
    for term in terms:
        for variant in like_variants(term):
            if variant not in seen:
                seen.add(variant)
                weighted.append((variant, 1))

    clauses: list[str] = []
    params: list[object] = []
    for term, weight in weighted:
        esc = _escape_like(term)
        clauses.append(
            f"(CASE WHEN title LIKE '%'||?||'%' ESCAPE '\\' "
            f"OR body LIKE '%'||?||'%' ESCAPE '\\' THEN {weight} ELSE 0 END)"
        )
        params.extend([esc, esc])
    score = " + ".join(clauses)
    params.append(int(limit))
    rows = db._execute(
        f"""
        SELECT id, ({score}) AS hits FROM wiki_history
        WHERE hits > 0
        ORDER BY hits DESC, id DESC LIMIT ?
        """,
        tuple(params),
    ).fetchall()
    return [int(r["id"]) for r in rows]


def _vector_ranked(
    db: Database,
    query: str,
    limit: int,
    embedder: Embedder,
    margin: float | None = _VEC_MARGIN,
) -> list[tuple[int, float]]:
    ensure_index_schema(db)
    try:
        qvecs = embedder.embed([query])
    except Exception:
        return []
    if not qvecs:
        return []
    qarr = _normalize(qvecs[0])
    if qarr.size == 0:
        return []
    rows = db._execute(
        "SELECT history_id, dim, vector FROM wiki_history_vectors WHERE model = ?",
        (embedder.model,),
    ).fetchall()
    best: dict[int, float] = {}
    for row in rows:
        if int(row["dim"]) != int(qarr.size):
            continue  # 모델이 바뀌어 차원이 다른 잔재 — 건너뛴다
        vec = np.frombuffer(row["vector"], dtype=np.float32)
        if vec.size != qarr.size:
            continue
        score = float(np.dot(qarr, vec))
        hid = int(row["history_id"])
        if score > best.get(hid, -2.0):
            best[hid] = score
    ordered = sorted(best.items(), key=lambda kv: kv[1], reverse=True)
    if not ordered:
        return []
    cut = _VEC_FLOOR if margin is None else max(_VEC_FLOOR, ordered[0][1] - margin)
    return [(hid, score) for hid, score in ordered[: int(limit)] if score >= cut]


def search(
    db: Database,
    query: str,
    *,
    limit: int = 8,
    embedder: Embedder | None = None,
    conversation_id: int | None = None,
    exclude_conversation_id: int | None = None,
    kinds: tuple[str, ...] | None = None,
    pool: int = 40,
    vector_margin: float | None = _VEC_MARGIN,
) -> list[SearchHit]:
    """History 하이브리드 검색. 상위 `limit` 건.

    `exclude_conversation_id` — 지금 대화는 이미 모델 컨텍스트에 있으니 빼고
    찾을 때 쓴다. 안 빼면 방금 보낸 질문이 자기 자신을 1위로 찾아온다.
    """
    text = (query or "").strip()
    if not text:
        return []
    ensure_index_schema(db)
    kw = _keyword_ranked(db, text, pool)
    # vector_margin=None — 1위 대비 컷을 끈다. 1위가 쓸모없는 기록(예: 지금 질문과
    # 똑같은 옛 질문, 유사도 1.0)이면 컷이 0.9까지 올라 나머지가 다 잘린다.
    # 이전 대화 참고는 자체 절대 기준으로 거르므로 이걸 끈다.
    vec = (
        _vector_ranked(db, text, pool, embedder, vector_margin)
        if embedder is not None
        else []
    )

    fused: dict[int, float] = {}
    kw_rank: dict[int, int] = {}
    vec_rank: dict[int, int] = {}
    vec_sim: dict[int, float] = {}
    for rank, hid in enumerate(kw):
        kw_rank[hid] = rank + 1
        fused[hid] = fused.get(hid, 0.0) + 1.0 / (_RRF_K + rank + 1)
    for rank, (hid, sim) in enumerate(vec):
        vec_rank[hid] = rank + 1
        vec_sim[hid] = sim
        fused[hid] = fused.get(hid, 0.0) + 1.0 / (_RRF_K + rank + 1)

    hits: list[SearchHit] = []
    for hid, score in sorted(fused.items(), key=lambda kv: kv[1], reverse=True):
        entry = get_entry(db, hid)
        if entry is None:
            continue
        if conversation_id is not None and entry.conversation_id != conversation_id:
            continue
        if exclude_conversation_id is not None and entry.conversation_id == exclude_conversation_id:
            continue
        if kinds and entry.kind not in kinds:
            continue
        hits.append(
            SearchHit(
                entry=entry,
                score=score,
                keyword_rank=kw_rank.get(hid),
                vector_rank=vec_rank.get(hid),
                similarity=vec_sim.get(hid),
            )
        )
        if len(hits) >= int(limit):
            break
    return hits


_WIKI_BLOCK_RE = re.compile(r"(?m)^(?=## )")
_WIKI_ID_RE = re.compile(r"<!--[^>]*\bid:(\d+)\b")


def forget_conversation(db: Database, conversation_id: int, *, wiki=None) -> int:
    """채팅을 지우면 그 대화의 History도 지운다 — DB·키워드·벡터 색인·위키 사본 모두.

    이걸 안 하면 "이전 대화 참고"가 사용자가 지운 대화를 다시 꺼내 온다.
    conversation_id 가 0(대화 밖에서 생긴 수행 기록 등)이면 아무것도 안 지운다.
    지운 건수를 돌려준다.
    """
    cid = int(conversation_id or 0)
    if cid <= 0:
        return 0
    has_fts = ensure_index_schema(db)
    rows = db._execute(
        "SELECT id, rel_path FROM wiki_history WHERE conversation_id = ?", (cid,)
    ).fetchall()
    if not rows:
        return 0
    ids = [int(r["id"]) for r in rows]
    for hid in ids:
        db._execute("DELETE FROM wiki_history_vectors WHERE history_id = ?", (hid,))
        if has_fts:
            db._execute("DELETE FROM wiki_history_fts WHERE rowid = ?", (hid,))
    db._execute("DELETE FROM wiki_history WHERE conversation_id = ?", (cid,))
    db._commit()

    if wiki is not None:
        gone = set(ids)
        for rel in {str(r["rel_path"] or "") for r in rows}:
            if not rel:
                continue
            path = wiki.user_root / rel
            if rel.startswith(EPISODE_DIR + "/"):
                # 에피소드 노트는 파일 하나가 기록 하나다.
                try:
                    path.unlink(missing_ok=True)
                except OSError:
                    pass
            else:
                _scrub_wiki_file(path, gone)
    return len(ids)


def _scrub_wiki_file(path, gone: set[int]) -> None:
    """일별 노트에서 지운 id의 `## …` 블록만 뺀다. 다른 대화의 블록은 그대로."""
    try:
        if not path.is_file():
            return
        text = path.read_text(encoding="utf-8")
    except OSError:
        return
    blocks = _WIKI_BLOCK_RE.split(text)
    kept: list[str] = []
    dropped = False
    for block in blocks:
        m = _WIKI_ID_RE.search(block)
        if m and int(m.group(1)) in gone:
            dropped = True
            continue
        kept.append(block)
    if not dropped:
        return
    try:
        path.write_text("".join(kept), encoding="utf-8")
    except OSError:
        pass


def format_hits_for_prompt(hits: list[SearchHit], *, body_limit: int = 700) -> str:
    """검색 결과 → 모델에 넣을 근거 블록."""
    if not hits:
        return ""
    lines = ["# 아이리스 위키 History 발췌", ""]
    for hit in hits:
        entry = hit.entry
        lines.append(f"## {entry.as_context_line()}  ({hit.matched_by})")
        if entry.source:
            lines.append(f"- 출처: {entry.source}")
        if entry.model:
            lines.append(f"- 당시 모델: `{entry.model}`")
        body = entry.body.strip()
        if len(body) > body_limit:
            body = body[:body_limit] + " …(생략)"
        lines.extend(["", body, ""])
    return "\n".join(lines)


if __name__ == "__main__":
    import tempfile
    from pathlib import Path

    from iris.knowledge.history_store import (
        KIND_ACTION,
        KIND_INPUT,
        record_entry,
        record_turn,
    )

    assert chunk_text("") == []
    assert chunk_text("짧다") == ["짧다"]
    big = chunk_text("가" * 3000)
    assert len(big) > 1 and all(len(c) <= _CHUNK_CHARS for c in big)

    assert build_fts_query("설치 프로그램") == '"프로그램"'  # '설치'는 2글자라 빠짐
    assert build_fts_query("가 나") == ""
    assert build_fts_query('"; DROP TABLE x --') == '"DROP" OR "TABLE"'
    assert build_fts_query("") == ""

    class _FakeEmbedder:
        """단어 겹침을 코사인처럼 흉내내는 결정적 임베더."""

        model = "fake-embed"

        _VOCAB = ("설치", "프로그램", "권한", "일정", "회의", "커피")

        def embed(self, texts: list[str]) -> list[list[float]]:
            out = []
            for t in texts:
                out.append([1.0 if w in t else 0.0 for w in self._VOCAB])
            return out

    with tempfile.TemporaryDirectory() as tmp:
        db = Database(Path(tmp) / "t.db")
        assert ensure_index_schema(db) is True

        e1 = record_turn(db, 1, "user", "설치 프로그램이 권한 때문에 죽습니다")
        e2 = record_turn(db, 1, "assistant", "venv 폴더 권한을 고치면 됩니다")
        e3 = record_entry(db, kind=KIND_ACTION, body="내일 회의 일정을 캘린더에 넣었다", conversation_id=2)
        e4 = record_entry(db, kind=KIND_INPUT, body="커피 원두 주문 내역 PDF", conversation_id=2)
        for e in (e1, e2, e3, e4):
            assert e is not None
            index_entry(db, e)

        # 키워드만 — 임베더 없이도 동작
        hits = search(db, "프로그램")
        assert hits and hits[0].entry.id == e1.id
        assert hits[0].matched_by == "키워드"

        # 2글자 질의는 trigram이 못 받지만 LIKE 보충이 잡는다
        short = search(db, "회의")
        assert [h.entry.id for h in short] == [e3.id], short

        # 조사가 달라 substring이 어긋나도(`권한을` vs `권한`) 보충 검색이 잡는다
        assert like_terms("설치 권한 오류가") == ["설치", "권한", "오류가"]
        assert like_terms("가 나 다") == []
        assert like_variants("권한을") == ["권한"]
        assert like_variants("고치는") == ["고치"]
        assert like_variants("가나") == []
        assert like_variants("installer") == []  # 영문은 자르지 않는다
        inflected = search(db, "권한을 고치는 법")
        assert {h.entry.id for h in inflected} >= {e1.id, e2.id}, inflected
        # 본딧말이 정확히 맞은 쪽이 축약형만 맞은 쪽보다 위에 온다
        assert inflected[0].entry.id == e2.id, inflected

        # LIKE 와일드카드가 사용자 입력으로 들어와도 전체 일치가 되면 안 된다
        assert _escape_like("100%_x") == "100\\%\\_x"
        assert search(db, "%%%") == []

        # 임베딩 붙이면 의미 검색이 더해진다
        emb = _FakeEmbedder()
        for e in (e1, e2, e3, e4):
            assert embed_entry(db, e, emb) >= 1
        assert unembedded_ids(db, "fake-embed") == []
        assert len(unembedded_ids(db, "다른모델")) == 4

        hybrid = search(db, "설치 권한 문제", embedder=emb)
        assert hybrid and hybrid[0].entry.id == e1.id
        assert hybrid[0].vector_rank is not None

        # 필터
        only2 = search(db, "일정", embedder=emb, conversation_id=2)
        assert all(h.entry.conversation_id == 2 for h in only2)
        assert search(db, "일정", kinds=(KIND_INPUT,), embedder=emb) == [] or all(
            h.entry.kind == KIND_INPUT for h in search(db, "일정", kinds=(KIND_INPUT,), embedder=emb)
        )
        assert search(db, "") == []

        # 임베더가 터져도 키워드 결과는 살아있어야 한다
        class _Broken:
            model = "broken"

            def embed(self, texts):
                raise RuntimeError("Ollama 연결 실패")

        assert embed_entry(db, e1, _Broken()) == 0
        survived = search(db, "프로그램", embedder=_Broken())
        assert survived and survived[0].entry.id == e1.id

        block = format_hits_for_prompt(search(db, "프로그램"))
        assert "History 발췌" in block and "설치 프로그램" in block
        assert format_hits_for_prompt([]) == ""

        assert reindex_all(db, embedder=emb) == 4
        db.close()

    print("history_index self-check ok")
