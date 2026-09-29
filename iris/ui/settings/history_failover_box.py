"""설정 — 위키 History 기록·검색, 모델 자동 전환 체인.

`build_history_failover_box(db)` 가 QGroupBox 를 돌려주고, 위젯을 박스 속성으로
달아 둔다(이 저장소의 `build_chat_title_box` 방식). 저장은 `save_history_failover`
가 맡는다 — 다이얼로그가 Save 를 누를 때 부른다.
"""

from __future__ import annotations

from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
)

from iris.runtime.model_failover import MODE_MODEL_CHAIN, MODE_OFF, MODE_RETRY
from iris.storage.database import Database
from iris.storage.failover_prefs import (
    BACKENDS,
    FailoverSettings,
    FallbackEntry,
    HistorySettings,
    load_failover_settings,
    load_history_settings,
    save_failover_settings,
    save_history_settings,
)
from iris.ui.settings.hud_dialog import (
    TOKENS,
    configure_form,
    make_form_label,
    make_hint,
)


def _entry_label(entry: FallbackEntry) -> str:
    tail = " · 무료" if entry.free else ""
    return f"{entry.model}  [{entry.backend}]{tail}"


def build_history_failover_box(db: Database) -> QGroupBox:
    """History 기록·검색 + 모델 자동 전환 설정."""
    history = load_history_settings(db)
    failover = load_failover_settings(db)

    box = QGroupBox("대화 기록 (History) · 모델 자동 전환")
    lay = QVBoxLayout(box)
    lay.setSpacing(TOKENS.spacing_sm)
    lay.addWidget(
        make_hint(
            "아이리스와 나눈 대화, 수행한 일, 만든 것, 들어온 데이터를 Iris Wiki "
            "History에 쌓고 검색해 씁니다. 모델을 바꾸거나 할당량이 떨어져 다른 "
            "모델로 넘어갈 때 이 기록에서 맥락을 되찾습니다. 전부 이 PC 안에만 "
            "저장됩니다."
        )
    )

    enabled = QCheckBox("History 기록·검색 사용")
    enabled.setChecked(history.enabled)
    lay.addWidget(enabled)

    kinds_row = QHBoxLayout()
    rec_chat = QCheckBox("대화")
    rec_actions = QCheckBox("수행")
    rec_artifacts = QCheckBox("생성물")
    rec_inputs = QCheckBox("입력 데이터")
    rec_chat.setChecked(history.record_chat)
    rec_actions.setChecked(history.record_actions)
    rec_artifacts.setChecked(history.record_artifacts)
    rec_inputs.setChecked(history.record_inputs)
    for widget in (rec_chat, rec_actions, rec_artifacts, rec_inputs):
        kinds_row.addWidget(widget)
    kinds_row.addStretch(1)
    lay.addLayout(kinds_row)

    past_chats = QCheckBox("새 채팅에서도 이전 대화 참고 (참고한 기록은 답변 위에 표시)")
    past_chats.setChecked(history.reference_past_chats)
    lay.addWidget(past_chats)

    form = QFormLayout()
    configure_form(form)

    retrieval = QSpinBox()
    retrieval.setRange(0, 20)
    retrieval.setValue(history.retrieval_limit)
    retrieval.setMinimumHeight(32)
    form.addRow(make_form_label("모델에 붙일 과거 기록 수"), retrieval)

    embed_enabled = QCheckBox("의미 검색 사용 (Ollama 임베딩 모델 필요)")
    embed_enabled.setChecked(history.embed_enabled)
    form.addRow(make_form_label("검색 방식"), embed_enabled)

    embed_model = QLineEdit(history.embed_model)
    embed_model.setPlaceholderText("비우면 설치된 것 중 자동 선택 (bge-m3 권장)")
    embed_model.setMinimumHeight(32)
    form.addRow(make_form_label("임베딩 모델"), embed_model)
    lay.addLayout(form)
    lay.addWidget(
        make_hint(
            "임베딩 모델이 없으면 키워드 검색만 씁니다. `ollama pull bge-m3` 로 "
            "한국어 의미 검색을 켤 수 있습니다."
        )
    )

    # --- 자동 전환 --------------------------------------------------

    lay.addWidget(
        make_hint(
            "쓰던 모델이 할당량 소진(429)이나 서버 오류로 막히면 아래 순서대로 "
            "다음 모델에 다시 요청합니다. 대화 맥락은 같이 넘어갑니다."
        )
    )
    failover_enabled = QCheckBox("모델 자동 전환 사용")
    failover_enabled.setChecked(failover.enabled)
    lay.addWidget(failover_enabled)

    f_form = QFormLayout()
    configure_form(f_form)

    mode = QComboBox()
    mode.addItem("다른 모델로 전환", MODE_MODEL_CHAIN)
    mode.addItem("같은 모델로 재시도", MODE_RETRY)
    mode.addItem("전환 안 함", MODE_OFF)
    idx = mode.findData(failover.mode)
    mode.setCurrentIndex(idx if idx >= 0 else 0)
    mode.setMinimumHeight(32)
    f_form.addRow(make_form_label("실패했을 때"), mode)

    retry_count = QSpinBox()
    retry_count.setRange(0, 10)
    retry_count.setValue(failover.retry_count)
    retry_count.setMinimumHeight(32)
    f_form.addRow(make_form_label("재시도 횟수"), retry_count)

    preempt_enabled = QCheckBox("한도에 가까워지면 미리 전환")
    preempt_enabled.setChecked(failover.preempt_enabled)
    f_form.addRow(make_form_label("선제 전환"), preempt_enabled)

    preempt_percent = QSpinBox()
    preempt_percent.setRange(50, 100)
    preempt_percent.setSuffix(" %")
    preempt_percent.setValue(int(failover.preempt_percent))
    preempt_percent.setMinimumHeight(32)
    f_form.addRow(make_form_label("선제 전환 기준"), preempt_percent)

    ask_summary = QCheckBox("전환 전에 쓰던 모델이 인수인계문을 쓰게 함")
    ask_summary.setChecked(failover.ask_old_model_summary)
    f_form.addRow(make_form_label("인수인계"), ask_summary)
    lay.addLayout(f_form)

    chain_list = QListWidget()
    chain_list.setMinimumHeight(96)
    for entry in failover.chain:
        item = QListWidgetItem(_entry_label(entry))
        item.setData(256, entry)
        chain_list.addItem(item)
    lay.addWidget(chain_list)

    add_row = QHBoxLayout()
    new_model = QLineEdit()
    new_model.setPlaceholderText("전환할 모델 이름 (예: gemma4:free)")
    new_model.setMinimumHeight(32)
    new_backend = QComboBox()
    for backend in BACKENDS:
        new_backend.addItem(backend, backend)
    new_backend.setMinimumHeight(32)
    add_btn = QPushButton("추가")
    up_btn = QPushButton("↑")
    down_btn = QPushButton("↓")
    del_btn = QPushButton("삭제")
    for widget in (new_model, new_backend, add_btn, up_btn, down_btn, del_btn):
        add_row.addWidget(widget)
    lay.addLayout(add_row)
    lay.addWidget(
        make_hint(
            "Hermes 가 켜져 있으면(기본값) 모든 후보를 Hermes 게이트웨이로 시도합니다. "
            "Hermes 를 끄면 지금 쓰는 모델과 같은 종류의 후보만 쓸 수 있습니다 — "
            "Ollama 모델이면 Ollama 후보만, 커스텀 API 모델이면 API 후보만 시도합니다."
        )
    )

    def _add() -> None:
        name = new_model.text().strip()
        if not name:
            return
        entry = FallbackEntry(model=name, backend=new_backend.currentData(), free=True)
        item = QListWidgetItem(_entry_label(entry))
        item.setData(256, entry)
        chain_list.addItem(item)
        new_model.clear()

    def _move(delta: int) -> None:
        row = chain_list.currentRow()
        target = row + delta
        if row < 0 or not (0 <= target < chain_list.count()):
            return
        item = chain_list.takeItem(row)
        chain_list.insertItem(target, item)
        chain_list.setCurrentRow(target)

    def _delete() -> None:
        row = chain_list.currentRow()
        if row >= 0:
            chain_list.takeItem(row)

    add_btn.clicked.connect(_add)
    new_model.returnPressed.connect(_add)
    up_btn.clicked.connect(lambda: _move(-1))
    down_btn.clicked.connect(lambda: _move(1))
    del_btn.clicked.connect(_delete)

    def _sync_enabled() -> None:
        on = enabled.isChecked()
        for widget in (
            rec_chat, rec_actions, rec_artifacts, rec_inputs,
            past_chats, retrieval, embed_enabled, embed_model,
        ):
            widget.setEnabled(on)
        embed_model.setEnabled(on and embed_enabled.isChecked())

        f_on = failover_enabled.isChecked()
        for widget in (
            mode, retry_count, preempt_enabled, ask_summary,
            chain_list, new_model, new_backend, add_btn, up_btn, down_btn, del_btn,
        ):
            widget.setEnabled(f_on)
        retry_count.setEnabled(f_on and mode.currentData() == MODE_RETRY)
        preempt_percent.setEnabled(f_on and preempt_enabled.isChecked())

    enabled.toggled.connect(_sync_enabled)
    embed_enabled.toggled.connect(_sync_enabled)
    failover_enabled.toggled.connect(_sync_enabled)
    preempt_enabled.toggled.connect(_sync_enabled)
    mode.currentIndexChanged.connect(_sync_enabled)
    _sync_enabled()

    box.history_enabled = enabled  # type: ignore[attr-defined]
    box.record_chat = rec_chat  # type: ignore[attr-defined]
    box.record_actions = rec_actions  # type: ignore[attr-defined]
    box.record_artifacts = rec_artifacts  # type: ignore[attr-defined]
    box.record_inputs = rec_inputs  # type: ignore[attr-defined]
    box.retrieval_limit = retrieval  # type: ignore[attr-defined]
    box.reference_past_chats = past_chats  # type: ignore[attr-defined]
    box.embed_enabled = embed_enabled  # type: ignore[attr-defined]
    box.embed_model = embed_model  # type: ignore[attr-defined]
    box.failover_enabled = failover_enabled  # type: ignore[attr-defined]
    box.failover_mode = mode  # type: ignore[attr-defined]
    box.retry_count = retry_count  # type: ignore[attr-defined]
    box.preempt_enabled = preempt_enabled  # type: ignore[attr-defined]
    box.preempt_percent = preempt_percent  # type: ignore[attr-defined]
    box.ask_old_model_summary = ask_summary  # type: ignore[attr-defined]
    box.chain_list = chain_list  # type: ignore[attr-defined]
    return box


