"""사용자가 아이리스에게 시킨 반복 작업 — SQLite `iris_routines`.

"매일 9시에 뉴스 3개 정리해서 알려줘" 같은 요청이 여기 한 줄로 남는다.
할 일은 자연어 지시(`task`)로 그대로 보관한다. 아이리스가 실행할 때 그 문장을
그대로 자기 자신에게 물어보기 때문이다 — 미리 액션으로 쪼개 두면 사용자가 말한
뉘앙스를 잃는다.

전달 방식(`deliver`)은 루틴마다 다르다. 기본은 채팅 + 알림.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from iris.runtime.routine_schedule import (
    KIND_DAILY,
    Schedule,
    format_weekdays,
    normalize_kind,
    parse_time_of_day,
    parse_weekdays,
)
from iris.storage.database import Database

DELIVER_CHAT = "chat"
DELIVER_NOTIFY = "notify"
DELIVER_VOICE = "voice"
DELIVER_WIKI = "wiki"
DELIVERS: tuple[str, ...] = (DELIVER_CHAT, DELIVER_NOTIFY, DELIVER_VOICE, DELIVER_WIKI)
DEFAULT_DELIVER = f"{DELIVER_CHAT},{DELIVER_NOTIFY}"

STATUS_OK = "ok"
STATUS_FAILED = "failed"
STATUS_MISSED = "missed"
STATUS_NEVER = "never"

_DELIVER_LABELS = {
    DELIVER_CHAT: "채팅",
    DELIVER_NOTIFY: "알림",
    DELIVER_VOICE: "음성",
    DELIVER_WIKI: "위키 저장",
}


def normalize_deliver(text: str) -> str:
    """`chat, 알림` → `chat,notify`. 빈 값이면 기본(채팅+알림)."""
    raw = str(text or "")
    alias = {
        "채팅": DELIVER_CHAT,
        "대화": DELIVER_CHAT,
        "알림": DELIVER_NOTIFY,
        "notification": DELIVER_NOTIFY,
        "음성": DELIVER_VOICE,
        "tts": DELIVER_VOICE,
        "말": DELIVER_VOICE,
        "위키": DELIVER_WIKI,
        "wiki": DELIVER_WIKI,
    }
    out: list[str] = []
    for piece in raw.replace("+", ",").split(","):
        token = piece.strip().lower()
        if not token:
            continue
        token = alias.get(token, token)
        if token in DELIVERS and token not in out:
            out.append(token)
    return ",".join(out) if out else DEFAULT_DELIVER


def deliver_labels(deliver: str) -> str:
    parts = [_DELIVER_LABELS.get(d, d) for d in normalize_deliver(deliver).split(",")]
    return " · ".join(parts)


@dataclass(frozen=True)
class Routine:
    id: int
    name: str
    task: str
    kind: str = KIND_DAILY
    time_of_day: str = "09:00"
    weekdays: str = ""
    interval_minutes: int = 60
    at: str = ""
    deliver: str = DEFAULT_DELIVER
    enabled: bool = True
    next_run_at: str = ""
    last_run_at: str = ""
    last_status: str = STATUS_NEVER
    last_result: str = ""
    run_count: int = 0
    miss_count: int = 0
    source: str = "chat"
    # 빈 값이면 그때 선택돼 있는 모델을 쓴다.
    model: str = ""
    # 아이리스가 꺼져 있어도 Windows 작업 스케줄러가 깨워서 실행할지.
    wake_when_closed: bool = False
    # 실행 전에 이 말로 웹을 검색해 결과를 모델에 근거로 넣는다. 비면 검색 안 함.
    # 모델에게 도구를 맡기지 않는 이유는 routine_search 모듈 설명 참고.
    search: str = ""
    search_engine: str = "google_news"
    created_at: str = ""
    updated_at: str = ""

    @property
    def schedule(self) -> Schedule:
        return Schedule.build(
            self.kind,
            time_of_day=self.time_of_day,
            weekdays=self.weekdays,
            interval_minutes=self.interval_minutes,
            at=self.at,
        )

    @property
    def deliver_list(self) -> list[str]:
        return normalize_deliver(self.deliver).split(",")

    def wants(self, channel: str) -> bool:
        return channel in self.deliver_list

    def summary_line(self) -> str:
        state = "" if self.enabled else " (꺼짐)"
        return f"{self.name} — {self.schedule.describe()} · {deliver_labels(self.deliver)}{state}"


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def ensure_routine_schema(db: Database) -> None:
    db._execute(
        """
        CREATE TABLE IF NOT EXISTS iris_routines (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            task TEXT NOT NULL,
            kind TEXT NOT NULL DEFAULT 'daily',
            time_of_day TEXT NOT NULL DEFAULT '09:00',
            weekdays TEXT NOT NULL DEFAULT '',
            interval_minutes INTEGER NOT NULL DEFAULT 60,
            at TEXT NOT NULL DEFAULT '',
            deliver TEXT NOT NULL DEFAULT 'chat,notify',
            enabled INTEGER NOT NULL DEFAULT 1,
            next_run_at TEXT NOT NULL DEFAULT '',
            last_run_at TEXT NOT NULL DEFAULT '',
            last_status TEXT NOT NULL DEFAULT 'never',
            last_result TEXT NOT NULL DEFAULT '',
            run_count INTEGER NOT NULL DEFAULT 0,
            miss_count INTEGER NOT NULL DEFAULT 0,
            source TEXT NOT NULL DEFAULT 'chat',
            model TEXT NOT NULL DEFAULT '',
            wake_when_closed INTEGER NOT NULL DEFAULT 0,
            search TEXT NOT NULL DEFAULT '',
            search_engine TEXT NOT NULL DEFAULT 'google_news',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """
    )
    # 이미 쓰던 DB — CREATE TABLE IF NOT EXISTS 로는 컬럼이 안 생긴다.
    cols = {
        str(row["name"])
        for row in db._execute("PRAGMA table_info(iris_routines)").fetchall()
    }
    if "model" not in cols:
        db._execute("ALTER TABLE iris_routines ADD COLUMN model TEXT NOT NULL DEFAULT ''")
    if "wake_when_closed" not in cols:
        db._execute(
            "ALTER TABLE iris_routines "
            "ADD COLUMN wake_when_closed INTEGER NOT NULL DEFAULT 0"
        )
    if "search" not in cols:
        db._execute("ALTER TABLE iris_routines ADD COLUMN search TEXT NOT NULL DEFAULT ''")
    if "search_engine" not in cols:
        db._execute(
            "ALTER TABLE iris_routines "
            "ADD COLUMN search_engine TEXT NOT NULL DEFAULT 'google_news'"
        )
    db._execute(
        "CREATE INDEX IF NOT EXISTS idx_iris_routines_due "
        "ON iris_routines(enabled, next_run_at)"
    )
    db._commit()


def _col(row, name: str, default=None):
    """옛 DB 에 없는 컬럼을 읽어도 터지지 않게."""
    try:
        return row[name]
    except (IndexError, KeyError):
        return default


def _row_to_routine(row) -> Routine:
    return Routine(
        id=int(row["id"]),
        name=str(row["name"] or ""),
        task=str(row["task"] or ""),
        kind=str(row["kind"] or KIND_DAILY),
        time_of_day=str(row["time_of_day"] or "09:00"),
        weekdays=str(row["weekdays"] or ""),
        interval_minutes=int(row["interval_minutes"] or 60),
        at=str(row["at"] or ""),
        deliver=str(row["deliver"] or DEFAULT_DELIVER),
        enabled=bool(row["enabled"]),
        next_run_at=str(row["next_run_at"] or ""),
        last_run_at=str(row["last_run_at"] or ""),
        last_status=str(row["last_status"] or STATUS_NEVER),
        last_result=str(row["last_result"] or ""),
        run_count=int(row["run_count"] or 0),
        miss_count=int(row["miss_count"] or 0),
        source=str(row["source"] or "chat"),
        model=str(_col(row, "model") or ""),
        wake_when_closed=bool(_col(row, "wake_when_closed")),
        search=str(_col(row, "search") or ""),
        search_engine=str(_col(row, "search_engine") or "google_news"),
        created_at=str(row["created_at"] or ""),
        updated_at=str(row["updated_at"] or ""),
    )


def create_routine(
    db: Database,
    *,
    name: str,
    task: str,
    kind: str = KIND_DAILY,
    time_of_day: str = "09:00",
    weekdays: str = "",
    interval_minutes: int = 60,
    at: str = "",
    deliver: str = "",
    source: str = "chat",
    model: str = "",
    wake_when_closed: bool = False,
    search: str = "",
    search_engine: str = "google_news",
    now: datetime | None = None,
) -> Routine:
    """루틴 등록. 할 일(`task`)이 비면 만들지 않는다."""
    title = str(name or "").strip()
    body = str(task or "").strip()
    if not body:
        raise ValueError("task required")
    if not title:
        title = body[:40]
    ensure_routine_schema(db)
    moment = now or datetime.now()
    schedule = Schedule.build(
        kind,
        time_of_day=time_of_day,
        weekdays=weekdays,
        interval_minutes=interval_minutes,
        at=at,
    )
    first = schedule.first_run_from(moment)
    stamp = _now()
    cur = db._execute(
        """
        INSERT INTO iris_routines(
            name, task, kind, time_of_day, weekdays, interval_minutes, at,
            deliver, enabled, next_run_at, source, model, wake_when_closed,
            search, search_engine, created_at, updated_at
        ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            title,
            body,
            normalize_kind(kind),
            parse_time_of_day(time_of_day),
            format_weekdays(parse_weekdays(weekdays)),
            max(1, int(interval_minutes or 1)),
            str(at or "").strip(),
            normalize_deliver(deliver),
            first.isoformat(timespec="seconds") if first else "",
            str(source or "chat"),
            str(model or "").strip(),
            1 if wake_when_closed else 0,
            str(search or "").strip(),
            str(search_engine or "google_news").strip(),
            stamp,
            stamp,
        ),
    )
    db._commit()
    created = get_routine(db, int(cur.lastrowid or 0))
    assert created is not None
    return created


