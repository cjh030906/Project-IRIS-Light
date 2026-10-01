"""노트 한 건을 폴더에 배정한다.

점수는 임베딩 코사인이다. 본문 단어 목록으로 폴더를 고르지 않는다.
임베딩이 없거나 새 분야 이름이 필요할 때만 모델 JSON을 쓴다.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Callable

import numpy as np

from iris.knowledge.history_index import Embedder
from iris.knowledge.wiki_note_index import (
    _unit,
    load_folder_vectors,
    load_proto_vector,
    store_proto_vector,
)
from iris.knowledge.wiki_places import (
    PLACE_FLOOR,
    PLACE_MARGIN,
    PLACES,
    PLACES_BY_ID,
    Place,
    clean_field_name,
    project_prototype,
)
from iris.storage.database import Database

Namer = Callable[[str], str]

CLASSIFY_SYSTEM = (
    "Iris Wiki 분류기다. JSON 객체 하나만 출력한다. 설명 문장은 쓰지 않는다."
)


@dataclass(frozen=True)
class Decision:
    folder: str
    place_id: str
    ask_folder: bool


def note_embed_text(title: str, body: str) -> str:
    text = (body or "").strip()
    if len(text) > 4000:
        text = text[:4000]
    return f"{(title or '').strip()}\n{text}".strip()


def parse_model_json(text: str) -> dict:
    raw = text or ""
    start = raw.find("{")
    end = raw.rfind("}")
    if start < 0 or end <= start:
        return {}
    try:
        data = json.loads(raw[start : end + 1])
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def _cosine(left: np.ndarray, right: np.ndarray) -> float:
    if left.size == 0 or left.size != right.size:
        return -1.0
    return float(np.dot(left, right))


def _best(scored: list[tuple[str, float]]) -> str:
    """바닥 이상인 1위. 2위와 차가 좁으면 빈 문자열."""
    ranked = sorted(scored, key=lambda item: item[1], reverse=True)
    above = [item for item in ranked if item[1] >= PLACE_FLOOR]
    if not above:
        return ""
    if len(above) >= 2 and above[0][1] - above[1][1] < PLACE_MARGIN:
        return ""
    return above[0][0]


def _proto_text(place: Place, slug: str) -> str:
    if place.needs_project:
        return project_prototype(slug)
    return place.prototype


def _proto_key(place: Place, slug: str) -> str:
    if place.needs_project:
        return f"project:{slug}"
    return place.id


def _vectors_for(db, embedder: Embedder, items: list[tuple[str, str]]) -> dict[str, np.ndarray]:
    out: dict[str, np.ndarray] = {}
    missing: list[tuple[str, str]] = []
    for key, text in items:
        cached = load_proto_vector(db, embedder.model, key) if db is not None else None
        if cached is None:
            missing.append((key, text))
        else:
            out[key] = cached
    if not missing:
        return out
    try:
        raw = embedder.embed([text for _key, text in missing])
    except Exception:
        return out
    if len(raw) != len(missing):
        return out
    for (key, _text), vec in zip(missing, raw):
        arr = _unit(vec)
        if arr.size == 0:
            continue
        out[key] = arr
        if db is not None:
            store_proto_vector(db, embedder.model, key, arr)
    return out


def _child_scores(parent: str, note_vec, folder_vectors) -> list[tuple[str, float]]:
    prefix = parent + "/"
    grouped: dict[str, list] = {}
    for folder, vectors in folder_vectors.items():
        if not str(folder).startswith(prefix):
            continue
        top = str(folder)[len(prefix) :].split("/", 1)[0]
        if top:
            grouped.setdefault(prefix + top, []).extend(vectors)
    scored = []
    for folder, vectors in grouped.items():
        best = max((_cosine(note_vec, vec) for vec in vectors), default=-1.0)
        scored.append((folder, best))
    return scored


def _folder_boost(place: Place, note_vec, folder_vectors) -> float:
    best = -1.0
    for folder, vectors in folder_vectors.items():
        if folder != place.folder and not str(folder).startswith(place.folder + "/"):
            continue
        for vec in vectors:
            best = max(best, _cosine(note_vec, vec))
    return best


def _ask(namer: Namer | None, prompt: str) -> dict:
    if namer is None:
        return {}
    try:
        return parse_model_json(namer(prompt))
    except Exception:
        return {}


def _active_places(slug: str) -> list[Place]:
    return [place for place in PLACES if not place.needs_project or slug]


def _from_model(namer, title: str, body: str, places: list[Place], slug: str) -> Decision:
    lines = [
        "노트가 들어갈 place id 하나를 JSON으로 답하라.",
        '{"place":"<id>","field":""}',
        "field 는 study, insight, research 일 때만 짧은 분야 이름이다.",
    ]
    for place in places:
        lines.append(f"- {place.id}: {place.prototype}")
    snippet = (body or "").strip()[:1500]
    lines.append(f"제목: {title}\n본문:\n{snippet}")
    data = _ask(namer, "\n".join(lines))
    place = PLACES_BY_ID.get(str(data.get("place") or "").strip())
    if place is None or place not in places:
        return Decision("inbox", "", True)
    if place.needs_project:
        if not slug:
            return Decision("inbox", "", True)
        return Decision(f"projects/{slug}", place.id, False)
    if place.dynamic:
        field = clean_field_name(str(data.get("field") or ""))
        folder = f"{place.folder}/{field}" if field else place.folder
        return Decision(folder, place.id, False)
    return Decision(place.folder, place.id, False)


def classify_note(
    title: str,
    body: str,
    *,
    db: Database | None = None,
    embedder: Embedder | None = None,
    namer: Namer | None = None,
    project_slug: str = "",
) -> Decision:
    slug = (project_slug or "").strip()
    places = _active_places(slug)
    if embedder is None:
        return _from_model(namer, title, body, places, slug)
    try:
        raw_note = embedder.embed([note_embed_text(title, body)])
    except Exception:
        return _from_model(namer, title, body, places, slug)
    if not raw_note:
        return _from_model(namer, title, body, places, slug)
    note_vec = _unit(raw_note[0])
    if note_vec.size == 0:
        return _from_model(namer, title, body, places, slug)

    items = [(_proto_key(place, slug), _proto_text(place, slug)) for place in places]
    prototypes = _vectors_for(db, embedder, items)
    if len(prototypes) < len(places):
        return _from_model(namer, title, body, places, slug)
    folder_vectors = load_folder_vectors(db, embedder.model) if db is not None else {}
    scored = []
    for place in places:
        proto = prototypes.get(_proto_key(place, slug))
        if proto is None:
            continue
        score = max(_cosine(note_vec, proto), _folder_boost(place, note_vec, folder_vectors))
        scored.append((place.id, score))
    winner_id = _best(scored)
    if not winner_id:
        return Decision("inbox", "", True)
    winner = PLACES_BY_ID[winner_id]
    if winner.needs_project:
        return Decision(f"projects/{slug}", winner.id, False)
    if not winner.dynamic:
        return Decision(winner.folder, winner.id, False)
    child = _best(_child_scores(winner.folder, note_vec, folder_vectors))
    if child:
        return Decision(child, winner.id, False)
    snippet = (body or "").strip()[:1500]
    prompt = (
        "부모 폴더는 이미 정해졌다. 분야 폴더 이름만 JSON으로 답하라.\n"
        '{"field":"짧은 이름"}\n'
        f"부모: {winner.label} ({winner.folder})\n제목: {title}\n본문:\n{snippet}"
    )
    field = clean_field_name(str(_ask(namer, prompt).get("field") or ""))
    folder = f"{winner.folder}/{field}" if field else winner.folder
    return Decision(folder, winner.id, False)