def chain_from_box(box: QGroupBox) -> list[FallbackEntry]:
    widget = box.chain_list  # type: ignore[attr-defined]
    out: list[FallbackEntry] = []
    for row in range(widget.count()):
        entry = widget.item(row).data(256)
        if isinstance(entry, FallbackEntry):
            out.append(entry)
    return out


def save_history_failover(db: Database, box: QGroupBox) -> None:
    """박스의 현재 값을 저장한다. 다이얼로그 Save 에서 부른다."""
    save_history_settings(
        db,
        HistorySettings(
            enabled=box.history_enabled.isChecked(),  # type: ignore[attr-defined]
            record_chat=box.record_chat.isChecked(),  # type: ignore[attr-defined]
            record_actions=box.record_actions.isChecked(),  # type: ignore[attr-defined]
            record_artifacts=box.record_artifacts.isChecked(),  # type: ignore[attr-defined]
            record_inputs=box.record_inputs.isChecked(),  # type: ignore[attr-defined]
            retrieval_limit=box.retrieval_limit.value(),  # type: ignore[attr-defined]
            embed_model=box.embed_model.text(),  # type: ignore[attr-defined]
            embed_enabled=box.embed_enabled.isChecked(),  # type: ignore[attr-defined]
            reference_past_chats=box.reference_past_chats.isChecked(),  # type: ignore[attr-defined]
        ),
    )
    save_failover_settings(
        db,
        FailoverSettings(
            enabled=box.failover_enabled.isChecked(),  # type: ignore[attr-defined]
            mode=box.failover_mode.currentData(),  # type: ignore[attr-defined]
            retry_count=box.retry_count.value(),  # type: ignore[attr-defined]
            preempt_percent=float(box.preempt_percent.value()),  # type: ignore[attr-defined]
            preempt_enabled=box.preempt_enabled.isChecked(),  # type: ignore[attr-defined]
            ask_old_model_summary=box.ask_old_model_summary.isChecked(),  # type: ignore[attr-defined]
            chain=chain_from_box(box),
        ),
    )
