"""Android SDK 패키지 — sdkmanager로 emulator·adb·플랫폼·시스템 이미지를 받는다."""

from __future__ import annotations

import os
import queue
import shutil
import subprocess
import sys
import threading
import time
import zipfile
from pathlib import Path
from typing import Callable
from urllib.request import Request, urlopen

# Google commandlinetools-win 고정 URL. 다른 곳에는 두지 않는다.
_CMDLINE_TOOLS_ZIP_URL = (
    "https://dl.google.com/android/repository/commandlinetools-win-13114758_latest.zip"
)
_IDLE_SEC = 600.0
_HARD_SEC = 3600.0

ProgressFn = Callable[[str], None]
FetchFn = Callable[[Path, ProgressFn | None], None]
RunFn = Callable[..., int]


def sdk_package_ids() -> tuple[str, ...]:
    """설치 패키지. API 이미지는 AVD 상수와 같아야 한다."""
    from iris.system.android_emulator import _AVD_TARGET, _SYSTEM_IMAGE

    return (
        "platform-tools",
        "emulator",
        f"platforms;{_AVD_TARGET}",
        _SYSTEM_IMAGE,
    )


def _fail(reason: str) -> tuple[bool, str]:
    ids = ", ".join(sdk_package_ids())
    return False, f"{reason} 필요 패키지: {ids}"


def _sdkmanager_path(root: Path) -> Path:
    name = "sdkmanager.bat" if sys.platform == "win32" else "sdkmanager"
    return root / "cmdline-tools" / "latest" / "bin" / name


def _image_dir(root: Path) -> Path:
    from iris.system.android_emulator import _SYSTEM_IMAGE

    return root.joinpath(*_SYSTEM_IMAGE.split(";"))


def _sdk_ready(root: Path) -> bool:
    emu = "emulator.exe" if sys.platform == "win32" else "emulator"
    adb = "adb.exe" if sys.platform == "win32" else "adb"
    mgr = "avdmanager.bat" if sys.platform == "win32" else "avdmanager"
    bin_dir = root / "cmdline-tools" / "latest" / "bin"
    return (
        (root / "emulator" / emu).is_file()
        and (root / "platform-tools" / adb).is_file()
        and (bin_dir / mgr).is_file()
        and _image_dir(root).is_dir()
    )


def _default_root() -> Path:
    from iris.system.android_emulator import _sdk_root

    return _sdk_root()


def _java_home() -> str | None:
    home = os.environ.get("JAVA_HOME", "").strip()
    java_name = "java.exe" if sys.platform == "win32" else "java"
    if home and (Path(home) / "bin" / java_name).is_file():
        return home
    found = shutil.which("java")
    if found:
        return str(Path(found).resolve().parent.parent)
    roots: list[Path] = []
    local = os.environ.get("LOCALAPPDATA", "")
    if local:
        roots.append(Path(local) / "Programs" / "Android" / "Android Studio" / "jbr")
    for key in ("ProgramFiles", "ProgramFiles(x86)"):
        base = os.environ.get(key, "")
        if base:
            roots.append(Path(base) / "Android" / "Android Studio" / "jbr")
    for cand in roots:
        if (cand / "bin" / java_name).is_file():
            return str(cand)
    return None


def _sdk_env(root: Path) -> dict[str, str]:
    env = os.environ.copy()
    env["ANDROID_SDK_ROOT"] = str(root)
    env["ANDROID_HOME"] = str(root)
    java = _java_home()
    if java:
        env["JAVA_HOME"] = java
        env["PATH"] = str(Path(java) / "bin") + os.pathsep + env.get("PATH", "")
    return env


def _emit(progress: ProgressFn | None, line: str) -> None:
    if progress and line.strip():
        progress(line.strip())


