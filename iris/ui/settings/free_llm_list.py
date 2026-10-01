"""설정 LLM 칸 — 무료 한도 AI. 항목 클릭 시 키 발급 페이지."""

from __future__ import annotations

from collections.abc import Callable

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QListWidget, QListWidgetItem, QVBoxLayout, QWidget

from iris.storage.api_providers import FREE_LLM_OFFERS, FreeLlmOffer
from iris.ui.settings.hud_dialog import make_hint


def build_free_llm_list(on_pick: Callable[[FreeLlmOffer], None]) -> QWidget:
    host = QWidget()
    lay = QVBoxLayout(host)
    lay.setContentsMargins(0, 4, 0, 0)
    lay.setSpacing(6)
    lay.addWidget(
        make_hint(
            "무료 한도로 키를 받을 수 있는 AI입니다. 항목을 누르면 발급 페이지가 열리고, "
            "아래 이름과 제공자 프리셋이 그 브랜드로 채워집니다. 한도는 제공자 정책이라 바뀔 수 있습니다."
        )
    )
    listing = QListWidget()
    listing.setCursor(Qt.CursorShape.PointingHandCursor)
    listing.setMaximumHeight(220)
    for index, offer in enumerate(FREE_LLM_OFFERS):
        item = QListWidgetItem(f"{offer.name}  ·  {offer.limit_note}")
        item.setData(Qt.ItemDataRole.UserRole, index)
        item.setToolTip(f"{offer.signup_url}\nBase URL: {offer.base_url}")
        listing.addItem(item)

    def _open(item: QListWidgetItem) -> None:
        raw = item.data(Qt.ItemDataRole.UserRole)
        if not isinstance(raw, int) or not 0 <= raw < len(FREE_LLM_OFFERS):
            return
        on_pick(FREE_LLM_OFFERS[raw])

    listing.itemClicked.connect(_open)
    lay.addWidget(listing)
    return host
