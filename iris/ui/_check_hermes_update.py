"""Hermes 업데이트 채팅 프롬프트 자검. 실제 업데이트는 호출하지 않는다."""

from __future__ import annotations

from PyQt6.QtWidgets import QApplication

from iris.ui.chat.chat_panel import ChatPanel


def _main() -> None:
    app = QApplication([])
    panel = ChatPanel()
    panel.append_hermes_update_prompt(detail="abc1234 → def5678")
    html = panel._log.toHtml()
    assert "iris-hermes-update://apply" in html
    assert "iris-hermes-update://later" in html
    assert "[업데이트]" in html and "[나중에]" in html
    assert "Hermes 업데이트가 가능합니다" in html
    panel.dismiss_hermes_update_prompt("미룸")
    html2 = panel._log.toHtml()
    assert "iris-hermes-update://apply" not in html2
    assert "미룸" in panel._log.toPlainText()
    print("hermes_update prompt ok")


if __name__ == "__main__":
    _main()
