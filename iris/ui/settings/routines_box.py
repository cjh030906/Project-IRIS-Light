"""설정 — 예약 루틴 목록. 체크박스로 켜고 끄고, 주기·모델·전달을 손으로 고친다.

말로도 다 되지만(`routine.*` MCP 액션), 한눈에 보고 마우스로 끄는 화면이 있어야
"내가 아이리스한테 뭘 시켜놨더라"를 확인할 수 있다.

저장은 즉시 DB 에 쓴다 — 설정 창의 Save 를 기다리지 않는다. 루틴은 다른 설정과
달리 개별 항목이라 "체크 풀었는데 취소 눌렀으니 되돌아감"이 더 헷갈린다.
"""

from __future__ import annotations

from collections.abc import Callable

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from iris.runtime.routine_schedule import (
    KIND_DAILY,
    KIND_INTERVAL,
    KIND_ONCE,
    KIND_WEEKLY,
)
from iris.storage.database import Database
from iris.storage.routines import (
    Routine,
    delete_routine,
    deliver_labels,
    list_routines,
    update_routine,
)
from iris.ui.settings.hud_dialog import TOKENS, make_hint

COL_ON, COL_NAME, COL_WHEN, COL_DELIVER, COL_MODEL, COL_SEARCH, COL_WAKE, COL_LAST = range(8)
_HEADERS = ("켜기", "이름", "주기", "전달", "모델", "검색", "꺼져도", "최근")

_STATUS_LABELS = {
    "ok": "성공",
    "failed": "실패",
    "missed": "놓침",
    "never": "아직 없음",
}


def _last_run_text(r: Routine) -> str:
    if not r.last_run_at and r.last_status == "never":
        return "아직 없음"
    status = _STATUS_LABELS.get(r.last_status, r.last_status)
    when = (r.last_run_at or "")[5:16].replace("T", " ")
    tail = f" · 놓침 {r.miss_count}" if r.miss_count else ""
    return f"{when} {status}{tail}".strip()


