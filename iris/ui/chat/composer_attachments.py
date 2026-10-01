"""Composer 파일 첨부 칩 스트립 — Cursor식 이름 + 아이콘."""

from __future__ import annotations

import os
from pathlib import Path

from PyQt6.QtCore import QFileInfo, Qt, pyqtSignal
from PyQt6.QtGui import QPixmap
from PyQt6.QtWidgets import (
    QFileIconProvider,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

_ICON_PROVIDER = QFileIconProvider()
_ICON_PX = 16


def at_ref_path(raw: str) -> str:
    """@참조에서 경로만. `C:` 드라이브 콜론은 자르지 않고 `:줄:칸`만 분리한다."""
    body = (raw or "").strip()
    if body.startswith("@"):
        body = body[1:].strip()
    from iris.ui.chat.chat_blocks import parse_file_chip_location

    path, _line, _col = parse_file_chip_location(body)
    return path or body


def format_byte_size(n: int) -> str:
    size = max(0, int(n))
    if size < 1024:
        return f"{size} B"
    if size < 1024 * 1024:
        return f"{size / 1024:.1f} KB"
    return f"{size / (1024 * 1024):.1f} MB"


def chip_fs_path(path: str, *, workspace_root: str = "") -> Path | None:
    """칩이 가리키는 로컬 경로. 없으면 None."""
    raw = (path or "").strip()
    if not raw:
        return None
    if raw.startswith("@"):
        rel = at_ref_path(raw)
        ws = (workspace_root or "").strip()
        candidate = Path(rel)
        if ws and not candidate.is_absolute():
            candidate = Path(ws).expanduser() / rel.replace("/", os.sep)
        try:
            if candidate.exists():
                return candidate.resolve()
        except OSError:
            return None
        return candidate if candidate.suffix or candidate.name else None
    try:
        return Path(raw).expanduser()
    except OSError:
        return None


def composer_chip_kind(path: str, *, workspace_root: str = "") -> str:
    """확장자 대문자, 폴더, 또는 파일."""
    fs = chip_fs_path(path, workspace_root=workspace_root)
    if fs is not None:
        try:
            if fs.is_dir():
                return "폴더"
        except OSError:
            pass
        suffix = fs.suffix
    else:
        suffix = Path(at_ref_path(path) if (path or "").startswith("@") else path).suffix
    ext = suffix.lower().lstrip(".")
    return ext.upper() if ext else "파일"


def composer_chip_meta(path: str, *, workspace_root: str = "") -> str:
    """칩 보조 줄 — 형식, 파일이면 크기."""
    kind = composer_chip_kind(path, workspace_root=workspace_root)
    if kind == "폴더":
        return kind
    fs = chip_fs_path(path, workspace_root=workspace_root)
    if fs is None:
        return kind
    try:
        if fs.is_file():
            return f"{kind} · {format_byte_size(fs.stat().st_size)}"
    except OSError:
        pass
    return kind


def normalize_paths(paths: list[str]) -> list[str]:
    """파일 선택·드롭 공통. 존재하는 경로는 절대경로로, 파일명은 바꾸지 않는다."""
    out: list[str] = []
    for raw in paths:
        item = str(raw).strip().strip('"')
        if not item:
            continue
        if item.startswith("@"):
            token = item.split()[0]
            if token:
                out.append(token)
            continue
        try:
            path = Path(item).expanduser()
            if path.exists():
                path = path.resolve()
            out.append(str(path))
        except OSError:
            out.append(item)
    return out


def validate_files(paths: list[str]) -> tuple[list[str], list[str]]:
    """normalize 후 실제 파일만 통과. 반환은 (ok, errors)."""
    return partition_attachment_paths(normalize_paths(paths))


def partition_attachment_paths(paths: list[str]) -> tuple[list[str], list[str]]:
    """파일 선택과 동일한 규칙 — 있는 로컬 경로와 @참조만 첨부.

    선택 대화상자는 존재하는 파일만 돌려준다. 용량·확장자 상한은 없다.
    """
    ok: list[str] = []
    errors: list[str] = []
    for raw in paths:
        item = str(raw).strip()
        if not item:
            continue
        if item.startswith("@"):
            token = item.split()[0]
            if token:
                ok.append(token)
            continue
        try:
            exists = Path(item).expanduser().exists()
        except OSError:
            exists = False
        if not exists:
            name = Path(item).name or item
            errors.append(f"파일을 찾을 수 없습니다: {name}")
            continue
        ok.append(item)
    return ok, errors


def attachment_filename(path: str) -> str:
    """칩·메시지에 쓰는 원본 파일명. 드라이브 콜론으로 자르지 않는다."""
    raw = (path or "").strip()
    if not raw:
        return ""
    target = at_ref_path(raw) if raw.startswith("@") else raw
    name = Path(target).name
    return name or target


def composer_chip_label(path: str) -> str:
    """칩 표시명 — @ref는 basename, 로컬 경로는 파일/폴더명."""
    return attachment_filename(path)


def composer_chip_icon(path: str, *, workspace_root: str = "") -> QPixmap:
    """칩 아이콘 — OS 파일 아이콘(QFileIconProvider)."""
    raw = (path or "").strip()
    fs_path = raw
    if raw.startswith("@"):
        rel = at_ref_path(raw)
        ws = (workspace_root or "").strip()
        if ws:
            candidate = Path(ws).expanduser() / rel.replace("/", os.sep)
            if candidate.exists():
                fs_path = str(candidate.resolve())
            else:
                ext = Path(rel).suffix
                if not ext:
                    icon = _ICON_PROVIDER.icon(QFileIconProvider.IconType.Folder)
                else:
                    icon = _ICON_PROVIDER.icon(QFileIconProvider.IconType.File)
                return icon.pixmap(_ICON_PX, _ICON_PX)
    p = Path(fs_path)
    if p.is_dir():
        icon = _ICON_PROVIDER.icon(QFileIconProvider.IconType.Folder)
    elif p.is_file():
        icon = _ICON_PROVIDER.icon(QFileInfo(str(p.resolve())))
    else:
        icon = _ICON_PROVIDER.icon(QFileIconProvider.IconType.File)
    return icon.pixmap(_ICON_PX, _ICON_PX)


class ComposerAttachmentStrip(QWidget):
    changed = pyqtSignal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("ComposerAttachmentStrip")
        self._paths: list[str] = []
        self._workspace_root = ""
        self._row = QHBoxLayout(self)
        self._row.setContentsMargins(8, 0, 8, 4)
        self._row.setSpacing(6)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.hide()

    def set_workspace_root(self, root: str) -> None:
        self._workspace_root = (root or "").strip()
        if self._paths:
            self._rebuild()

    def paths(self) -> list[str]:
        return list(self._paths)

    def add_paths(self, paths: list[str]) -> None:
        for raw in paths:
            p = str(raw).strip()
            if not p:
                continue
            token = p.split()[0] if p.startswith("@") else p
            if token in self._paths:
                continue
            self._paths.append(token)
        self._rebuild()

    def take_paths(self) -> list[str]:
        out = list(self._paths)
        self._paths.clear()
        self._rebuild()
        return out

    def clear_paths(self) -> None:
        self._paths.clear()
        self._rebuild()

    def _rebuild(self) -> None:
        while self._row.count():
            item = self._row.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        if not self._paths:
            self.hide()
            self.changed.emit()
            return
        for path in self._paths:
            self._row.addWidget(self._make_chip(path))
        self._row.addStretch(1)
        self.show()
        self.changed.emit()

    def _make_chip(self, path: str) -> QWidget:
        wrap = QWidget()
        wrap.setObjectName("ComposerAttachmentChip")
        lay = QHBoxLayout(wrap)
        lay.setContentsMargins(6, 2, 4, 2)
        lay.setSpacing(4)

        icon_label = QLabel()
        icon_label.setFixedSize(_ICON_PX, _ICON_PX)
        icon_label.setPixmap(
            composer_chip_icon(path, workspace_root=self._workspace_root)
        )
        icon_label.setScaledContents(True)

        name = composer_chip_label(path)
        label = QLabel(name)
        label.setToolTip(path)
        label.setStyleSheet("color: #e2e8f0; font-size: 11px; background: transparent; border: none;")

        meta = QLabel(composer_chip_meta(path, workspace_root=self._workspace_root))
        meta.setObjectName("ComposerAttachmentMeta")
        meta.setStyleSheet("color: #94a3b8; font-size: 10px; background: transparent; border: none;")

        text_col = QVBoxLayout()
        text_col.setContentsMargins(0, 0, 0, 0)
        text_col.setSpacing(0)
        text_col.addWidget(label)
        text_col.addWidget(meta)

        btn = QPushButton("×")
        btn.setFixedSize(18, 18)
        btn.setFlat(True)
        btn.setToolTip("첨부 취소")
        btn.setStyleSheet("color: #94a3b8; border: none; background: transparent;")
        btn.clicked.connect(lambda _=False, p=path: self._remove(p))

        lay.addWidget(icon_label, 0, Qt.AlignmentFlag.AlignVCenter)
        lay.addLayout(text_col)
        lay.addWidget(btn, 0, Qt.AlignmentFlag.AlignVCenter)
        wrap.setStyleSheet(
            """
            QWidget#ComposerAttachmentChip {
                background: rgba(56, 189, 248, 0.12);
                border: 1px solid rgba(56, 189, 248, 0.28);
                border-radius: 10px;
            }
            """
        )
        return wrap

    def _remove(self, path: str) -> None:
        self._paths = [p for p in self._paths if p != path]
        self._rebuild()
