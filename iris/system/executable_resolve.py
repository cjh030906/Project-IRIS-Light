"""stdio 실행 파일을 CreateProcess가 띄울 수 있는 경로로 해석한다.

Windows CreateProcess는 PATHEXT를 적용하지 않는다. ``Popen(["npx", ...])`` 는
PATH에 ``npx.cmd``가 있어도 WinError 2가 난다. ``shell=True`` 는 쓰지 않는다.
"""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

_NODE_NAMES = frozenset({"node", "npm", "npx", "corepack"})
_WIN_SUFFIXES = (".cmd", ".exe", ".bat", ".com")
_NODE_DIR_TEMPLATES = (
    r"%ProgramFiles%\nodejs",
    r"%ProgramFiles(x86)%\nodejs",
    r"%LOCALAPPDATA%\Programs\nodejs",
    r"%APPDATA%\npm",
)


def _stem(command: str) -> str:
    name = Path(command).name.lower()
    for ext in _WIN_SUFFIXES:
        if name.endswith(ext):
            return name[: -len(ext)]
    return name


def node_install_dirs() -> list[Path]:
    """PATH에 없을 때도 찾을 Node 설치 디렉터리."""
    out: list[Path] = []
    seen: set[str] = set()
    for raw in _NODE_DIR_TEMPLATES:
        expanded = os.path.expandvars(os.path.expanduser(raw))
        if not expanded or ("%" in expanded):
            continue
        path = Path(expanded)
        if not path.is_dir():
            continue
        key = os.path.normcase(str(path.resolve()))
        if key in seen:
            continue
        seen.add(key)
        out.append(path)
    return out


def resolve_executable(command: str) -> str | None:
    """명령 이름을 실행 가능한 절대 경로로. 없으면 None.

    Windows: ``npx`` → ``npx.cmd`` (PATH, 그다음 Node 설치 경로).
    macOS/Linux: PATH의 ``shutil.which``.
    """
    raw = (command or "").strip().strip('"').strip("'")
    if not raw:
        return None
    direct = Path(raw)
    if direct.is_file():
        return str(direct.resolve())
    found = shutil.which(raw)
    if found and Path(found).is_file():
        return str(Path(found).resolve())
    stem = _stem(raw)
    if sys.platform == "win32":
        for ext in _WIN_SUFFIXES:
            hit = shutil.which(f"{stem}{ext}")
            if hit and Path(hit).is_file():
                return str(Path(hit).resolve())
        if stem in _NODE_NAMES:
            for directory in node_install_dirs():
                for ext in (".cmd", ".exe", ".bat"):
                    candidate = directory / f"{stem}{ext}"
                    if candidate.is_file():
                        return str(candidate.resolve())
    return None
