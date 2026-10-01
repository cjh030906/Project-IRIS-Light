"""위키 분류·색인·특성·링크 자검. 임베더는 스크립트 벡터다."""

from __future__ import annotations

import tempfile
from pathlib import Path

from iris.knowledge.iris_wiki import IrisWiki
from iris.knowledge.wiki_classify import note_embed_text
from iris.knowledge.wiki_filing import file_user_note
from iris.knowledge.wiki_links import parse_wiki_links
from iris.knowledge.wiki_note_index import search_notes
from iris.knowledge.wiki_places import PLACES, project_prototype
from iris.knowledge.wiki_session import merge_traits
from iris.storage.database import Database


def _axis(index: int, size: int = 12) -> list[float]:
    vector = [0.0] * size
    vector[index] = 1.0
    return vector


def _blend(left: int, right: int, size: int = 12) -> list[float]:
    vector = [0.0] * size
    vector[left] = 1.0
    vector[right] = 1.0
    return vector


class ScriptedEmbedder:
    """테스트용 임베더. 등록된 문장만 정해진 벡터를 준다."""

    model = "scripted"

    def __init__(self) -> None:
        self.exact: dict[str, list[float]] = {}
        self.fallback: list[float] | None = None

    def embed(self, texts: list[str]) -> list[list[float]]:
        out: list[list[float]] = []
        for text in texts:
            if text in self.exact:
                out.append(self.exact[text])
            elif self.fallback is not None:
                out.append(self.fallback)
            else:
                raise KeyError(text)
        return out


def _arm(embedder: ScriptedEmbedder, title: str, body: str, vector: list[float], slug: str = "") -> None:
    axes = {place.id: i for i, place in enumerate(PLACES)}
    for place in PLACES:
        if place.needs_project:
            if slug:
                embedder.exact[project_prototype(slug)] = _axis(axes[place.id])
            continue
        embedder.exact[place.prototype] = _axis(axes[place.id])
    embedder.exact[note_embed_text(title, body)] = vector
    embedder.fallback = vector


def _open(tmp: str):
    root = Path(tmp)
    wiki = IrisWiki(docs_root=root / "docs", user_root=root / "wiki")
    return wiki, Database(root / "t.db")


def check_hobby_without_folder_word() -> None:
    axes = {place.id: i for i, place in enumerate(PLACES)}
    title, body = "주말 메모", "주말에는 기타를 친다. 밴드 연습이 좋다."
    assert "취미" not in title + body
    embedder = ScriptedEmbedder()
    _arm(embedder, title, body, _axis(axes["user.hobbies"]))
    with tempfile.TemporaryDirectory() as tmp:
        wiki, db = _open(tmp)
        filed = file_user_note(wiki, title, body, db=db, embedder=embedder, classify=True)
        assert filed["rel_path"].startswith("user/사용자/취미/"), filed
        assert filed["ask_folder"] is False
        db.close()


def check_ambiguous_stays_inbox() -> None:
    axes = {place.id: i for i, place in enumerate(PLACES)}
    title, body = "메모", "그냥 적어두기"
    embedder = ScriptedEmbedder()
    _arm(embedder, title, body, _blend(axes["user.hobbies"], axes["study"]))
    with tempfile.TemporaryDirectory() as tmp:
        wiki, db = _open(tmp)
        filed = file_user_note(wiki, title, body, db=db, embedder=embedder, classify=True)
        assert "/inbox/" in filed["rel_path"], filed
        assert filed["ask_folder"] is True
        db.close()


def check_study_field_then_neighbor() -> None:
    axes = {place.id: i for i, place in enumerate(PLACES)}
    calls: list[str] = []

    def namer(prompt: str) -> str:
        calls.append(prompt)
        return '{"field":"선형대수"}'

    first = ("고유값", "행렬의 고유값과 고유벡터를 정리한다.")
    second = ("행렬식", "행렬식은 선형변환의 부피 배율이다.")
    assert "학습" not in first[0] + first[1]
    with tempfile.TemporaryDirectory() as tmp:
        wiki, db = _open(tmp)
        embedder = ScriptedEmbedder()
        _arm(embedder, *first, _axis(axes["study"]))
        filed = file_user_note(
            wiki, first[0], first[1], db=db, embedder=embedder, namer=namer, classify=True,
        )
        assert "/학습자료/선형대수/" in filed["rel_path"], filed
        assert len(calls) == 1
        embedder2 = ScriptedEmbedder()
        _arm(embedder2, *second, _axis(axes["study"]))
        again = file_user_note(
            wiki, second[0], second[1], db=db, embedder=embedder2, namer=namer, classify=True,
        )
        assert "/학습자료/선형대수/" in again["rel_path"], again
        assert len(calls) == 1, calls
        db.close()


