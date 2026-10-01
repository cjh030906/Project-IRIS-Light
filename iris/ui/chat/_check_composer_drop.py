"""Composer 드롭 @경로 변환 · 칩 self-check."""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

from PyQt6.QtCore import QEvent, QMimeData, QPoint, QPointF, Qt, QUrl
from PyQt6.QtGui import QDragEnterEvent, QDragLeaveEvent, QDropEvent, QMouseEvent
from PyQt6.QtWidgets import QApplication, QLabel

from iris.ui.chat.chat_panel import ChatPanel
from iris.ui.chat.composer_attachments import (
    composer_chip_label,
    composer_chip_meta,
    format_byte_size,
    partition_attachment_paths,
)


def main() -> None:
    app = QApplication.instance() or QApplication(sys.argv)
    panel = ChatPanel()
    root = Path(__file__).resolve().parents[3]
    panel.set_workspace_root(str(root))
    ref = panel._path_to_at_ref(str(root / "iris" / "ui" / "chat" / "chat_panel.py"))
    assert ref == "@iris/ui/chat/chat_panel.py", ref
    assert panel._path_to_at_ref("@integrations/iris-ide/tsconfig.json") == "@integrations/iris-ide/tsconfig.json"
    folder_ref = panel._path_to_at_ref(str(root / "iris" / "ui" / "chat"))
    assert folder_ref == "@iris/ui/chat", folder_ref
    panel._on_composer_drop_paths(
        [ref, str(root / "iris" / "assets" / "iris_icon.png"), str(root / "iris" / "ui" / "chat")]
    )
    chips = panel._input_area.attachment_strip.paths()
    assert ref in chips, chips
    assert folder_ref in chips, chips
    assert composer_chip_label(ref) == "chat_panel.py", composer_chip_label(ref)
    assert composer_chip_label(folder_ref) == "chat", composer_chip_label(folder_ref)
    win = "@C:/Users/serin/network_security.pdf"
    assert composer_chip_label(win) == "network_security.pdf", composer_chip_label(win)
    korean = r"C:\Users\serin\Documents\실전모의고사(엑셀).pdf"
    spaced = r"C:\Users\serin\Documents\보고서 최종본.pdf"
    assert composer_chip_label(korean) == "실전모의고사(엑셀).pdf", composer_chip_label(korean)
    assert composer_chip_label(spaced) == "보고서 최종본.pdf", composer_chip_label(spaced)
    assert composer_chip_label("@" + korean.replace("\\", "/")) == "실전모의고사(엑셀).pdf"
    lined = "@iris/ui/chat/chat_panel.py:10:2"
    assert composer_chip_label(lined) == "chat_panel.py", composer_chip_label(lined)
    assert panel.acceptDrops() is True
    assert panel._log.acceptDrops() is True
    py = root / "iris" / "ui" / "chat" / "chat_panel.py"
    meta = composer_chip_meta(str(py), workspace_root=str(root))
    assert meta.startswith("PY · "), meta
    assert format_byte_size(1536) == "1.5 KB"
    texts = [w.text() for w in panel._input_area.attachment_strip.findChildren(QLabel)]
    assert any(t.startswith("PY · ") for t in texts), texts
    assert any(t == "chat_panel.py" for t in texts), texts

    missing = str(root / "no-such-attachment.xyz")
    ok, errors = partition_attachment_paths([missing, str(py)])
    assert ok == [str(py)], ok
    assert errors and "찾을 수 없습니다" in errors[0], errors
    panel._on_composer_drop_paths([missing])
    assert "찾을 수 없습니다" in panel._input_area.attach_notice.text()
    # 용량·확장자 상한은 파일 선택(All Files)과 같다. 있는 파일은 형식과 무관하게 칩이 된다.
    odd = Path(tempfile.gettempdir()) / "iris_drop_odd.bin"
    odd.write_bytes(b"abc")
    try:
        before = len(panel._input_area.attachment_strip.paths())
        panel._input_area.input_bar._on_paths_attached([str(odd)])
        assert len(panel._input_area.attachment_strip.paths()) == before + 1
        odd_meta = composer_chip_meta(str(odd))
        assert odd_meta.startswith("BIN · "), odd_meta
    finally:
        odd.unlink(missing_ok=True)

    panel._input_area.attachment_strip._remove(
        panel._input_area.attachment_strip.paths()[-1]
    )

    png = root / "iris" / "assets" / "iris_icon.png"
    pdf = Path(tempfile.gettempdir()) / "iris_drop_sample.pdf"
    doc = Path(tempfile.gettempdir()) / "iris_drop_sample.txt"
    pdf.write_bytes(b"%PDF-1.1")
    doc.write_text("hello", encoding="utf-8")
    try:
        panel._input_area.attachment_strip.clear_paths()
        mime = QMimeData()
        mime.setUrls([QUrl.fromLocalFile(str(png)), QUrl.fromLocalFile(str(pdf)), QUrl.fromLocalFile(str(doc))])
        panel.dropEvent(
            QDropEvent(
                QPointF(8, 8),
                Qt.DropAction.CopyAction,
                mime,
                Qt.MouseButton.LeftButton,
                Qt.KeyboardModifier.NoModifier,
            )
        )
        dropped = panel._input_area.attachment_strip.paths()
        assert len(dropped) == 3, dropped
        assert panel._input.text() == ""
        assert any(p.endswith(".png") or p.endswith("iris_icon.png") for p in dropped), dropped
        shown = [w.text() for w in panel._input_area.attachment_strip.findChildren(QLabel)]
        assert any(t.startswith("PDF · ") for t in shown), shown
        assert any(t.startswith("TXT · ") for t in shown), shown
        assert any(t.startswith("PNG · ") for t in shown), shown
        sent: list[tuple[str, list]] = []
        panel.send_clicked.connect(lambda text, images: sent.append((text, list(images))))
        panel.set_input_text("첨부 확인")
        panel._emit_send()
        assert sent and "첨부 확인" in sent[0][0], sent
        assert panel._input_area.attachment_strip.paths() == []
    finally:
        pdf.unlink(missing_ok=True)
        doc.unlink(missing_ok=True)

    panel.mousePressEvent(
        QMouseEvent(
            QEvent.Type.MouseButtonPress,
            QPointF(8, 8),
            QPointF(8, 8),
            Qt.MouseButton.LeftButton,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
        )
    )
    assert panel._drop_hint.isHidden() is True
    panel.note_file_drag(True, force=True)
    assert panel._drop_hint.isHidden() is False
    panel.dragLeaveEvent(QDragLeaveEvent())
    panel._hide_drop_hint(panel._drop_hint_gen)
    assert panel._drop_hint.isHidden() is True

    one = QMimeData()
    one.setUrls([QUrl.fromLocalFile(str(py))])
    enter = QDragEnterEvent(
        QPoint(4, 4),
        Qt.DropAction.CopyAction,
        one,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )
    assert panel._input.eventFilter(panel._input.viewport(), enter) is True
    assert enter.isAccepted()
    print("composer_drop ok", ref, "folder", folder_ref, "chips", len(chips))
    app.quit()


if __name__ == "__main__":
    main()