def _download_cmdline_tools(root: Path, progress: ProgressFn | None) -> None:
    dest = root / "cmdline-tools" / "_download.zip"
    dest.parent.mkdir(parents=True, exist_ok=True)
    _emit(progress, "Android command-line tools 받는 중")
    req = Request(_CMDLINE_TOOLS_ZIP_URL, headers={"User-Agent": "IRIS-Light"})
    with urlopen(req, timeout=120) as resp, dest.open("wb") as out:
        total = int(resp.headers.get("Content-Length") or 0)
        got = 0
        last_pct = -1
        while True:
            chunk = resp.read(256 * 1024)
            if not chunk:
                break
            out.write(chunk)
            got += len(chunk)
            if total:
                pct = got * 100 // total
                if pct >= last_pct + 5:
                    last_pct = pct
                    _emit(progress, f"command-line tools {pct}%")
    _extract_cmdline_tools(dest, root)
    dest.unlink(missing_ok=True)


def _extract_cmdline_tools(zip_path: Path, root: Path) -> None:
    staging = root / "cmdline-tools" / "_zip"
    latest = root / "cmdline-tools" / "latest"
    if staging.exists():
        shutil.rmtree(staging)
    staging.mkdir(parents=True)
    with zipfile.ZipFile(zip_path) as zf:
        for info in zf.infolist():
            if ".." in Path(info.filename).parts:
                raise OSError(f"zip 경로 거부: {info.filename}")
        zf.extractall(staging)
    src = staging / "cmdline-tools"
    if not (src / "bin").is_dir():
        dirs = [p for p in staging.iterdir() if p.is_dir()]
        src = dirs[0] if len(dirs) == 1 else staging
    if latest.exists():
        shutil.rmtree(latest)
    if src == staging:
        staging.rename(latest)
        return
    shutil.move(str(src), str(latest))
    shutil.rmtree(staging, ignore_errors=True)


def _stream_cmd(
    cmd: list[str],
    *,
    stdin_text: str | None,
    progress: ProgressFn | None,
    idle_sec: float,
    hard_sec: float,
    env: dict[str, str],
) -> int:
    from iris.system.win_subprocess import no_window_kwargs

    proc = subprocess.Popen(
        cmd,
        stdin=subprocess.PIPE if stdin_text else subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        env=env,
        **no_window_kwargs(),
    )
    if stdin_text and proc.stdin is not None:
        try:
            proc.stdin.write(stdin_text.encode("utf-8"))
            proc.stdin.close()
        except OSError:
            pass
    out_q: queue.Queue[bytes | None] = queue.Queue()

    def _reader() -> None:
        try:
            stdout = proc.stdout
            if stdout is None:
                return
            while True:
                chunk = stdout.readline()
                if not chunk:
                    break
                out_q.put(chunk)
        finally:
            out_q.put(None)

    threading.Thread(target=_reader, daemon=True).start()
    started = time.monotonic()
    last = started
    while True:
        now = time.monotonic()
        if now - started > hard_sec or now - last > idle_sec:
            proc.kill()
            return 1
        try:
            piece = out_q.get(timeout=0.2)
        except queue.Empty:
            if proc.poll() is not None:
                return int(proc.returncode or 0)
            continue
        if piece is None:
            try:
                proc.wait(timeout=8)
            except subprocess.TimeoutExpired:
                proc.kill()
            return int(proc.returncode or 0)
        last = time.monotonic()
        _emit(progress, piece.decode("utf-8", errors="replace"))


def _manager_cmd(root: Path, extra: list[str]) -> list[str]:
    bat = _sdkmanager_path(root)
    if sys.platform == "win32":
        return ["cmd.exe", "/c", str(bat), f"--sdk_root={root}", *extra]
    return [str(bat), f"--sdk_root={root}", *extra]


def _real_run_manager(
    cmd: list[str],
    *,
    stdin_text: str | None,
    progress: ProgressFn | None,
    idle_sec: float,
    hard_sec: float,
    env: dict[str, str],
) -> int:
    return _stream_cmd(
        cmd,
        stdin_text=stdin_text,
        progress=progress,
        idle_sec=idle_sec,
        hard_sec=hard_sec,
        env=env,
    )