def check_model_place_without_embedder() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        wiki, db = _open(tmp)
        filed = file_user_note(
            wiki, "선택", "약속은 지킨다.", db=db,
            namer=lambda _prompt: '{"place":"user.values","field":""}',
            classify=True,
        )
        assert filed["rel_path"].startswith("user/사용자/가치관/"), filed
        broken = file_user_note(
            wiki, "실패", "본문", db=db, namer=lambda _prompt: "not json", classify=True,
        )
        assert "/inbox/" in broken["rel_path"] and broken["ask_folder"] is True
        db.close()


def check_open_project_folder() -> None:
    axes = {place.id: i for i, place in enumerate(PLACES)}
    title, body = "이번 수정", "이 저장소에서 저장 경로를 바꿨다."
    embedder = ScriptedEmbedder()
    _arm(embedder, title, body, _axis(axes["project"]), slug="iris-light")
    with tempfile.TemporaryDirectory() as tmp:
        wiki, db = _open(tmp)
        filed = file_user_note(
            wiki, title, body, db=db, embedder=embedder,
            opened_slug="iris-light", classify=True,
        )
        assert filed["rel_path"].startswith("user/projects/iris-light/"), filed
        db.close()


def check_explicit_path() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        wiki, db = _open(tmp)
        filed = file_user_note(
            wiki, "직접", "본문", rel_path="인사이트/직접.md", db=db, classify=True,
        )
        assert filed["rel_path"] == "user/인사이트/직접.md", filed
        db.close()


def check_search_hides_secrets() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        wiki, db = _open(tmp)
        file_user_note(wiki, "삼각", "삼각함수의 덧셈 정리를 적는다.", db=db)
        file_user_note(wiki, "비밀", "api_key: sk-this-must-not-appear-in-search", db=db)
        hits = search_notes(db, "삼각함수")
        assert hits and "삼각함수" in hits[0].excerpt
        assert search_notes(db, "api_key") == []
        db.close()


def check_session_writes_traits() -> None:
    from iris.knowledge.wiki_session import close_session

    payload = (
        '{"title":"기타 연습","summary":"연습 시간을 정했다",'
        '"interests":"기타","level":"초보","improved":"연습 시간을 정함"}'
    )
    with tempfile.TemporaryDirectory() as tmp:
        wiki, db = _open(tmp)
        ok = close_session(
            db,
            wiki,
            conversation_id=3,
            messages=[
                {"role": "user", "content": "기타를 더 치고 싶어"},
                {"role": "assistant", "content": "매일 20분씩 연습하자"},
            ],
            summarize=lambda _prompt: payload,
            model="test",
        )
        text = (wiki.user_root / "profile" / "traits.md").read_text(encoding="utf-8")
        assert ok and "기타" in text and "[[기타 연습]]" in text
        assert "성격 점수" not in text.split("<!-- iris-traits -->", 1)[-1]
        assert list((wiki.user_root / "history" / "episodes").glob("*.md"))
        assert close_session(
            db, wiki, conversation_id=3, messages=[{"role": "user", "content": "한 마디"}],
            summarize=lambda _prompt: payload, model="test",
        ) is False
        db.close()


def check_traits_keep_preamble() -> None:
    merged = merge_traits("사용자가 직접 고친 문장.\n", "## s0\n\n- 관심사: 0")
    assert merged.startswith("사용자가 직접 고친 문장.")
    for index in range(1, 14):
        merged = merge_traits(merged, f"## s{index}\n\n- 관심사: {index}")
    body = merged.split("<!-- iris-traits -->", 1)[1]
    assert body.count("## ") == 12
    assert "\n## s1\n" not in body
    assert "\n## s13\n" in "\n" + body


def check_links_and_graph() -> None:
    assert parse_wiki_links("see [[가치관|별명]] and [[경로#절]]") == ["가치관", "경로"]
    from iris.knowledge.wiki_links import extend_link_index, link_edges_from_index

    class _Note:
        def __init__(self, rel: str, title: str) -> None:
            self.rel_path = rel
            self.title = title

    notes = [
        _Note("user/사용자/취미/기타.md", "기타"),
        _Note("user/사용자/가치관/삶.md", "가치관"),
    ]
    edges = link_edges_from_index(
        extend_link_index({"기타": 1, "가치관": 2}, notes),
        notes,
        {notes[0].rel_path: "[[가치관]] 과 연결", notes[1].rel_path: "지키는 것"},
    )
    assert edges == [(1, 2)], edges


def main() -> None:
    check_hobby_without_folder_word()
    check_ambiguous_stays_inbox()
    check_study_field_then_neighbor()
    check_model_place_without_embedder()
    check_open_project_folder()
    check_explicit_path()
    check_search_hides_secrets()
    check_traits_keep_preamble()
    check_session_writes_traits()
    check_links_and_graph()
    print("wiki filing self-check ok")


if __name__ == "__main__":
    main()