def get_routine(db: Database, routine_id: int) -> Routine | None:
    ensure_routine_schema(db)
    row = db._execute(
        "SELECT * FROM iris_routines WHERE id = ?", (int(routine_id),)
    ).fetchone()
    return _row_to_routine(row) if row else None


def find_routine_by_name(db: Database, name: str) -> Routine | None:
    ensure_routine_schema(db)
    row = db._execute(
        "SELECT * FROM iris_routines WHERE name = ? ORDER BY id DESC LIMIT 1",
        (str(name or "").strip(),),
    ).fetchone()
    return _row_to_routine(row) if row else None


def list_routines(db: Database, *, enabled_only: bool = False) -> list[Routine]:
    ensure_routine_schema(db)
    clause = "WHERE enabled = 1" if enabled_only else ""
    rows = db._execute(
        f"SELECT * FROM iris_routines {clause} ORDER BY id"
    ).fetchall()
    return [_row_to_routine(r) for r in rows]


def update_routine(db: Database, routine_id: int, **fields) -> Routine | None:
    """바꿀 필드만 넘긴다. 주기가 바뀌면 다음 실행 시각을 다시 잡는다.

    `name`·`task` 는 빈 값을 주면 기존 값을 지킨다(실수로 지우는 걸 막는다).
    `model` 은 반대로 빈 값이 뜻을 가진다 — 고정을 풀고 그때 선택된 모델을 쓴다.
    """
    current = get_routine(db, routine_id)
    if current is None:
        return None
    ensure_routine_schema(db)

    allowed = {
        "name": lambda v: str(v or "").strip() or current.name,
        "task": lambda v: str(v or "").strip() or current.task,
        "kind": lambda v: normalize_kind(v),
        "time_of_day": lambda v: parse_time_of_day(v, default=current.time_of_day),
        "weekdays": lambda v: format_weekdays(parse_weekdays(v)),
        "interval_minutes": lambda v: max(1, int(v or 1)),
        "at": lambda v: str(v or "").strip(),
        "deliver": lambda v: normalize_deliver(v),
        "enabled": lambda v: 1 if bool(v) else 0,
        "model": lambda v: str(v or "").strip(),
        "wake_when_closed": lambda v: 1 if bool(v) else 0,
        "search": lambda v: str(v or "").strip(),
        "search_engine": lambda v: str(v or "google_news").strip(),
    }
    sets: list[str] = []
    params: list[object] = []
    schedule_touched = False
    for key, value in fields.items():
        if key not in allowed or value is None:
            continue
        sets.append(f"{key} = ?")
        params.append(allowed[key](value))
        if key in ("kind", "time_of_day", "weekdays", "interval_minutes", "at"):
            schedule_touched = True
    if not sets:
        return current

    sets.append("updated_at = ?")
    params.append(_now())
    params.append(int(routine_id))
    db._execute(f"UPDATE iris_routines SET {', '.join(sets)} WHERE id = ?", tuple(params))
    db._commit()

    updated = get_routine(db, routine_id)
    if updated is not None and schedule_touched:
        nxt = updated.schedule.first_run_from(datetime.now())
        set_next_run(db, routine_id, nxt.isoformat(timespec="seconds") if nxt else "")
        updated = get_routine(db, routine_id)
    return updated


