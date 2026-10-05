"""이미 있는 사용자 노트를 같은 바이트로 옮긴다.

모델이 본문을 다시 쓰지 않는다. 폴더 이름은 호출자가 넘긴 문자열이다.
"""

from __future__ import annotations

from pathlib import Path

from iris.knowledge.iris_wiki import USER_PREFIX, IrisWiki


def clean_dest_folder(raw: str) -> str:
    """슬러그로 바꾸지 않는다. 빈 칸·`..`·파일명만 거부한다."""
    rel = _user_rel(raw)
    if rel.endswith(".md"):
        raise ValueError("dest_folder is a folder, not a file")
    return rel


def move_user_bytes(wiki: IrisWiki, sources: list[str], dest_folder: str) -> dict:
    """복사 검증이 끝난 뒤에만 원본을 지운다."""
    dest_rel = clean_dest_folder(dest_folder)
    root = wiki.user_root.resolve()
    dest_root = (root / dest_rel).resolve()
    if root != dest_root and root not in dest_root.parents:
        raise ValueError("invalid dest_folder")
    pairs: list[tuple[Path, Path, bool]] = []
    folders = False
    for raw in sources:
        rel = _user_rel(raw)
        src_path, files, is_dir = _files(root, rel)
        if is_dir and (dest_root == src_path or _is_inside(dest_root, src_path)):
            raise ValueError("dest is inside source")
        folders = folders or is_dir
        for src in files:
            if is_dir:
                rel_under = src.relative_to(src_path.parent)
            else:
                rel_under = Path(src.name)
            pairs.append((src, dest_root / rel_under, is_dir))
    if not pairs:
        raise ValueError("sources required")
    staged: list[tuple[Path, Path, bytes]] = []
    for src, dest, _is_dir in pairs:
        data = src.read_bytes()
        if dest.exists() and dest.resolve() != src.resolve() and dest.read_bytes() != data:
            raise ValueError(f"dest exists with different bytes: {dest}")
        dest.parent.mkdir(parents=True, exist_ok=True)
        if dest.resolve() != src.resolve():
            dest.write_bytes(data)
        staged.append((src, dest, data))
    for _src, dest, data in staged:
        if dest.read_bytes() != data:
            raise ValueError("byte mismatch")
    moved: list[dict] = []
    for src, dest, data in staged:
        if src.resolve() != dest.resolve() and src.is_file():
            src.unlink()
            _prune_empty(src.parent, root)
        moved.append(
            {
                "from": _display(root, src),
                "to": _display(root, dest),
                "bytes": len(data),
            }
        )
    left = [row["from"] for row in moved if (root / row["from"].removeprefix(USER_PREFIX)).is_file() and row["from"] != row["to"]]
    return {
        "moved": moved,
        "count": len(moved),
        "dest_folder": f"{USER_PREFIX}{dest_rel}",
        "left": left,
        "folders": folders,
    }


def _user_rel(raw: str) -> str:
    rel = (raw or "").strip().replace("\\", "/").lstrip("/")
    if rel.startswith(USER_PREFIX):
        rel = rel[len(USER_PREFIX) :]
    if not rel or rel == "docs" or rel.startswith("docs/"):
        raise ValueError("user notes only")
    parts = [part for part in rel.split("/") if part and part != "."]
    if not parts or any(part == ".." for part in parts):
        raise ValueError("invalid path")
    return "/".join(parts)


def _files(root: Path, rel: str) -> tuple[Path, list[Path], bool]:
    path = (root / rel).resolve()
    if root != path and root not in path.parents:
        raise ValueError("invalid path")
    if path.is_file():
        return path, [path], False
    if path.is_dir():
        files = sorted(
            item
            for item in path.rglob("*.md")
            if item.is_file() and not item.name.startswith(".")
        )
        if not files:
            raise ValueError(f"no notes in {rel}")
        return path, files, True
    raise FileNotFoundError(rel)


def _is_inside(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
    except ValueError:
        return False
    return True


def _display(root: Path, path: Path) -> str:
    try:
        rel = path.resolve().relative_to(root).as_posix()
    except ValueError:
        rel = path.as_posix()
    return f"{USER_PREFIX}{rel}"


def _prune_empty(start: Path, stop: Path) -> None:
    cur = start
    while cur.resolve() != stop.resolve() and cur != cur.parent:
        try:
            cur.rmdir()
        except OSError:
            break
        cur = cur.parent


def _check() -> None:
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        wiki = IrisWiki(docs_root=Path(tmp) / "docs", user_root=Path(tmp) / "wiki")
        chapter = wiki.user_root / "inbox" / "chapter-11"
        chapter.mkdir(parents=True)
        body = b"# DeZero\r\n\r\nsame-bytes\n"
        (chapter / "a.md").write_bytes(body)
        lone = wiki.user_root / "inbox" / "b.md"
        lone.write_bytes(b"only-name\n")
        moved = move_user_bytes(wiki, ["inbox/chapter-11"], "학습자료/fine-tuning")
        dest = wiki.user_root / "학습자료" / "fine-tuning" / "chapter-11" / "a.md"
        assert dest.read_bytes() == body
        assert not (chapter / "a.md").exists()
        assert moved["count"] == 1 and moved["left"] == [] and moved["folders"] is True
        assert moved["dest_folder"] == "user/학습자료/fine-tuning"
        named = move_user_bytes(wiki, ["user/inbox/b.md"], "학습자료/강화학습")
        assert (wiki.user_root / "학습자료" / "강화학습" / "b.md").read_bytes() == b"only-name\n"
        assert not lone.exists()
        assert named["folders"] is False
        try:
            move_user_bytes(wiki, ["../secret.md"], "학습자료")
            raise AssertionError(".. should fail")
        except ValueError:
            pass
        kept = wiki.user_root / "inbox" / "keep.md"
        kept.parent.mkdir(parents=True, exist_ok=True)
        kept.write_bytes(b"keep\n")
        (wiki.user_root / "학습자료" / "강화학습" / "keep.md").write_bytes(b"other\n")
        try:
            move_user_bytes(wiki, ["inbox/keep.md"], "학습자료/강화학습")
            raise AssertionError("different dest should fail")
        except ValueError:
            pass
        assert kept.read_bytes() == b"keep\n"
    print("wiki_move ok")


if __name__ == "__main__":
    _check()
