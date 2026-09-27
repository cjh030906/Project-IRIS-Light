"""로컬 Ollama 서버 감지 및 자동 기동."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from iris.infrastructure.ollama_client import _native_base

_WINDOWS_DEFAULT = Path.home() / "AppData" / "Local" / "Programs" / "Ollama" / "ollama.exe"


def is_ollama_running(base_url: str, *, timeout_sec: float = 2.0) -> bool:
    """서버가 응답하면 True. HTTP 401/403 등도 '켜짐'으로 간주(응답했으므로)."""
    url = f"{_native_base(base_url)}/api/version"
    try:
        with urlopen(Request(url, method="GET"), timeout=timeout_sec):
            return True
    except HTTPError:
        return True
    except (URLError, TimeoutError, OSError):
        return False


def ollama_executable() -> str | None:
    found = shutil.which("ollama")
    if found:
        return found
    if sys.platform == "win32" and _WINDOWS_DEFAULT.is_file():
        return str(_WINDOWS_DEFAULT)
    return None


def start_ollama_server() -> bool:
    """`ollama serve`를 백그라운드로 기동. 실행 파일이 없으면 False."""
    exe = ollama_executable()
    if not exe:
        return False
    popen_kwargs: dict = {
        "stdout": subprocess.DEVNULL,
        "stderr": subprocess.DEVNULL,
        "stdin": subprocess.DEVNULL,
        "close_fds": True,
    }
    if sys.platform == "win32":
        # 콘솔 창 없이 백그라운드 — CREATE_NO_WINDOW만 (DETACHED와 섞지 않음)
        creationflags = int(getattr(subprocess, "CREATE_NO_WINDOW", 0))
        creationflags |= int(getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0))
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startupinfo.wShowWindow = 0  # SW_HIDE
        popen_kwargs["creationflags"] = creationflags
        popen_kwargs["startupinfo"] = startupinfo
    else:
        popen_kwargs["start_new_session"] = True
    try:
        subprocess.Popen([exe, "serve"], **popen_kwargs)
        return True
    except OSError:
        return False


def ensure_ollama_running(base_url: str, *, wait_sec: float = 12.0) -> bool:
    """켜져 있으면 즉시 True. 아니면 기동 후 준비될 때까지 대기."""
    if is_ollama_running(base_url):
        return True
    if not start_ollama_server():
        return False
    deadline = time.monotonic() + wait_sec
    while time.monotonic() < deadline:
        if is_ollama_running(base_url):
            return True
        time.sleep(0.5)
    return False


def ollama_app_candidates() -> list[Path]:
    """클라우드 로그인 UI가 있는 Ollama 데스크톱 앱 후보 (CLI ollama.exe 제외)."""
    home = Path.home()
    local = Path(os.environ.get("LOCALAPPDATA", str(home / "AppData" / "Local")))
    base = local / "Programs" / "Ollama"
    # GUI만 — ollama.exe 는 serve/CLI라 창이 안 뜸
    return [
        base / "ollama app.exe",
        base / "Ollama.exe",
    ]


def _shell_execute_open(path: Path) -> bool:
    """Windows ShellExecuteW 로 GUI 앱을 연다 (SW_SHOWNORMAL)."""
    if sys.platform != "win32":
        return False
    try:
        import ctypes

        # SW_SHOWNORMAL=1 — 트레이만 있으면 창을 보이게
        rc = int(
            ctypes.windll.shell32.ShellExecuteW(  # type: ignore[attr-defined]
                None, "open", str(path), None, None, 1
            )
        )
        return rc > 32
    except Exception:
        return False


def _ollama_app_pids() -> set[int]:
    """GUI 후보 PID — ollama app.exe 만 (서버 ollama.exe 제외)."""
    try:
        import psutil  # type: ignore
    except Exception:
        return set()
    out: set[int] = set()
    for p in psutil.process_iter(["pid", "name"]):
        try:
            name = (p.info.get("name") or "").lower()
        except Exception:
            continue
        if "ollama app" in name:
            out.add(int(p.info["pid"]))
    return out


def reset_stuck_ollama_apps() -> int:
    """좀비 ollama app.exe 를 모두 종료. 반환=종료 시도 수.

    단일 인스턴스가 숨은 채로 쌓이면 시작 메뉴/검색으로도 창이 안 뜬다.
    """
    if sys.platform != "win32":
        return 0
    pids = sorted(_ollama_app_pids())
    if not pids:
        return 0
    killed = 0
    for pid in pids:
        try:
            subprocess.run(
                ["taskkill", "/PID", str(pid), "/T", "/F"],
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
                creationflags=int(getattr(subprocess, "CREATE_NO_WINDOW", 0)),
            )
            killed += 1
        except (OSError, subprocess.TimeoutExpired):
            pass
    deadline = time.monotonic() + 3.0
    while time.monotonic() < deadline and _ollama_app_pids():
        time.sleep(0.2)
    return killed


def _has_visible_ollama_window() -> bool:
    if sys.platform != "win32":
        return False
    try:
        import ctypes
        from ctypes import wintypes
    except Exception:
        return False
    user32 = ctypes.windll.user32  # type: ignore[attr-defined]
    pids = _ollama_app_pids()
    if not pids:
        return False
    found = [False]

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def _enum(hwnd: int, _lp: int) -> bool:  # noqa: ANN001
        if not user32.IsWindowVisible(hwnd):
            return True
        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if int(pid.value) not in pids:
            return True
        cbuf = ctypes.create_unicode_buffer(256)
        user32.GetClassNameW(hwnd, cbuf, 256)
        cls = (cbuf.value or "").strip().lower()
        n = int(user32.GetWindowTextLengthW(hwnd))
        title = ""
        if n > 0:
            tbuf = ctypes.create_unicode_buffer(n + 1)
            user32.GetWindowTextW(hwnd, tbuf, n + 1)
            title = (tbuf.value or "").strip().lower()
        if cls in ("webview", "ollamaclass") or "ollama" in title:
            found[0] = True
            return False
        return True

    try:
        user32.EnumWindows(_enum, 0)
    except Exception:
        return False
    return bool(found[0])


def _foreground_ollama_windows_impl() -> bool:
    """보이는 webview(Ollama) 창만 앞으로 — 숨은 OllamaClass ShowWindow는 멈출 수 있음."""
    if sys.platform != "win32":
        return False
    try:
        import ctypes
        from ctypes import wintypes
    except Exception:
        return False

    user32 = ctypes.windll.user32  # type: ignore[attr-defined]
    pids = _ollama_app_pids()
    if not pids:
        return False

    candidates: list[tuple[int, int]] = []

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def _enum(hwnd: int, _lp: int) -> bool:  # noqa: ANN001
        if not user32.IsWindowVisible(hwnd):
            return True
        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if int(pid.value) not in pids:
            return True
        cbuf = ctypes.create_unicode_buffer(256)
        user32.GetClassNameW(hwnd, cbuf, 256)
        cls = (cbuf.value or "").strip()
        n = int(user32.GetWindowTextLengthW(hwnd))
        title = ""
        if n > 0:
            tbuf = ctypes.create_unicode_buffer(n + 1)
            user32.GetWindowTextW(hwnd, tbuf, n + 1)
            title = (tbuf.value or "").strip()
        score = 0
        if cls.lower() == "webview" and "ollama" in title.lower():
            score = 200
        elif cls.lower() == "webview":
            score = 150
        if score:
            candidates.append((score, int(hwnd)))
        return True

    try:
        user32.EnumWindows(_enum, 0)
    except Exception:
        return False
    if not candidates:
        return False
    candidates.sort(reverse=True)
    hwnd = candidates[0][1]
    try:
        user32.ShowWindow(hwnd, 9)  # SW_RESTORE
        user32.SetForegroundWindow(hwnd)
        return True
    except Exception:
        return False


def _foreground_ollama_windows() -> bool:
    """짧은 타임아웃으로 감싼다."""
    if sys.platform != "win32":
        return False
    import threading

    box: list[bool] = [False]

    def _run() -> None:
        try:
            box[0] = _foreground_ollama_windows_impl()
        except Exception:
            box[0] = False

    t = threading.Thread(target=_run, daemon=True)
    t.start()
    t.join(timeout=1.2)
    return bool(box[0]) and not t.is_alive()


def open_ollama_app() -> tuple[bool, str]:
    """Ollama 데스크톱 앱을 연다 (클라우드 로그인은 앱 UI에서 해야 함).

    Returns: (ok, detail) — detail은 UI 힌트용, 시크릿 없음.
    """
    if sys.platform != "win32":
        exe = ollama_executable()
        if not exe:
            return False, "ollama 실행 파일을 찾지 못했습니다"
        try:
            subprocess.Popen([exe], start_new_session=True)  # noqa: S603
            return True, exe
        except OSError as exc:
            return False, str(exc)[:160]

    # 보이는 창이 있으면 앞으로만
    if _has_visible_ollama_window() and _foreground_ollama_windows():
        return True, "foreground"

    # 프로세스는 있는데 창이 없거나 중복이면 좀비 — 정리 후 재기동
    app_count = len(_ollama_app_pids())
    if app_count >= 2 or (app_count >= 1 and not _has_visible_ollama_window()):
        reset_stuck_ollama_apps()
        ensure_ollama_running("http://127.0.0.1:11434/v1", wait_sec=8.0)

    last_err = ""
    for cand in ollama_app_candidates():
        if not cand.is_file():
            continue
        try:
            subprocess.Popen(  # noqa: S603
                [str(cand)],
                cwd=str(cand.parent),
                close_fds=True,
            )
            time.sleep(1.0)
            _foreground_ollama_windows()
            return True, str(cand)
        except OSError as exc:
            last_err = str(exc)[:160]
        if _shell_execute_open(cand):
            time.sleep(1.0)
            _foreground_ollama_windows()
            return True, str(cand)
        try:
            os.startfile(str(cand))  # type: ignore[attr-defined]
            time.sleep(1.0)
            _foreground_ollama_windows()
            return True, str(cand)
        except OSError as exc:
            last_err = str(exc)[:160]
    if last_err:
        return False, last_err
    return False, "Ollama 앱을 찾지 못했습니다 — 설치 후 다시 시도하세요"


if __name__ == "__main__":
    base = "http://127.0.0.1:11434/v1"
    assert is_ollama_running(base) in (True, False)
    # 잘못된 포트는 반드시 꺼짐으로 감지되어야 함
    assert is_ollama_running("http://127.0.0.1:1/v1", timeout_sec=1.0) is False
    assert isinstance(ollama_app_candidates(), list)
    print("ollama_server ok - running:", is_ollama_running(base))
