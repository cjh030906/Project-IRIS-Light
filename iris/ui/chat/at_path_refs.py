"""채팅 @경로 참조 — Cursor식 파일/폴더 IDE 이동."""

from __future__ import annotations

import re
import sys
from difflib import SequenceMatcher
from pathlib import Path

from iris.ui.chat.chat_blocks import parse_file_chip_location

# @mcp:foo 는 제외, @integrations/foo/bar.ts:12 형태 지원
_AT_PATH_RE = re.compile(
    r"(?<![\w/@])@((?:[A-Za-z]:[\\/])?[^\s@,;]+?)"
    r"(?=\s|$|[,;)}\]])"
)


def extract_at_path_refs(text: str) -> list[str]:
    """@로 시작하는 경로 참조 목록 (중복 제거, 순서 유지)."""
    seen: set[str] = set()
    out: list[str] = []
    for m in _AT_PATH_RE.finditer(text or ""):
        raw = (m.group(1) or "").strip().strip('"').strip("'")
        if not raw or raw.startswith("mcp:"):
            continue
        if raw not in seen:
            seen.add(raw)
            out.append(raw)
    return out


def _looks_like_path(ref: str) -> bool:
    if "/" in ref or "\\" in ref:
        return True
    if re.match(r"^[A-Za-z]:", ref):
        return True
    return "." in ref and not ref.startswith(".")


def normalize_at_path(ref: str) -> str:
    """드라이브 문자 뒤에 구분자가 없으면 넣는다. c:\\ 와 c:/ 와 mcp: 는 유지."""
    raw = (ref or "").strip().strip('"').strip("'")
    if not raw or raw.lower().startswith("mcp:"):
        return raw
    if sys.platform != "win32":
        return raw
    matched = re.match(r"^([A-Za-z]):(?![\\/])(.*)$", raw)
    if not matched:
        return raw
    rest = matched.group(2).replace("/", "\\")
    return f"{matched.group(1)}:\\{rest}"


def _name_score(query: str, name: str) -> float:
    q = (query or "").casefold()
    n = (name or "").casefold()
    if not q or not n:
        return 0.0
    if q == n:
        return 1.0
    if n.startswith(q) or q.startswith(n) or q in n or n in q:
        return 0.85
    ratio = SequenceMatcher(None, q, n).ratio()
    return ratio if ratio >= 0.72 else 0.0


def _similar_dirs(missing: str, search_roots: list[str], limit: int = 5) -> list[str]:
    """ponytail: 검색 루트 바로 아래 폴더만. 더 깊으면 os.walk 로 바꾸면 된다."""
    query = Path(missing).name
    scored: list[tuple[float, str]] = []
    seen: set[str] = set()
    for raw in search_roots:
        root = Path(raw)
        if not root.is_dir():
            continue
        names = [(root.name, root)]
        try:
            children = list(root.iterdir())
        except OSError:
            children = []
        for child in children:
            try:
                if child.is_dir():
                    names.append((child.name, child))
            except OSError:
                continue
        for name, folder in names:
            score = _name_score(query, name)
            if score <= 0:
                continue
            try:
                key = str(folder.resolve())
            except OSError:
                continue
            if key.casefold() in seen:
                continue
            seen.add(key.casefold())
            scored.append((score, key))
    scored.sort(key=lambda item: (-item[0], item[1].casefold()))
    return [path for _score, path in scored[:limit]]


def resolve_at_kind(
    ref: str,
    *,
    workspace_root: str = "",
    project_root: str = "",
    search_roots: list[str] | None = None,
) -> dict:
    """file | folder | missing. missing 은 쓰기 호출 없이 후보만 (최대 5)."""
    path_part, _, _ = parse_file_chip_location(ref)
    path_part = normalize_at_path((path_part or ref or "").strip())
    empty = {"kind": "missing", "path": "", "candidates": []}
    if not path_part or path_part.lower().startswith("mcp:") or not _looks_like_path(path_part):
        return empty
    candidates: list[Path] = []
    drive = bool(re.match(r"^[A-Za-z]:[\\/]", path_part))
    if drive or Path(path_part).is_absolute():
        candidates.append(Path(path_part))
    else:
        for base in (workspace_root, project_root):
            if base:
                candidates.append(Path(base).expanduser() / path_part)
    for cand in candidates:
        try:
            resolved = cand.expanduser().resolve()
        except OSError:
            continue
        if resolved.is_file():
            return {"kind": "file", "path": str(resolved), "candidates": []}
        if resolved.is_dir():
            return {"kind": "folder", "path": str(resolved), "candidates": []}
    return {
        "kind": "missing",
        "path": "",
        "candidates": _similar_dirs(path_part, list(search_roots or [])),
    }


def resolve_at_path(ref: str, *, workspace_root: str = "", project_root: str = "") -> str | None:
    """@참조를 절대 파일 경로로 해석. 폴더·없으면 None."""
    hit = resolve_at_kind(ref, workspace_root=workspace_root, project_root=project_root)
    if hit["kind"] == "file":
        return str(hit["path"])
    return None


def _self_check() -> None:
    refs = extract_at_path_refs("열어줘 @integrations/iris-ide/tsconfig.json 그리고 @mcp:foo")
    assert refs == ["integrations/iris-ide/tsconfig.json"]
    root = Path(__file__).resolve().parents[3]
    ws = str(root)
    resolved = resolve_at_path("integrations/iris-ide/tsconfig.json", workspace_root=ws)
    assert resolved and Path(resolved).is_file()
    p, ln, col = parse_file_chip_location("integrations/iris-ide/tsconfig.json:5:2")
    assert ln == 5 and col == 2
    print("at_path_refs ok", p)


if __name__ == "__main__":
    _self_check()