def build_routines_box(
    db: Database,
    *,
    model_names: list[str] | None = None,
    on_run_now: Callable[[int], bool] | None = None,
) -> QGroupBox:
    """예약 루틴 목록. 위젯은 box 속성으로 달아 둔다."""
    box = QGroupBox("예약 루틴")
    lay = QVBoxLayout(box)
    lay.setSpacing(TOKENS.spacing_sm)
    lay.addWidget(
        make_hint(
            "아이리스에게 \"매일 9시에 뉴스 3개 정리해줘\" 처럼 말하면 여기 쌓입니다. "
            "체크를 풀면 지우지 않고 잠시 멈춥니다. 바뀐 내용은 바로 저장됩니다. "
            "뉴스·날씨처럼 오늘 정보가 필요한 루틴은 **검색어**를 넣어야 실제 자료를 "
            "찾아옵니다 — 비워 두면 모델이 아는 것만으로 답합니다."
        )
    )

    table = QTableWidget(0, len(_HEADERS))
    table.setHorizontalHeaderLabels(list(_HEADERS))
    table.verticalHeader().setVisible(False)
    table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
    table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
    table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
    table.setMinimumHeight(160)
    header = table.horizontalHeader()
    header.setSectionResizeMode(COL_NAME, QHeaderView.ResizeMode.Stretch)
    for col in (COL_ON, COL_WHEN, COL_DELIVER, COL_MODEL, COL_SEARCH, COL_WAKE, COL_LAST):
        header.setSectionResizeMode(col, QHeaderView.ResizeMode.ResizeToContents)
    lay.addWidget(table)

    empty = QLabel("아직 등록된 루틴이 없습니다.")
    empty.setWordWrap(True)
    lay.addWidget(empty)

    # --- 선택한 루틴 편집 --------------------------------------------

    edit_row = QHBoxLayout()
    kind = QComboBox()
    kind.addItem("매일", KIND_DAILY)
    kind.addItem("매주", KIND_WEEKLY)
    kind.addItem("N분마다", KIND_INTERVAL)
    kind.addItem("한 번만", KIND_ONCE)
    time_edit = QLineEdit()
    time_edit.setPlaceholderText("09:00")
    time_edit.setMaximumWidth(80)
    weekdays = QLineEdit()
    weekdays.setPlaceholderText("mon,fri (매주일 때)")
    deliver = QLineEdit()
    deliver.setPlaceholderText("chat,notify")
    search = QLineEdit()
    search.setPlaceholderText("검색어 (뉴스·날씨 등 오늘 정보가 필요할 때)")
    model = QComboBox()
    model.setEditable(True)
    model.addItem("(지금 선택된 모델)", "")
    for name in model_names or []:
        model.addItem(name, name)
    for widget in (kind, time_edit, weekdays, deliver, search, model):
        widget.setMinimumHeight(30)
        edit_row.addWidget(widget)
    lay.addLayout(edit_row)

    wake = QCheckBox("아이리스가 꺼져 있어도 실행 (Windows 작업 스케줄러)")
    lay.addWidget(wake)

    btn_row = QHBoxLayout()
    apply_btn = QPushButton("선택 항목에 적용")
    run_btn = QPushButton("지금 실행")
    delete_btn = QPushButton("삭제")
    refresh_btn = QPushButton("새로고침")
    for widget in (apply_btn, run_btn, delete_btn, refresh_btn):
        btn_row.addWidget(widget)
    btn_row.addStretch(1)
    lay.addLayout(btn_row)

    status = QLabel("")
    status.setWordWrap(True)
    lay.addWidget(status)

    state: dict[str, object] = {"rows": [], "loading": False}

    def _selected() -> Routine | None:
        row = table.currentRow()
        rows = state["rows"]
        if 0 <= row < len(rows):
            return rows[row]
        return None

    def _sync_edit_enabled() -> None:
        has = _selected() is not None
        for widget in (kind, time_edit, weekdays, deliver, search, model, wake,
                       apply_btn, run_btn, delete_btn):
            widget.setEnabled(has)
        weekdays.setEnabled(has and kind.currentData() == KIND_WEEKLY)
        time_edit.setEnabled(has and kind.currentData() in (KIND_DAILY, KIND_WEEKLY))

    def _fill_editor(r: Routine | None) -> None:
        if r is None:
            _sync_edit_enabled()
            return
        state["loading"] = True
        idx = kind.findData(r.kind)
        kind.setCurrentIndex(idx if idx >= 0 else 0)
        time_edit.setText(r.time_of_day)
        weekdays.setText(r.weekdays)
        deliver.setText(r.deliver)
        search.setText(r.search)
        midx = model.findData(r.model)
        if midx >= 0:
            model.setCurrentIndex(midx)
        else:
            model.setEditText(r.model)
        wake.setChecked(r.wake_when_closed)
        state["loading"] = False
        _sync_edit_enabled()

    def reload() -> None:
        state["loading"] = True
        rows = list_routines(db)
        state["rows"] = rows
        table.setRowCount(len(rows))
        for i, r in enumerate(rows):
            check = QTableWidgetItem()
            check.setFlags(
                Qt.ItemFlag.ItemIsUserCheckable
                | Qt.ItemFlag.ItemIsEnabled
                | Qt.ItemFlag.ItemIsSelectable
            )
            check.setCheckState(
                Qt.CheckState.Checked if r.enabled else Qt.CheckState.Unchecked
            )
            table.setItem(i, COL_ON, check)
            for col, text in (
                (COL_NAME, r.name),
                (COL_WHEN, r.schedule.describe()),
                (COL_DELIVER, deliver_labels(r.deliver)),
                (COL_MODEL, r.model or "현재 모델"),
                (COL_SEARCH, r.search or "-"),
                (COL_WAKE, "O" if r.wake_when_closed else "-"),
                (COL_LAST, _last_run_text(r)),
            ):
                item = QTableWidgetItem(text)
                if col == COL_NAME:
                    item.setToolTip(r.task)
                table.setItem(i, col, item)
        table.setVisible(bool(rows))
        empty.setVisible(not rows)
        state["loading"] = False
        if rows and table.currentRow() < 0:
            table.selectRow(0)
        _fill_editor(_selected())

    def _on_item_changed(item: QTableWidgetItem) -> None:
        if state["loading"] or item.column() != COL_ON:
            return
        rows = state["rows"]
        if not (0 <= item.row() < len(rows)):
            return
        routine = rows[item.row()]
        enabled = item.checkState() == Qt.CheckState.Checked
        update_routine(db, routine.id, enabled=enabled)
        status.setText(f"'{routine.name}' {'켬' if enabled else '멈춤'}")
        reload()

    def _apply() -> None:
        routine = _selected()
        if routine is None:
            return
        fields = {
            "kind": kind.currentData(),
            "time_of_day": time_edit.text().strip() or routine.time_of_day,
            "weekdays": weekdays.text().strip(),
            "deliver": deliver.text().strip(),
            "search": search.text().strip(),
            "wake_when_closed": wake.isChecked(),
        }
        chosen = model.currentData()
        # 직접 입력했으면 currentData 가 안 따라온다.
        fields["model"] = chosen if chosen is not None else model.currentText().strip()
        if fields["model"] == "(지금 선택된 모델)":
            fields["model"] = ""
        updated = update_routine(db, routine.id, **fields)
        status.setText(
            f"'{updated.name}' 저장 — {updated.schedule.describe()}"
            if updated
            else "저장 실패"
        )
        reload()

    def _delete() -> None:
        routine = _selected()
        if routine is None:
            return
        answer = QMessageBox.question(
            box,
            "루틴 삭제",
            f"'{routine.name}' 을(를) 삭제할까요?\n"
            "잠시 멈추려면 삭제 대신 체크를 푸세요.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        delete_routine(db, routine.id)
        status.setText(f"'{routine.name}' 삭제됨")
        reload()

    def _run_now() -> None:
        routine = _selected()
        if routine is None:
            return
        if on_run_now is None:
            status.setText("이 창에서는 실행할 수 없습니다.")
            return
        started = bool(on_run_now(routine.id))
        status.setText(
            f"'{routine.name}' 실행 시작 — 결과는 설정한 방식으로 옵니다."
            if started
            else "다른 루틴이 실행 중입니다. 잠시 후 다시 시도하세요."
        )

    table.itemChanged.connect(_on_item_changed)
    table.itemSelectionChanged.connect(lambda: _fill_editor(_selected()))
    kind.currentIndexChanged.connect(lambda: _sync_edit_enabled())
    apply_btn.clicked.connect(_apply)
    delete_btn.clicked.connect(_delete)
    run_btn.clicked.connect(_run_now)
    refresh_btn.clicked.connect(reload)

    reload()

    box.routines_table = table  # type: ignore[attr-defined]
    box.reload_routines = reload  # type: ignore[attr-defined]
    box.routine_status = status  # type: ignore[attr-defined]
    box.routine_kind = kind  # type: ignore[attr-defined]
    box.routine_time = time_edit  # type: ignore[attr-defined]
    box.routine_weekdays = weekdays  # type: ignore[attr-defined]
    box.routine_deliver = deliver  # type: ignore[attr-defined]
    box.routine_search = search  # type: ignore[attr-defined]
    box.routine_model = model  # type: ignore[attr-defined]
    box.routine_wake = wake  # type: ignore[attr-defined]
    box.routine_apply = _apply  # type: ignore[attr-defined]
    box.routine_selected = _selected  # type: ignore[attr-defined]
    return box