def set_next_run(db: Database, routine_id: int, next_run_at: str) -> None:
    ensure_routine_schema(db)
    db._execute(
        "UPDATE iris_routines SET next_run_at = ?, updated_at = ? WHERE id = ?",
        (str(next_run_at or ""), _now(), int(routine_id)),
    )
    db._commit()


def mark_ran(
    db: Database,
    routine_id: int,
    *,
    status: str,
    result: str = "",
    ran_at: str = "",
    next_run_at: str = "",
) -> Routine | None:
    """실행 결과 기록. missed 는 실행 횟수로 세지 않는다."""
    ensure_routine_schema(db)
    stamp = _now()
    is_miss = status == STATUS_MISSED
    db._execute(
        """
        UPDATE iris_routines SET
            last_run_at = CASE WHEN ? THEN last_run_at ELSE ? END,
            last_status = ?,
            last_result = ?,
            run_count = run_count + CASE WHEN ? THEN 0 ELSE 1 END,
            miss_count = miss_count + CASE WHEN ? THEN 1 ELSE 0 END,
            next_run_at = ?,
            updated_at = ?
        WHERE id = ?
        """,
        (
            1 if is_miss else 0,
            str(ran_at or stamp),
            str(status or STATUS_OK),
            str(result or "")[:4000],
            1 if is_miss else 0,
            1 if is_miss else 0,
            str(next_run_at or ""),
            stamp,
            int(routine_id),
        ),
    )
    db._commit()
    return get_routine(db, routine_id)


