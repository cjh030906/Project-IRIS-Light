"""메일 미연결 시 안내 — 제공자 선택 → 연결 방법 + 발급/설정 페이지 열기."""

from __future__ import annotations

from dataclasses import dataclass

from PyQt6.QtCore import Qt, QUrl
from PyQt6.QtGui import QDesktopServices
from PyQt6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from iris.ui.settings.hud_dialog import configure_hud_dialog, make_hint, make_title
from iris.ui.shared.theme_tokens import TOKENS


@dataclass(frozen=True)
class EmailProviderGuide:
    name: str
    domains: str
    steps: str
    open_url: str
    open_label: str = "열기"


EMAIL_PROVIDER_GUIDES: tuple[EmailProviderGuide, ...] = (
    EmailProviderGuide(
        name="Gmail (Google)",
        domains="gmail.com / googlemail.com",
        steps=(
            "1. Google 계정에서 2단계 인증을 켭니다.\n"
            "2. '앱 비밀번호' 페이지에서 메일용 16자리 비밀번호를 만듭니다.\n"
            "3. Iris 설정 → 이메일 계정에 주소와 앱 비밀번호를 넣고 계정 추가를 누릅니다."
        ),
        open_url="https://myaccount.google.com/apppasswords",
        open_label="앱 비밀번호 열기",
    ),
    EmailProviderGuide(
        name="네이버 메일",
        domains="naver.com",
        steps=(
            "1. 네이버 메일 → 환경설정에서 IMAP/SMTP 사용을 켭니다.\n"
            "2. 보안 설정에서 애플리케이션 비밀번호(또는 2단계 인증 앱 비번)를 발급합니다.\n"
            "3. Iris 설정 → 이메일 계정에 네이버 주소와 앱 비밀번호를 넣고 추가합니다."
        ),
        open_url="https://mail.naver.com/v2/folders/0/option/imap",
        open_label="IMAP 설정 열기",
    ),
    EmailProviderGuide(
        name="Outlook / Hotmail",
        domains="outlook.com / hotmail.com / live.com",
        steps=(
            "1. Microsoft 계정 보안에서 앱 비밀번호를 만듭니다.\n"
            "2. Iris 설정 → 이메일 계정에 Outlook 주소와 앱 비밀번호를 넣고 추가합니다.\n"
            "3. 연결이 안 되면 IMAP이 켜져 있는지 메일 설정을 확인하세요."
        ),
        open_url="https://account.live.com/proofs/AppPassword",
        open_label="앱 비밀번호 열기",
    ),
    EmailProviderGuide(
        name="다음 메일 (Kakao)",
        domains="daum.net / hanmail.net",
        steps=(
            "1. 다음 메일 설정에서 POP3/IMAP 사용을 켭니다.\n"
            "2. 필요하면 애플리케이션 비밀번호를 발급합니다.\n"
            "3. Iris 설정 → 이메일 계정에 주소와 비밀번호를 넣고 추가합니다."
        ),
        open_url="https://mail.daum.net/",
        open_label="다음 메일 열기",
    ),
)


class EmailConnectGuideDialog(QDialog):
    """메일함 진입 시 계정 없을 때 띄우는 연결 안내."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        configure_hud_dialog(
            self,
            title="메일 연결",
            min_w=520,
            min_h=420,
            default_w=560,
            default_h=480,
        )
        root = QVBoxLayout(self)
        root.setContentsMargins(18, 16, 18, 16)
        root.setSpacing(TOKENS.spacing_sm)
        root.addWidget(make_title("메일을 연결해 주세요"))
        root.addWidget(
            make_hint(
                "연결된 계정이 없습니다. 아래에서 메일 서비스를 고르면 "
                "연결 방법이 나오고, 우측 버튼으로 설정 페이지를 열 수 있습니다."
            )
        )

        self._list = QListWidget()
        self._list.setMinimumHeight(120)
        for guide in EMAIL_PROVIDER_GUIDES:
            item = QListWidgetItem(f"{guide.name}  ·  {guide.domains}")
            item.setData(Qt.ItemDataRole.UserRole, guide)
            self._list.addItem(item)
        self._list.currentRowChanged.connect(self._on_select)
        root.addWidget(self._list)

        self._steps = QLabel("")
        self._steps.setObjectName("HudDialogHint")
        self._steps.setWordWrap(True)
        self._steps.setMinimumHeight(96)
        root.addWidget(self._steps)

        action = QHBoxLayout()
        action.addStretch(1)
        self._open_btn = QPushButton("열기")
        self._open_btn.setMinimumWidth(120)
        self._open_btn.clicked.connect(self._open_link)
        self._open_btn.setEnabled(False)
        close_btn = QPushButton("닫기")
        close_btn.clicked.connect(self.accept)
        action.addWidget(self._open_btn)
        action.addWidget(close_btn)
        root.addLayout(action)

        self._current: EmailProviderGuide | None = None
        if self._list.count():
            self._list.setCurrentRow(0)

    def _on_select(self, row: int) -> None:
        item = self._list.item(row) if row >= 0 else None
        guide = item.data(Qt.ItemDataRole.UserRole) if item is not None else None
        self._current = guide if isinstance(guide, EmailProviderGuide) else None
        if self._current is None:
            self._steps.setText("")
            self._open_btn.setEnabled(False)
            self._open_btn.setText("열기")
            return
        self._steps.setText(self._current.steps)
        self._open_btn.setText(self._current.open_label)
        self._open_btn.setEnabled(True)

    def _open_link(self) -> None:
        if self._current is None:
            return
        QDesktopServices.openUrl(QUrl(self._current.open_url))


def run_email_connect_guide(parent: QWidget | None = None) -> None:
    EmailConnectGuideDialog(parent).exec()


if __name__ == "__main__":
    assert len(EMAIL_PROVIDER_GUIDES) >= 2
    assert "gmail" in EMAIL_PROVIDER_GUIDES[0].open_url or "google" in EMAIL_PROVIDER_GUIDES[0].open_url
    print("email_connect_guide ok")
