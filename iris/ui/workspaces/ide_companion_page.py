"""IDE Companion — 우측 20% 전용 세로 레이아웃 (사이드바 없음)."""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QSizePolicy,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from iris.ui.shared.theme_tokens import TOKENS

# 상단 구체 슬롯 — 좁은 20% 컬럼에서 3.0 스케일은 슬롯 밖으로 번져 로그와 겹쳤음
EMAIL_ORB_HEIGHT = 260
EMAIL_ORB_SCALE = 2.1
_UNIFIED_IDE_RATIO = 0.8


class IdeUnifiedShell(QWidget):
    """단일 창 내부 — 좌 IDE 80% + 우 Iris Companion 20% (두 창 타일 대체)."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("IdeUnifiedShell")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(f"background-color: {TOKENS.void_black};")

        self._split = QSplitter(Qt.Orientation.Horizontal, self)
        self._split.setChildrenCollapsible(False)
        self._split.setHandleWidth(0)
        self._split.setStyleSheet("QSplitter::handle { width: 0; }")

        self._ide_host = QWidget(self)
        self._ide_host.setObjectName("IdeUnifiedIdeHost")
        self._ide_lay = QVBoxLayout(self._ide_host)
        self._ide_lay.setContentsMargins(0, 0, 0, 0)
        self._ide_lay.setSpacing(0)

        self._iris_host = QWidget(self)
        self._iris_host.setObjectName("IdeUnifiedIrisHost")
        self._iris_lay = QVBoxLayout(self._iris_host)
        self._iris_lay.setContentsMargins(0, 0, 0, 0)
        self._iris_lay.setSpacing(0)

        self._split.addWidget(self._ide_host)
        self._split.addWidget(self._iris_host)
        self._split.setStretchFactor(0, 4)
        self._split.setStretchFactor(1, 1)

        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(self._split)

        self._ide: QWidget | None = None
        self._companion: IdeCompanionPage | None = None
        self._split.splitterMoved.connect(self._lock_ratio)

    def mount(self, ide: QWidget, companion: IdeCompanionPage, *, total_w: int) -> None:
        if self._ide is not None and self._ide is not ide:
            self._ide_lay.removeWidget(self._ide)
        if self._companion is not None and self._companion is not companion:
            self._iris_lay.removeWidget(self._companion)
        self._ide_lay.addWidget(ide)
        self._iris_lay.addWidget(companion)
        self._ide = ide
        self._companion = companion
        ide.show()
        companion.show()
        self.apply_ratio(total_w)

    def apply_ratio(self, total_w: int, ratio: float = _UNIFIED_IDE_RATIO) -> None:
        w = max(1, int(total_w))
        ide_w = int(w * ratio)
        iris_w = w - ide_w
        self._split.setSizes([ide_w, max(1, iris_w)])

    def _lock_ratio(self, *_args) -> None:
        # ponytail: 핸들 폭 0이어도 드래그되면 8:2로 되돌림
        total = sum(self._split.sizes()) or self.width()
        self.apply_ratio(total)

    def is_mounted(self) -> bool:
        return self._ide is not None and self._companion is not None

    def clear_hosts(self) -> None:
        """자식은 호출 측이 다른 레이아웃으로 옮김 — 여기선 참조만 끊음."""
        self._ide = None
        self._companion = None


class IdeCompanionPage(QWidget):
    """
    위→아래: 구체 슬롯 · Live Activity · 채팅 (이메일 우측 패널과 동일 배치).
    addWidget만으로 reparent — remove/setParent(None) 금지.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("IdeCompanionPage")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(f"background-color: {TOKENS.void_black};")
        self._lay = QVBoxLayout(self)
        # ponytail: companion은 IDE와 왼쪽이 맞닿음 — 좌측 여백 없음
        self._lay.setContentsMargins(0, 6, 6, 6)
        self._lay.setSpacing(6)
        self._mounted: list[QWidget] = []

    def mount(
        self,
        *,
        orb_spacer: QWidget,
        live_activity: QWidget,
        chat: QWidget,
        orb_height: int = EMAIL_ORB_HEIGHT,
        activity_height: int,
    ) -> None:
        orb_spacer.setMinimumHeight(orb_height)
        orb_spacer.setMaximumHeight(orb_height)
        orb_spacer.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        live_activity.setMinimumHeight(activity_height)
        live_activity.setMaximumHeight(activity_height)
        live_activity.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        chat.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        # addWidget이 이전 레이아웃에서 원자적으로 옮김 (orphan 창 없음)
        self._lay.addWidget(orb_spacer, 0)
        self._lay.addWidget(live_activity, 0)
        self._lay.addWidget(chat, 1)
        self._mounted = [orb_spacer, live_activity, chat]
        for w in self._mounted:
            w.show()

    def transfer_to(self, target_layout: QVBoxLayout, stretches: tuple[int, int, int]) -> None:
        """companion → assistant center 로 원자적 복귀."""
        if len(self._mounted) != 3:
            return
        orb, activity, chat = self._mounted
        self._mounted = []
        target_layout.addWidget(orb, stretches[0])
        target_layout.addWidget(activity, stretches[1])
        target_layout.addWidget(chat, stretches[2])
        orb.show()
        activity.show()
        chat.show()

    def is_mounted(self) -> bool:
        return bool(self._mounted)