def delete_routine(db: Database, routine_id: int) -> bool:
    ensure_routine_schema(db)
    existed = get_routine(db, routine_id) is not None
    db._execute("DELETE FROM iris_routines WHERE id = ?", (int(routine_id),))
    db._commit()
    return existed


def count_routines(db: Database) -> tuple[int, int]:
    """(전체, 켜진 것)."""
    ensure_routine_schema(db)
    row = db._execute(
        "SELECT COUNT(*) AS total, SUM(enabled) AS on_count FROM iris_routines"
    ).fetchone()
    if row is None:
        return (0, 0)
    return (int(row["total"] or 0), int(row["on_count"] or 0))


if __name__ == "__main__":
    import tempfile
    from pathlib import Path

    assert normalize_deliver("") == DEFAULT_DELIVER
    assert normalize_deliver("채팅, 알림") == "chat,notify"
    assert normalize_deliver("voice") == "voice"
    assert normalize_deliver("chat+wiki") == "chat,wiki"
    assert normalize_deliver("없는채널") == DEFAULT_DELIVER
    assert normalize_deliver("chat,chat") == "chat"
    assert deliver_labels("chat,notify") == "채팅 · 알림"

    with tempfile.TemporaryDirectory() as tmp:
        db = Database(Path(tmp) / "r.db")
        base = datetime(2026, 9, 29, 8, 0)

        r = create_routine(
            db,
            name="아침 뉴스",
            task="오늘 주요 뉴스 3개를 골라 한 줄씩 정리해줘",
            kind="daily",
            time_of_day="9:00",
            now=base,
        )
        assert r.id > 0 and r.enabled is True
        assert r.deliver == "chat,notify"
        assert r.next_run_at == "2026-09-29T09:00:00", r.next_run_at
        assert r.schedule.describe() == "매일 09:00"
        assert r.wants("chat") and r.wants("notify") and not r.wants("voice")
        assert "아침 뉴스" in r.summary_line() and "채팅 · 알림" in r.summary_line()

        try:
            create_routine(db, name="빈 것", task="   ")
            raise AssertionError("빈 task 는 거부해야 한다")
        except ValueError:
            pass

        # 이름을 안 주면 할 일에서 딴다
        auto = create_routine(db, name="", task="주간 메일함 정리해줘", now=base)
        assert auto.name == "주간 메일함 정리해줘"

        assert get_routine(db, r.id).name == "아침 뉴스"
        assert find_routine_by_name(db, "아침 뉴스").id == r.id
        assert find_routine_by_name(db, "없음") is None
        assert len(list_routines(db)) == 2

        # 전달 방식은 언제든 바꿀 수 있다
        changed = update_routine(db, r.id, deliver="음성")
        assert changed.deliver == "voice" and changed.wants("voice")

        # 주기를 바꾸면 다음 실행이 다시 잡힌다
        rescheduled = update_routine(db, r.id, kind="weekly", weekdays="mon,fri")
        assert rescheduled.kind == "weekly" and rescheduled.weekdays == "mon,fri"
        assert rescheduled.next_run_at and rescheduled.next_run_at != r.next_run_at

        assert update_routine(db, r.id) .id == r.id  # 바꿀 게 없으면 그대로
        assert update_routine(db, 9999, name="없음") is None

        off = update_routine(db, r.id, enabled=False)
        assert off.enabled is False and "(꺼짐)" in off.summary_line()
        assert len(list_routines(db, enabled_only=True)) == 1

        ran = mark_ran(db, r.id, status=STATUS_OK, result="뉴스 3건", next_run_at="2026-10-05T09:00:00")
        assert ran.run_count == 1 and ran.miss_count == 0
        assert ran.last_status == STATUS_OK and ran.last_result == "뉴스 3건"
        assert ran.next_run_at == "2026-10-05T09:00:00"

        missed = mark_ran(db, r.id, status=STATUS_MISSED, next_run_at="2026-10-12T09:00:00")
        assert missed.run_count == 1 and missed.miss_count == 1  # 놓친 건 실행이 아니다
        assert missed.last_run_at == ran.last_run_at  # 마지막 실행 시각은 그대로

        # 루틴별 모델 지정 — 빈 값이면 그때 선택된 모델을 쓴다
        assert r.model == "" and r.wake_when_closed is False
        pinned = create_routine(
            db, name="무거운 정리", task="길게 정리해줘",
            model="qwen3:32b", wake_when_closed=True, now=base,
        )
        assert pinned.model == "qwen3:32b" and pinned.wake_when_closed is True
        repinned = update_routine(db, pinned.id, model="  gemma4:free  ")
        assert repinned.model == "gemma4:free"
        # 이름·할 일과 달리 model 은 빈 값이 뜻을 가진다 — "고정 해제, 현재 모델 사용"
        unpinned = update_routine(db, pinned.id, model="")
        assert unpinned.model == ""
        assert update_routine(db, pinned.id, wake_when_closed=False).wake_when_closed is False
        delete_routine(db, pinned.id)

        # 검색어 — 비면 검색 안 함. model 과 마찬가지로 빈 값이 "끄기"를 뜻한다.
        assert r.search == "" and r.search_engine == "google_news"
        searcher = create_routine(
            db, name="뉴스", task="뉴스 3개", search="한국 주요 뉴스 속보", now=base
        )
        assert searcher.search == "한국 주요 뉴스 속보"
        assert update_routine(db, searcher.id, search="환율").search == "환율"
        assert update_routine(db, searcher.id, search="").search == ""
        delete_routine(db, searcher.id)

        assert count_routines(db) == (2, 1)
        assert delete_routine(db, auto.id) is True
        assert delete_routine(db, 9999) is False
        assert count_routines(db) == (1, 0)
        db.close()

    print("routines self-check ok")
