"""메일 연결 안내 — 제공자별 순서와 설정 페이지.

비밀번호 IMAP으로 붙는 서비스만 둔다. Outlook/Hotmail은
OAuth만 허용해서 이 목록에 없다.
"""

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
class EmailConnectStep:
    summary: str
    url: str = ""
    link_label: str = "열기"


@dataclass(frozen=True)
class EmailProviderGuide:
    name: str
    domains: str
    steps: tuple[EmailConnectStep, ...]

    @property
    def steps_text(self) -> str:
        return "\n".join(f"{i}. {step.summary}" for i, step in enumerate(self.steps, 1))

    @property
    def open_url(self) -> str:
        for step in self.steps:
            if step.url:
                return step.url
        return ""

    @property
    def open_label(self) -> str:
        for step in self.steps:
            if step.url:
                return step.link_label
        return "열기"


def _open_url(url: str) -> None:
    if url:
        QDesktopServices.openUrl(QUrl(url))


EMAIL_PROVIDER_GUIDES: tuple[EmailProviderGuide, ...] = (
    EmailProviderGuide(
        name="Gmail (Google)",
        domains="gmail.com / googlemail.com",
        steps=(
            EmailConnectStep(
                "Google 계정에서 2단계 인증을 켭니다.",
                "https://myaccount.google.com/signinoptions/two-step-verification",
                "2단계 인증",
            ),
            EmailConnectStep(
                "앱 비밀번호에서 메일용 16자리 비밀번호를 만듭니다.",
                "https://myaccount.google.com/apppasswords",
                "앱 비밀번호",
            ),
            EmailConnectStep(
                "Gmail 설정 → 전달 및 POP/IMAP에서 IMAP 사용을 켭니다.",
                "https://mail.google.com/mail/u/0/#settings/fwdandpop",
                "IMAP 설정",
            ),
            EmailConnectStep("아래 칸에 Gmail 주소와 앱 비밀번호를 넣고 계정 추가를 누릅니다."),
        ),
    ),
    EmailProviderGuide(
        name="네이버 메일",
        domains="naver.com",
        steps=(
            EmailConnectStep(
                "네이버 로그인 2단계 인증을 켜고 애플리케이션 비밀번호를 만듭니다.",
                "https://nid.naver.com/user2/help/myInfo?m=viewSecurity",
                "보안 설정",
            ),
            EmailConnectStep(
                "메일 환경설정에서 IMAP/SMTP를 사용함으로 저장합니다.",
                "https://mail.naver.com/v2/settings/imap",
                "IMAP 설정",
            ),
            EmailConnectStep("아래 칸에 네이버 주소와 애플리케이션 비밀번호를 넣고 계정 추가를 누릅니다."),
        ),
    ),
    EmailProviderGuide(
        name="다음 메일 (Kakao)",
        domains="daum.net / hanmail.net",
        steps=(
            EmailConnectStep(
                "다음 메일에 로그인한 뒤 환경설정에서 IMAP 사용을 켭니다.",
                "https://mail.daum.net/",
                "다음 메일",
            ),
            EmailConnectStep(
                "카카오계정에 2단계 인증이 있으면 애플리케이션 비밀번호를 만듭니다. 없으면 계정 비밀번호를 씁니다.",
                "https://accounts.kakao.com/weblogin/account/security",
                "카카오 보안",
            ),
            EmailConnectStep("아래 칸에 daum 또는 hanmail 주소와 그 비밀번호를 넣고 계정 추가를 누릅니다."),
        ),
    ),
    EmailProviderGuide(
        name="Yahoo 메일",
        domains="yahoo.com / ymail.com",
        steps=(
            EmailConnectStep(
                "Yahoo 계정 보안에서 앱 비밀번호를 만듭니다.",
                "https://login.yahoo.com/myaccount/security",
                "앱 비밀번호",
            ),
            EmailConnectStep("아래 칸에 Yahoo 주소와 앱 비밀번호를 넣고 계정 추가를 누릅니다."),
        ),
    ),
    EmailProviderGuide(
        name="iCloud 메일",
        domains="icloud.com / me.com / mac.com",
        steps=(
            EmailConnectStep(
                "Apple ID 로그인 및 보안에서 앱 암호를 만듭니다.",
                "https://appleid.apple.com/account/manage",
                "앱 암호",
            ),
            EmailConnectStep("아래 칸에 iCloud 주소와 앱 암호를 넣고 계정 추가를 누릅니다."),
        ),
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
                "연결 순서가 나오고, 우측 버튼으로 그 단계의 페이지를 엽니다."
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
        self._steps.setText(self._current.steps_text)
        self._open_btn.setText(self._current.open_label)
        self._open_btn.setEnabled(bool(self._current.open_url))

    def _open_link(self) -> None:
        if self._current is not None:
            _open_url(self._current.open_url)


def build_email_connect_panel() -> QWidget:
    """설정 이메일 칸. 메일을 고르면 순서가 나오고, 항목·단계 버튼이 설정 페이지를 연다."""
    host = QWidget()
    lay = QVBoxLayout(host)
    lay.setContentsMargins(0, 0, 0, 0)
    lay.setSpacing(6)
    lay.addWidget(
        make_hint(
            "연결할 메일을 누르면 그 서비스의 설정 페이지가 열리고, 아래에 따라 할 순서가 나옵니다. "
            "각 단계의 버튼으로도 그 페이지에 들어갈 수 있습니다."
        )
    )
    listing = QListWidget(host)
    listing.setCursor(Qt.CursorShape.PointingHandCursor)
    listing.setMaximumHeight(132)
    for guide in EMAIL_PROVIDER_GUIDES:
        item = QListWidgetItem(f"{guide.name}  ·  {guide.domains}")
        item.setData(Qt.ItemDataRole.UserRole, guide)
        item.setToolTip(guide.open_url)
        listing.addItem(item)
    lay.addWidget(listing)

    steps_host = QWidget(host)
    steps_lay = QVBoxLayout(steps_host)
    steps_lay.setContentsMargins(0, 0, 0, 0)
    steps_lay.setSpacing(4)
    lay.addWidget(steps_host)

    def _show(guide: EmailProviderGuide) -> None:
        while steps_lay.count():
            item = steps_lay.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        for index, step in enumerate(guide.steps, 1):
            row_w = QWidget(steps_host)
            row = QHBoxLayout(row_w)
            row.setContentsMargins(0, 0, 0, 0)
            row.setSpacing(8)
            label = QLabel(f"{index}. {step.summary}", row_w)
            label.setObjectName("HudDialogHint")
            label.setWordWrap(True)
            row.addWidget(label, 1)
            if step.url:
                button = QPushButton(step.link_label, row_w)
                button.setFixedWidth(88)
                button.setToolTip(step.url)
                button.clicked.connect(lambda _=False, url=step.url: _open_url(url))
                row.addWidget(button, 0)
            steps_lay.addWidget(row_w)

    def _on_row(row: int) -> None:
        item = listing.item(row) if row >= 0 else None
        guide = item.data(Qt.ItemDataRole.UserRole) if item is not None else None
        if isinstance(guide, EmailProviderGuide):
            _show(guide)

    def _on_click(item: QListWidgetItem) -> None:
        guide = item.data(Qt.ItemDataRole.UserRole)
        if isinstance(guide, EmailProviderGuide):
            _open_url(guide.open_url)

    listing.currentRowChanged.connect(_on_row)
    listing.itemClicked.connect(_on_click)
    if listing.count():
        listing.setCurrentRow(0)
    return host


def run_email_connect_guide(parent: QWidget | None = None) -> None:
    EmailConnectGuideDialog(parent).exec()


if __name__ == "__main__":
    assert len(EMAIL_PROVIDER_GUIDES) >= 4
    names = [guide.name for guide in EMAIL_PROVIDER_GUIDES]
    assert len(names) == len(set(names))
    gmail = EMAIL_PROVIDER_GUIDES[0]
    assert "google.com" in gmail.open_url
    assert "1. " in gmail.steps_text and gmail.steps[-1].url == ""
    assert all(step.url.startswith("https://") for guide in EMAIL_PROVIDER_GUIDES for step in guide.steps if step.url)
    print("email_connect_guide ok")
