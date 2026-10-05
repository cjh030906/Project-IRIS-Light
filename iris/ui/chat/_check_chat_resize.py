"""채팅 영역 높이 드래그 자검 — overlay 없이 패널 자체가 커진다."""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import QApplication, QSizePolicy, QVBoxLayout, QWidget

from iris.ui.chat.chat_panel import ChatPanel
from iris.ui.widgets.visualizer import Visualizer


def _host(app: QApplication) -> tuple[QWidget, QWidget, ChatPanel]:
    host = QWidget()
    host.resize(480, 720)
    lay = QVBoxLayout(host)
    lay.setContentsMargins(0, 0, 0, 0)
    lay.setSpacing(10)
    above = QWidget()
    above.setMinimumHeight(80)
    above.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
    lay.addWidget(above, 2)
    panel = ChatPanel()
    lay.addWidget(panel, 3)
    host._viz = Visualizer(host)
    host.show()
    app.processEvents()
    return host, above, panel


def main() -> int:
    app = QApplication.instance() or QApplication(sys.argv)
    app.setFont(QFont("Noto Sans KR", 10))
    host, above, panel = _host(app)

    assert panel._height_handle.objectName() == "ChatHeightHandle"
    assert not hasattr(panel, "open_full_view")
    assert not hasattr(panel._log, "reading_requested")
    overlays = [w for w in app.allWidgets() if w.objectName() == "MessageReadingOverlay"]
    assert overlays == [], overlays

    h0 = panel.height()
    a0 = above.height()
    log0 = panel._log.height()
    assert a0 > 80, a0
    assert h0 > 120, h0

    panel._begin_height_drag(400)
    panel._on_height_drag(220)
    app.processEvents()
    extra = panel._extra_h
    assert extra == 180, extra
    assert not panel._is_fully_expanded()
    assert panel.height() > h0, (h0, panel.height())
    assert panel._log.height() > log0, (log0, panel._log.height())
    assert above.height() < a0, (a0, above.height())
    assert panel.testAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
    assert not panel.autoFillBackground()
    fade_mid = host._viz.particle_core().chat_fade_y()
    assert fade_mid is not None and fade_mid > 0, fade_mid

    panel._on_height_drag(400)
    app.processEvents()
    assert panel._extra_h == 0, panel._extra_h
    assert panel.testAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
    assert abs(panel.height() - h0) <= 12, (h0, panel.height())
    assert host._viz.particle_core().chat_fade_y() is None

    panel._apply_chat_extra(10_000)
    app.processEvents()
    fade_max = host._viz.particle_core().chat_fade_y()
    assert fade_max is not None and fade_max < fade_mid, (fade_max, fade_mid)
    max_h = panel.height()
    assert max_h >= host.height() - 4, (max_h, host.height())
    assert panel._is_fully_expanded()
    assert (not above.isVisible()) or above.height() == 0, (above.isVisible(), above.height())

    panel._apply_chat_extra(0)
    app.processEvents()
    assert panel._extra_h == 0
    assert above.isVisible()
    assert host._viz.particle_core().chat_fade_y() is None

    from iris.ui.shared.theme_tokens import TOKENS

    panel.append_message_instant("You", "짧은 질문")
    panel.append_message_instant("Iris", ("긴 답변입니다. 줄이 자연스럽게 넘어가야 합니다. ") * 40)
    from iris.ui.chat.chat_renderer import render_iris_message

    card = render_iris_message(
        "설명입니다.\n```python\ndef hello():\n    return 1\n```\nhttps://example.com"
    )
    assert "hello" in card and "example.com" in card and "15px" in card
    panel.append_message_instant("You", '@"C:/Users/serin/Docs/document.pdf" 분석해 줘')
    app.processEvents()
    shown = panel._log.toHtml()
    assert "document.pdf" in shown and "C:/Users" not in shown and "Docs/" not in shown
    assert TOKENS.chat_user_name in shown or "7dd3fc" in shown.lower()
    shot_dir = Path(tempfile.gettempdir()) / "iris-ui-check"
    shot_dir.mkdir(parents=True, exist_ok=True)
    panel.grab().save(str(shot_dir / "chat_rest.png"))
    panel._apply_chat_extra(180)
    app.processEvents()
    panel.grab().save(str(shot_dir / "chat_mid.png"))
    panel._apply_chat_extra(10_000)
    app.processEvents()
    panel.grab().save(str(shot_dir / "chat_full.png"))
    core = host._viz.particle_core()
    host._viz.resize(480, 720)
    host._viz.show()
    app.processEvents()
    core.set_chat_fade_y(None)
    app.processEvents()
    core.grab().save(str(shot_dir / "orb_rest.png"))
    core.set_chat_fade_y(360)
    app.processEvents()
    core.grab().save(str(shot_dir / "orb_mid.png"))
    core.set_chat_fade_y(80)
    app.processEvents()
    core.grab().save(str(shot_dir / "orb_high.png"))
    print("chat resize ok", h0, "-> extra 180 / max", max_h, "shots", shot_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
