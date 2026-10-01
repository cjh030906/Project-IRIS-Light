"""아이리스가 꺼져 있어도 루틴이 돌게 하는 Windows 작업 스케줄러 등록.

**루틴마다 작업을 만들지 않는다.** 대신 몇 분마다 깨어나는 마스터 작업 하나만
등록하고, 무엇을 돌릴지는 DB(`next_run_at`)가 정한다. 이유는 셋이다.

- `schtasks /SC ONCE` 의 `/SD` 날짜 형식이 **로케일마다 다르다**. 한국어 Windows 와
  영어 Windows 가 다르게 먹어서 등록이 조용히 실패하기 쉽다. 분 단위 반복(`/SC
  MINUTE /MO n`)만 쓰면 날짜를 아예 안 적는다.
- 루틴을 만들고 지울 때마다 작업을 만들고 지우면 어긋난 잔재가 남는다.
- 주기 종류(daily/weekly/interval/once)를 두 군데서 해석하지 않아도 된다.

`wake_when_closed` 를 켠 루틴이 하나도 없으면 작업을 **지운다** — 쓰지도 않는
예약 작업이 사용자 PC 에 남아 있으면 안 된다.
"""

from __future__ import annotations

import locale
import platform
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

TASK_NAME = r"\IrisLight\RoutineWake"
DEFAULT_INTERVAL_MINUTES = 5
_TIMEOUT_SEC = 15

# schtasks 종료 코드 1 은 "없음"도 포함한다 — 문구로 갈라야 한다.
_NOT_FOUND_HINTS = ("cannot find", "does not exist", "찾을 수 없", "없습니다")


@dataclass(frozen=True)
class WakeStatus:
    registered: bool
    detail: str = ""
    interval_minutes: int = DEFAULT_INTERVAL_MINUTES


def is_supported() -> bool:
    return platform.system() == "Windows"


def python_runner() -> Path:
    """콘솔 창이 안 뜨는 pythonw 우선. 없으면 python."""
    exe = Path(sys.executable)
    pythonw = exe.with_name("pythonw.exe")
    return pythonw if pythonw.is_file() else exe


def cli_script() -> Path:
    return Path(__file__).resolve().parents[1] / "routine_cli.py"


def build_task_command(runner: Path | None = None, script: Path | None = None) -> str:
    """schtasks /TR 값. 경로에 공백이 있어 따옴표가 필수다."""
    run = runner or python_runner()
    src = script or cli_script()
    return f'"{run}" "{src}" tick'


def _run(args: list[str]) -> tuple[int, str]:
    try:
        done = subprocess.run(
            args,
            capture_output=True,
            timeout=_TIMEOUT_SEC,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return (-1, str(exc))
    text = _decode(done.stdout) + _decode(done.stderr)
    return (done.returncode, text.strip())


def _decode(raw: bytes | None) -> str:
    """schtasks 는 콘솔 코드페이지로 말한다(한국어 Windows 는 cp949).

    utf-8 로만 읽으면 한글 안내문이 깨져 "찾을 수 없습니다" 판정이 통째로 어긋난다.
    """
    if not raw:
        return ""
    for encoding in (locale.getpreferredencoding(False), "cp949", "utf-8"):
        if not encoding:
            continue
        try:
            return raw.decode(encoding)
        except (UnicodeDecodeError, LookupError):
            continue
    return raw.decode("utf-8", errors="replace")


def query() -> WakeStatus:
    """지금 등록돼 있나."""
    if not is_supported():
        return WakeStatus(registered=False, detail="Windows 에서만 지원합니다")
    code, text = _run(["schtasks", "/Query", "/TN", TASK_NAME])
    if code == 0:
        return WakeStatus(registered=True, detail="등록됨")
    low = text.lower()
    if any(h in low for h in _NOT_FOUND_HINTS):
        return WakeStatus(registered=False, detail="등록 안 됨")
    return WakeStatus(registered=False, detail=text[:200] or f"schtasks 종료 코드 {code}")


def register(interval_minutes: int = DEFAULT_INTERVAL_MINUTES) -> WakeStatus:
    """마스터 작업을 등록(또는 갱신)한다."""
    if not is_supported():
        return WakeStatus(registered=False, detail="Windows 에서만 지원합니다")
    minutes = max(1, min(1439, int(interval_minutes or DEFAULT_INTERVAL_MINUTES)))
    script = cli_script()
    if not script.is_file():
        return WakeStatus(registered=False, detail=f"실행 파일을 찾을 수 없습니다: {script}")
    code, text = _run(
        [
            "schtasks", "/Create", "/TN", TASK_NAME,
            "/TR", build_task_command(),
            "/SC", "MINUTE", "/MO", str(minutes),
            "/F",  # 이미 있으면 덮어쓴다
        ]
    )
    if code == 0:
        return WakeStatus(
            registered=True, detail=f"{minutes}분마다 확인", interval_minutes=minutes
        )
    return WakeStatus(
        registered=False,
        detail=text[:300] or f"schtasks 종료 코드 {code}",
        interval_minutes=minutes,
    )


def unregister() -> WakeStatus:
    """작업을 지운다. 원래 없었어도 성공으로 본다."""
    if not is_supported():
        return WakeStatus(registered=False, detail="Windows 에서만 지원합니다")
    code, text = _run(["schtasks", "/Delete", "/TN", TASK_NAME, "/F"])
    if code == 0:
        return WakeStatus(registered=False, detail="해제됨")
    low = text.lower()
    if any(h in low for h in _NOT_FOUND_HINTS):
        return WakeStatus(registered=False, detail="원래 없음")
    return WakeStatus(registered=False, detail=text[:300] or f"schtasks 종료 코드 {code}")


def sync(wanted: bool, interval_minutes: int = DEFAULT_INTERVAL_MINUTES) -> WakeStatus:
    """`wake_when_closed` 켠 루틴 유무에 맞춰 작업을 맞춘다.

    필요 없으면 지운다 — 쓰지도 않는 예약 작업을 남겨두지 않는다.
    """
    current = query()
    if wanted:
        return current if current.registered else register(interval_minutes)
    # 원래 없으면 굳이 /Delete 를 부르지 않는다 — 프로세스 한 번이 아깝다.
    return unregister() if current.registered else WakeStatus(False, "필요 없음")


if __name__ == "__main__":
    assert TASK_NAME.startswith("\\Iris")

    cmd = build_task_command(Path(r"C:\py w\pythonw.exe"), Path(r"C:\proj\routine_cli.py"))
    assert cmd == '"C:\\py w\\pythonw.exe" "C:\\proj\\routine_cli.py" tick'
    assert cmd.count('"') == 4  # 공백 있는 경로가 둘 다 감싸여 있다

    assert cli_script().name == "routine_cli.py"
    runner = python_runner()
    assert runner.name in ("pythonw.exe", "python.exe", Path(sys.executable).name)

    if is_supported():
        before = query()
        assert isinstance(before.registered, bool)
        print("  현재 상태:", before.detail.encode("ascii", "replace").decode())
    else:
        assert register().registered is False
        assert query().registered is False

    print("routine_wake self-check ok")
