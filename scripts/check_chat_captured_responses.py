"""Inspect real model responses captured by check_chat_live_rendering.py."""
from __future__ import annotations
import os
import re
import sys
import json
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QFontDatabase, QTextCursor
from iris.ui.chat.chat_panel import ChatPanel
from iris.ui.workspaces.workspace_iris_chat import WorkspaceIrisChatLog
from iris.ui.chat.chat_renderer import render_iris_message
from iris.ui.chat.chat_blocks import parse_copy_anchor

def main():
    app = QApplication([])
    for font in ("malgun.ttf", "segoeui.ttf", "consola.ttf"):
        QFontDatabase.addApplicationFont("C:/Windows/Fonts/" + font)
    out = Path(".iris_light_test_tmp/chat-live")
    results = []
    for path in sorted(out.glob("test-*-raw.md")):
        number = int(path.name.split("-")[1])
        source = path.read_text(encoding="utf-8")
        if not source:
            continue
        for width in (480, 1100):
            panel = ChatPanel()
            workspace = WorkspaceIrisChatLog("CapturedResponse")
            panel.resize(width, 950)
            workspace.resize(width, 950)
            panel.show()
            workspace.show()
            app.processEvents()
            panel.append_message_instant("Iris", source)
            workspace.end_iris(source)
            app.processEvents()
            for label, widget in (("main", panel._log), ("workspace", workspace)):
                text = widget.toPlainText()
                assert not re.search(r"#{3,6}|\*\*|&#(?:x[0-9a-fA-F]+|\d+);|\|\s*:?-{3}", text), (number, label)
                if number == 2:
                    assert "iris-copy://" in widget.toHtml()
                if number == 3:
                    assert widget.toHtml().count("<table") >= 2
                if number == 4:
                    assert "iris-copy://" in widget.toHtml() and "핵심 개념" in text
                widget.setStyleSheet("QTextEdit {background:#0b1120; color:#f8fafc; border:none; padding:12px 16px;}")
                app.processEvents()
                viewport = widget.viewport().width()
                document_width = widget.document().size().width()
                results.append({"test": number, "view": label, "width": width,
                                "viewport": viewport, "document_width": round(document_width, 1),
                                "clipped": document_width > viewport + 1})
                widget.verticalScrollBar().setValue(0)
                widget.grab().save(str(out / f"final-{number}-{label}-{width}.png"))
                widget.verticalScrollBar().setValue(widget.verticalScrollBar().maximum() // 2)
                widget.grab().save(str(out / f"final-{number}-{label}-{width}-middle.png"))
            panel.close()
            workspace.close()
    (out / "layout-results.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(json.dumps(results, indent=2))
    return 1 if any(item["clipped"] for item in results) else 0

if __name__ == "__main__":
    sys.exit(main())
