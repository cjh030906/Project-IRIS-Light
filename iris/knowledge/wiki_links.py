"""위키링크 [[노트]] 해석. 그래프가 폴더 선만 그리지 않게 한다."""

from __future__ import annotations

import re

_WIKI_LINK = re.compile(r"\[\[([^\]\n]+)\]\]")


def parse_wiki_links(text: str) -> list[str]:
    """[[대상]], [[대상|보이는 이름]], [[대상#절]] 에서 대상만."""
    found: list[str] = []
    for match in _WIKI_LINK.finditer(text or ""):
        raw = match.group(1).strip()
        raw = raw.split("|", 1)[0]
        raw = raw.split("#", 1)[0].strip()
        if raw:
            found.append(raw)
    return found


def _norm(value: str) -> str:
    return (value or "").strip().casefold()


def extend_link_index(link_to_idx: dict[str, int], notes: list) -> dict[str, int]:
    """_add_cluster 가 제목으로 만든 인덱스에 경로·파일명을 보탠다."""
    extra = dict(link_to_idx)
    for note in notes:
        idx = extra.get(getattr(note, "title", ""))
        if idx is None:
            continue
        rel = str(getattr(note, "rel_path", "") or "")
        extra.setdefault(rel, idx)
        name = rel.rsplit("/", 1)[-1]
        stem = name[:-3] if name.lower().endswith(".md") else name
        extra.setdefault(name, idx)
        extra.setdefault(stem, idx)
    return extra


def link_edges_from_index(
    link_to_idx: dict[str, int],
    notes: list,
    bodies: dict[str, str],
) -> list[tuple[int, int]]:
    """노트 본문의 [[대상]] 을 인덱스에 있는 노드로 잇는다."""
    folded: dict[str, int] = {}
    for key, idx in link_to_idx.items():
        folded.setdefault(_norm(str(key)), idx)
    edges: list[tuple[int, int]] = []
    seen: set[tuple[int, int]] = set()
    for note in notes:
        rel = str(getattr(note, "rel_path", "") or "")
        title = str(getattr(note, "title", "") or "")
        src = folded.get(_norm(title))
        if src is None:
            src = folded.get(_norm(rel))
        if src is None:
            continue
        for target in parse_wiki_links(bodies.get(rel, "")):
            dst = folded.get(_norm(target))
            if dst is None or dst == src:
                continue
            pair = (src, dst)
            if pair in seen:
                continue
            seen.add(pair)
            edges.append(pair)
    return edges