def ensure_sdk(
    progress: ProgressFn | None = None,
    *,
    idle_sec: float = _IDLE_SEC,
    hard_sec: float = _HARD_SEC,
    root: Path | None = None,
    fetch_tools: FetchFn | None = None,
    run_manager: RunFn | None = None,
) -> tuple[bool, str]:
    """emulator·adb·avdmanager·시스템 이미지가 없으면 sdkmanager로 받는다.

    이미 있으면 다운로드하지 않는다. 성공해도 AVD는 만들지 않는다.
    """
    sdk = Path(root) if root is not None else _default_root()
    if _sdk_ready(sdk):
        return True, "SDK 준비됨 (emulator·adb·cmdline-tools·시스템 이미지)"

    mgr = _sdkmanager_path(sdk)
    if not mgr.is_file():
        try:
            (fetch_tools or _download_cmdline_tools)(sdk, progress)
        except Exception as exc:  # noqa: BLE001 — 네트워크·zip 실패는 재시도 가능
            return _fail(f"command-line tools를 받지 못했습니다 ({exc}).")
        mgr = _sdkmanager_path(sdk)
        if not mgr.is_file():
            return _fail("sdkmanager가 없습니다.")
    if _sdk_ready(sdk):
        return True, "SDK 준비됨 (emulator·adb·cmdline-tools·시스템 이미지)"

    invoke = run_manager or _real_run_manager
    if run_manager is None and _java_home() is None:
        return _fail("Java(JDK)가 없어 sdkmanager를 실행하지 못했습니다.")

    env = _sdk_env(sdk)
    _emit(progress, "sdkmanager 라이선스 동의")
    invoke(
        _manager_cmd(sdk, ["--licenses"]),
        stdin_text="y\n" * 80,
        progress=progress,
        idle_sec=idle_sec,
        hard_sec=hard_sec,
        env=env,
    )
    ids = list(sdk_package_ids())
    _emit(progress, "sdkmanager 설치: " + " ".join(ids))
    code = invoke(
        _manager_cmd(sdk, ids),
        stdin_text=None,
        progress=progress,
        idle_sec=idle_sec,
        hard_sec=hard_sec,
        env=env,
    )
    if _sdk_ready(sdk):
        return True, "SDK 패키지를 설치했습니다 (emulator·adb·플랫폼·시스템 이미지)"
    return _fail(f"sdkmanager 종료 코드 {code}.")


def _self_check_ensure_sdk() -> None:
    import tempfile

    from iris.system.android_emulator import _SYSTEM_IMAGE

    calls: list[str] = []

    def _fetch(root: Path, progress: ProgressFn | None) -> None:
        calls.append("fetch")
        bat = _sdkmanager_path(root)
        bat.parent.mkdir(parents=True, exist_ok=True)
        bat.write_text("@echo off\n", encoding="utf-8")

    def _run(*_a: object, **_k: object) -> int:
        calls.append("run")
        return 1

    missing = Path(tempfile.mkdtemp(prefix="iris-sdk-miss-"))
    try:
        ok, msg = ensure_sdk(root=missing, fetch_tools=_fetch, run_manager=_run)
        assert ok is False, msg
        assert _SYSTEM_IMAGE in msg, msg
        assert "fetch" in calls and "run" in calls
    finally:
        shutil.rmtree(missing, ignore_errors=True)

    ready = Path(tempfile.mkdtemp(prefix="iris-sdk-ready-"))
    try:
        (ready / "emulator").mkdir(parents=True)
        (ready / "emulator" / ("emulator.exe" if sys.platform == "win32" else "emulator")).write_bytes(b"")
        (ready / "platform-tools").mkdir(parents=True)
        (ready / "platform-tools" / ("adb.exe" if sys.platform == "win32" else "adb")).write_bytes(b"")
        mgr_name = "avdmanager.bat" if sys.platform == "win32" else "avdmanager"
        mgr = ready / "cmdline-tools" / "latest" / "bin" / mgr_name
        mgr.parent.mkdir(parents=True, exist_ok=True)
        mgr.write_text("", encoding="utf-8")
        _image_dir(ready).mkdir(parents=True)

        def _no_fetch(*_a: object, **_k: object) -> None:
            raise AssertionError("download")

        ok2, msg2 = ensure_sdk(
            root=ready,
            fetch_tools=_no_fetch,  # type: ignore[arg-type]
            run_manager=lambda *_a, **_k: (_ for _ in ()).throw(AssertionError("sdkmanager")),
        )
        assert ok2 is True, msg2
    finally:
        shutil.rmtree(ready, ignore_errors=True)


if __name__ == "__main__":
    _self_check_ensure_sdk()
    print("android_sdk_install ok")
