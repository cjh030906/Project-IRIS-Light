"""루틴 반복 주기 계산 — "매일 9시" 를 다음 실행 시각으로 바꾼다.

아이리스는 켜져 있을 때만 루틴을 돌린다. 그래서 **놓친 실행**을 어떻게 다룰지가
이 모듈의 핵심이다. 조용히 건너뛰면 사용자는 뉴스가 안 온 줄도 모르고, 무조건
몰아서 실행하면 새벽에 꺼뒀다 아침에 켰을 때 알림이 쏟아진다.

규칙은 이렇다.

- 예정 시각을 `CATCH_UP_MINUTES` 안에 지났으면 → 지금 실행하되 "늦음"으로 표시
- 그보다 오래 지났으면 → 그 회차는 **건너뛰고** "놓침"으로 기록, 다음 회차로
- 어느 쪽이든 사용자에게 사실대로 알린다

시각은 전부 로컬 시간 기준이다(사용자가 "아침 9시"라고 할 때 그 9시).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timedelta

KIND_DAILY = "daily"
KIND_WEEKLY = "weekly"
KIND_INTERVAL = "interval"
KIND_ONCE = "once"
KINDS: tuple[str, ...] = (KIND_DAILY, KIND_WEEKLY, KIND_INTERVAL, KIND_ONCE)

# 예정 시각을 이만큼 지나서 켜졌으면 지금이라도 실행한다. 더 지났으면 건너뛴다.
CATCH_UP_MINUTES = 120

WEEKDAY_NAMES: tuple[str, ...] = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")
WEEKDAY_KO: tuple[str, ...] = ("월", "화", "수", "목", "금", "토", "일")

_TIME_RE = re.compile(r"^\s*(\d{1,2})\s*:\s*(\d{2})\s*$")

OUTCOME_DUE = "due"  # 지금이 예정 시각
OUTCOME_LATE = "late"  # 지났지만 따라잡을 수 있다
OUTCOME_MISSED = "missed"  # 너무 지났다 — 건너뛴다
OUTCOME_WAIT = "wait"  # 아직 아니다


def normalize_kind(kind: str) -> str:
    value = (kind or "").strip().lower()
    return value if value in KINDS else KIND_DAILY


def parse_time_of_day(text: str, *, default: str = "09:00") -> str:
    """`9:00`·`09:5` 같은 입력을 `HH:MM` 으로. 못 읽으면 기본값."""
    match = _TIME_RE.match(str(text or ""))
    if not match:
        return default
    hour = int(match.group(1))
    minute = int(match.group(2))
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        return default
    return f"{hour:02d}:{minute:02d}"


def parse_weekdays(text: str) -> tuple[int, ...]:
    """`mon,wed` · `월,수` · `0,2` → (0, 2). 빈 값이면 전체 요일."""
    raw = str(text or "").strip()
    if not raw:
        return tuple(range(7))
    out: list[int] = []
    for piece in re.split(r"[,\s/]+", raw):
        token = piece.strip().lower()
        if not token:
            continue
        if token in WEEKDAY_NAMES:
            out.append(WEEKDAY_NAMES.index(token))
            continue
        if token in WEEKDAY_KO:
            out.append(WEEKDAY_KO.index(token))
            continue
        if token[:3] in WEEKDAY_NAMES:
            out.append(WEEKDAY_NAMES.index(token[:3]))
            continue
        if token.isdigit() and 0 <= int(token) <= 6:
            out.append(int(token))
    uniq = sorted(set(out))
    return tuple(uniq) if uniq else tuple(range(7))


def format_weekdays(days: tuple[int, ...]) -> str:
    if not days or len(days) == 7:
        return ""
    return ",".join(WEEKDAY_NAMES[d] for d in sorted(set(days)) if 0 <= d <= 6)


@dataclass(frozen=True)
class Schedule:
    """언제 돌릴지. 저장은 문자열로, 계산은 이 객체로 한다."""

    kind: str = KIND_DAILY
    time_of_day: str = "09:00"
    weekdays: tuple[int, ...] = tuple(range(7))
    interval_minutes: int = 60
    at: str = ""  # once 전용 ISO datetime

    @staticmethod
    def build(
        kind: str = KIND_DAILY,
        *,
        time_of_day: str = "09:00",
        weekdays: str | tuple[int, ...] = "",
        interval_minutes: int = 60,
        at: str = "",
    ) -> "Schedule":
        days = (
            parse_weekdays(weekdays)
            if isinstance(weekdays, str)
            else tuple(sorted({int(d) for d in weekdays if 0 <= int(d) <= 6}))
        )
        return Schedule(
            kind=normalize_kind(kind),
            time_of_day=parse_time_of_day(time_of_day),
            weekdays=days or tuple(range(7)),
            interval_minutes=max(1, int(interval_minutes or 1)),
            at=str(at or "").strip(),
        )

    @property
    def hour(self) -> int:
        return int(self.time_of_day.split(":")[0])

    @property
    def minute(self) -> int:
        return int(self.time_of_day.split(":")[1])

    def describe(self) -> str:
        """사용자에게 보여줄 한 줄."""
        if self.kind == KIND_INTERVAL:
            mins = self.interval_minutes
            if mins % 60 == 0:
                return f"{mins // 60}시간마다"
            return f"{mins}분마다"
        if self.kind == KIND_ONCE:
            return f"{self.at} 에 한 번" if self.at else "한 번"
        if self.kind == KIND_WEEKLY and len(self.weekdays) < 7:
            days = "·".join(WEEKDAY_KO[d] for d in self.weekdays)
            return f"매주 {days} {self.time_of_day}"
        return f"매일 {self.time_of_day}"

    def next_after(self, moment: datetime) -> datetime | None:
        """`moment` **이후** 첫 실행 시각. once 가 이미 지났으면 None."""
        if self.kind == KIND_ONCE:
            when = _parse_dt(self.at)
            if when is None or when <= moment:
                return None
            return when
        if self.kind == KIND_INTERVAL:
            return moment + timedelta(minutes=self.interval_minutes)

        days = self.weekdays if self.kind == KIND_WEEKLY else tuple(range(7))
        candidate = moment.replace(
            hour=self.hour, minute=self.minute, second=0, microsecond=0
        )
        if candidate <= moment:
            candidate += timedelta(days=1)
        for _ in range(8):
            if candidate.weekday() in days:
                return candidate
            candidate += timedelta(days=1)
        return None

    def first_run_from(self, moment: datetime) -> datetime | None:
        """등록 직후의 첫 실행 시각. 오늘 그 시각이 아직 안 지났으면 오늘."""
        if self.kind in (KIND_ONCE, KIND_INTERVAL):
            return self.next_after(moment)
        days = self.weekdays if self.kind == KIND_WEEKLY else tuple(range(7))
        candidate = moment.replace(
            hour=self.hour, minute=self.minute, second=0, microsecond=0
        )
        for _ in range(8):
            if candidate > moment and candidate.weekday() in days:
                return candidate
            candidate += timedelta(days=1)
        return None


def _parse_dt(text: str) -> datetime | None:
    try:
        return datetime.fromisoformat(str(text))
    except (TypeError, ValueError):
        return None


@dataclass(frozen=True)
class DueCheck:
    outcome: str
    late_by_minutes: int = 0
    scheduled_for: str = ""

    @property
    def should_run(self) -> bool:
        return self.outcome in (OUTCOME_DUE, OUTCOME_LATE)

    def note(self) -> str:
        """실행 결과에 붙일 솔직한 한 줄. 정시면 빈 문자열."""
        if self.outcome == OUTCOME_LATE:
            return (
                f"예정 시각({self.scheduled_for})보다 "
                f"{self.late_by_minutes}분 늦게 실행했습니다."
            )
        if self.outcome == OUTCOME_MISSED:
            return f"{self.scheduled_for} 예정분은 아이리스가 꺼져 있어 건너뛰었습니다."
        return ""


def check_due(
    next_run_at: str,
    now: datetime,
    *,
    catch_up_minutes: int = CATCH_UP_MINUTES,
) -> DueCheck:
    """예정 시각과 지금을 견줘 실행할지 판단한다."""
    when = _parse_dt(next_run_at)
    if when is None:
        return DueCheck(outcome=OUTCOME_WAIT)
    if now < when:
        return DueCheck(outcome=OUTCOME_WAIT, scheduled_for=next_run_at)
    late = int((now - when).total_seconds() // 60)
    if late <= 0:
        return DueCheck(outcome=OUTCOME_DUE, scheduled_for=next_run_at)
    if late <= max(0, int(catch_up_minutes)):
        return DueCheck(
            outcome=OUTCOME_LATE, late_by_minutes=late, scheduled_for=next_run_at
        )
    return DueCheck(
        outcome=OUTCOME_MISSED, late_by_minutes=late, scheduled_for=next_run_at
    )


if __name__ == "__main__":
    assert normalize_kind("WEEKLY") == KIND_WEEKLY
    assert normalize_kind("이상") == KIND_DAILY

    assert parse_time_of_day("9:00") == "09:00"
    assert parse_time_of_day("23:59") == "23:59"
    assert parse_time_of_day("25:00") == "09:00"  # 범위 밖 → 기본
    assert parse_time_of_day("아침") == "09:00"
    assert parse_time_of_day("7:30", default="00:00") == "07:30"

    assert parse_weekdays("mon,wed") == (0, 2)
    assert parse_weekdays("월, 수") == (0, 2)
    assert parse_weekdays("monday tuesday") == (0, 1)
    assert parse_weekdays("0,6") == (0, 6)
    assert parse_weekdays("") == tuple(range(7))
    assert parse_weekdays("쓰레기") == tuple(range(7))
    assert format_weekdays((0, 2)) == "mon,wed"
    assert format_weekdays(tuple(range(7))) == ""

    daily = Schedule.build(KIND_DAILY, time_of_day="9:00")
    assert daily.describe() == "매일 09:00"
    base = datetime(2026, 9, 29, 8, 0)  # 화요일 08:00
    assert daily.first_run_from(base) == datetime(2026, 9, 29, 9, 0)
    after9 = datetime(2026, 9, 29, 9, 30)
    assert daily.first_run_from(after9) == datetime(2026, 9, 30, 9, 0)
    assert daily.next_after(datetime(2026, 9, 29, 9, 0)) == datetime(2026, 9, 30, 9, 0)

    weekly = Schedule.build(KIND_WEEKLY, time_of_day="09:00", weekdays="mon,fri")
    assert "월·금" in weekly.describe()
    # 화요일에 등록 → 다음 금요일
    assert weekly.first_run_from(base) == datetime(2026, 10, 2, 9, 0)
    assert weekly.first_run_from(base).weekday() == 4

    interval = Schedule.build(KIND_INTERVAL, interval_minutes=90)
    assert interval.describe() == "90분마다"
    assert Schedule.build(KIND_INTERVAL, interval_minutes=120).describe() == "2시간마다"
    assert interval.next_after(base) == datetime(2026, 9, 29, 9, 30)
    assert Schedule.build(KIND_INTERVAL, interval_minutes=0).interval_minutes == 1

    once = Schedule.build(KIND_ONCE, at="2026-10-01T07:00:00")
    assert once.next_after(base) == datetime(2026, 10, 1, 7, 0)
    assert once.next_after(datetime(2026, 10, 2, 0, 0)) is None  # 이미 지났다
    assert Schedule.build(KIND_ONCE, at="쓰레기").next_after(base) is None

    # 실행 판단
    assert check_due("", base).outcome == OUTCOME_WAIT
    assert check_due("2026-09-29T09:00:00", datetime(2026, 9, 29, 8, 0)).outcome == OUTCOME_WAIT
    assert check_due("2026-09-29T09:00:00", datetime(2026, 9, 29, 9, 0)).outcome == OUTCOME_DUE

    late = check_due("2026-09-29T09:00:00", datetime(2026, 9, 29, 9, 45))
    assert late.outcome == OUTCOME_LATE and late.late_by_minutes == 45
    assert late.should_run is True
    assert "45분 늦게" in late.note()

    missed = check_due("2026-09-29T09:00:00", datetime(2026, 9, 30, 9, 0))
    assert missed.outcome == OUTCOME_MISSED and missed.should_run is False
    assert "건너뛰었습니다" in missed.note()
    assert check_due("2026-09-29T09:00:00", datetime(2026, 9, 29, 9, 0)).note() == ""

    # 경계: 딱 catch_up 만큼 늦었으면 아직 따라잡는다
    edge = check_due("2026-09-29T09:00:00", datetime(2026, 9, 29, 11, 0))
    assert edge.outcome == OUTCOME_LATE
    over = check_due("2026-09-29T09:00:00", datetime(2026, 9, 29, 11, 1))
    assert over.outcome == OUTCOME_MISSED

    print("routine_schedule self-check ok")
