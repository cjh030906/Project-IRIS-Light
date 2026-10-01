"""패키지 __init__ 이 Agent-readable 네 키를 가지는지 확인한다."""

from __future__ import annotations

import ast
from pathlib import Path

KEYS = ("Owns:", "Does not:", "Talks to:", "Extend via:")


def missing_headers(iris_root: Path) -> list[str]:
    bad: list[str] = []
    for path in sorted(iris_root.rglob("__init__.py")):
        if "__pycache__" in path.parts:
            continue
        doc = ast.get_docstring(ast.parse(path.read_text(encoding="utf-8"))) or ""
        if any(key not in doc for key in KEYS):
            bad.append(str(path.relative_to(iris_root.parent)))
    return bad


def main() -> None:
    iris_root = Path(__file__).resolve().parents[1]
    bad = missing_headers(iris_root)
    if bad:
        print("agent-readable headers missing:")
        for name in bad:
            print(" ", name)
        raise SystemExit(1)
    count = sum(1 for p in iris_root.rglob("__init__.py") if "__pycache__" not in p.parts)
    print("agent-readable package headers ok", count)


if __name__ == "__main__":
    main()
