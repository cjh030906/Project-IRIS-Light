"""MCP·Skill을 프로젝트에 둘지 아이리스 본체에 둘지."""

from __future__ import annotations

from pathlib import Path


def choose_extension_scope(ui_mode: str, project_root: str, asked: str) -> tuple[str, str]:
    """(scope, error). scope는 project 또는 iris. 오류면 scope는 빈 문자열."""
    mode = (ui_mode or "").strip()
    want = (asked or "").strip().lower()
    if want not in ("", "iris", "project"):
        want = ""
    in_ide = mode == "ide_companion"
    root = (project_root or "").strip()
    has_root = bool(root) and Path(root).expanduser().is_dir()
    if not want:
        want = "project" if in_ide else "iris"
    if want == "iris" and in_ide:
        return "", "아이리스 본체에 MCP·Skill을 붙이려면 IDE가 아닌 기본 화면에서 요청하세요."
    if want == "project":
        if not in_ide:
            return "", "프로젝트에 붙이려면 아이리스 IDE에서 그 프로젝트를 연 뒤 요청하세요."
        if not has_root:
            return "", "열린 프로젝트가 없습니다."
        return "project", ""
    return "iris", ""
