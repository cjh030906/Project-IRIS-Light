"""위키에 노트를 둘 장소.

설명 문장은 임베딩이 비교하는 앵커다. 본문에 단어가 있는지로 폴더를 고르지 않는다.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from iris.knowledge.iris_wiki import slugify_note_name

# History 벡터와 같은 바닥. 이보다 낮으면 그 장소로 보지 않는다.
PLACE_FLOOR = 0.45
# 1위와 2위가 이 차보다 좁으면 애매한 것이다.
PLACE_MARGIN = 0.04

_SECRET_RE = re.compile(
    r"(?i)(?:api[_-]?key|secret|password|passwd|token)\s*[:=]\s*\S+"
    r"|sk-[A-Za-z0-9]{20,}"
    r"|\b\d{6}-\d{7}\b"
)


@dataclass(frozen=True)
class Place:
    id: str
    folder: str
    label: str
    prototype: str
    dynamic: bool = False
    needs_project: bool = False


PLACES: tuple[Place, ...] = (
    Place(
        "user.traits",
        "사용자/특징",
        "특징",
        "대화에서 드러난 그 사람의 성격, 특징, 습관, 말투, 성향. "
        "취미 목록이나 가치 선언이 아니라 사람 자체에 대한 관찰.",
    ),
    Place(
        "user.hobbies",
        "사용자/취미",
        "취미",
        "사용자가 즐기는 취미와 여가, 반복해서 하는 놀이.",
    ),
    Place(
        "user.strengths",
        "사용자/강점",
        "강점",
        "사용자가 잘하고 자신 있어 하는 능력과 강점.",
    ),
    Place(
        "user.weaknesses",
        "사용자/약점",
        "약점",
        "사용자가 어려워하거나 자주 막히는 약점.",
    ),
    Place(
        "user.thinking",
        "사용자/사고력",
        "사고력",
        "사용자의 사고 방식, 문제를 푸는 순서, 추론의 특징.",
    ),
    Place(
        "user.values",
        "사용자/가치관",
        "가치관",
        "사용자가 중요하게 여기는 가치, 신념, 선택 기준.",
    ),
    Place(
        "study",
        "학습자료",
        "학습자료",
        "공부 자료, 교재, 강의, 문제, 단원, 시험 정리, 어떤 과목을 배우는 내용.",
        dynamic=True,
    ),
    Place(
        "insight",
        "인사이트",
        "인사이트",
        "개발에 다시 쓰는 기술 개념, 언어, 라이브러리, 설계, 알고리즘, 도구 사용법. "
        "한 저장소에서만 통하는 일회성 결정이 아니다.",
        dynamic=True,
    ),
    Place(
        "research",
        "research",
        "연구",
        "연구 질문, 논문, 실험, 가설, 조사에서 남긴 연구 메모.",
        dynamic=True,
    ),
    Place(
        "project",
        "projects",
        "프로젝트",
        "지금 열려 있는 프로젝트에서 내린 구현 결정과 이번 작업의 결론.",
        needs_project=True,
    ),
)

PLACES_BY_ID: dict[str, Place] = {place.id: place for place in PLACES}

# 노트 색인이 보는 트리. history·learning·schedule·IRIS 는 빠진다.
KNOWLEDGE_PREFIXES: tuple[str, ...] = (
    "inbox/",
    "사용자/",
    "학습자료/",
    "인사이트/",
    "projects/",
    "research/",
    "아이리스 IDE/",
)
TRAITS_REL = "profile/traits.md"

KNOWLEDGE_FOLDERS: tuple[str, ...] = (
    "사용자/특징",
    "사용자/취미",
    "사용자/강점",
    "사용자/약점",
    "사용자/사고력",
    "사용자/가치관",
    "학습자료",
    "인사이트",
    "projects",
    "research",
)


def is_sensitive(text: str) -> bool:
    """프롬프트에 넣으면 안 되는 비밀 형태."""
    return _SECRET_RE.search(text or "") is not None


def is_knowledge_rel(rel: str) -> bool:
    path = (rel or "").replace("\\", "/").lstrip("/")
    if path == TRAITS_REL:
        return True
    return any(path.startswith(prefix) for prefix in KNOWLEDGE_PREFIXES)


def project_slug(root: str) -> str:
    name = Path(root or "").name.strip()
    if not name:
        return ""
    return slugify_note_name(name)


def project_prototype(slug: str) -> str:
    """열린 프로젝트 이름이 들어간 앵커. 슬러그가 바뀌면 문장도 바뀐다."""
    shown = (slug or "").strip() or "현재 프로젝트"
    return (
        f"지금 열려 있는 프로젝트 {shown} 에서 내린 구현 결정, "
        "왜 이렇게 고쳤는지, 이번 작업의 결론. "
        "다른 곳에서도 쓰는 기술 개념이 아니라 이 저장소의 기록."
    )


def clean_field_name(name: str) -> str:
    """모델이 준 분야 이름 → 폴더 한 단계. 경로 구분자는 허용하지 않는다."""
    raw = (name or "").strip().replace("\\", "/").strip("/")
    if not raw or ".." in raw.split("/"):
        return ""
    leaf = raw.split("/")[-1].strip()
    slug = slugify_note_name(leaf, max_len=24)
    if slug in {"note", "inbox", "학습자료", "인사이트", "사용자", "research", "projects"}:
        return ""
    return slug
