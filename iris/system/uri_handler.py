"""`iris-light:` URI 스킴 등록 — 토스트를 눌렀을 때 아이리스가 반응하도록.

Windows 토스트를 눌러 앱을 깨우는 방법은 둘이다.

- **COM 활성화**: 제대로 된 방법이지만 CLSID·LocalServer32 COM 서버를 등록해야 하고,
  설치 프로그램과 얽히며 실패 지점이 많다.
- **프로토콜 활성화**: 토스트에 `activationType="protocol"` 과 `launch="iris-light://…"`
  를 넣으면 Windows 가 그 URI 를 기본 핸들러로 연다. COM 서버가 필요 없다.

여기서는 프로토콜 활성화를 쓴다. 등록은 `HKCU\\Software\\Classes` 라 **관리자 권한이
필요 없다** — 설치 프로그램을 또 건드리지 않아도 된다.
"""

from __future__ import annotations

import platform
import sys
from dataclasses import dataclass
from pathlib import Path

SCHEME = "iris-light"
_KEY = rf"Software\Classes\{SCHEME}"


@dataclass(frozen=True)
class SchemeStatus:
    registered: bool
    command: str = ""
    detail: str = ""


def is_supported() -> bool:
    return platform.system() == "Windows"


def handler_script() -> Path:
    return Path(__file__).resolve().parents[1] / "routine_cli.py"


def python_runner() -> Path:
    """콘솔 창이 안 뜨는 pythonw 우선."""
    exe = Path(sys.executable)
    pythonw = exe.with_name("pythonw.exe")
    return pythonw if pythonw.is_file() else exe


def build_command(runner: Path | None = None, script: Path | None = None) -> str:
    """레지스트리 `shell\\open\\command` 값. `%1` 에 눌린 URI 가 들어온다."""
    run = runner or python_runner()
    src = script or handler_script()
    return f'"{run}" "{src}" open --uri "%1"'


def query() -> SchemeStatus:
    if not is_supported():
        return SchemeStatus(False, detail="Windows 에서만 지원합니다")
    import winreg

    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, rf"{_KEY}\shell\open\command") as key:
            command, _ = winreg.QueryValueEx(key, "")
    except OSError:
        return SchemeStatus(False, detail="등록 안 됨")
    return SchemeStatus(True, command=str(command), detail="등록됨")


def register() -> SchemeStatus:
    """스킴을 등록(또는 갱신)한다. 이미 맞게 돼 있으면 건드리지 않는다."""
    if not is_supported():
        return SchemeStatus(False, detail="Windows 에서만 지원합니다")
    import winreg

    command = build_command()
    current = query()
    if current.registered and current.command == command:
        return current
    try:
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, _KEY) as key:
            winreg.SetValueEx(key, "", 0, winreg.REG_SZ, f"URL:{SCHEME}")
            # 이 값이 있어야 Windows 가 URL 스킴으로 인정한다.
            winreg.SetValueEx(key, "URL Protocol", 0, winreg.REG_SZ, "")
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, rf"{_KEY}\shell\open\command") as key:
            winreg.SetValueEx(key, "", 0, winreg.REG_SZ, command)
    except OSError as exc:
        return SchemeStatus(False, detail=str(exc)[:200])
    return SchemeStatus(True, command=command, detail="등록됨")


def unregister() -> SchemeStatus:
    if not is_supported():
        return SchemeStatus(False, detail="Windows 에서만 지원합니다")
    import winreg

    for sub in (rf"{_KEY}\shell\open\command", rf"{_KEY}\shell\open", rf"{_KEY}\shell", _KEY):
        try:
            winreg.DeleteKey(winreg.HKEY_CURRENT_USER, sub)
        except OSError:
            pass
    return SchemeStatus(False, detail="해제됨")


def routine_uri(routine_id: int) -> str:
    return f"{SCHEME}://routine/{int(routine_id)}"


def open_uri() -> str:
    return f"{SCHEME}://open"


def parse_uri(uri: str) -> tuple[str, str]:
    """`iris-light://routine/12` → ("routine", "12"). 모르면 ("open", "")."""
    raw = str(uri or "").strip().strip('"')
    prefix = f"{SCHEME}://"
    if not raw.lower().startswith(prefix):
        return ("open", "")
    rest = raw[len(prefix) :].strip("/")
    if not rest:
        return ("open", "")
    parts = rest.split("/", 1)
    kind = parts[0].lower()
    value = parts[1] if len(parts) > 1 else ""
    if kind == "routine":
        return ("routine", value)
    return ("open", "")


if __name__ == "__main__":
    assert SCHEME == "iris-light"
    assert routine_uri(12) == "iris-light://routine/12"
    assert open_uri() == "iris-light://open"

    assert parse_uri("iris-light://routine/12") == ("routine", "12")
    assert parse_uri("iris-light://routine/12/") == ("routine", "12")
    assert parse_uri('"iris-light://routine/7"') == ("routine", "7")
    assert parse_uri("IRIS-LIGHT://routine/7") == ("routine", "7")
    assert parse_uri("iris-light://open") == ("open", "")
    assert parse_uri("iris-light://") == ("open", "")
    assert parse_uri("https://evil.example/x") == ("open", "")
    assert parse_uri("") == ("open", "")
    assert parse_uri("iris-light://무언가/1") == ("open", "")

    cmd = build_command(Path(r"C:\py w\pythonw.exe"), Path(r"C:\proj\routine_cli.py"))
    assert cmd.endswith('open --uri "%1"')
    assert cmd.startswith('"C:\\py w\\pythonw.exe"')

    if is_supported():
        st = query()
        assert isinstance(st.registered, bool)
        print("  현재:", st.detail.encode("ascii", "replace").decode())
    print("uri_handler self-check ok")
